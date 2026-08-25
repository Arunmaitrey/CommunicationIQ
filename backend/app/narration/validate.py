"""Validating an untrusted model response before it can become a narration.

The model is never trusted. A draft is discarded unless it is well-formed,
within length limits, free of *fabricated assessment numbers*, and consistent
with the one authoritative fact it must not contradict — the frozen
primary_diagnosis. A discarded draft is a validation failure the job records and,
because it is not transient, does not blindly retry.

The number rule is the subtle part. The danger is an invented *measurement* —
a score, band, gain or percentage the engine never produced. It is not a
practice instruction that happens to contain a number ("read for 5 minutes",
"say it ten times"). The first version rejected every unsupplied number and so
threw away good, grounded explanations for their advice. This version
distinguishes the two: a number is a violation only when it is presented as an
assessment figure or sits in the score range, and is neither supplied nor a
plain practice-advice number. It stays fail-closed on fabricated scores.
"""
from __future__ import annotations

import re

from app.narration.contract import NarrationDraft, NarratorError, NarrationEvidence

MAX = {"headline": 120, "summary": 600, "primary_focus": 300,
       "practice_action": 400, "caveat": 200}
MAX_CAVEATS = 4

# Any markup at all is stripped, not sanitised — the card renders plain text.
_TAG = re.compile(r"<[^>]+>")
# Numbers in the prose. Up to 4 digits so a fabricated large value (e.g. an
# injected "9999") is seen and judged rather than slipping past a 3-digit cap.
_NUM = re.compile(r"\d{1,4}(?:\.\d)?")

# Units that mark a number as a practice instruction, not a measurement. A
# number immediately followed by one of these is advice ("60 seconds",
# "3 paragraphs") and is allowed even when it was not supplied.
_ADVICE_UNITS = (
    "minute", "min", "second", "sec", "hour", "hr", "day", "week", "month",
    "time", "sentence", "word", "paragraph", "line", "page", "item",
    "question", "session", "round",
)
# Tokens that mark a number as an assessment figure: a score/percentage/band.
_ASSESS_AFTER = ("out of", "/80", "/ 80", "%", "percent", "point", "band")
_ASSESS_BEFORE = ("score", "scored", "overall", "band", "rated", "rating")

# Semantic identity of each dimension, so a paraphrased biggest lever is
# recognised as the same lever. The check needs "the focus is about THIS
# dimension" — a model saying "improve your accuracy in repeating what you
# hear" is explaining the accuracy lever even though it did not echo the exact
# gloss string. Substrings, matched case-insensitively.
_LEVER_TERMS: dict[str, tuple[str, ...]] = {
    "pronunciation": ("pronunciation", "pronounce", "pronoun", "clearly",
                      "clarity", "articulat", "enunciat"),
    "accuracy": ("accuracy", "accurate", "repeat", "saying back", "what you heard",
                 "what you hear", "heard", "hear"),
    "fluency": ("fluency", "fluent", "flow", "stall", "pause", "pausing",
                "without stopping", "keep going", "keep talking", "steady", "hesitat"),
    "grammar": ("grammar", "grammatical", "tense", "agreement", "sentence structure"),
    "content": ("content", "cover", "coverage", "relevant", "on topic",
                "the question", "what the question", "what was asked"),
    "latency": ("latency", "start speaking", "starting", "start quickly",
                "begin", "response time", "the tone", "delay"),
    "disfluency": ("disfluency", "filler", "hesitation"),
    "completeness": ("completeness", "complete", "whole", "finish", "the whole"),
    "comprehension": ("comprehension", "understand", "follow", "meaning"),
    "vocabulary": ("vocabulary", "vocab", "word"),
    "appropriacy": ("appropriacy", "appropriate", "register", "tone", "politeness"),
}


def _clean(text: str) -> str:
    return _TAG.sub("", text or "").strip()


def check(draft: NarrationDraft, evidence: NarrationEvidence) -> NarrationDraft:
    """Return a cleaned draft, or raise NarratorError('invalid_response', …).

    Never raises anything retryable: a bad response is bad on retry too. The
    only cure is a new prompt/model version, which is a deliberate act.
    """
    headline = _clean(draft.headline)
    summary = _clean(draft.summary)
    focus = _clean(draft.primary_focus)
    action = _clean(draft.practice_action)
    caveats = [_clean(c) for c in (draft.caveats or []) if _clean(c)]

    if not (headline and summary and action):
        raise NarratorError("invalid_response", "missing required field")

    for name, value in (("headline", headline), ("summary", summary),
                        ("primary_focus", focus), ("practice_action", action)):
        if len(value) > MAX[name]:
            raise NarratorError("invalid_response", f"{name} too long")
    if len(caveats) > MAX_CAVEATS:
        raise NarratorError("invalid_response", "too many caveats")
    for c in caveats:
        if len(c) > MAX["caveat"]:
            raise NarratorError("invalid_response", "caveat too long")

    # Numbers: fabricated assessment figures are rejected; practice-advice
    # numbers and small counts are allowed. See module docstring.
    supplied = _supplied_numbers(evidence)
    scale = evidence.attempt.get("scale") or [20, 80]
    scale_min = float(scale[0]) if scale else 20.0
    for blob in (headline, summary, focus, action, *caveats):
        low = blob.lower()
        for m in _NUM.finditer(blob):
            token = m.group()
            if _norm(token) in supplied or token in supplied:
                continue
            after = low[m.end(): m.end() + 14]
            before = low[max(0, m.start() - 16): m.start()]
            if _is_advice(after):
                continue  # "5 minutes", "60 seconds", "3 paragraphs"
            if _is_assessment(before, after) or _val(token) >= scale_min:
                # An assessment-flagged or score-range number that was neither
                # supplied nor a practice instruction is a fabricated measure.
                raise NarratorError("invalid_response",
                                    f"unsupplied assessment number {token!r}")
            # Otherwise a small, unflagged count ("2 things", "3 areas") — fine.

    # Primary diagnosis: the AI explains it, it never chooses a different
    # one. With an identified dimension the focus must be about that
    # dimension, recognised semantically rather than by an exact gloss
    # string; a model that retargets to a different dimension fails. With
    # no identified dimension the focus must say so and must not name a
    # dimension outside the tied group as the thing to work on.
    primary = evidence.primary_diagnosis
    if primary:
        blob = (focus + " " + summary).lower()
        if primary.get("status") == "identified" and primary.get("dimension"):
            if not _mentions_dimension(blob, primary):
                raise NarratorError("invalid_response",
                                    "focus contradicts primary_diagnosis")
        else:
            if not any(p in focus.lower() for p in _NO_WINNER_PHRASES):
                raise NarratorError(
                    "invalid_response",
                    "no primary was identified but focus does not say so")
            allowed = {c.get("dimension") for c in (primary.get("candidates") or [])}
            low_focus = focus.lower()
            for dim, stems in _STRICT_TERMS.items():
                if dim in allowed:
                    continue
                if any(re.search(r"\b" + re.escape(t), low_focus) for t in stems):
                    raise NarratorError(
                        "invalid_response",
                        f"focus names {dim} though no primary was identified")

    # No overall was produced: the prose must not assert an *overall/total*
    # score. Dimension scores (which ARE supplied) are fine — the previous
    # rule wrongly rejected "your pronunciation score is 55".
    if not evidence.attempt.get("has_overall"):
        for blob in (headline, summary, focus):
            low = blob.lower()
            if re.search(r"\b(overall|total)\b[^.]{0,25}\d", low) or \
               re.search(r"\d[^.]{0,25}\b(overall|total)\b", low):
                raise NarratorError("invalid_response",
                                    "asserts an overall score that was withheld")

    return NarrationDraft(
        headline=headline, summary=summary, primary_focus=focus,
        practice_action=action, caveats=caveats[:MAX_CAVEATS],
        model_version=draft.model_version, input_tokens=draft.input_tokens,
        output_tokens=draft.output_tokens, latency_ms=draft.latency_ms)


def _val(token: str) -> float:
    try:
        return float(token)
    except ValueError:
        return 0.0


def _is_advice(after: str) -> bool:
    a = after.lstrip()
    return any(a.startswith(u) for u in _ADVICE_UNITS)


def _is_assessment(before: str, after: str) -> bool:
    if any(after.lstrip().startswith(s) or s in after[:8] for s in _ASSESS_AFTER):
        return True
    return any(before.rstrip().endswith(s) for s in _ASSESS_BEFORE)


# The unambiguous name of each dimension, for the NEGATIVE check: a focus
# that must not name an area fails only on the area's own name, never on a
# common word the positive synonym table above also accepts ("clearly",
# "word", "tone"), which would reject honest "nothing clearly stands out".
_STRICT_TERMS: dict[str, tuple[str, ...]] = {
    "pronunciation": ("pronunciation", "pronounc"),
    "accuracy": ("accuracy", "accurate"),
    "fluency": ("fluency", "fluent"),
    "grammar": ("grammar", "grammatical"),
    "content": ("content",),
    "latency": ("latency", "response speed"),
    "disfluency": ("disfluency", "filler"),
    "completeness": ("completeness",),
    "comprehension": ("comprehension",),
    "vocabulary": ("vocabulary", "vocab"),
    "appropriacy": ("appropriacy",),
}

# What a focus must contain when the diagnosis identified nothing. The
# prompt asks for exactly this; a draft that instead picks an area fails.
_NO_WINNER_PHRASES = ("stand out", "stands out", "more evidence",
                      "close together", "similar level", "same level",
                      "no single", "not enough evidence", "too early",
                      "not clear", "not yet clear", "isn't clear", "unclear",
                      "no clear", "hard to say", "cannot tell", "can't tell",
                      "can't say", "cannot say")


def _mentions_dimension(blob: str, lever: dict) -> bool:
    dim = (lever.get("dimension") or "").lower()
    # The gloss's own content words, plus the curated synonym set.
    gloss_words = [w for w in re.findall(r"[a-z]+", (lever.get("gloss") or "").lower())
                   if len(w) >= 5 and w not in _STOP]
    terms = set(_LEVER_TERMS.get(dim, ())) | set(gloss_words) | ({dim} if dim else set())
    for t in terms:
        if not t:
            continue
        if " " in t:                       # a phrase: plain substring
            if t in blob:
                return True
        elif re.search(r"\b" + re.escape(t), blob):  # a word or its prefix
            return True
    return False


_STOP = {"your", "what", "words", "clearly", "which", "there", "about", "these",
         "their", "would", "could", "should"}


def _norm(token: str) -> str:
    try:
        return str(round(float(token), 1))
    except ValueError:
        return token


def _supplied_numbers(evidence: NarrationEvidence) -> set[str]:
    nums: set[str] = set()

    def add(v):
        if isinstance(v, (int, float)):
            nums.add(str(round(float(v), 1)))
            nums.add(str(int(v)))

    a = evidence.attempt
    add(a.get("overall"))
    for x in (a.get("scale") or []):
        add(x)
    for d in evidence.dimensions:
        add(d.get("score"))
    primary = evidence.primary_diagnosis or {}
    add(primary.get("score")); add(primary.get("responses"))
    for c in primary.get("candidates") or []:
        add(c.get("score")); add(c.get("responses"))
    for h in evidence.strengths:
        add(h.get("score")); add(h.get("delta"))
    for f in evidence.evidence_facts:
        for v in f.values():
            add(v)
    return nums
