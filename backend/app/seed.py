"""Create realistic demo data:  python -m app.seed

Thandi's Spaza (Soweto)  - 90 days of trading, supplier slips, card/QR payments, confirmed credit
Lerato's Hair Studio     - 3 weeks of records, no payment evidence yet (lower score, for contrast)

WARNING: this deletes the existing database.
"""
from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from . import config
from .db import Base, SessionLocal, engine
from .models import Business, Customer, Payment, Transaction

random.seed(27)

# item: (sell price, cost price, average units per day)
SPAZA_ITEMS = {
    "bread": (18.0, 14.5, 22),
    "milk": (25.0, 18.0, 9),
    "cooldrink": (30.0, 22.0, 8),
    "sugar": (45.0, 38.0, 3),
    "maize meal": (85.0, 70.0, 2.5),
    "eggs": (3.0, 2.2, 18),
    "chips": (8.0, 5.5, 14),
    "sweets": (1.0, 0.6, 35),
    "candles": (5.0, 3.5, 4),
    "paraffin": (25.0, 19.0, 2),
    "airtime": (10.0, 9.5, 6),
}
CUSTOMERS = [("Sipho", "+27821110001"), ("Lerato", "+27821110002"), ("Bongani", "+27821110003"),
             ("Mpho", "+27821110004"), ("Zanele", "+27821110005")]
SUPPLIERS = ["Kasi Cash & Carry", "Jumbo Wholesale Soweto"]
PROVIDERS = ["Yoco", "SnapScan", "Zapper"]


def _day_factor(d: date) -> float:
    f = 1.0
    if d.weekday() >= 5:
        f *= 1.3
    if d.day >= 25 or d.day <= 3:  # month-end pay days
        f *= 1.4
    if 1 <= d.day <= 5:  # grant payment days
        f *= 1.15
    return f * random.uniform(0.85, 1.15)


def _rand_time(d: date, start_h: float = 6.5, end_h: float = 20.5) -> datetime:
    minutes = random.uniform(start_h * 60, end_h * 60)
    return datetime.combine(d, time()) + timedelta(minutes=minutes)


def seed_spaza(db) -> Business:
    today = date.today()
    start = today - timedelta(days=90)
    b = Business(name="Thandi's Spaza", owner_name="Thandi Mokoena", business_type="Spaza shop",
                 location="Orlando East, Soweto", address="sim:+27820000001", state="ready",
                 created_at=datetime.combine(start, time(8, 0)))
    db.add(b)
    db.flush()
    customers = [Customer(business_id=b.id, name=n, phone=p) for n, p in CUSTOMERS]
    db.add_all(customers)
    db.flush()

    # 1. Plan each day's sales
    days = [start + timedelta(days=i) for i in range(91)]  # includes today
    now = datetime.now()
    plan: dict[date, list[tuple[datetime, list[tuple[str, int]]]]] = {}
    for d in days:
        factor = _day_factor(d)
        demand = {k: max(0, round(v[2] * factor * random.uniform(0.8, 1.2))) for k, v in SPAZA_ITEMS.items()}
        baskets = []
        pool = [k for k, q in demand.items() for _ in range(q)]
        random.shuffle(pool)
        while pool:
            size = random.choice([1, 1, 2, 2, 3, 4])
            basket = defaultdict(int)
            for _ in range(min(size, len(pool))):
                basket[pool.pop()] += 1
            when = _rand_time(d)
            if d == today and when > now - timedelta(minutes=5):
                continue  # don't create "future" sales today
            baskets.append((when, list(basket.items())))
        plan[d] = sorted(baskets)

    # 2. Restock every 3 days to cover the next 3 days plus a 10% buffer
    stock: dict[str, float] = defaultdict(float)
    for i, d in enumerate(days):
        if i % 3 == 0:
            window = days[i:i + 3]
            need: dict[str, float] = defaultdict(float)
            for wd in window:
                for _, basket in plan.get(wd, []):
                    for name, q in basket:
                        need[name] += q
            items = []
            for name, (_, cost, _) in SPAZA_ITEMS.items():
                if name == "airtime":
                    continue
                buy = max(0, round(need[name] * 1.15 + 12 - stock[name]))
                if buy:
                    items.append({"name": name, "quantity": float(buy), "unit_price": cost})
                    stock[name] += buy
            if items:
                total = round(sum(it["quantity"] * it["unit_price"] for it in items), 2)
                supplier = random.choice(SUPPLIERS)
                db.add(Transaction(business_id=b.id, type="purchase", items=items, total=total, note=supplier,
                                   source="invoice" if random.random() < 0.75 else "text", status="confirmed",
                                   extractor="seed", raw_text=f"Till slip from {supplier}",
                                   created_at=datetime.combine(d, time(6, random.randint(5, 50)))))
                db.add(Transaction(business_id=b.id, type="expense", items=[{"name": "transport", "quantity": 1,
                                   "unit_price": 40.0}], total=40.0, note="transport", source="text",
                                   status="confirmed", extractor="seed", raw_text="expense taxi 40",
                                   created_at=datetime.combine(d, time(6, 55))))
        if d.day == 1:
            db.add(Transaction(business_id=b.id, type="expense", items=[{"name": "rent", "quantity": 1,
                               "unit_price": 900.0}], total=900.0, note="rent", source="text",
                               status="confirmed", extractor="seed", raw_text="paid rent 900",
                               created_at=datetime.combine(d, time(9, 0))))

        # 3. Record the day's sales; some on credit, some paid by card/QR
        for when, basket in plan.get(d, []):
            items = [{"name": n, "quantity": float(q), "unit_price": SPAZA_ITEMS[n][0]} for n, q in basket]
            for n, q in basket:
                if n != "airtime":
                    stock[n] -= q
            total = round(sum(it["quantity"] * it["unit_price"] for it in items), 2)
            on_credit = random.random() < 0.015 and total >= 15
            customer = random.choice(customers) if on_credit else None
            text = "sale " + ", ".join(f"{it['name']} {it['quantity']:g} {it['unit_price']:g}" for it in items)
            tx = Transaction(business_id=b.id, type="sale", items=items, total=total,
                             source=random.choice(["voice", "voice", "text"]), raw_text=text,
                             status="confirmed", extractor="seed", created_at=when,
                             on_credit=on_credit, customer=customer,
                             credit_confirmed=on_credit and random.random() < 0.85)
            db.add(tx)
            if on_credit and random.random() < 0.8:
                repay_day = when + timedelta(days=random.randint(2, 9), hours=random.randint(0, 5))
                if repay_day < now:
                    db.add(Transaction(business_id=b.id, type="repayment", items=[], total=total,
                                       customer=customer, source="text", status="confirmed", extractor="seed",
                                       raw_text=f"paid {customer.name} {total:g}", created_at=repay_day))
            elif not on_credit and random.random() < 0.42:
                db.add(Payment(business_id=b.id, paid_at=when + timedelta(seconds=40), amount=total,
                               provider=random.choice(PROVIDERS), reference=f"TX{random.randint(100000, 999999)}"))

    # 4. One old entry that was caught by the checks
    flagged_day = today - timedelta(days=37)
    db.add(Transaction(business_id=b.id, type="sale", items=[{"name": "cooldrink", "quantity": 120.0,
                       "unit_price": 30.0}], total=3600.0, source="voice", raw_text="sale cooldrink 120 30",
                       status="flagged", extractor="seed", created_at=datetime.combine(flagged_day, time(19, 12)),
                       flags=[{"code": "stock_mismatch",
                               "message": "Sold 120 cooldrink but recorded purchases only cover 14 in stock"},
                              {"code": "unusual_amount",
                               "message": "R3 600 is 52x this shop's average sale of R69"}]))
    return b


def seed_salon(db) -> Business:
    today = date.today()
    start = today - timedelta(days=21)
    b = Business(name="Lerato's Hair Studio", owner_name="Lerato Dlamini", business_type="Hair salon",
                 location="Tembisa", address="sim:+27820000003", state="ready",
                 created_at=datetime.combine(start, time(9, 0)))
    db.add(b)
    db.flush()
    for i in range(22):
        d = start + timedelta(days=i)
        if d.weekday() == 0 or random.random() < 0.25:
            continue
        for _ in range(random.randint(2, 6)):
            service, price = random.choice([("haircut", 60.0), ("braids", 350.0), ("haircut", 80.0)])
            when = _rand_time(d, 9, 18)
            if when > datetime.now():
                continue
            db.add(Transaction(business_id=b.id, type="sale", items=[{"name": service, "quantity": 1.0,
                               "unit_price": price}], total=price, source="voice", raw_text=f"sale {service} 1 {price:g}",
                               status="confirmed", extractor="seed", created_at=when))
    return b


def main() -> None:
    if config.DATABASE_URL.startswith("sqlite"):
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        spaza = seed_spaza(db)
        salon = seed_salon(db)
        db.commit()
        print(f"Seeded: {spaza.name} (phone {spaza.address[4:]}), {salon.name} (phone {salon.address[4:]})")


if __name__ == "__main__":
    main()
