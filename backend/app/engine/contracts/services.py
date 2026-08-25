"""Non-engine pluggable services — same abstraction pattern, same rules.

Notifications and payments sit behind contracts for the same reason the ASR
does: NOTIF-01 and BILL-01 require the channel and the gateway to be swappable
by configuration. Razorpay is Day-1, not Day-only.
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


@dataclass
class PaymentIntent:
    intent_id: str
    amount_paise: int
    currency: str = "INR"
    checkout_url: str = ""
    # Never a card number, never a token that can be replayed. The gateway
    # holds the instrument; we hold a reference (BILL-08).
    provider_ref: str = ""
    extra: dict = field(default_factory=dict)


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
