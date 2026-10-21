"""Checks that make self-reported records trustworthy, and the trust score.

Each check is simple on purpose - easy to explain to judges and lenders.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.lexicon import NON_STOCK_ITEMS
from ..models import Payment, Transaction
from .ledger import counted_transactions, items_ever_purchased, stock_levels


def _rand(v: float) -> str:
    return f"R{v:,.0f}".replace(",", " ")


def check_transaction(db: Session, tx: Transaction) -> list[dict]:
    """Return a list of flags ({code, message}) for a newly confirmed entry."""
    flags: list[dict] = []
    if tx.type != "sale":
        return flags

    # 1. Stock: you can't sell more than you bought
    levels = stock_levels(db, tx.business_id, exclude_id=tx.id)
    purchased = items_ever_purchased(db, tx.business_id)
    for it in tx.items or []:
        name = it.get("name")
        qty = float(it.get("quantity") or 0)
        if not name or name in NON_STOCK_ITEMS or name not in purchased:
            continue
        available = max(levels.get(name, 0), 0)
        if qty > available + 1e-6:
            flags.append({
                "code": "stock_mismatch",
                "message": f"Sold {qty:g} {name} but recorded purchases only cover {available:g} in stock",
            })

    # 2. Unusually large single sale compared with this shop's history
    since = datetime.now() - timedelta(days=30)
    history = [t for t in counted_transactions(db, tx.business_id, since=since, types=("sale",))
               if t.id != tx.id and t.status == "confirmed"]
    if len(history) >= 20:
        avg = mean(t.total for t in history)
        if tx.total > max(5 * avg, 300):
            flags.append({
                "code": "unusual_amount",
                "message": f"{_rand(tx.total)} is {tx.total / avg:.0f}x this shop's average sale of {_rand(avg)}",
            })

    # 3. Day total far above the normal daily takings
    by_day: dict[date, float] = defaultdict(float)
    for t in history:
        by_day[t.created_at.date()] += t.total
    today = tx.created_at.date()
    past_days = {d: v for d, v in by_day.items() if d != today}
    if len(past_days) >= 7:
        avg_day = mean(past_days.values())
        today_total = by_day.get(today, 0) + tx.total
        if today_total > max(3 * avg_day, 500) and not any(f["code"] == "unusual_amount" for f in flags):
            flags.append({
                "code": "unusual_day",
                "message": f"Today's sales of {_rand(today_total)} are {today_total / avg_day:.1f}x the usual {_rand(avg_day)} a day",
            })
    return flags


def trust_score(db: Session, business_id: int, days: int = 90) -> dict:
    since = datetime.combine(date.today() - timedelta(days=days - 1), datetime.min.time())
    txs = counted_transactions(db, business_id, since=since)
    sales = [t for t in txs if t.type == "sale" and t.status == "confirmed"]
    flagged = [t for t in txs if t.status == "flagged"]
    revenue = sum(t.total for t in sales)

    # 1. Trading history: active trading days (60+ in 90 days earns full marks)
    active_days = {t.created_at.date() for t in sales}
    history_pts = min(len(active_days) / 60, 1) * 20

    # 2. Stock-backed: share of item sales covered by recorded supplier purchases
    purchased = items_ever_purchased(db, business_id)
    item_sales = [t for t in sales if t.items]
    backed_value = 0.0
    item_value = 0.0
    for t in item_sales:
        item_value += t.total
        names = [it.get("name") for it in t.items]
        if all(n in NON_STOCK_ITEMS or n in purchased for n in names):
            backed_value += t.total
    stock_ratio = backed_value / item_value if item_value else 0
    stock_pts = stock_ratio * 25

    # 3. Payment-backed: card / QR payments that line up with recorded daily sales
    payments = db.scalars(select(Payment).where(Payment.business_id == business_id, Payment.paid_at >= since)).all()
    pay_day: dict[date, float] = defaultdict(float)
    for p in payments:
        pay_day[p.paid_at.date()] += p.amount
    sales_day: dict[date, float] = defaultdict(float)
    for t in sales:
        sales_day[t.created_at.date()] += t.total
    matched = sum(min(pay_day.get(d, 0), v) for d, v in sales_day.items())
    pay_ratio = matched / revenue if revenue else 0
    pay_pts = min(pay_ratio / 0.4, 1) * 20  # most spaza sales are cash; 40% digital earns full marks

    # 4. Customer-confirmed credit
    credit = [t for t in sales if t.on_credit]
    confirmed_credit = [t for t in credit if t.credit_confirmed]
    credit_ratio = len(confirmed_credit) / len(credit) if credit else None
    credit_pts = credit_ratio * 15 if credit_ratio is not None else 10

    # 5. Clean record: fewer flagged entries is better
    clean_pts = max(20 - 5 * len(flagged), 0)

    score = round(history_pts + stock_pts + pay_pts + credit_pts + clean_pts)
    level = "High" if score >= 75 else "Medium" if score >= 50 else "Low"

    first = min((t.created_at for t in sales), default=None)
    span_days = max((datetime.now() - first).days + 1, 1) if first else 1
    monthly_revenue = revenue / min(span_days, days) * 30 if revenue else 0

    return {
        "score": score,
        "level": level,
        "estimated_monthly_revenue": round(monthly_revenue, 2),
        "period_days": days,
        "revenue_in_period": round(revenue, 2),
        "components": [
            {"key": "history", "label": "Trading history", "points": round(history_pts, 1), "max": 20,
             "detail": f"{len(active_days)} active trading days in the last {days} days"},
            {"key": "stock", "label": "Sales backed by supplier purchases", "points": round(stock_pts, 1), "max": 25,
             "detail": f"{stock_ratio:.0%} of item sales are covered by recorded stock purchases"},
            {"key": "payments", "label": "Card / QR payment evidence", "points": round(pay_pts, 1), "max": 20,
             "detail": f"{pay_ratio:.0%} of sales value matched to imported card/QR payments"},
            {"key": "credit", "label": "Customer-confirmed credit", "points": round(credit_pts, 1), "max": 15,
             "detail": (f"{len(confirmed_credit)} of {len(credit)} credit sales confirmed by the customer"
                        if credit else "No credit sales recorded")},
            {"key": "clean", "label": "Clean record", "points": round(clean_pts, 1), "max": 20,
             "detail": f"{len(flagged)} {'entry' if len(flagged) == 1 else 'entries'} flagged for review"},
        ],
        "flags": [
            {"transaction_id": t.id, "total": t.total, "created_at": t.created_at.isoformat(),
             "raw_text": t.raw_text, "reasons": [f["message"] for f in (t.flags or [])]}
            for t in sorted(flagged, key=lambda t: t.created_at, reverse=True)
        ],
    }
