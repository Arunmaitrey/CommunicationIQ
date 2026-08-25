"""The narrator provider contract and its data types.

Versioned like the engine's speech contracts: a provider declares a
``contract_version`` and is refused if it declares one we do not serve. The
product can move from Anthropic to another provider by writing a new class
that satisfies this Protocol — the reporting layer never changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# What kind of failure a generation attempt hit. Drives retry-or-not, and is
# stored on the job so operations can see *why* things fail without any PII.
#
#   transient  — network, timeout, 429, provider 5xx: retry with backoff
#   invalid_response — provider replied but the output failed validation
#   refused    — provider content-policy refusal
#   bad_request — 4xx that is not 429: our request is wrong, do not retry
#   config     — no key / disabled / unknown provider: not retryable here
#   no_evidence — the attempt has nothing to explain (unscored/incomplete)
RETRYABLE = {"transient"}
TERMINAL = {"invalid_response", "refused", "bad_request", "config", "no_evidence"}


class NarratorError(Exception):
    """A generation failure, tagged with a category and a PII-free detail."""

    def __init__(self, category: str, detail: str = "") -> None:
        super().__init__(f"{category}: {detail}")
        self.category = category
        # Kept short and free of transcript/prompt text — it is logged and
        # stored on the job row for operators.
        self.detail = detail[:280]


@dataclass(frozen=True)
class NarrationEvidence:
    """The minimal, PII-free payload the model is allowed to see.

    Built only by evidence.build(); never constructed from an ORM object.
    Everything here is something the model *explains*, never something it
    derives — the scores are supplied so it cannot compute one.
    """

    schema_version: str
    attempt: dict
    dimensions: list
    # The product's one authoritative answer to "what should I work on
    # first?" (app/diagnosis.py), as data. The model explains it; it never
    # chooses a different one, and validate.check refuses a draft that does.
    primary_diagnosis: dict | None
    strengths: list
    # The practice priorities in the diagnosis's order, each with its
    # advice. Not a gain-ranked table: the narrator is never given a second
    # ordering it could present as the first thing to work on.
    recommendations: list
    unscored: dict
    evidence_facts: list
    l1_language: str = ""


@dataclass
class NarrationDraft:
    """What a provider returns. Still untrusted until validate.check passes."""

    headline: str
    summary: str
    primary_focus: str
    practice_action: str
    caveats: list = field(default_factory=list)
    # Observability, filled by the provider from the API response.
    model_version: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


@runtime_checkable
class FeedbackNarratorProvider(Protocol):
    contract_version = "1.0"
    provider_key: str
    model_version: str

    async def narrate(self, evidence: NarrationEvidence, *,
                      timeout_s: float) -> NarrationDraft:
        """Return a draft, or raise NarratorError with a category."""
        ...
