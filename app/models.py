from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class InvoiceRecord(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="needs_review", index=True)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    heuristic_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    reviews: Mapped[list["ReviewRecord"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    syncs: Mapped[list["SyncRecord"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class ReviewRecord(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    reviewer: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(32))
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    invoice: Mapped[InvoiceRecord] = relationship(back_populates="reviews")


class SyncRecord(Base):
    __tablename__ = "sync_records"
    __table_args__ = (UniqueConstraint("invoice_id", "provider", name="uq_invoice_provider_sync"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="quickbooks")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    invoice: Mapped[InvoiceRecord] = relationship(back_populates="syncs")


class QuickBooksCredential(Base):
    """Local sandbox token store. Encrypt token columns before any production use."""
    __tablename__ = "quickbooks_credentials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text)
    realm_id: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
