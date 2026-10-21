"""KasiLedger API.  Run:  uvicorn app.main:app --reload"""
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from . import config
from .channels import outbox, telegram
from .db import SessionLocal, init_db
from .models import Business
from .routers.api import router
from .services.conversation import daily_summary_text
from .services.events import hub


async def daily_summary_loop() -> None:
    """Send every business its daily summary at DAILY_SUMMARY_TIME (HH:MM)."""
    last_sent = None
    while True:
        now = datetime.now()
        if now.strftime("%H:%M") == config.DAILY_SUMMARY_TIME and last_sent != now.date():
            last_sent = now.date()
            with SessionLocal() as db:
                businesses = db.scalars(select(Business).where(Business.state == "ready")).all()
                messages = [(b.address, daily_summary_text(db, b)) for b in businesses]
            for address, text in messages:
                await outbox.send_text(address, text)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    hub.loop = asyncio.get_running_loop()
    tasks = []
    if telegram.enabled() and config.TELEGRAM_MODE == "polling":
        tasks.append(asyncio.create_task(telegram.poll_forever()))
    if config.DAILY_SUMMARY_TIME:
        tasks.append(asyncio.create_task(daily_summary_loop()))
    yield
    for t in tasks:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t


app = FastAPI(title="KasiLedger API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.mount("/media", StaticFiles(directory=config.UPLOAD_DIR), name="media")


@app.get("/")
def root():
    return {"name": "KasiLedger API", "docs": "/docs"}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive pings from the dashboard
    except WebSocketDisconnect:
        hub.disconnect(ws)
