"""REST API used by the dashboard and the built-in phone simulator."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..ai.extractor import get_extractor
from ..ai.ocr import get_ocr
from ..ai.speech import get_speech
from ..channels import outbox, telegram, whatsapp
from ..db import get_db
from ..models import Business, Message, Payment, Transaction
from ..services import ledger
from ..services.conversation import daily_summary_text, handle_incoming
from ..services.report import build_report
from ..services.verification import trust_score

router = APIRouter()


def _business(db: Session, business_id: int) -> Business:
    b = db.get(Business, business_id)
    if not b:
        raise HTTPException(404, "Business not found")
    return b


@router.get("/api/config")
def get_config():
    return {
        "extractor": get_extractor().name,
        "speech": get_speech().name if get_speech().available else "none",
        "ocr": get_ocr().name if get_ocr().available else "none",
        "channels": {"simulator": True, "telegram": telegram.enabled(), "whatsapp": whatsapp.enabled()},
        "tier": "free",
    }


@router.get("/api/businesses")
def list_businesses(db: Session = Depends(get_db)):
    rows = db.scalars(select(Business).where(Business.state == "ready").order_by(Business.id)).all()
    return [ledger.business_to_dict(b) for b in rows]


@router.get("/api/businesses/{business_id}")
def get_business(business_id: int, db: Session = Depends(get_db)):
    b = _business(db, business_id)
    return {**ledger.business_to_dict(b), "today": ledger.day_summary(db, b.id)}


@router.get("/api/businesses/{business_id}/transactions")
def list_transactions(business_id: int, limit: int = 50, include_pending: bool = True, db: Session = Depends(get_db)):
    statuses = ["confirmed", "flagged"] + (["pending"] if include_pending else [])
    rows = db.scalars(
        select(Transaction).where(Transaction.business_id == business_id, Transaction.status.in_(statuses))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc()).limit(min(limit, 500))
    ).all()
    return [ledger.tx_to_dict(t) for t in rows]


@router.get("/api/businesses/{business_id}/trust")
def get_trust(business_id: int, db: Session = Depends(get_db)):
    _business(db, business_id)
    return trust_score(db, business_id)


@router.get("/api/businesses/{business_id}/analytics")
def get_analytics(business_id: int, days: int = 90, db: Session = Depends(get_db)):
    _business(db, business_id)
    return ledger.analytics(db, business_id, days=min(max(days, 7), 365))


@router.get("/api/businesses/{business_id}/report.pdf")
def get_report(business_id: int, db: Session = Depends(get_db)):
    b = _business(db, business_id)
    pdf = build_report(db, b)
    filename = f"{(b.name or 'business').replace(' ', '_')}_verified_report.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.post("/api/businesses/{business_id}/summary")
async def send_summary(business_id: int, db: Session = Depends(get_db)):
    b = _business(db, business_id)
    text = daily_summary_text(db, b)
    await outbox.send_text(b.address, text)
    return {"sent": True, "text": text}


@router.post("/api/businesses/{business_id}/payments/import")
async def import_payments(business_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """CSV with columns: date, amount, provider, reference  (date as YYYY-MM-DD or YYYY-MM-DD HH:MM)."""
    _business(db, business_id)
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    added, skipped = 0, 0
    for row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            when_raw = row.get("date") or row.get("paid_at") or row.get("datetime")
            when = datetime.fromisoformat(when_raw.replace("/", "-"))
            amount = float((row.get("amount") or "0").replace("R", "").replace(" ", "").replace(",", "."))
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        if amount <= 0:
            skipped += 1
            continue
        db.add(Payment(business_id=business_id, paid_at=when, amount=amount,
                       provider=row.get("provider", ""), reference=row.get("reference", "")))
        added += 1
    db.commit()
    return {"added": added, "skipped": skipped}


@router.get("/api/businesses/{business_id}/payments/sample.csv")
def sample_payments_csv(business_id: int):
    sample = "date,amount,provider,reference\n2026-10-01 10:15,45.00,Yoco,TXN001\n2026-10-01 16:40,120.00,SnapScan,TXN002\n"
    return PlainTextResponse(sample, media_type="text/csv")


# ---------------------------------------------------------------- simulator

@router.get("/api/messages")
def list_messages(address: str, limit: int = 100, db: Session = Depends(get_db)):
    rows = db.scalars(select(Message).where(Message.address == address)
                      .order_by(Message.id.desc()).limit(limit)).all()
    return [{"id": m.id, "address": m.address, "direction": m.direction, "text": m.text, "kind": m.kind,
             "media_url": m.media_url, "created_at": m.created_at.isoformat()} for m in reversed(rows)]


@router.post("/api/simulator/send")
async def simulator_send(phone: str = Form(...), text: str = Form(""), file: UploadFile | None = File(None)):
    address = f"sim:{phone.strip()}"
    media_path = None
    media_kind = None
    if file is not None and file.filename:
        suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        media_path = config.UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
        media_path.write_bytes(await file.read())
        media_kind = "image" if (file.content_type or "").startswith("image/") else "voice"
    await handle_incoming(address, text=text or None, media_path=media_path, media_kind=media_kind)
    return {"ok": True}


@router.get("/api/simulator/demo-receipt.png")
def demo_receipt():
    """A sample supplier till slip, so the demo can 'photograph' one without a real slip."""
    from scripts.make_demo_receipt import main as make_receipt

    path = make_receipt(str(config.DATA_DIR / "demo_receipt.png"))
    return Response(path.read_bytes(), media_type="image/png")


@router.post("/api/simulator/reset")
def simulator_reset(phone: str = Form(...), db: Session = Depends(get_db)):
    """Clear the chat history shown for a simulated phone (records are kept)."""
    for m in db.scalars(select(Message).where(Message.address == f"sim:{phone.strip()}")):
        db.delete(m)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- channel webhooks

@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request):
    await telegram.handle_update(await request.json())
    return {"ok": True}


@router.get("/webhooks/whatsapp")
def whatsapp_verify(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == config.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(p.get("hub.challenge", ""))
    raise HTTPException(403, "Verification failed")


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request):
    import asyncio

    body = await request.json()
    asyncio.create_task(whatsapp.handle_webhook(body))  # reply to Meta quickly
    return {"ok": True}
