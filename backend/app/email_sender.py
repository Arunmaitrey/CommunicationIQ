"""Transactional email — system-triggered only.

Emails are never composed or sent by hand from the admin UI. The platform
fires them automatically on real events (student created, first login,
report ready) and this module sends them through the saved SMTP config
(Platform → Email / SMTP). A tenant-specific SMTP row is preferred when the
caller passes ``tenant_id``; otherwise the platform row (``tenant_id: null``)
is used. If no active SMTP configuration exists the send simply reports
``False`` — callers treat that as \"email not configured yet\", never as a
crash.

Templates are built in (``_TEMPLATES``), so sending works without any admin
template management.
"""
from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage

from app.db import control_db


async def _load_smtp(tenant_id: str | None) -> dict | None:
    db = control_db()
    cfg = None
    if tenant_id:
        cfg = await db["smtp_configs"].find_one(
            {"tenant_id": tenant_id, "is_active": True})
    if cfg is None:
        cfg = await db["smtp_configs"].find_one(
            {"tenant_id": None, "is_active": True})
    if cfg is None:
        cfg = await db["smtp_configs"].find_one({"is_active": True})
    if not cfg or not cfg.get("host"):
        return None
    return cfg


def _render(template: str, variables: dict) -> str:
    """Fill {{name}}, {{email}} etc. plus bare {name} placeholders."""
    def _sub(m: re.Match) -> str:
        key = m.group(1).strip()
        return str(variables.get(key, m.group(0)))
    out = re.sub(r"\{\{\s*(\w+)\s*\}\}", _sub, template or "")
    out = re.sub(r"\{\s*(\w+)\s*\}", _sub, out)
    return out


async def send_email(to_email: str, subject: str,
                     body_html: str = "", body_text: str = "",
                     tenant_id: str | None = None,
                     from_name: str | None = None) -> bool:
    """Send one email through the configured SMTP server. Never raises."""
    if not to_email or not subject:
        return False
    try:
        cfg = await _load_smtp(tenant_id)
        if cfg is None:
            return False

        msg = EmailMessage()
        msg["Subject"] = subject
        sender = cfg.get("from_email") or cfg.get("username") or ""
        if not sender:
            return False
        display = from_name or cfg.get("from_name") or "CommunicationIQ"
        msg["From"] = f"{display} <{sender}>"
        msg["To"] = to_email
        if body_text:
            msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        host = cfg.get("host", "")
        port = int(cfg.get("port") or (465 if cfg.get("use_ssl") else 587))
        username = cfg.get("username") or sender
        password = cfg.get("password") or ""
        use_ssl = bool(cfg.get("use_ssl"))
        use_tls = bool(cfg.get("use_tls"))

        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
                if username:
                    server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                if use_tls:
                    server.starttls(context=ssl.create_default_context())
                if username:
                    server.login(username, password)
                server.send_message(msg)
        return True
    except Exception:  # noqa: BLE001 — email must never break the request
        return False


# Built-in templates — system-triggered events, no admin template UI.
_TEMPLATES: dict[str, dict] = {
    "first_login": {
        "subject": "Welcome to CommunicationIQ, {{name}}!",
        "body_html": (
            "<h2>Welcome, {{name}}!</h2>"
            "<p>Your CommunicationIQ account is ready. Start practising to "
            "improve your communication skills.</p>"
            "<p>Login at <a href='{{login_url}}'>CommunicationIQ</a></p>"
        ),
        "body_text": "Welcome, {{name}}! Your account is ready. "
                      "Start practising at {{login_url}}",
    },
    "student_created": {
        "subject": "Your CommunicationIQ account is ready, {{name}}",
        "body_html": (
            "<h2>Hi {{name}}</h2>"
            "<p>Your institution has created a CommunicationIQ account for "
            "you.</p>"
            "<p>Email: <strong>{{email}}</strong></p>"
            "<p>Temporary password: <strong>{{temp_password}}</strong></p>"
            "<p>You will be asked to set a new password on first login.</p>"
            "<p>Login at <a href='{{login_url}}'>CommunicationIQ</a></p>"
        ),
        "body_text": "Hi {{name}}, your institution created a "
                      "CommunicationIQ account for you. Email: {{email}}. "
                      "Temporary password: {{temp_password}}. "
                      "Login at {{login_url}}",
    },
    "report_ready": {
        "subject": "Your exam results are ready, {{name}}",
        "body_html": (
            "<h2>Hi {{name}}</h2>"
            "<p>Your <strong>{{exam_name}}</strong> results are ready. "
            "Score: <strong>{{score}}</strong></p>"
            "<p>View details at <a href='{{report_url}}'>your dashboard</a></p>"
        ),
        "body_text": "Hi {{name}}, your {{exam_name}} results are ready. "
                      "Score: {{score}}. View at {{report_url}}",
    },
    "password_reset": {
        "subject": "Reset your CommunicationIQ password",
        "body_html": (
            "<h2>Password Reset</h2>"
            "<p>Click the link to reset your password: "
            "<a href='{{reset_url}}'>Reset Password</a></p>"
            "<p>This link expires in 1 hour.</p>"
        ),
        "body_text": "Reset your password: {{reset_url}}. "
                      "This link expires in 1 hour.",
    },
}


async def send_template_email(template_key: str, to_email: str,
                              variables: dict | None = None,
                              tenant_id: str | None = None) -> bool:
    """Send a system-triggered email from a built-in template by key."""
    try:
        tpl = _TEMPLATES.get(template_key)
        if tpl is None:
            return False
        vars_ = variables or {}
        subject = _render(tpl.get("subject", ""), vars_)
        html = _render(tpl.get("body_html", ""), vars_)
        text = _render(tpl.get("body_text", ""), vars_)
        return await send_email(to_email=to_email, subject=subject,
                                body_html=html, body_text=text,
                                tenant_id=tenant_id)
    except Exception:  # noqa: BLE001
        return False
