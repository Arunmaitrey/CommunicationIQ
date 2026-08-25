"""The narration providers: the real one (Anthropic over httpx) and echo.

httpx rather than a vendor SDK, for two reasons that matter here: it is already
a dependency, so nothing new ships to production; and the base URL is a setting,
so the exact same real code path can be pointed at a stand-in endpoint that
speaks the Messages API for an end-to-end test without a live key.

echo is a local, no-network provider that returns a valid grounded draft from
the evidence. It is the default in tests and a fallback *provider selection*
for a developer with no key — it is never what a failed Anthropic call silently
becomes. A failed real call is a visible failed/retrying job, not echo output.
"""
from __future__ import annotations

import json
import time

import httpx

from app.config import settings
from app.narration.contract import (FeedbackNarratorProvider, NarrationDraft,
                                    NarrationEvidence, NarratorError)
from app.narration import prompt as prompt_mod


class AnthropicNarrator:
    """Calls the Anthropic Messages API. contract_version 1.0."""

    contract_version = "1.0"
    provider_key = "anthropic"

    def __init__(self) -> None:
        self.model_version = settings.narration_model
        self._url = settings.anthropic_base_url.rstrip("/") + "/v1/messages"
        self._key = settings.anthropic_api_key

    async def narrate(self, evidence: NarrationEvidence, *,
                      timeout_s: float) -> NarrationDraft:
        if not self._key:
            # Not retryable: retrying a missing key wastes attempts and hides
            # the real fix. It surfaces as a terminal config failure.
            raise NarratorError("config", "ANTHROPIC_API_KEY is not set")

        body = {
            "model": self.model_version,
            "max_tokens": settings.narration_max_output_tokens,
            "system": prompt_mod.SYSTEM,
            "messages": [{"role": "user",
                          "content": prompt_mod.user_message(evidence)}],
        }
        headers = {
            "x-api-key": self._key,
            "anthropic-version": settings.anthropic_version,
            "content-type": "application/json",
        }

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(self._url, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise NarratorError("transient", type(exc).__name__) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code == 429:
            raise NarratorError("transient", "rate limited (429)")
        if resp.status_code >= 500:
            raise NarratorError("transient", f"provider {resp.status_code}")
        if resp.status_code >= 400:
            raise NarratorError("bad_request", f"provider {resp.status_code}")

        data = resp.json()
        if data.get("stop_reason") == "refusal" or data.get("type") == "error":
            raise NarratorError("refused", "content policy refusal")

        text = _first_text(data)
        if not text:
            raise NarratorError("invalid_response", "empty completion")
        parsed = _parse_json(text)

        usage = data.get("usage") or {}
        return NarrationDraft(
            headline=str(parsed.get("headline", "")),
            summary=str(parsed.get("summary", "")),
            primary_focus=str(parsed.get("primary_focus", "")),
            practice_action=str(parsed.get("practice_action", "")),
            caveats=list(parsed.get("caveats", []) or []),
            model_version=data.get("model", self.model_version),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            latency_ms=latency_ms,
        )


class OpenSourceNarrator:
    """An OpenAI-compatible chat-completions provider. contract_version 1.0.

    The same FeedbackNarratorProvider contract as Anthropic — it takes the same
    NarrationEvidence, uses the same system prompt and grounding rules, and
    returns a NarrationDraft the same validator judges. The only thing that
    differs from AnthropicNarrator is the wire format: POST {base_url}/chat/
    completions with a system+user message pair, the OpenAI response shape.

    Works unchanged against vLLM, Ollama, TGI, llama.cpp server and LM Studio,
    because they all speak this interface. api_key is optional: a local server
    needs none, a hosted one gets a bearer header.
    """

    contract_version = "1.0"
    provider_key = "opensource"

    def __init__(self) -> None:
        self.model_version = settings.oss_model
        self._url = settings.oss_base_url.rstrip("/") + "/chat/completions"
        self._key = settings.oss_api_key

    async def narrate(self, evidence: NarrationEvidence, *,
                      timeout_s: float) -> NarrationDraft:
        body = {
            "model": self.model_version,
            "max_tokens": settings.narration_max_output_tokens,
            "temperature": settings.oss_temperature,
            "messages": [
                {"role": "system", "content": prompt_mod.SYSTEM},
                {"role": "user", "content": prompt_mod.user_message(evidence)},
            ],
            # Ask for JSON where the server supports it; harmless where it does
            # not, and the parser tolerates a fenced or bare object regardless.
            "response_format": {"type": "json_object"},
        }
        headers = {"content-type": "application/json"}
        if self._key:
            headers["authorization"] = f"Bearer {self._key}"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(self._url, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise NarratorError("transient", type(exc).__name__) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code == 429:
            raise NarratorError("transient", "rate limited (429)")
        if resp.status_code >= 500:
            raise NarratorError("transient", f"server {resp.status_code}")
        if resp.status_code >= 400:
            # Some servers reject response_format; retry once without it before
            # giving up, since that is a capability gap, not a bad request.
            if resp.status_code == 400 and "response_format" in body:
                body.pop("response_format")
                try:
                    async with httpx.AsyncClient(timeout=timeout_s) as client:
                        resp = await client.post(self._url, json=body, headers=headers)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    raise NarratorError("transient", type(exc).__name__) from exc
                if resp.status_code >= 400:
                    raise NarratorError("bad_request", f"server {resp.status_code}")
            else:
                raise NarratorError("bad_request", f"server {resp.status_code}")

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise NarratorError("invalid_response", "no choices")
        message = choices[0].get("message") or {}
        if choices[0].get("finish_reason") == "content_filter":
            raise NarratorError("refused", "content filter")
        text = message.get("content") or ""
        if not text:
            raise NarratorError("invalid_response", "empty completion")
        parsed = _parse_json(text)

        usage = data.get("usage") or {}
        return NarrationDraft(
            headline=str(parsed.get("headline", "")),
            summary=str(parsed.get("summary", "")),
            primary_focus=str(parsed.get("primary_focus", "")),
            practice_action=str(parsed.get("practice_action", "")),
            caveats=list(parsed.get("caveats", []) or []),
            model_version=data.get("model", self.model_version),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
        )


class NvidiaNarrator(OpenSourceNarrator):
    """NVIDIA NIM (build.nvidia.com). contract_version 1.0.

    The same OpenAI-compatible chat-completions wire OpenSourceNarrator
    speaks -- NIM implements it -- pointed at NVIDIA's hosted endpoint with
    its own key and model. Kept as its own provider (not "opensource with a
    different URL") so the console can hold both configurations at once and
    switching between them is one dropdown, not re-typing endpoints.

    Configuration (all admin-editable in the platform console):
        nvidia_base_url   default https://integrate.api.nvidia.com/v1
        nvidia_model      default nvidia/llama-3.1-nemotron-70b-instruct
        nvidia_api_key    empty until the operator supplies one
    """

    provider_key = "nvidia"

    def __init__(self) -> None:  # noqa: D107 — contract documented on class
        self.model_version = settings.nvidia_model
        self._url = settings.nvidia_base_url.rstrip("/") + "/chat/completions"
        self._key = settings.nvidia_api_key

    async def narrate(self, evidence, *, timeout_s: float):
        if not self._key:
            # Same rule as Anthropic: a missing key is a terminal config
            # failure the console must surface, not something to retry.
            raise NarratorError("config", "NVIDIA API key is not set "
                                          "(platform console -> AI narration)")
        return await super().narrate(evidence, timeout_s=timeout_s)


class EchoNarrator:
    """A grounded draft built locally from the evidence. No network."""

    contract_version = "1.0"
    provider_key = "echo"

    def __init__(self) -> None:
        self.model_version = "echo-1"

    async def narrate(self, evidence: NarrationEvidence, *,
                      timeout_s: float) -> NarrationDraft:
        a = evidence.attempt
        primary = evidence.primary_diagnosis or {}
        if a.get("has_overall"):
            headline = f"You scored {a['overall']} out of {a['scale'][1]}."
            summary = (f"Your result is {a['band_phrase']}. It reflects several "
                       f"measured areas of your spoken English.")
        else:
            headline = "Your attempt was recorded."
            summary = "An overall score was not produced for this attempt."
        if not a.get("calibrated"):
            summary += " These scores are not yet validated against human raters."

        focus = ("Nothing clearly stands out yet -- a little more evidence "
                 "is needed before one area can be named.")
        action = "Do one short practice session today, then take another attempt."
        if primary.get("status") == "identified" and primary.get("gloss"):
            focus = (f"The area to work on first is {primary['gloss']}, "
                     f"currently {primary.get('score')}.")
            if evidence.recommendations:
                action = evidence.recommendations[0]["advice"]

        caveats = []
        if not a.get("calibrated"):
            caveats.append("Scores are uncalibrated and indicative.")
        if evidence.unscored:
            caveats.append("Some measures were not available and were left out.")

        return NarrationDraft(headline=headline, summary=summary,
                              primary_focus=focus, practice_action=action,
                              caveats=caveats, model_version=self.model_version)


def _first_text(data: dict) -> str:
    for block in data.get("content", []) or []:
        if block.get("type") == "text":
            return block.get("text", "")
    return ""


def _parse_json(text: str) -> dict:
    text = text.strip()
    # Tolerate a fenced block; anything else non-JSON is an invalid response.
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise NarratorError("invalid_response", "no JSON object in completion")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise NarratorError("invalid_response", "unparseable JSON") from exc


def get_narrator(provider_key: str | None = None) -> FeedbackNarratorProvider:
    """Select the configured provider. Refuses an unknown one at config time."""
    key = provider_key or settings.narration_provider
    if key == "anthropic":
        return AnthropicNarrator()
    if key == "nvidia":
        return NvidiaNarrator()
    if key == "opensource":
        return OpenSourceNarrator()
    if key == "echo":
        return EchoNarrator()
    raise NarratorError("config", f"unknown narration provider {key!r}")
