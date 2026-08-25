"""Language-content capability contracts — Layer 3 of the engine."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.engine.contracts.types import (GrammarResult, RelevanceResult,
                                        SynthesisResult)


@runtime_checkable
class GrammarProvider(Protocol):
    """ENG-10 — grammar error detection and typing on the transcript."""

    contract_version = "1.0"
    provider_key: str
    version: str

    async def analyse(self, transcript: str, *, task_type: str = "") -> GrammarResult:
        ...


@runtime_checkable
class ContentRelevanceProvider(Protocol):
    """ENG-11 — retell recall and open-response relevance.

    ``rubric`` carries the required key points. Implementations may use a
    language model as one signal; the contract requires the returned
    ``key_points`` to show which rubric points were matched, so the verdict is
    always inspectable rather than asserted.
    """

    contract_version = "1.0"
    provider_key: str
    version: str

    async def score(self, transcript: str, *, rubric: dict,
                    task_type: str = "") -> RelevanceResult:
        ...


@runtime_checkable
class TTSProvider(Protocol):
    """Prompt audio synthesis (SIM-06 — Indian, US and UK voices at test pace)."""

    contract_version = "1.0"
    provider_key: str
    version: str

    async def synthesize(self, text: str, *, accent: str = "indian",
                         rate: float = 1.0) -> SynthesisResult:
        ...
