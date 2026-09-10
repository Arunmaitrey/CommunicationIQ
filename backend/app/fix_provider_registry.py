"""Correct stale entrypoints in the provider registry.

Every provider file lives under a tier subdirectory (tier0/, tier1/,
tier2/) -- but eight of the eleven `provider_registry` rows in the live
database still pointed at the old flat `app.engine.providers.<name>`
paths from before that reorganisation, and one (the VAD primary) was
simply marked inactive with no working fallback.

None of this showed up in testing because the one long-lived backend
process had these providers loaded and cached in memory from before
whatever changed the paths -- `_load()` in engine/registry.py only
imports a fresh module when nothing is cached yet, and a successful load
is cached forever. The moment that process restarts for any reason
(a deploy, a crash, `--reload` firing on an unrelated edit), every one of
these capabilities -- including ASR itself, so every transcript along
with it -- fails, and every response comes back unscored. This is not a
theoretical risk: it is exactly what happened partway through this fix,
when an unrelated code change forced a reload and the whole engine went
dark until this was found.

Idempotent: only touches rows whose entrypoint doesn't already match the
correct one, and re-running it after the real files move again just
needs this dict updated, not spelunking through logs for the next AttributeError.

    python -m app.fix_provider_registry
"""
from __future__ import annotations

import asyncio

CORRECT_ENTRYPOINTS = {
    "energy_vad": "app.engine.providers.tier0.vad:EnergyVAD",
    "feature_fluency": "app.engine.providers.tier0.fluency:FeatureFluency",
    "reference_match": "app.engine.providers.tier1.accuracy:ReferenceMatchAccuracy",
    "faster_whisper": "app.engine.providers.tier1.asr:FasterWhisperASR",
    "common_error_rules": "app.engine.providers.tier1.grammar:CommonErrorGrammar",
    "wav2vec2_gop": "app.engine.providers.tier1.pronunciation:Wav2VecGOP",
    "transcript_disfluency": "app.engine.providers.tier1.disfluency:TranscriptDisfluency",
    "rubric_coverage": "app.engine.providers.tier1.relevance:RubricRelevance",
}

# The VAD primary being inactive (with the fallback also broken, above) is
# what actually surfaced this: every response came back with no fluency,
# no latency, and nothing downstream that depends on knowing where speech
# starts. Silero is bundled with faster-whisper -- already installed,
# nothing extra to download -- so there's no reason for it to sit off.
ACTIVATE = ["silero_vad"]


async def main() -> None:
    from app.db import init_mongo
    from app.models.platform import ProviderRegistry

    await init_mongo()

    fixed_entrypoints = 0
    for key, entrypoint in CORRECT_ENTRYPOINTS.items():
        row = await ProviderRegistry.find_one(ProviderRegistry.provider_key == key)
        if row is None:
            print(f"{key}: not found in registry, skipping")
            continue
        if row.entrypoint == entrypoint:
            continue
        row.entrypoint = entrypoint
        await row.save()
        fixed_entrypoints += 1
        print(f"{key}: entrypoint -> {entrypoint}")

    activated = 0
    for key in ACTIVATE:
        row = await ProviderRegistry.find_one(ProviderRegistry.provider_key == key)
        if row is None or row.active:
            continue
        row.active = True
        await row.save()
        activated += 1
        print(f"{key}: activated")

    print(f"\nfixed {fixed_entrypoints} entrypoints, activated {activated} providers")


if __name__ == "__main__":
    asyncio.run(main())
