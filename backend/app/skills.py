"""The four language skills, and how much of each this build can actually do.

Reading, Writing, Listening and Speaking are how every student, admin and
placement officer already thinks about English. The product measured exactly
one of them and never said so: there was no Listening screen, no Reading
screen, no Writing anything, and nothing anywhere admitted the gap.

The four exist here as first-class things, and each one reports its own
readiness **computed from the content actually in the database** rather than
from a constant somebody has to remember to update.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

from beanie.operators import In

# Enough material to face a student with. Below this a module is a promise,
# not a product: five items is one sitting and then immediate repetition,
# which measures memory rather than skill.
MIN_ITEMS_FOR_LIVE = 12

# Writing is counted in prompts, not questions, and the units are not
# comparable: one prompt is fifteen to twenty-five minutes of work, where
# twelve quiz questions are five.
MIN_PROMPTS_FOR_LIVE = 4

# Speaking task types, and the quiz categories that are text comprehension
# rather than listening.
SPEAKING_TASKS = ("read_aloud", "repeat_sentence", "sentence_build",
                  "short_answer", "story_retell", "open_response")
READING_CATEGORIES = ("reading_comprehension",)
QUIZ_TEXT_CATEGORIES = ("grammar", "vocabulary", "sentence_correction", "error_id")
LISTENING_CATEGORIES = ("audio_comprehension",)


@dataclass
class SkillModule:
    key: str
    label: str
    status: str
    summary: str
    measures: list[str] = field(default_factory=list)
    item_count: int = 0
    href: str = ""
    gap: str = ""
    mastery: float | None = None
    mastery_basis: str = ""


async def _count_tasks(models: SimpleNamespace, types: tuple[str, ...]) -> int:
    """Count published task items of the given types."""
    items = await models.TaskItem.find(
        In(models.TaskItem.task_type, list(types)),
        models.TaskItem.status == "published",
    ).to_list()
    return len(items)


async def _count_quiz(models: SimpleNamespace, categories: tuple[str, ...]) -> int:
    """Count published quiz items in the given categories."""
    items = await models.QuizItem.find(
        In(models.QuizItem.category, list(categories)),
        models.QuizItem.status == "published",
    ).to_list()
    return len(items)


async def _mastery(models: SimpleNamespace, user_id: str,
                   skills: tuple[str, ...]) -> float | None:
    """Average mastery for the given skills, or None if never measured."""
    rows = await models.SkillMastery.find(
        models.SkillMastery.user_id == user_id,
        In(models.SkillMastery.skill, list(skills)),
    ).to_list()
    if not rows:
        return None
    return round(100 * sum(r.mastery for r in rows) / len(rows), 1)


async def _count_writing_prompts(models: SimpleNamespace) -> int:
    """Count published writing prompts."""
    return len(await models.WritingPrompt.find(
        models.WritingPrompt.status == "published",
    ).to_list())


async def modules_for(models: SimpleNamespace, user_id: str) -> list[SkillModule]:
    """The four skills, in the order they are usually taught and tested.

    Each count and each module below reads its own, unrelated rows, so
    fetching them one `await` at a time only serialises round-trips a remote
    database actually has to pay for — nothing here depends on anything
    else's result.
    """
    speaking_items, listening_items, reading_items, writing_prompts = await asyncio.gather(
        _count_tasks(models, SPEAKING_TASKS),
        _count_quiz(models, LISTENING_CATEGORIES),
        _count_quiz(models, READING_CATEGORIES),
        _count_writing_prompts(models),
    )

    if writing_prompts:
        speaking, listening, reading, writing = await asyncio.gather(
            _speaking(models, user_id, speaking_items),
            _listening(models, user_id, listening_items),
            _reading(models, user_id, reading_items),
            _writing_live(models, user_id, writing_prompts),
        )
    else:
        # _writing() needs no query — nothing to gather it with.
        speaking, listening, reading = await asyncio.gather(
            _speaking(models, user_id, speaking_items),
            _listening(models, user_id, listening_items),
            _reading(models, user_id, reading_items),
        )
        writing = _writing()
    return [speaking, listening, reading, writing]


async def _speaking(models: SimpleNamespace, user_id: str, items: int) -> SkillModule:
    """The one that is genuinely finished."""
    return SkillModule(
        key="speaking", label="Speaking",
        status="live" if items >= MIN_ITEMS_FOR_LIVE else "partial",
        summary=("Read aloud, repeat, build sentences, answer and retell. "
                 "Scored on pronunciation, fluency, timing and content."),
        measures=["pronunciation", "fluency", "response latency", "grammar",
                  "content"],
        item_count=items,
        href="/simulate",
        mastery=await _mastery(models, user_id,
                               ("pronunciation", "fluency", "response_latency")),
        mastery_basis="Measured directly from your recordings.",
    )


async def _listening(models: SimpleNamespace, user_id: str, items: int) -> SkillModule:
    """Half-built, and the half that exists is easy to mistake for the whole."""
    live = items >= MIN_ITEMS_FOR_LIVE
    return SkillModule(
        key="listening", label="Listening",
        status="live" if live else "partial",
        summary=("Hear a passage once, then answer questions about what it "
                 "meant. Announcements, instructions, talks, voicemail and "
                 "conversation." if live else
                 "Repeat Sentence already tests whether you heard accurately. "
                 "Comprehension — following a talk and answering about it — is "
                 "not built yet."),
        measures=["listening comprehension"] if live else ["accuracy of what you heard"],
        item_count=items,
        href="/listening",
        gap="" if live else (
            f"Needs audio-comprehension items; there are {items} in the bank. "
            f"Until then your Listening reading comes indirectly from Repeat "
            f"Sentence."),
        mastery=await _mastery(models, user_id, ("listening",)),
        mastery_basis=(
            "From comprehension questions you answered after listening."
            if live else
            "Derived from how accurately you reproduce sentences, which "
            "includes Read Aloud — where the text was on screen. It is an "
            "indirect signal and flatters your listening."),
    )


async def _reading(models: SimpleNamespace, user_id: str, items: int) -> SkillModule:
    """Comprehension over real passages, plus a rate measure."""
    live = items >= MIN_ITEMS_FOR_LIVE
    return SkillModule(
        key="reading", label="Reading",
        status="live" if live else "partial",
        summary=("Emails, notices, reports and articles. Comprehension and "
                 "reading speed, reported separately." if live else
                 "Passage comprehension is not built yet. The grammar and "
                 "vocabulary questions under Quiz are language knowledge, "
                 "which is a different thing."),
        measures=["reading comprehension", "reading rate"] if live else [],
        item_count=items,
        href="/reading",
        gap="" if live else (
            "Needs passages with comprehension questions; there are "
            f"{items} in the bank."),
        mastery=await _mastery(models, user_id, ("vocabulary",)),
        mastery_basis=(
            "From reading comprehension, sharing the vocabulary mastery track."
            if live else
            "From grammar and vocabulary questions — an indirect signal, not "
            "reading comprehension."),
    )


async def _writing_live(models: SimpleNamespace, user_id: str,
                        prompts: int) -> SkillModule:
    """Now built: five measures over real workplace writing tasks."""
    return SkillModule(
        key="writing", label="Writing",
        status="live" if prompts >= MIN_PROMPTS_FOR_LIVE else "partial",
        summary=("Awkward emails, status reports, summaries. Scored on task "
                 "response, coherence, lexical range, grammar and mechanics."),
        measures=["task response", "coherence", "lexical range",
                  "grammatical accuracy", "mechanics"],
        item_count=prompts,
        href="/writing",
        gap=("The scorer counts structure, coverage and error patterns. It "
             "cannot judge whether an argument is sound or whether the "
             "writing is worth reading — those need a human marker."),
        mastery=await _mastery(models, user_id, ("grammar",)),
        mastery_basis=("Shares the grammar mastery track; there is no "
                       "separate writing skill fitted yet."),
    )


def _writing() -> SkillModule:
    """Nothing. Not a screen, not an item, not a scorer."""
    return SkillModule(
        key="writing", label="Writing",
        status="planned",
        summary=("Not built. Writing needs its own scoring engine — task "
                 "response, coherence, range and accuracy — which is separate "
                 "work from the speech pipeline."),
        measures=[],
        item_count=0,
        href="/writing",
        gap=("No items, no scoring, no screen. Listed here so the gap is "
             "visible rather than something you have to discover."),
        mastery=None,
        mastery_basis="",
    )
