"""Send messages to whichever channel an address belongs to, and log them.

Address prefixes:  sim: (built-in simulator)  tg: (Telegram)  wa: (WhatsApp Cloud API)
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from ..db import SessionLocal
from ..models import Message
from ..services.events import hub
from . import telegram, whatsapp


def channel_of(address: str) -> str:
    return address.split(":", 1)[0]


def can_message_by_phone(address: str) -> bool:
    """Can we start a chat with a customer just from their phone number on this channel?"""
    return channel_of(address) in ("sim", "wa")


def log_message(address: str, direction: str, text: str, kind: str = "text", media_url: str = "") -> dict:
    with SessionLocal() as db:
        m = Message(address=address, direction=direction, text=text, kind=kind, media_url=media_url)
        db.add(m)
        db.commit()
        event = {"type": "message", "message": {
            "id": m.id, "address": address, "direction": direction, "text": text, "kind": kind,
            "media_url": media_url, "created_at": m.created_at.isoformat()}}
    hub.publish(event)
    return event["message"]


async def send_text(address: str, text: str) -> None:
    log_message(address, "out", text)
    channel, to = address.split(":", 1)
    try:
        if channel == "tg" and telegram.enabled():
            await telegram.send_text(to, text)
        elif channel == "wa" and whatsapp.enabled():
            await whatsapp.send_text(to, text)
    except Exception as exc:  # noqa: BLE001
        print(f"[outbox] failed to send to {address}: {exc}")


async def send_report(address: str, business_id: int, pdf_path: Path) -> None:
    url_path = f"/api/businesses/{business_id}/report.pdf"
    caption = "📄 Your verified business report"
    log_message(address, "out", caption, kind="document", media_url=url_path)
    channel, to = address.split(":", 1)
    try:
        if channel == "tg" and telegram.enabled():
            await telegram.send_document(to, pdf_path, caption)
        elif channel == "wa" and whatsapp.enabled():
            await whatsapp.send_text(to, f"{caption}: {config.PUBLIC_BASE_URL}{url_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[outbox] failed to send report to {address}: {exc}")
