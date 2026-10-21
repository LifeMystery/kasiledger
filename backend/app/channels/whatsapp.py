"""WhatsApp Cloud API (Meta). The developer test number is free for development.

Setup (developers.facebook.com): create an app -> add WhatsApp -> copy the temporary
access token and the phone number ID into .env, add your own number as a test recipient,
and point the webhook at  https://<your-tunnel>/webhooks/whatsapp  with WHATSAPP_VERIFY_TOKEN.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import httpx

from .. import config

GRAPH = "https://graph.facebook.com"


def enabled() -> bool:
    return bool(config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_NUMBER_ID)


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"}


async def send_text(to: str, text: str) -> None:
    url = f"{GRAPH}/{config.WHATSAPP_API_VERSION}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"body": text}}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload, headers=_headers())
        if r.status_code >= 400:
            print(f"[whatsapp] send failed: {r.text}")


async def download(media_id: str, suffix: str) -> Path | None:
    async with httpx.AsyncClient(timeout=60) as client:
        meta = await client.get(f"{GRAPH}/{config.WHATSAPP_API_VERSION}/{media_id}", headers=_headers())
        if meta.status_code >= 400:
            print(f"[whatsapp] media lookup failed: {meta.text}")
            return None
        data = await client.get(meta.json()["url"], headers=_headers())
        out = config.UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
        out.write_bytes(data.content)
        return out


async def handle_webhook(body: dict) -> None:
    from ..services.conversation import handle_incoming

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []) or []:
                address = f"wa:+{msg['from'].lstrip('+')}"
                kind = msg.get("type")
                if kind == "text":
                    await handle_incoming(address, text=msg["text"]["body"])
                elif kind == "audio":
                    path = await download(msg["audio"]["id"], ".ogg")
                    await handle_incoming(address, media_path=path, media_kind="voice")
                elif kind == "image":
                    path = await download(msg["image"]["id"], ".jpg")
                    await handle_incoming(address, media_path=path, media_kind="image",
                                          text=msg["image"].get("caption"))
                elif kind == "interactive":
                    reply = msg["interactive"].get("button_reply") or msg["interactive"].get("list_reply") or {}
                    await handle_incoming(address, text=reply.get("id") or reply.get("title", ""))
