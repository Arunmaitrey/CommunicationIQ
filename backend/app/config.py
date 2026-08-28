"""CommunicationIQ backend settings — loaded from environment / .env.

MongoDB: the control-plane database is
control plane lives in one database (``CommunicationIQ`` by default, taken from
the URI), and every institution gets its *own* database named ``tenant_<slug>``
so tenant isolation is structural, not a filter (TEN-12).
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017/CommunicationIQ"
    mongo_server_selection_timeout_ms: int = 5000

    @property
    def control_db_name(self) -> str:
        """The control-plane database name, taken from the URI path.

        Falls back to ``CommunicationIQ`` when the URI carries no database.
        """
        parsed = urlparse(self.mongo_uri)
        name = parsed.path.lstrip("/").split("?")[0].strip()
        return name or "CommunicationIQ"
    jwt_secret: str = "commiq-dev-secret-do-not-use-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    # NoDecode matters here. Without it pydantic-settings JSON-decodes a
    # complex field inside the settings source, before any validator runs, so
    # CORS_ORIGINS had to be perfect JSON or the process died at startup with
    # "error parsing value for field" and no hint about what it wanted. Every
    # hosting dashboard is a plain text box; expecting brackets and quotes to
    # survive it, typed correctly, is a bad bet to hang a deployment on.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3010", "http://localhost:3000",
        # The same machine by its other name. A browser treats
        # http://127.0.0.1:3010 as a different origin from
        # http://localhost:3010, so a developer who typed the address rather
        # than the name got a CORS refusal -- which the client reports as
        # "Could not reach the server", pointing at the wrong thing entirely.
        # This grants nothing new: both already resolve to this host.
        "http://127.0.0.1:3010", "http://127.0.0.1:3000",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: object) -> list[str]:
        """Accept the shapes people actually type.

            https://app.example.com
            https://app.example.com, https://admin.example.com
            ["https://app.example.com"]

        All three mean the same thing and all three now work. Still an
        explicit allow-list -- "*" is not special-cased, because a wildcard
        would let any site call this API with a signed-in user's credentials.
        """
        if v is None or isinstance(v, list):
            return list(v or [])
        text = str(v).strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"CORS_ORIGINS looks like JSON but will not parse ({exc}). "
                    "A plain comma-separated list works too: "
                    "https://a.example.com, https://b.example.com"
                ) from exc
            return [str(x).strip() for x in loaded if str(x).strip()]
        return [part.strip() for part in text.split(",") if part.strip()]
    app_url: str = "http://localhost:3010"
    port: int = 8010

    # Tenant schemas are named tenant_<slug>; the control plane lives in `public`.
    tenant_schema_prefix: str = "tenant_"

    # Working storage. Student audio, prompt audio and exports all live under
    # MEDIA_ROOT for now; the Storage contract (app/storage) is what makes
    # swapping this for S3-class object storage a config change, not a rewrite.
    media_root: str = "../tmp"
    upload_max_mb: int = 25

    # DPDP: recordings are not kept forever. The sweeper reads this.
    recording_retention_days: int = 30



    # --- AI Feedback Narrator (explains the frozen scores; never computes one) ---
    #
    # The narrator turns the deterministic report into a plain-language
    # explanation. It sits strictly downstream of scoring: it reads a finished
    # result and writes to its own table, and nothing in the scoring path waits
    # on it. Every knob here is about the job, not the score.
    narration_enabled: bool = False
    # Provider selected by config alone; all three satisfy one contract and
    # feed the identical evidence/validation/privacy/retry pipeline.
    #   opensource — a self-hosted OpenAI-compatible server (the default): with
    #                qwen2.5:7b it benchmarked 94% grounded, injection-safe, and
    #                Apache-2.0, and keeps all student data on our own infra.
    #   anthropic  — the commercial fallback option, one env var away.
    #   echo       — local no-network grounded draft, for tests / no-GPU dev.
    # A failed real call becomes a visible failed/retrying job, never echo.
    narration_provider: str = "opensource"
    # Haiku-class is the right tier for a bounded explain task: cheap enough to
    # run on every scored attempt, strong enough to ground faithfully.
    narration_model: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_version: str = "2023-06-01"
    narration_timeout_s: float = 8.0
    narration_max_output_tokens: int = 1024
    narration_prompt_version: str = "1.0"
    # Retry policy for the durable job. Transient failures back off
    # exponentially with jitter, up to the cap, for at most this many attempts;
    # then the row is terminally `failed` and visible to operations.
    narration_max_attempts: int = 5
    narration_backoff_base_s: float = 30.0
    narration_backoff_cap_s: float = 3600.0
    # A `processing` row whose worker died is reclaimable after its lease.
    narration_lease_seconds: int = 120
    # The in-process recovery sweeper. It is the restart-safety net; the
    # BackgroundTask kick is the fast path. Disable to run the CLI worker only.
    narration_worker_enabled: bool = False
    narration_worker_interval_s: float = 15.0
    # How many due jobs one sweeper tick claims per tenant.
    narration_worker_batch: int = 20

    # --- Open-source / self-hosted provider (same contract as Anthropic) ---
    #
    # Set NARRATION_PROVIDER=opensource to route through an OpenAI-compatible
    # inference server (vLLM, Ollama, TGI, llama.cpp server, LM Studio...). The
    # evidence, grounding, validation, privacy, retry and persistence pipeline
    # is identical — only the HTTP shape differs, inside the provider.
    #
    # base_url points at the server's /v1; api_key is optional for a truly
    # local deployment (Ollama needs none). temperature is low by default: this
    # is a faithful-explanation task, not a creative one.
    # NVIDIA NIM (build.nvidia.com) — an OpenAI-compatible endpoint. The key
    # ships empty and is supplied by the operator in the platform console
    # (Providers → AI narration); every field below is admin-configurable at
    # runtime and these are only the defaults.
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    nvidia_api_key: str = ""

    oss_base_url: str = "http://localhost:11434/v1"
    # qwen2.5:7b-instruct: Apache-2.0 (OSI open source, clean to ship), 94%
    # grounded on the benchmark, injection-safe. NOT the 3B, which is under a
    # non-commercial Qwen Research license.
    oss_model: str = "qwen2.5:7b-instruct"
    oss_api_key: str = ""
    oss_temperature: float = 0.2
    # Concurrency ceiling for a self-hosted server, which unlike a commercial
    # API has finite RAM/VRAM and will thrash past its batch capacity.
    oss_max_concurrency: int = 4

    @property
    def media_path(self) -> Path:
        root = Path(self.media_root)
        if not root.is_absolute():
            root = (Path(__file__).resolve().parent.parent / root).resolve()
        return root


settings = Settings()
