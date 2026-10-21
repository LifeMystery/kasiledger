"""The chat flow: every incoming message from any channel lands here."""
from __future__ import annotations

import random
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..ai.extractor import ExtractedTransaction, get_extractor, normalise_phone
from ..ai.ocr import get_ocr
from ..ai.speech import get_speech
from ..channels import outbox
from ..db import SessionLocal
from ..models import Business, Customer, Transaction
from . import ledger
from .events import hub
from .report import build_report
from .verification import check_transaction, trust_score

YES = {"1", "yes", "y", "ok", "okay", "yebo", "ewe", "ee", "ja", "save", "correct", "confirm", "👍"}
NO = {"2", "no", "n", "cha", "che", "nee", "aowa", "fix", "wrong", "cancel", "dispute"}
CONFIRM_CODE_RE = re.compile(r"^(?:confirm|yes|yebo|ewe|ok)?\s*(\d{4})$", re.I)
DISPUTE_CODE_RE = re.compile(r"^(?:no|dispute|cha|nee)\s+(\d{4})$", re.I)

HELP = (
    "📒 *KasiLedger* - send entries like this:\n\n"
    "*Sale:*  sale bread 3 18\n"
    "*Several items:*  sale bread 2 18, milk 1 25\n"
    "*Stock bought:*  buy bread 40 14.50  (or send a photo of the till slip)\n"
    "*Expense:*  expense taxi 30\n"
    "*On credit:*  owe Sipho 40 0821234567\n"
    "*Paid back:*  paid Sipho 20\n\n"
    "Commands: *summary*, *stock*, *owed*, *score*, *report*, *undo*, *help*"
)


def _r(v: float) -> str:
    return f"R{v:,.2f}".replace(",", " ").replace(".00", "")


def _describe(tx: Transaction) -> str:
    label = {"sale": "Sale", "purchase": "Stock bought", "expense": "Expense", "repayment": "Paid back"}[tx.type]
    if tx.on_credit:
        label = "Sale on credit"
    parts = []
    for it in tx.items or []:
        q = it.get("quantity") or 1
        price = f" @ {_r(it['unit_price'])}" if it.get("unit_price") else ""
        parts.append(f"{q:g}× {it['name']}{price}")
    lines = [f"*{label}*"]
    if tx.customer:
        lines.append(f"Customer: {tx.customer.name}")
    if parts:
        lines.append(", ".join(parts))
    lines.append(f"Total: *{_r(tx.total)}*")
    return "\n".join(lines)


def _publish_tx(tx: Transaction, event: str = "transaction") -> None:
    hub.publish({"type": event, "transaction": ledger.tx_to_dict(tx)})


async def handle_incoming(address: str, text: str | None = None, media_path: Path | None = None,
                          media_kind: str | None = None) -> None:
    """Entry point for all channels."""
    media_url = f"/media/{media_path.name}" if media_path else ""
    outbox.log_message(address, "in", text or "", kind=media_kind or "text", media_url=media_url)
    with SessionLocal() as db:
        replies = await _route(db, address, (text or "").strip(), media_path, media_kind)
    for to, body in replies:
        if body.startswith("__REPORT__:"):
            business_id = int(body.split(":", 1)[1])
            path = config.DATA_DIR / f"report_{business_id}.pdf"
            with SessionLocal() as db:
                path.write_bytes(build_report(db, db.get(Business, business_id)))
            await outbox.send_report(to, business_id, path)
        else:
            await outbox.send_text(to, body)


Reply = tuple[str, str]


async def _route(db: Session, address: str, text: str, media_path: Path | None, media_kind: str | None) -> list[Reply]:
    low = text.lower()

    # A customer confirming a credit entry with a code: "CONFIRM 4821"
    m = CONFIRM_CODE_RE.match(low) or DISPUTE_CODE_RE.match(low)
    if m and not media_path:
        tx = db.scalars(select(Transaction).where(Transaction.confirm_code == m.group(1),
                                                  Transaction.credit_confirmed.is_(False))).first()
        if tx:
            return _customer_answer(db, tx, address, agree=not DISPUTE_CODE_RE.match(low))

    business = db.scalars(select(Business).where(Business.address == address)).first()

    if business is None:
        # A customer answering a direct confirmation request with just "yes" / "no"
        tx = db.scalars(
            select(Transaction).where(Transaction.confirm_address == address, Transaction.credit_confirmed.is_(False),
                                      Transaction.status.in_(ledger.COUNTED))
            .order_by(Transaction.created_at.desc())
        ).first()
        if tx and (low in YES or low in NO):
            return _customer_answer(db, tx, address, agree=low in YES)
        business = Business(address=address, state="awaiting_name")
        db.add(business)
        db.commit()
        return [(address, "👋 Welcome to *KasiLedger*! I help you keep your business records on your phone "
                          "so you can prove your income and qualify for funding.\n\nWhat is your business called?")]

    if business.state == "awaiting_name":
        if not text:
            return [(address, "Please type your business name to get started.")]
        business.name = text[:120]
        business.state = "ready"
        db.commit()
        hub.publish({"type": "business", "business": ledger.business_to_dict(business)})
        return [(address, f"✅ *{business.name}* is set up!\n\n{HELP}")]

    # Owner confirming or rejecting the entry we just read back
    pending = db.get(Transaction, business.pending_transaction_id) if business.pending_transaction_id else None
    if pending and pending.status == "pending" and not media_path:
        if low in YES:
            return await _confirm(db, business, pending)
        if low in NO:
            pending.status = "discarded"
            business.pending_transaction_id = None
            db.commit()
            _publish_tx(pending, "transaction_updated")
            return [(address, "❌ Not saved. Please send it again, for example: *sale bread 3 18*")]

    # Commands
    if not media_path:
        command_reply = _command(db, business, low)
        if command_reply is not None:
            return command_reply

    # New entry: voice note, photo or text
    source = "text"
    raw = text
    heard = ""
    if media_kind == "voice" and media_path:
        source = "voice"
        transcript = get_speech().transcribe(media_path)
        if not transcript:
            if get_speech().available:
                return [(address, "🎤 Sorry, I couldn't hear that clearly. Please try again or type it, "
                                  "for example: *sale bread 3 18*")]
            return [(address, "🎤 Voice notes are switched off in free mode. Please type it, "
                              "for example: *sale bread 3 18*")]
        raw = transcript
        heard = f'🎤 I heard: "{transcript}"\n\n'

    if media_kind == "image" and media_path:
        return _invoice(db, business, media_path)

    extracted = get_extractor().extract(raw)
    if extracted is None or not extracted.is_complete:
        hint = ""
        if extracted and extracted.total is None:
            hint = "I couldn't find the amount. "
        elif extracted and (extracted.on_credit or extracted.type == "repayment") and not extracted.customer_name:
            hint = "I couldn't find the customer's name. "
        return [(address, f"{heard}🤔 {hint}I didn't understand that.\n\nTry: *sale bread 3 18*  or type *help*")]

    tx = _create_pending(db, business, extracted, source=source, raw_text=raw,
                         media_path=str(media_path) if media_path else "")
    return [(address, f"{heard}✅ Got it:\n{_describe(tx)}\n\nReply *1* to save or *2* to fix")]


def _create_pending(db: Session, business: Business, ex: ExtractedTransaction, source: str, raw_text: str,
                    media_path: str = "", note: str = "") -> Transaction:
    if business.pending_transaction_id:
        old = db.get(Transaction, business.pending_transaction_id)
        if old and old.status == "pending":
            old.status = "discarded"
            _publish_tx(old, "transaction_updated")
    customer = None
    if ex.customer_name:
        customer = db.scalars(select(Customer).where(Customer.business_id == business.id,
                                                     Customer.name == ex.customer_name)).first()
        if customer is None:
            customer = Customer(business_id=business.id, name=ex.customer_name, phone=ex.customer_phone or "")
            db.add(customer)
        elif ex.customer_phone:
            customer.phone = ex.customer_phone
    tx = Transaction(
        business_id=business.id, type=ex.type, items=[i.as_dict() for i in ex.items], total=round(ex.total or 0, 2),
        note=note or ex.note, source=source, raw_text=raw_text, media_path=media_path, status="pending",
        extractor=ex.extractor, on_credit=ex.on_credit, customer=customer,
    )
    db.add(tx)
    db.flush()
    business.pending_transaction_id = tx.id
    db.commit()
    _publish_tx(tx)
    return tx


async def _confirm(db: Session, business: Business, tx: Transaction) -> list[Reply]:
    tx.status = "confirmed"
    business.pending_transaction_id = None
    db.flush()
    flags = check_transaction(db, tx)
    replies: list[Reply] = []
    if flags:
        tx.flags = flags
        tx.status = "flagged"
        reasons = "\n".join(f"• {f['message']}" for f in flags)
        replies.append((business.address, f"⚠️ Saved, but *flagged for review*:\n{reasons}\n\n"
                                          "Flagged entries don't count towards your verified income. "
                                          "If this is real, send a photo of the supplier slip for the stock."))
    else:
        replies.append((business.address, "💾 Saved. Type *summary* to see today's totals."))

    if tx.on_credit and tx.customer:
        tx.confirm_code = f"{random.randint(1000, 9999)}"
        if tx.customer.phone and outbox.can_message_by_phone(business.address):
            customer_address = f"{outbox.channel_of(business.address)}:{normalise_phone(tx.customer.phone)}"
            tx.confirm_address = customer_address
            replies.append((customer_address,
                            f"Hi {tx.customer.name}, *{business.name}* recorded that you owe *{_r(tx.total)}*.\n\n"
                            "Reply *YES* to confirm or *NO* if this is wrong."))
            replies.append((business.address, f"📨 I've asked {tx.customer.name} to confirm the {_r(tx.total)}."))
        else:
            replies.append((business.address,
                            f"📨 Ask {tx.customer.name} to send *CONFIRM {tx.confirm_code}* to this number "
                            "to confirm the credit. Confirmed credit raises your trust score."))
    db.commit()
    _publish_tx(tx, "transaction_updated")
    return replies


def _customer_answer(db: Session, tx: Transaction, address: str, agree: bool) -> list[Reply]:
    business = db.get(Business, tx.business_id)
    name = tx.customer.name if tx.customer else "The customer"
    if agree:
        tx.credit_confirmed = True
        msg_owner = f"✅ {name} confirmed they owe you {_r(tx.total)}."
        msg_customer = "Thank you! ✅ Confirmed."
    else:
        tx.flags = (tx.flags or []) + [{"code": "credit_disputed", "message": f"{name} disputed this credit entry"}]
        tx.status = "flagged"
        msg_owner = f"⚠️ {name} says they don't owe {_r(tx.total)}. The entry is flagged for review."
        msg_customer = "Thanks, we've let the shop know. ❌"
    tx.confirm_address = tx.confirm_address or address
    db.commit()
    _publish_tx(tx, "transaction_updated")
    return [(address, msg_customer), (business.address, msg_owner)]


def _invoice(db: Session, business: Business, path: Path) -> list[Reply]:
    ocr = get_ocr()
    result = ocr.read_invoice(path) if ocr.available else None
    if not result:
        return [(business.address, "🧾 I couldn't read that slip. Take the photo flat, in good light - "
                                   "or type it, for example: *buy bread 40 14.50*")]
    ex = ExtractedTransaction(type="purchase", items=result.items, total=result.total, extractor=f"ocr:{ocr.name}",
                              confidence=0.7)
    tx = _create_pending(db, business, ex, source="invoice", raw_text=result.raw_text[:2000],
                         media_path=str(path), note=result.supplier)
    supplier = f"Supplier: {result.supplier}\n" if result.supplier else ""
    return [(business.address, f"🧾 I read this slip:\n{supplier}{_describe(tx)}\n\nReply *1* to save or *2* to fix")]


def _command(db: Session, business: Business, low: str) -> list[Reply] | None:
    to = business.address
    if low in {"help", "menu", "hi", "hello", "usizo", "thuso", "sawubona", "dumela", "molo", "?"}:
        return [(to, HELP)]
    if low in {"summary", "today", "namhlanje", "kajeno", "vandag", "report today"}:
        return [(to, daily_summary_text(db, business))]
    if low in {"stock", "isitoko", "setoko", "voorraad"}:
        levels = ledger.stock_levels(db, business.id)
        if not levels:
            return [(to, "📦 No stock recorded yet. Send *buy bread 40 14.50* or a photo of a till slip.")]
        lines = [f"{'⚠️ ' if v <= 5 else ''}{k}: {v:g}" for k, v in sorted(levels.items())]
        return [(to, "📦 *Stock on hand* (bought minus sold):\n" + "\n".join(lines))]
    if low in {"owed", "owe", "debts", "who owes", "credit", "izikweletu", "dikoloto"}:
        owed = ledger.outstanding_credit(db, business.id)
        if not owed:
            return [(to, "🙌 Nobody owes you money right now.")]
        lines = [f"{o['customer']}: {_r(o['amount'])}{'' if o['confirmed'] else ' (not confirmed)'}" for o in owed]
        return [(to, f"💳 *Money owed to you:* {_r(sum(o['amount'] for o in owed))}\n" + "\n".join(lines))]
    if low in {"score", "trust", "trust score"}:
        t = trust_score(db, business.id)
        lines = [f"• {c['label']}: {c['points']:g}/{c['max']}" for c in t["components"]]
        return [(to, f"🛡️ *Trust score: {t['score']}/100* ({t['level']})\n"
                     f"Estimated monthly revenue: {_r(t['estimated_monthly_revenue'])}\n\n" + "\n".join(lines))]
    if low in {"report", "pdf", "statement"}:
        return [(to, "⏳ Preparing your verified business report..."), (to, f"__REPORT__:{business.id}")]
    if low == "undo":
        last = db.scalars(select(Transaction).where(Transaction.business_id == business.id,
                                                    Transaction.status.in_(ledger.COUNTED))
                          .order_by(Transaction.created_at.desc())).first()
        if not last or (datetime.now() - last.created_at).total_seconds() > 3600:
            return [(to, "Nothing to undo (only entries from the last hour can be undone).")]
        last.status = "discarded"
        db.commit()
        _publish_tx(last, "transaction_updated")
        return [(to, f"↩️ Removed:\n{_describe(last)}")]
    return None


def daily_summary_text(db: Session, business: Business) -> str:
    s = ledger.day_summary(db, business.id)
    if s["sales_count"] == 0 and s["expenses"] == 0 and s["stock_bought"] == 0:
        return "📊 Nothing recorded today yet. Send a sale like *sale bread 3 18*."
    top = ", ".join(f"{t['name']} ({t['quantity']:g})" for t in s["top_items"]) or "-"
    owed = ledger.outstanding_credit(db, business.id)
    lines = [
        f"📊 *Today at {business.name}*",
        f"Sales: *{_r(s['revenue'])}* ({s['sales_count']} sales)",
        f"Estimated profit: *{_r(s['estimated_profit'])}*",
        f"Expenses: {_r(s['expenses'])}",
        f"Stock bought: {_r(s['stock_bought'])}",
        f"Top sellers: {top}",
    ]
    if s["credit_given"]:
        lines.append(f"Given on credit: {_r(s['credit_given'])}")
    if owed:
        lines.append(f"Total owed to you: {_r(sum(o['amount'] for o in owed))}")
    if s["flagged"]:
        lines.append(f"⚠️ {s['flagged']} entry flagged for review")
    return "\n".join(lines)
