"""Outbound email over each institution's configured SMTP settings.

Referenced by ``routers/auth.py`` (first-login welcome email) and
``routers/platform_writes.py`` (the SMTP test button and template-based
notifications) but excluded by ``.gitignore`` -- both call sites import it
lazily inside a function, so the app still starts, but every path through
them raised ``ModuleNotFoundError`` the moment it ran.

Institution-specific configuration wins over the global default, matching
how ``ProviderConfig`` resolution already works elsewhere in this codebase.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.models.platform import EmailTemplate, SmtpConfig

log = logging.getLogger(__name__)


async def _config_for(tenant_id: str | None) -> SmtpConfig | None:
    if tenant_id:
        row = await SmtpConfig.find_one(SmtpConfig.tenant_id == tenant_id,
                                        SmtpConfig.is_active == True)  # noqa: E712
        if row is not None:
            return row
    return await SmtpConfig.find_one(SmtpConfig.tenant_id == None,  # noqa: E711
                                     SmtpConfig.is_active == True)  # noqa: E712


def _send_sync(config: SmtpConfig, to_email: str, subject: str,
               body_html: str, body_text: str) -> None:
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{config.from_name} <{config.from_email}>" if config.from_name else config.from_email
    message["To"] = to_email
    message.attach(MIMEText(body_text or "", "plain"))
    message.attach(MIMEText(body_html or body_text or "", "html"))

    if config.use_ssl:
        smtp = smtplib.SMTP_SSL(config.host, config.port, timeout=10)
    else:
        smtp = smtplib.SMTP(config.host, config.port, timeout=10)
    try:
        if config.use_tls and not config.use_ssl:
            smtp.starttls()
        if config.username:
            smtp.login(config.username, config.password)
        smtp.sendmail(config.from_email, [to_email], message.as_string())
    finally:
        smtp.quit()


async def send_email(*, to_email: str, subject: str, body_html: str = "",
                     body_text: str = "", tenant_id: str | None = None) -> bool:
    """Send one email. Returns whether it went out -- never raises."""
    config = await _config_for(tenant_id)
    if config is None:
        log.warning("no active SMTP configuration for tenant %s", tenant_id)
        return False
    try:
        await asyncio.to_thread(_send_sync, config, to_email, subject,
                                body_html, body_text)
        return True
    except Exception:  # noqa: BLE001
        log.exception("failed to send email to %s", to_email)
        return False


async def send_template_email(template_key: str, to_email: str,
                              context: dict, *,
                              tenant_id: str | None = None) -> bool:
    """Render a stored template and send it. Returns whether it went out."""
    template = await EmailTemplate.find_one(EmailTemplate.key == template_key,
                                            EmailTemplate.is_active == True)  # noqa: E712
    if template is None:
        log.warning("no active email template %r", template_key)
        return False

    def _render(text: str) -> str:
        try:
            return text.format(**context)
        except (KeyError, IndexError):
            # A template referencing a field this call didn't supply should
            # still send -- with the placeholder visible -- rather than
            # silently dropping the whole email.
            return text

    return await send_email(
        to_email=to_email, subject=_render(template.subject),
        body_html=_render(template.body_html),
        body_text=_render(template.body_text), tenant_id=tenant_id,
    )
