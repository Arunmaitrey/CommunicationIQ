"""The evidence boundary — the only thing that decides what leaves our infra.

Built field by field from an AttemptResult that already exists. It never
serialises an ORM object and never reads the database: give it the finished
result and it returns a dict that, by construction, contains scores and their
plain-language glosses and nothing that identifies a person, a device or an
institution.

The deny-list is enforced by *omission*: this builder names every field it
emits, so a new column added to any model cannot leak here by default — it
would have to be added to this file, in review, on purpose.
"""
from __future__ import annotations

from app import reporting
from app.narration.contract import NarrationEvidence, NarratorError

# 2.0: biggest_lever replaced by primary_diagnosis; recommendations are the
# diagnosis-ordered priorities rather than the weighted-gain table.
SCHEMA_VERSION = "2.0"

# Numbers the model may cite per dimension, drawn from the per-response
# metrics the report already computes. Counts and rates only — never words.
_FACT_KEYS = ("pause_count", "words_per_minute", "articulation_rate",
             "longest_pause_ms", "onset_ms")


def build(result, *, l1_language: str = "") -> NarrationEvidence:
    """Project a finished AttemptResult into the minimal evidence payload.

    Raises NarratorError("no_evidence") when there is nothing to explain — an
    attempt with no overall and no dimensions is not narratable, and calling a
    model to say "we could not measure anything" is waste.
    """
    dimensions = getattr(result, "dimensions", {}) or {}
    overall = getattr(result, "overall", None)
    if overall is None and not dimensions:
        raise NarratorError("no_evidence", "attempt has no overall and no dimensions")

    say = reporting._say  # the product's own plain-language dimension names

    attempt = {
        "status": getattr(result, "status", ""),
        "has_overall": overall is not None,
        "overall": round(overall, 1) if overall is not None else None,
        "scale": [getattr(result, "scale_min", 20), getattr(result, "scale_max", 80)],
        "band_phrase": reporting.band_phrase(overall) if overall is not None else "",
        "calibrated": bool(getattr(result, "calibrated", False)),
        "has_audio": any(getattr(r, "has_audio", False)
                         for r in getattr(result, "responses", []) or []),
    }

    dims = [{"key": d, "score": round(v, 1), "gloss": say(d)}
            for d, v in sorted(dimensions.items())]

    primary = getattr(result, "primary_diagnosis", None)
    primary_out = None
    if primary is not None:
        get = (primary.get if isinstance(primary, dict)
               else lambda k, d=None: getattr(primary, k, d))
        dim = get("dimension") or ""
        primary_out = {
            "status": get("status") or "",
            "dimension": dim,
            "gloss": say(dim) if dim else "",
            "label": get("label") or "",
            "score": get("score"),
            "responses": get("responses") or 0,
            "reason": get("reason") or "",
            "evidence": get("evidence") or "",
            "candidates": [
                {"dimension": c.get("dimension"), "gloss": say(c.get("dimension", "")),
                 "score": c.get("score"), "responses": c.get("responses")}
                for c in (get("candidates") or [])
                if isinstance(c, dict)],
        }

    strengths = [{"key": h.dimension, "gloss": say(h.dimension),
                  "score": h.score, "delta": h.delta}
                 for h in (getattr(result, "strengths", []) or [])]

    # The diagnosis-ordered priorities, not the weighted-gain table: the
    # first entry is the primary (or the first of a tied group), so a
    # provider that takes "recommendations[0]" cannot drift from it.
    recs = [{"dimension": r.dimension, "gloss": say(r.dimension),
             "advice": r.advice}
            for r in (getattr(result, "priorities", []) or [])]

    unscored = dict(getattr(result, "unscored", {}) or {})

    # Structured, per-dimension numeric facts — the honest, PII-free stand-in
    # for quoting the transcript. Grammar/word errors are counts, not text.
    facts: list = []
    for r in getattr(result, "responses", []) or []:
        scores = getattr(r, "scores", {}) or {}
        for dim in scores:
            entry: dict = {"dimension": dim}
            for key in _FACT_KEYS:
                val = getattr(r, key, None)
                if val not in (None, "", [], {}):
                    entry[key] = val
            ge = getattr(r, "grammar_errors", None) or []
            we = getattr(r, "word_errors", None) or []
            if dim == "grammar" and ge:
                entry["grammar_error_count"] = len(ge)
            if dim == "accuracy" and we:
                entry["word_error_count"] = len(we)
            if len(entry) > 1:
                facts.append(entry)

    return NarrationEvidence(
        schema_version=SCHEMA_VERSION,
        attempt=attempt,
        dimensions=dims,
        primary_diagnosis=primary_out,
        strengths=strengths,
        recommendations=recs,
        unscored=unscored,
        evidence_facts=facts[:20],
        # Label only — routes tone, never used to diagnose sounds.
        l1_language=(l1_language or "")[:20],
    )


# The deny-list, asserted rather than implied. A test walks a payload and
# fails if any of these substrings appear, so a regression is caught even if
# someone adds a field by hand later.
FORBIDDEN_SUBSTRINGS = (
    "@", "email", "roll", "phone", "user_id", "attempt_id", "response_id",
    "tenant", "slug", "password", "token", "storage_key", "ip_",
)


def as_payload(evidence: NarrationEvidence) -> dict:
    """The dict actually sent to a provider. Also what the privacy test scans."""
    return {
        "schema_version": evidence.schema_version,
        "attempt": evidence.attempt,
        "dimensions": evidence.dimensions,
        "primary_diagnosis": evidence.primary_diagnosis,
        "strengths": evidence.strengths,
        "recommendations": evidence.recommendations,
        "unscored": evidence.unscored,
        "evidence_facts": evidence.evidence_facts,
        "l1_language": evidence.l1_language,
    }
