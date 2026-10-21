"""Telegram Bot API - completely free, supports voice notes and photos.

Setup: message @BotFather on Telegram, send /newbot, copy the token into .env.
Polling mode (default) works from your laptop with no public URL.
"""
from __future__ import annotations

import asyncio
import html
import re
import uuid
from pathlib import Path

import httpx

from .. import config

API = "https://api.telegram.org"


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN)


def _to_html(text: str) -> str:
    # WhatsApp-style *bold* -> Telegram HTML
    return re.sub(r"\*(.+?)\*", r"<b>\1</b>", html.escape(text))


async def send_text(chat_id: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{API}/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                              json={"chat_id": chat_id, "text": _to_html(text), "parse_mode": "HTML"})
        if r.status_code >= 400:
            print(f"[telegram] send failed: {r.text}")


async def send_document(chat_id: str, path: Path, caption: str = "") -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        with open(path, "rb") as fh:
            r = await client.post(
                f"{API}/bot{config.TELEGRAM_BOT_TOKEN}/sendDocument",
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (path.name, fh, "application/pdf")},
            )
        if r.status_code >= 400:
            print(f"[telegram] document failed: {r.text}")


async def download(file_id: str, suffix: str) -> Path | None:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{API}/bot{config.TELEGRAM_BOT_TOKEN}/getFile", params={"file_id": file_id})
        if r.status_code >= 400:
            return None
        file_path = r.json()["result"]["file_path"]
        data = await client.get(f"{API}/file/bot{config.TELEGRAM_BOT_TOKEN}/{file_path}")
        out = config.UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
        out.write_bytes(data.content)
        return out


async def handle_update(update: dict) -> None:
    from ..services.conversation import handle_incoming

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    address = f"tg:{msg['chat']['id']}"
    if msg.get("text"):
        text = msg["text"]
        if text.strip() == "/start":
            text = "hi"
        await handle_incoming(address, text=text)
    elif msg.get("voice") or msg.get("audio"):
        media = msg.get("voice") or msg.get("audio")
        path = await download(media["file_id"], ".ogg")
        await handle_incoming(address, media_path=path, media_kind="voice")
    elif msg.get("photo"):
        path = await download(msg["photo"][-1]["file_id"], ".jpg")
        await handle_incoming(address, media_path=path, media_kind="image", text=msg.get("caption"))
    elif msg.get("document", {}).get("mime_type", "").startswith("image/"):
        path = await download(msg["document"]["file_id"], ".jpg")
        await handle_incoming(address, media_path=path, media_kind="image", text=msg.get("caption"))


async def poll_forever() -> None:
    """Long-polling loop - no public URL or tunnel needed."""
    base = f"{API}/bot{config.TELEGRAM_BOT_TOKEN}"
    offset = 0
    async with httpx.AsyncClient(timeout=45) as client:
        try:
            await client.post(f"{base}/deleteWebhook")
            me = (await client.get(f"{base}/getMe")).json()
            print(f"[telegram] polling as @{me.get('result', {}).get('username')}")
        except Exception as exc:  # noqa: BLE001
            print(f"[telegram] could not start: {exc}")
        while True:
            try:
                r = await client.get(f"{base}/getUpdates", params={"timeout": 30, "offset": offset})
                for update in r.json().get("result", []):
                    offset = update["update_id"] + 1
                    try:
                        await handle_update(update)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[telegram] error handling update: {exc}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"[telegram] polling error: {exc}")
                await asyncio.sleep(5)
