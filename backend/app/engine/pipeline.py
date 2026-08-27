"""Scoring an attempt.

The pipeline talks to capabilities, never to implementations: every call goes
through the registry, so which provider ran — and what happened when it timed
out — is configuration. Each score it writes carries the provider id and
version that produced it (ENG-21).

**Scoring happens as each answer arrives, not in a batch at the end.** A local
speech model runs at roughly 0.6× real time on CPU, so a batch of eight items
would leave a student watching a spinner for twenty seconds. Scored on ingest,
item four is transcribed while item five is being spoken, and by the time they
press submit the work is already done. ``finalise_attempt`` then only has to
compose what is there.

What it will not do is fill gaps. A capability with no provider configured
leaves its dimension unscored and says why — a plausible number with nothing
behind it is worse than a blank, because a student would act on it.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.sqlbridge import delete, select
# The session object threaded through the scoring path is the Beanie-backed
# bridge session from app.db; the historical annotation name is kept so the
# call signatures stay readable.
from app.db import Session as AsyncSession

from app.engine import calibration, freeze
from app.engine.contracts import AudioRef, Capability
from app.engine.contracts.types import (AccuracyResult, DisfluencyResult,
                                         FluencyResult, ProviderUnavailable,
                                         TranscriptResult)
from app.engine.providers.tier1.accuracy import COVERAGE_SHARE, ORDER_SHARE
from app.engine.psychometrics import bkt
from app.engine.registry import Providers
from app.models.tenant import (Attempt, FeatureRecord, ProfileSection,
                               Response, ResponseAudio, ScoreRecord,
                               SkillMastery, TaskItem)

log = logging.getLogger(__name__)

SCALE_MIN = 20.0
SCALE_MAX = 80.0

# How the overall number is composed. Only dimensions that were actually
# measured take part, and the weights are renormalised over those — so an
# attempt scored by Tier 0 alone still produces an honest overall from the two
# dimensions it could reach.
WEIGHTS = {"pronunciation": 0.20, "accuracy": 0.20, "fluency": 0.17,
           "latency": 0.11, "disfluency": 0.08, "grammar": 0.09, "content": 0.07,
           "completeness": 0.08}

# Response latency bands, in milliseconds from the beep to the first speech.
LATENCY_EXCELLENT = 800
LATENCY_GOOD = 1400
LATENCY_POOR = 3500

# How much of the expected answer counts as a whole one.
#
# Completeness asks a question none of the other dimensions do: did the
# candidate produce the *whole* answer. It is not content, which judges the
# relevance of what was said; it is not fluency, which judges how it came out.
# A candidate who reads two thirds of a passage beautifully and stops has
# nothing wrong with their speech, and every other dimension will say so
# while the report stays silent about the third that is missing.
#
# Below this share of what was asked for, the answer is a fragment.
COMPLETE_ENOUGH = 0.95
# And below this, there is barely an answer at all.
BARELY_STARTED = 0.15
# What an open-ended item expects when its rubric does not say. Deliberately
# short: guessing high would fail candidates for being concise.
DEFAULT_MIN_SECONDS = 15.0

# A recording whose last speech runs this close to the end did not finish —
# the timer cut the speaker off. It matters because the engine's other signals
# cannot tell that apart from bad speech: the words never said score as
# unclear, and the accuracy they were never given a chance to earn is charged
# against them. Detected here so the report can say "you ran out of time"
# instead of "these words were mispronounced", which is a different problem
# with a different fix.
TRUNCATION_MARGIN_MS = 200

DIMENSION_TO_SKILL = {
    "fluency": "fluency",
    "latency": "response_latency",
    "accuracy": "listening",
    "pronunciation": "pronunciation",
    "disfluency": "fluency",
    "grammar": "grammar",
    "content": "content_recall",
    "completeness": "content_recall",
}

# What remains genuinely out of reach, and why. Surfaced to the student rather
# than silently omitted.
# Everything the engine can reach is now scored. What remains is depth rather
# than coverage: per-phoneme confusion pairs (DIAG-03) need a phoneme-output
# model, and the intelligibility rating that is the actual moat needs the
# human rater panel.
UNSCORED: dict[str, str] = {}

# Tasks where the words were ours, not the student's, or where there are too
# few of them to judge. Grammar-scoring these measures our own item bank.
# Why a dimension went missing on a degraded deployment. Written for the
# student: "we could not measure this here" is useful, a provider key is not.
# None of these promise that the recording still exists. A deployment without
# a persistent disk loses audio on every restart, so "your recording is saved,
# it can be scored later" is a claim the product cannot keep -- and a false
# reassurance is worse than the missing measure it was meant to soften.
NO_TRANSCRIPT = ("Needs speech recognition, which is not installed on this "
                 "server. Nothing is wrong with your recording.")
NO_VAD = ("Needs speech detection, which is not available on this server. "
          "Nothing is wrong with your recording.")


def _no_provider(capability: str) -> str:
    return (f"The {capability} model is not available on this server, so this "
            f"measure was left out rather than guessed.")


NOT_A_GRAMMAR_SAMPLE = {"read_aloud", "repeat_sentence", "short_answer",
                        # Scripted targets: the sentence is ours, so its
                        # grammar is not the candidate's own sample.
                        "spoken_completion", "spoken_correction"}

# Tasks with a target utterance to align articulation against.
SCRIPTED_FOR_PRONUNCIATION = {"read_aloud", "repeat_sentence", "sentence_build",
                              "spoken_completion", "spoken_correction"}

# Items whose reference text is the whole expected answer, so "how much of it
# arrived" is answerable by comparing against it. Imported from the accuracy
# provider rather than restated, because a task type in one list and not the
# other would be scored for accuracy against a reference and for completeness
# against nothing.
from app.engine.providers.tier1.accuracy import (  # noqa: E402
    SCRIPTED_TASKS as ACCURACY_SCRIPTED)

# Items with no reference at all, where the only signal is whether they spoke
# for as long as the item expects. Short Answer is absent on purpose: a
# correct answer to it is one word, and measuring that against a duration
# would fail every candidate who got it right.
OPEN_SPOKEN_TASKS = {"open_response", "story_retell", "conversation_question",
                     "passage_question"}

# Said out loud next to the grammar score, because a partial check presented as
# a complete one is the failure mode that matters here.
COVERAGE_NOTES = {
    "pronunciation": ("Measures how clearly each word was articulated, not how "
                      "close it is to any particular accent. Character-level, "
                      "so it cannot yet name the specific sounds."),
    "grammar": ("Checks a set of high-frequency error patterns rather than every "
                "possible mistake — and never treats Indian English as an error."),
    "content": ("Measured against the key points the item author wrote down, not "
                "against a model's opinion of your answer."),
}


@dataclass
class ResponseOutcome:
    response_id: str
    task_type: str
    scores: dict[str, float] = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    transcript: str = ""
    quality_verdict: str = "good"
    skipped: bool = False
    elapsed_ms: int = 0
    # Dimension -> why this attempt could not produce it. Distinct from
    # UNSCORED, which is what the engine cannot do *by design*; this is what
    # this particular deployment could not do *today*.
    unscored: dict[str, str] = field(default_factory=dict)


@dataclass
class AttemptOutcome:
    attempt_id: str
    overall: float | None
    dimensions: dict[str, float]
    responses: list[ResponseOutcome]
    unscored: dict[str, str]
    elapsed_ms: int
    biggest_lever: dict | None


# --------------------------------------------------------------------------
# One response
# --------------------------------------------------------------------------

def _also_correct(item) -> tuple[str, ...]:
    """Other arrangements an item accepts, from its rubric.

    Only Sentence Build reads this, and the bank carries none today. Most of
    those sentences have exactly one natural arrangement -- but not all do,
    and where a second is legitimate this makes accepting it a content change
    rather than a code change.
    """
    if item is None:
        return ()
    written = (item.rubric or {}).get("also_correct") or ()
    return tuple(str(x) for x in written if str(x).strip())


async def score_response(tenant: AsyncSession, providers: Providers,
                          tenant_id: str | None, response_id: str) -> ResponseOutcome:
    """Score one answer. Safe to call twice — the second call is a no-op.

    Idempotent because it runs from a background task on upload *and* can be
    retried by submit if that task died. Doing the work twice would double the
    score records, which is a quieter and nastier bug than not doing it at all.
    """
    started = time.perf_counter()

    response = await tenant.get(Response, response_id)
    if response is None:
        raise ValueError(f"no such response: {response_id}")

    section = (await tenant.get(ProfileSection, response.section_id)
               if response.section_id else None)
    task_type = section.task_type if section else ""

    existing = (await tenant.execute(
        select(FeatureRecord).where(FeatureRecord.response_id == response_id)
    )).scalar_one_or_none()
    if existing is not None:
        return ResponseOutcome(response_id=response_id, task_type=task_type,
                               metrics=existing.metrics or {},
                               transcript=existing.transcript)

    audio = (await tenant.execute(
        select(ResponseAudio).where(ResponseAudio.response_id == response_id)
    )).scalar_one_or_none()

    if response.skipped or audio is None or audio.deleted_at is not None:
        return ResponseOutcome(response_id=response_id, task_type=task_type,
                               skipped=True)

    item = await tenant.get(TaskItem, response.item_id) if response.item_id else None
    reference = (item.reference_text or item.prompt_text) if item else ""

    ref = AudioRef(storage_key=audio.storage_key, mime_type=audio.mime_type,
                   sample_rate=audio.sample_rate, duration_ms=audio.duration_ms)

    # -- hearing ----------------------------------------------------------
    # Recording starts at the beep, so the first speech frame is the response
    # latency with no offset to subtract.
    try:
        vad, vad_meta = await providers.invoke(
            Capability.VAD, tenant_id,
            lambda impl: impl.detect(ref, prompt_end_ms=0),
        )
    except ProviderUnavailable as exc:
        # Emphatically not `skipped=True`. Skipped means the *student* did not
        # answer, and reporting an engine failure that way is a lie about the
        # candidate that also erases the reason: a skipped response carries no
        # dimensions and no explanation, which is how an attempt with eight
        # good recordings came back completely blank with nothing to say.
        log.warning("no VAD provider: %s", exc)
        return ResponseOutcome(
            response_id=response_id, task_type=task_type,
            unscored={d: NO_VAD for d in ("fluency", "latency")},
        )

    transcript = TranscriptResult(text="", confidence=0.0)
    transcript_meta = None
    try:
        transcript, transcript_meta = await providers.invoke(
            Capability.ASR, tenant_id,
            # The reference is deliberately not passed as a hint: priming the
            # model with the answer would make every scripted score a
            # measurement of our own prompt.
            lambda impl: impl.transcribe(ref, language="en"),
        )
    except ProviderUnavailable:
        # Tier 0 has no ASR. Everything transcript-shaped stays unscored -- and
        # now says so, instead of vanishing.
        for dimension in ("accuracy", "disfluency", "grammar", "content"):
            unscored[dimension] = NO_TRANSCRIPT

    scores: dict[str, float] = {}
    records: list[ScoreRecord] = []
    unscored: dict[str, str] = {}

    def add(dimension: str, value: float, confidence: float, meta) -> None:
        scores[dimension] = value
        records.append(ScoreRecord(
            attempt_id=response.attempt_id, response_id=response.id,
            dimension=dimension, score=round(value, 1),
            scale_min=SCALE_MIN, scale_max=SCALE_MAX,
            band=band_label(value), confidence=confidence,
            provider_id=getattr(meta, "provider_id", "") or "",
            provider_key=getattr(meta, "provider_key", "") or "pipeline",
            provider_version=getattr(meta, "version", "") or "0.1.0",
        ))

    # -- speech quality ----------------------------------------------------
    fluency: FluencyResult | None = None
    try:
        fluency, fluency_meta = await providers.invoke(
            Capability.FLUENCY, tenant_id,
            lambda impl: impl.score(ref, transcript=transcript, vad=vad,
                                    task_type=task_type),
        )
        if fluency.confidence > 0:
            add("fluency", fluency.score, fluency.confidence, fluency_meta)
    except ProviderUnavailable as exc:
        log.warning("no fluency provider: %s", exc)
        unscored["fluency"] = _no_provider("fluency")

    if vad.onset_ms is not None:
        add("latency", latency_score(vad.onset_ms), 0.7, vad_meta)

    # -- what was said -----------------------------------------------------
    accuracy: AccuracyResult | None = None
    if transcript.text and reference:
        try:
            accuracy, accuracy_meta = await providers.invoke(
                Capability.ACCURACY, tenant_id,
                lambda impl: impl.score(transcript=transcript,
                                        reference_text=reference,
                                        task_type=task_type,
                                        alternatives=_also_correct(item)),
            )
            if accuracy.confidence > 0:
                add("accuracy", accuracy.score, accuracy.confidence, accuracy_meta)
                # Sentence Build: separate construction score from word accuracy.
                # The construction score measures word-order arrangement, which
                # is the specific thing this task type exists to assess.
                if task_type == "sentence_build" and accuracy.coverage is not None and accuracy.order is not None:
                    construction = COVERAGE_SHARE * accuracy.coverage + ORDER_SHARE * accuracy.order
                    construction_score = SCALE_MIN + construction * (SCALE_MAX - SCALE_MIN)
                    add("construction", round(construction_score, 1), accuracy.confidence, accuracy_meta)
        except ProviderUnavailable:
            unscored["accuracy"] = _no_provider("word-accuracy")

    disfluency: DisfluencyResult | None = None
    if transcript.words:
        try:
            disfluency, disfluency_meta = await providers.invoke(
                Capability.DISFLUENCY, tenant_id,
                lambda impl: impl.detect(transcript=transcript, vad=vad),
            )
            if disfluency.confidence > 0:
                add("disfluency", disfluency.score, disfluency.confidence,
                    disfluency_meta)
        except ProviderUnavailable:
            unscored["disfluency"] = _no_provider("disfluency")

    grammar = None
    # Only free speech is worth grammar-checking. Reading a sentence aloud
    # tests the reading, not the grammar — the sentence was ours. A one-word
    # Short Answer is not a grammar sample either.
    if transcript.text and task_type not in NOT_A_GRAMMAR_SAMPLE:
        try:
            grammar, grammar_meta = await providers.invoke(
                Capability.GRAMMAR, tenant_id,
                lambda impl: impl.analyse(transcript.text, task_type=task_type),
            )
            if grammar.confidence > 0:
                add("grammar", grammar.score, grammar.confidence, grammar_meta)
        except ProviderUnavailable:
            unscored["grammar"] = _no_provider("grammar")

    pronunciation = None
    # Only where there is a target the student was asked to produce. Scoring
    # articulation against a transcript the recogniser guessed would be marking
    # its own homework.
    if reference and task_type in SCRIPTED_FOR_PRONUNCIATION:
        try:
            pronunciation, pron_meta = await providers.invoke(
                Capability.PRONUNCIATION, tenant_id,
                lambda impl: impl.score(ref, reference_text=reference,
                                        l1_language=""),
            )
            # Measured at ingest. A poor signal-to-noise ratio cuts how far
            # the pronunciation number is trusted, because this GOP variant
            # cannot otherwise tell a quiet speaker from a noisy room.
            snr = _snr_of(audio)
            if snr is not None:
                pronunciation.confidence = round(
                    pronunciation.confidence * _snr_penalty(snr), 2)
            if pronunciation.confidence > 0:
                add("pronunciation", pronunciation.score, pronunciation.confidence,
                    pron_meta)
        except ProviderUnavailable:
            unscored["pronunciation"] = _no_provider("pronunciation")

    relevance = None
    if transcript.text and task_type in {"story_retell", "open_response", "short_answer"}:
        rubric = dict(item.rubric or {}) if item else {}
        rubric.setdefault("prompt", (item.prompt_text if item else ""))
        try:
            relevance, relevance_meta = await providers.invoke(
                Capability.CONTENT_RELEVANCE, tenant_id,
                lambda impl: impl.score(transcript.text, rubric=rubric,
                                        task_type=task_type),
            )
            # An open response comes back with zero confidence on purpose:
            # it is a flag about staying on topic, not a content grade.
            if relevance.confidence > 0:
                add("content", relevance.score, relevance.confidence, relevance_meta)
        except ProviderUnavailable:
            unscored["content"] = _no_provider("content-relevance")

    # -- completeness ------------------------------------------------------
    #
    # Deliberately after everything else, because it is computed from what
    # they produced rather than measured by a provider of its own.
    complete, complete_reason = _completeness(
        task_type=task_type, item=item, reference=reference,
        transcript=transcript, vad=vad)
    if complete is None:
        unscored["completeness"] = complete_reason
    else:
        # Confidence is fixed rather than derived. This is a proportion of
        # something asked for against something produced -- there is no model
        # in it to be unsure of, and pretending otherwise by echoing the ASR
        # confidence would make the number look more measured than it is.
        add("completeness", SCALE_MIN + complete * (SCALE_MAX - SCALE_MIN),
            0.6, None)

    # -- record ------------------------------------------------------------
    ended_mid_speech = bool(
        vad.segments
        and audio.duration_ms - vad.segments[-1].end_ms <= TRUNCATION_MARGIN_MS
    )

    metrics: dict = {
        "completeness": complete,
        "onset_ms": vad.onset_ms,
        "ended_mid_speech": ended_mid_speech,
        "speech_ms": vad.speech_ms,
        "silence_ms": vad.silence_ms,
        "segment_count": len(vad.segments),
        "quality": quality_verdict(audio),
    }
    if fluency is not None:
        metrics.update({
            "words_per_minute": fluency.words_per_minute,
            "articulation_rate": fluency.articulation_rate,
            "pause_count": fluency.pause_count,
            "mean_pause_ms": fluency.mean_pause_ms,
            "longest_pause_ms": fluency.longest_pause_ms,
        })
    if accuracy is not None:
        metrics.update({
            "accuracy": accuracy.accuracy,
            "matched_words": accuracy.matched,
            "reference_words": accuracy.reference_words,
            # Reported next to the score on purpose. Every word the recogniser
            # got wrong is counted against the student, so how sure it was is
            # part of reading the number — this is the main channel through
            # which an accent could become a penalty.
            "asr_confidence_for_accuracy": transcript.confidence,
        })
    if disfluency is not None:
        metrics.update({
            "filler_count": disfluency.filler_count,
            "repetition_count": disfluency.repetition_count,
        })
    # Which engine produced this. A study set scored under one fingerprint
    # and calibrated under another is the failure the freeze exists to catch,
    # and this is what lets it be caught per recording rather than in bulk.
    metrics["engine_hash"] = freeze.current_hash()
    if transcript.words:
        metrics["asr_confidence"] = transcript.confidence
        metrics["asr_provider"] = getattr(transcript_meta, "provider_key", "")
    if grammar is not None:
        metrics["grammar_error_count"] = len(grammar.errors)
    if relevance is not None:
        metrics["content_coverage"] = relevance.coverage
        metrics["off_topic"] = relevance.off_topic
    if pronunciation is not None:
        metrics["unclear_words"] = len(pronunciation.mispronounced_words)

    feature = FeatureRecord(
        response_id=response.id,
        transcript=transcript.text,
        word_timings=[{"word": w.word, "start_ms": w.start_ms,
                       "end_ms": w.end_ms, "confidence": w.confidence}
                      for w in transcript.words],
        speech_segments=[{"start_ms": s.start_ms, "end_ms": s.end_ms}
                         for s in vad.segments],
        metrics=metrics,
        disfluencies=disfluency.events if disfluency else [],
        # Per-word clarity, which is what the listen-back highlights. Named
        # for the contract; per-word in fact, and labelled as such.
        phoneme_scores=(pronunciation.phonemes if pronunciation
                        else (relevance.key_points if relevance else [])),
        # And separately, what the words themselves were measured against.
        # These two answer different questions -- "was this word clear" and
        # "was this the right word" -- and serving one under the other's name
        # is how the listen-back came to show "undefined" for every item.
        word_errors=accuracy.word_errors if accuracy else [],
        grammar_errors=grammar.errors if grammar else [],
    )
    tenant.add(feature)
    tenant.add_all(records)

    response.response_latency_ms = vad.onset_ms
    response.duration_ms = audio.duration_ms
    if accuracy is not None:
        response.is_correct = accuracy.accuracy >= 0.8

    await tenant.commit()

    elapsed = int((time.perf_counter() - started) * 1000)
    return ResponseOutcome(
        response_id=response.id, task_type=task_type, scores=scores,
        metrics=metrics, transcript=transcript.text,
        quality_verdict=metrics["quality"], elapsed_ms=elapsed,
        # Only what this response actually failed to produce. A dimension that
        # scored here is not reported missing just because a sibling response
        # could not produce it.
        unscored={d: why for d, why in unscored.items() if d not in scores},
    )


def _unscored_for(outcomes: list[ResponseOutcome]) -> dict[str, str]:
    """What this attempt could not measure, and why.

    This used to be ``dict(UNSCORED)`` -- a module-level constant that is
    empty, because on a full install there is nothing the engine cannot
    reach. On a deployment missing its speech models that same empty dict was
    still reported, so an attempt that measured *nothing* was indistinguishable
    from one that measured everything. The student got a blank score with no
    explanation and no reason to think anything had gone wrong.

    A dimension counts as unscored only if no response managed to produce it:
    one bad recording in eight is a quality problem, not a missing capability.
    """
    reasons: dict[str, str] = dict(UNSCORED)
    produced = {d for o in outcomes for d in o.scores}
    for outcome in outcomes:
        for dimension, why in outcome.unscored.items():
            if dimension not in produced:
                reasons.setdefault(dimension, why)
    return reasons


# --------------------------------------------------------------------------
# The attempt
# --------------------------------------------------------------------------

async def pending_responses(tenant: AsyncSession, attempt_id: str) -> list[str]:
    """Responses with audio but no features yet — what submit is waiting on."""
    responses = (await tenant.execute(
        select(Response).where(Response.attempt_id == attempt_id,
                               Response.skipped.is_(False))
    )).scalars().all()
    if not responses:
        return []
    ids = [r.id for r in responses]
    audible = {a.response_id for a in (await tenant.execute(
        select(ResponseAudio.response_id).where(
            ResponseAudio.response_id.in_(ids),
            ResponseAudio.deleted_at.is_(None))
    )).scalars().all()}
    featured = {f.response_id for f in (await tenant.execute(
        select(FeatureRecord.response_id).where(FeatureRecord.response_id.in_(ids))
    )).scalars().all()}
    return [r.id for r in responses
            if r.id in audible and r.id not in featured]


async def finalise_attempt(tenant: AsyncSession, attempt_id: str) -> AttemptOutcome:
    """Compose the attempt-level scores from whatever the responses produced."""
    started = time.perf_counter()

    attempt = await tenant.get(Attempt, attempt_id)
    if attempt is None:
        raise ValueError(f"no such attempt: {attempt_id}")

    responses = (await tenant.execute(
        select(Response).where(Response.attempt_id == attempt_id)
        .order_by(Response.position)
    )).scalars().all()

    features = {f.response_id: f for f in (await tenant.execute(
        select(FeatureRecord).where(
            FeatureRecord.response_id.in_([r.id for r in responses] or [""]))
    )).scalars().all()}

    per_response: dict[str, dict[str, float]] = {}
    for row in (await tenant.execute(
        select(ScoreRecord).where(ScoreRecord.attempt_id == attempt_id,
                                  ScoreRecord.response_id.is_not(None),
                                  ScoreRecord.is_shadow.is_(False))
    )).scalars().all():
        per_response.setdefault(row.response_id, {})[row.dimension] = row.score

    outcomes = [
        ResponseOutcome(
            response_id=r.id,
            task_type="",
            scores=per_response.get(r.id, {}),
            metrics=(features[r.id].metrics if r.id in features else {}),
            transcript=(features[r.id].transcript if r.id in features else ""),
            skipped=r.skipped or r.id not in features,
        )
        for r in responses
    ]

    dimensions = average_dimensions(outcomes)
    overall = compose_overall(dimensions)

    # Re-running finalise must not stack a second set of attempt-level rows.
    await tenant.execute(delete(ScoreRecord).where(
        ScoreRecord.attempt_id == attempt_id,
        ScoreRecord.response_id.is_(None)))

    def _attempt_row(dimension: str, value: float, confidence: float) -> ScoreRecord:
        return ScoreRecord(
            attempt_id=attempt_id, response_id=None, dimension=dimension,
            score=round(value, 1), scale_min=SCALE_MIN, scale_max=SCALE_MAX,
            band=band_label(value), confidence=confidence,
            provider_key="pipeline", provider_version="0.2.0",
        )

    for dimension, value in dimensions.items():
        tenant.add(_attempt_row(dimension, value,
                                confidence_for(outcomes, dimension)))

    if overall is not None:
        measured = len([d for d in dimensions if d in WEIGHTS])
        tenant.add(_attempt_row("overall", overall,
                                round(min(0.7, 0.25 + 0.12 * measured), 2)))

    await update_mastery(tenant, attempt.user_id, dimensions)

    attempt.status = "scored"
    attempt.scored_at = datetime.now(timezone.utc)
    await tenant.commit()

    return AttemptOutcome(
        attempt_id=attempt_id,
        overall=round(overall, 1) if overall is not None else None,
        dimensions={k: round(v, 1) for k, v in dimensions.items()},
        responses=outcomes,
        unscored=_unscored_for(outcomes),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        biggest_lever=biggest_lever(dimensions),
    )


async def update_mastery(tenant: AsyncSession, user_id: str,
                         dimensions: dict[str, float]) -> None:
    """Move mastery on evidence, using Bayesian Knowledge Tracing (ENG-13)."""
    for dimension, value in dimensions.items():
        skill = DIMENSION_TO_SKILL.get(dimension)
        if skill is None:
            continue

        row = (await tenant.execute(
            select(SkillMastery).where(SkillMastery.user_id == user_id,
                                       SkillMastery.skill == skill)
        )).scalar_one_or_none()

        if row is None:
            prior = bkt.parameters_for(skill).p_init
            posterior = bkt.update_from_score(prior, value, skill)
            tenant.add(SkillMastery(
                user_id=user_id, skill=skill, mastery=round(posterior, 4),
                baseline=round(posterior, 4),
                confidence=bkt.confidence_after(1), observations=1,
                last_change=0.0,
            ))
            continue

        posterior = bkt.update_from_score(row.mastery, value, skill)
        row.last_change = round(posterior - row.mastery, 4)
        row.mastery = round(posterior, 4)
        row.observations += 1
        row.confidence = bkt.confidence_after(row.observations)
        if row.baseline is None:
            row.baseline = round(posterior, 4)
        row.updated_at = datetime.now(timezone.utc)

    await tenant.commit()


class AttemptScorer:
    """Score every response, then compose. Used when nothing was scored on ingest."""

    def __init__(self, tenant: AsyncSession, providers: Providers,
                 tenant_id: str | None) -> None:
        self.tenant = tenant
        self.providers = providers
        self.tenant_id = tenant_id

    async def run(self, attempt_id: str) -> AttemptOutcome:
        attempt = await self.tenant.get(Attempt, attempt_id)
        if attempt is None:
            raise ValueError(f"no such attempt: {attempt_id}")
        attempt.status = "scoring"
        await self.tenant.commit()

        response_ids = [r.id for r in (await self.tenant.execute(
            select(Response).where(Response.attempt_id == attempt_id)
            .order_by(Response.position)
        )).scalars().all()]
        for response_id in response_ids:
            await score_response(self.tenant, self.providers, self.tenant_id, response_id)

        return await finalise_attempt(self.tenant, attempt_id)


# --------------------------------------------------------------------------
# Composition
# --------------------------------------------------------------------------

def latency_score(onset_ms: int) -> float:
    if onset_ms <= LATENCY_EXCELLENT:
        return SCALE_MAX
    if onset_ms >= LATENCY_POOR:
        return SCALE_MIN
    if onset_ms <= LATENCY_GOOD:
        span = LATENCY_GOOD - LATENCY_EXCELLENT
        return SCALE_MAX - 12.0 * (onset_ms - LATENCY_EXCELLENT) / span
    span = LATENCY_POOR - LATENCY_GOOD
    return (SCALE_MAX - 12.0) - (SCALE_MAX - 12.0 - SCALE_MIN) * (onset_ms - LATENCY_GOOD) / span


def average_dimensions(outcomes: list[ResponseOutcome]) -> dict[str, float]:
    totals: dict[str, list[float]] = {}
    for outcome in outcomes:
        for dimension, value in outcome.scores.items():
            totals.setdefault(dimension, []).append(value)
    return {d: sum(v) / len(v) for d, v in totals.items() if v}


def compose_overall(dimensions: dict[str, float]) -> float | None:
    """Weighted mean over the dimensions that were measured, renormalised.

    Two things this deliberately will not do.

    It will not compose from one or two dimensions. Renormalising over a
    fraction of the picture produces a number that looks like the same
    measurement as a full one and is not — a Read Aloud attempt and a
    six-part simulation would both be labelled "overall" while being computed
    on different bases. Below the threshold there is no overall at all, and
    the report shows the dimensions instead.

    And the weights themselves are not validated. They are a considered guess
    at relative importance, nothing more, which is why every consumer of this
    number is handed the calibration state alongside it.
    """
    usable = {d: v for d, v in dimensions.items() if d in WEIGHTS}
    if len(usable) < calibration.MIN_DIMENSIONS_FOR_OVERALL:
        return None
    return _weighted_mean(usable)


def _weighted_mean(dimensions: dict[str, float]) -> float | None:
    """The arithmetic behind the composite, without the publication gate.

    Used where two composites are compared on the same basis — the biggest
    lever asks "what would the number become", and that difference is
    meaningful even when the absolute value is not fit to show. Gating this
    too would silently remove the lever from every short attempt.
    """
    usable = {d: v for d, v in dimensions.items() if d in WEIGHTS}
    if not usable:
        return None
    total_weight = sum(WEIGHTS[d] for d in usable)
    return sum(WEIGHTS[d] * v for d, v in usable.items()) / total_weight


def confidence_for(outcomes: list[ResponseOutcome], dimension: str) -> float:
    scored = sum(1 for o in outcomes if dimension in o.scores)
    if scored == 0:
        return 0.0
    return round(min(0.75, 0.35 + 0.06 * scored), 2)


def biggest_lever(dimensions: dict[str, float]) -> dict | None:
    """The one change that moves the number most — and by how much, truthfully.

    The gain quoted is computed, not chosen for effect: it is what the overall
    would become if this dimension matched the student's own best one. If the
    dimensions are already level there is no lever, and it says so rather than
    inventing one (GAM-19).
    """
    usable = {d: v for d, v in dimensions.items() if d in WEIGHTS}
    if len(usable) < 2:
        return None

    weakest = min(usable, key=lambda d: usable[d])
    best = max(usable.values())
    if best - usable[weakest] < 2.0:
        return None

    before = _weighted_mean(usable) or 0.0
    after = _weighted_mean({**usable, weakest: best}) or before
    gain = round(after - before, 1)
    if gain < 1.0:
        return None

    return {"dimension": weakest, "current": round(usable[weakest], 1),
            "target": round(best, 1), "predicted_gain": gain}


def _snr_of(audio: ResponseAudio) -> float | None:
    if audio.peak_dbfs is None or audio.noise_floor_dbfs is None:
        return None
    return audio.peak_dbfs - audio.noise_floor_dbfs


def _snr_penalty(snr_db: float) -> float:
    """Mirrors the provider's own scale. Kept here so the pipeline can apply
    it without importing a Tier-1 module directly — the whole point of the
    contract layer is that consumers do not know which provider ran."""
    if snr_db >= 20:
        return 1.0
    if snr_db >= 12:
        return 0.75
    if snr_db >= 6:
        return 0.45
    return 0.2


def quality_verdict(audio: ResponseAudio) -> str:
    if audio.clipped:
        return "clipped"
    if audio.noise_floor_dbfs is not None and audio.peak_dbfs is not None:
        if audio.peak_dbfs - audio.noise_floor_dbfs < 12:
            return "noisy"
    return "good"


def band_label(score: float) -> str:
    if score >= 65:
        return "Strong"
    if score >= 51:
        return "Competent"
    if score >= 36:
        return "Developing"
    return "Beginning"


def to_unit(score: float) -> float:
    return round(max(0.0, min(1.0, (score - SCALE_MIN) / (SCALE_MAX - SCALE_MIN))), 4)


# Older call sites used the underscored names.
_biggest_lever = biggest_lever
_latency_score = latency_score
_band_label = band_label
UNSCORED_AT_TIER0 = UNSCORED


def _completeness(*, task_type: str, item, reference: str,
                  transcript: TranscriptResult, vad) -> tuple[float | None, str]:
    """How much of the answer that was asked for actually arrived.

    Two different questions depending on what the item is, because "the whole
    answer" means two different things:

    * **A scripted item has a reference**, so completeness is how much of it
      was attempted. Word coverage, order ignored -- getting the order wrong
      is what ``accuracy`` measures, and charging it twice would make a single
      mistake look like two.
    * **An open item has no reference**, so the only honest proxy is whether
      they spoke for as long as the item expects. A crude measure, and it is
      capped at 1.0 so that talking longer can never earn marks: the failure
      it exists to catch is the four-word answer to a sixty-second question.

    Returns ``(None, reason)`` where neither applies, rather than a zero.
    An item with no reference and no stated expectation has not told us what
    complete would look like, and scoring that as incomplete would fail
    candidates for the bank's silence.
    """
    from app.engine.providers.tier1.accuracy import _coverage, normalise

    if reference and task_type in ACCURACY_SCRIPTED:
        expected = normalise(reference)
        if not expected:
            return None, "This item has no reference to be complete against."
        if not transcript.text:
            return None, NO_TRANSCRIPT
        return round(min(1.0, _coverage(expected, normalise(transcript.text))), 3), ""

    expects = 0.0
    if item is not None:
        expects = float((item.rubric or {}).get("min_seconds") or 0.0)
    if not expects and task_type in OPEN_SPOKEN_TASKS:
        expects = DEFAULT_MIN_SECONDS
    if not expects:
        return None, ("This kind of item does not say how long a complete "
                      "answer is, so completeness was not scored.")

    spoke = (vad.speech_ms or 0) / 1000.0
    return round(min(1.0, spoke / expects), 3), ""
