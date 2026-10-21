"""Database tables.

Addresses identify a person on a channel: "sim:+27820000001", "tg:123456789", "wa:27821234567".
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now()


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    owner_name: Mapped[str] = mapped_column(String(120), default="")
    business_type: Mapped[str] = mapped_column(String(80), default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    address: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    # Conversation state: "awaiting_name" | "ready"
    state: Mapped[str] = mapped_column(String(30), default="ready")
    pending_transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="business")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(30), default="")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    # sale | purchase | expense | repayment
    type: Mapped[str] = mapped_column(String(20))
    # [{"name": "bread", "quantity": 3, "unit_price": 18.0}]
    items: Mapped[list] = mapped_column(JSON, default=list)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(String(200), default="")
    # voice | text | invoice | seed
    source: Mapped[str] = mapped_column(String(20), default="text")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    media_path: Mapped[str] = mapped_column(String(300), default="")
    # pending (awaiting owner confirmation) | confirmed | flagged | discarded
    status: Mapped[str] = mapped_column(String(20), default="pending")
    flags: Mapped[list] = mapped_column(JSON, default=list)
    extractor: Mapped[str] = mapped_column(String(30), default="")

    # Credit (sale on account) and repayments
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    on_credit: Mapped[bool] = mapped_column(Boolean, default=False)
    credit_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    confirm_code: Mapped[str] = mapped_column(String(8), default="")
    confirm_address: Mapped[str] = mapped_column(String(80), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)

    business: Mapped[Business] = relationship(back_populates="transactions")
    customer: Mapped[Customer | None] = relationship()


class Payment(Base):
    """Card / QR payment records imported from a payment provider statement (CSV)."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    amount: Mapped[float] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String(40), default="")
    reference: Mapped[str] = mapped_column(String(80), default="")


class Message(Base):
    """Every message in and out, so the dashboard and simulator can show conversations."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(80), index=True)
    direction: Mapped[str] = mapped_column(String(3))  # in | out
    text: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="text")  # text | voice | image | document
    media_url: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
