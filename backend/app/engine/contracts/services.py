"""Non-engine pluggable services — same abstraction pattern, same rules.

Notifications sit behind contracts for the same reason the ASR
does: NOTIF-01 requires the channel to be swappable
by configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class NotificationResult:
    delivered: bool
    channel: str
    provider_message_id: str = ""
    error: str = ""


@runtime_checkable
class NotificationProvider(Protocol):
    """Capability: ``notification``. One implementation per channel."""

    contract_version = "1.0"
    provider_key: str
    version: str
    channel: str  # email | sms | whatsapp | push | in_app

    async def send(self, *, to: str, subject: str, body: str,
                   template: str = "", data: dict | None = None) -> NotificationResult:
        ...


@runtime_checkable
class PaymentProvider(Protocol):
    """Capability: ``payment``."""

    contract_version = "1.0"
    provider_key: str
    version: str

    async def create_intent(self, *, amount_paise: int, currency: str,
                            reference: str, description: str = "") -> PaymentIntent:
        ...

    async def verify_webhook(self, *, payload: bytes, signature: str) -> bool:
        ...
