"""Pre-render the fixed prompt audio into the committed bank.

Run once, on a host that can synthesise (macOS), whenever the spoken banks
change:

    python -m app.prerender_audio

It walks every tenant for the two kinds of prompt that are *heard* -- Repeat
Sentence items (their reference text) and listening passages (their transcript)
-- and renders each to app/prompt_audio/, keyed by the same (text, voice) hash
the runtime serves. Committing that directory is what makes prompt audio work
on a Linux production box, which has no `say`: the clips are just served from
disk. Text that is shown rather than heard (Read Aloud, Speak on a Topic) has
no audio and is skipped.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app import sections as app_sections
from app import tts
from app.db import platform_sessionmaker, tenant_sessionmaker
from app.models.platform import Tenant
from app.models.tenant import ListeningPassage, TaskItem


async def _pairs_for(slug: str) -> set[tuple[str, str]]:
    """Every (text, accent) that this tenant would ever ask to be spoken."""
    pairs: set[tuple[str, str]] = set()
    async with tenant_sessionmaker(slug)() as s:
        items = (await s.execute(
            select(TaskItem).where(TaskItem.status == "published")
        )).scalars().all()
        for it in items:
            # Tasks whose reference is heard aloud (Repeat Sentence, Story
            # Retell, Conversation/Passage Questions, Dictation). Read Aloud
            # is shown, not played, so it is excluded.
            if app_sections.speaks_reference(it.task_type) and it.reference_text:
                pairs.add((it.reference_text.strip(), it.prompt_accent or "indian"))
            # Short Questions play the question itself (prompt_text): heard,
            # never shown. Every company round and Versant Part C uses these.
            if it.task_type in ("short_answer", "spoken_completion",
                                "spoken_correction") and it.prompt_text:
                # Heard prompts that live in prompt_text: short questions, and
                # the gapped/flawed sentences of the spoken grammar sections.
                pairs.add((it.prompt_text.strip(), it.prompt_accent or "indian"))
        passages = (await s.execute(
            select(ListeningPassage).where(ListeningPassage.status == "published")
        )).scalars().all()
        for p in passages:
            if p.transcript:
                pairs.add((p.transcript.strip(), p.accent or "indian"))
    return pairs


async def main() -> None:
    if not tts._available():  # noqa: SLF001 -- the pre-render step needs the tools
        raise SystemExit(
            "This host cannot synthesise (no `say`/`afconvert`). Run the "
            "pre-render on macOS; the committed clips then serve everywhere.")

    async with platform_sessionmaker()() as s:
        slugs = list((await s.execute(select(Tenant.slug))).scalars().all())

    pairs: set[tuple[str, str]] = set()
    for slug in slugs:
        pairs |= await _pairs_for(slug)

    ok = 0
    for text, accent in sorted(pairs):
        if tts.render_to_bank(text, accent):
            ok += 1
        else:
            print(f"  FAILED: [{accent}] {text[:60]!r}")
    print(f"pre-rendered {ok}/{len(pairs)} prompt clips into {tts._prerendered}")  # noqa: SLF001


if __name__ == "__main__":
    asyncio.run(main())
