"""Ledger queries: stock, balances, summaries and analytics."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.lexicon import NON_STOCK_ITEMS
from ..models import Business, Customer, Payment, Transaction

COUNTED = ("confirmed", "flagged")  # statuses that are real entries (pending/discarded are not)


def tx_to_dict(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "business_id": tx.business_id,
        "type": tx.type,
        "items": tx.items or [],
        "total": tx.total,
        "note": tx.note,
        "source": tx.source,
        "raw_text": tx.raw_text,
        "status": tx.status,
        "flags": tx.flags or [],
        "extractor": tx.extractor,
        "on_credit": tx.on_credit,
        "credit_confirmed": tx.credit_confirmed,
        "customer": tx.customer.name if tx.customer else None,
        "created_at": tx.created_at.isoformat(),
    }


def business_to_dict(b: Business) -> dict:
    return {
        "id": b.id,
        "name": b.name or "New business",
        "owner_name": b.owner_name,
        "business_type": b.business_type,
        "location": b.location,
        "address": b.address,
        "channel": b.address.split(":", 1)[0],
        "created_at": b.created_at.isoformat(),
    }


def counted_transactions(db: Session, business_id: int, since: datetime | None = None, types=None) -> list[Transaction]:
    q = select(Transaction).where(Transaction.business_id == business_id, Transaction.status.in_(COUNTED))
    if since is not None:
        q = q.where(Transaction.created_at >= since)
    if types:
        q = q.where(Transaction.type.in_(types))
    return list(db.scalars(q.order_by(Transaction.created_at)))


def stock_levels(db: Session, business_id: int, exclude_id: int | None = None) -> dict[str, float]:
    """Units bought minus units sold, per physical item (confirmed entries only)."""
    levels: dict[str, float] = defaultdict(float)
    q = select(Transaction).where(
        Transaction.business_id == business_id,
        Transaction.status == "confirmed",
        Transaction.type.in_(("sale", "purchase")),
    )
    for tx in db.scalars(q):
        if tx.id == exclude_id:
            continue
        sign = 1 if tx.type == "purchase" else -1
        for it in tx.items or []:
            name = it.get("name")
            if name and name not in NON_STOCK_ITEMS:
                levels[name] += sign * float(it.get("quantity") or 0)
    return dict(levels)


def items_ever_purchased(db: Session, business_id: int) -> set[str]:
    names: set[str] = set()
    for tx in counted_transactions(db, business_id, types=("purchase",)):
        names.update(it.get("name") for it in tx.items or [] if it.get("name"))
    return names


def latest_unit_costs(db: Session, business_id: int) -> dict[str, float]:
    costs: dict[str, float] = {}
    for tx in counted_transactions(db, business_id, types=("purchase",)):
        for it in tx.items or []:
            if it.get("name") and it.get("unit_price"):
                costs[it["name"]] = float(it["unit_price"])
    return costs


def outstanding_credit(db: Session, business_id: int) -> list[dict]:
    """What each customer still owes (credit sales minus repayments), and how much of it
    the customer has confirmed. Repayments clear the oldest credit first."""
    credit: dict[int, list[Transaction]] = defaultdict(list)
    repaid: dict[int, float] = defaultdict(float)
    for tx in counted_transactions(db, business_id, types=("sale", "repayment")):
        if tx.customer_id is None or tx.status != "confirmed":
            continue
        if tx.type == "sale" and tx.on_credit:
            credit[tx.customer_id].append(tx)
        elif tx.type == "repayment":
            repaid[tx.customer_id] += tx.total
    out = []
    for cid, entries in credit.items():
        owed = sum(t.total for t in entries) - repaid[cid]
        if owed <= 0.009:
            continue
        # Walk back from the newest entry to find which entries are still unpaid
        remaining, confirmed_amount = owed, 0.0
        for t in sorted(entries, key=lambda t: t.created_at, reverse=True):
            part = min(t.total, remaining)
            if t.credit_confirmed:
                confirmed_amount += part
            remaining -= part
            if remaining <= 0.009:
                break
        c = db.get(Customer, cid)
        out.append({"customer": c.name if c else "?", "amount": round(owed, 2),
                    "confirmed_amount": round(confirmed_amount, 2),
                    "confirmed": confirmed_amount >= owed - 0.009})
    return sorted(out, key=lambda r: -r["amount"])


def day_summary(db: Session, business_id: int, day: date | None = None) -> dict:
    day = day or date.today()
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    txs = [t for t in counted_transactions(db, business_id, since=start) if t.created_at < end]
    costs = latest_unit_costs(db, business_id)
    sales = [t for t in txs if t.type == "sale" and t.status == "confirmed"]
    revenue = sum(t.total for t in sales)
    cogs = 0.0
    item_counts: dict[str, float] = defaultdict(float)
    for t in sales:
        for it in t.items or []:
            q = float(it.get("quantity") or 0)
            item_counts[it["name"]] += q
            cogs += q * costs.get(it["name"], 0)
    expenses = sum(t.total for t in txs if t.type == "expense")
    purchases = sum(t.total for t in txs if t.type == "purchase")
    credit_given = sum(t.total for t in sales if t.on_credit)
    repaid = sum(t.total for t in txs if t.type == "repayment")
    top = sorted(item_counts.items(), key=lambda kv: -kv[1])[:3]
    return {
        "date": day.isoformat(),
        "sales_count": len(sales),
        "revenue": round(revenue, 2),
        "estimated_profit": round(revenue - cogs - expenses, 2),
        "expenses": round(expenses, 2),
        "stock_bought": round(purchases, 2),
        "credit_given": round(credit_given, 2),
        "repaid": round(repaid, 2),
        "top_items": [{"name": n, "quantity": q} for n, q in top],
        "flagged": sum(1 for t in txs if t.status == "flagged"),
    }


def analytics(db: Session, business_id: int, days: int = 90) -> dict:
    today = date.today()
    since = datetime.combine(today - timedelta(days=days - 1), datetime.min.time())
    txs = counted_transactions(db, business_id, since=since)

    daily = {(today - timedelta(days=i)).isoformat(): 0.0 for i in range(days - 1, -1, -1)}
    monthly: dict[str, dict[str, float]] = defaultdict(lambda: {"sales": 0.0, "purchases": 0.0, "expenses": 0.0})
    items: dict[str, dict[str, float]] = defaultdict(lambda: {"quantity": 0.0, "revenue": 0.0})
    for t in txs:
        key = t.created_at.strftime("%Y-%m")
        if t.type == "sale" and t.status == "confirmed":
            daily[t.created_at.date().isoformat()] = daily.get(t.created_at.date().isoformat(), 0) + t.total
            monthly[key]["sales"] += t.total
            for it in t.items or []:
                q = float(it.get("quantity") or 0)
                items[it["name"]]["quantity"] += q
                items[it["name"]]["revenue"] += q * float(it.get("unit_price") or 0)
        elif t.type == "purchase":
            monthly[key]["purchases"] += t.total
        elif t.type == "expense":
            monthly[key]["expenses"] += t.total

    payments = db.scalars(
        select(Payment).where(Payment.business_id == business_id, Payment.paid_at >= since)
    ).all()
    pay_daily: dict[str, float] = defaultdict(float)
    for p in payments:
        pay_daily[p.paid_at.date().isoformat()] += p.amount

    return {
        "daily": [{"date": d, "sales": round(v, 2), "card_qr": round(pay_daily.get(d, 0), 2)} for d, v in daily.items()],
        "monthly": [{"month": k, **{kk: round(vv, 2) for kk, vv in v.items()}} for k, v in sorted(monthly.items())],
        "top_items": sorted(
            ({"name": k, "quantity": round(v["quantity"], 1), "revenue": round(v["revenue"], 2)} for k, v in items.items()),
            key=lambda r: -r["revenue"],
        )[:8],
        "stock": [
            {"name": k, "units": round(v, 1)}
            for k, v in sorted(stock_levels(db, business_id).items(), key=lambda kv: kv[0])
        ],
        "outstanding_credit": outstanding_credit(db, business_id),
    }
