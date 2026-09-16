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
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    @field_validator("jwt_secret")
    @classmethod
    def _require_jwt_secret(cls, v: str) -> str:
        import os
        if not v or v == "commiq-dev-secret-do-not-use-in-prod":
            env = os.environ.get("JWT_SECRET", "")
            if env:
                return env
            if os.environ.get("ENVIRONMENT", "") == "production":
                raise ValueError("JWT_SECRET must be set in production")
            return "commiq-dev-secret-do-not-use-in-prod"
        return v

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

    # Speech engine model config
    whisper_model: str = "small.en"
    whisper_compute_type: str = "int8"



    # --- AI Feedback Narrator (explains the frozen scores; never computes one) ---
    #
    # (The AI narration and Groq question-generation settings were removed:
    #  scoring and reports are deterministic and open-source only.)

    @property
    def media_path(self) -> Path:
        root = Path(self.media_root)
        if not root.is_absolute():
            root = (Path(__file__).resolve().parent.parent / root).resolve()
        return root


settings = Settings()
