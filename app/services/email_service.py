"""Optional SMTP notification layer.

If SMTP is not configured every function becomes a no-op and returns False — the
Telegram flow must keep working regardless.
"""
import smtplib
from email.message import EmailMessage
from typing import List, Optional

import anyio

from app.config.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def is_enabled() -> bool:
    return settings.email_enabled


def _send_sync(to_email: str, subject: str, body: str, html: Optional[str] = None) -> bool:
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    try:
        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
            if settings.SMTP_USE_TLS:
                server.starttls()
        with server:
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception as exc:
        logger.warning("Email send failed: %s", exc.__class__.__name__)
        return False


async def send_email(to_email: str, subject: str, body: str,
                     html: Optional[str] = None) -> bool:
    if not is_enabled():
        logger.debug("SMTP not configured; skipping email to %s", to_email)
        return False
    if not to_email:
        return False
    return await anyio.to_thread.run_sync(_send_sync, to_email, subject, body, html)


async def send_verification_email(to_email: str, full_name: str, link: str) -> bool:
    return await send_email(
        to_email,
        "Verify your Vyapaar-Mitra account",
        f"Hello {full_name},\n\nPlease verify your account:\n{link}\n\n"
        "If you did not sign up, ignore this email.",
    )


async def send_login_alert(to_email: str, full_name: str) -> bool:
    return await send_email(
        to_email, "New login to Vyapaar-Mitra",
        f"Hello {full_name},\n\nA new login to your account was just recorded.\n"
        "If this wasn't you, please change your password.",
    )


async def send_khata_reminder(to_email: str, customer_name: str, shop_name: str,
                              outstanding: float) -> bool:
    return await send_email(
        to_email, f"Payment reminder from {shop_name}",
        f"Dear {customer_name},\n\nYour outstanding amount with {shop_name} is "
        f"Rs. {outstanding:g}.\n\nThank you.",
    )


async def send_demand_report(to_email: str, shop_name: str, report_text: str) -> bool:
    return await send_email(
        to_email, f"Local demand report — {shop_name}",
        f"Hello {shop_name},\n\n{report_text}\n\n— Vyapaar-Mitra",
    )


async def send_request_update(to_email: str, product: str, message: str) -> bool:
    return await send_email(
        to_email, f"Update on your request: {product}", message
    )


async def send_bulk(recipients: List[str], subject: str, body: str) -> int:
    sent = 0
    for address in recipients:
        if await send_email(address, subject, body):
            sent += 1
    return sent
