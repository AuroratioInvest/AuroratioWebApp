from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketPriceSnapshot(Base):
    """One validated scheduler observation set, shared through PostgreSQL."""

    __tablename__ = "market_price_snapshots"
    __table_args__ = (
        CheckConstraint("xau_usd > 0", name="ck_market_price_snapshot_xau_positive"),
        CheckConstraint("xag_usd > 0", name="ck_market_price_snapshot_xag_positive"),
        CheckConstraint("xpt_usd > 0", name="ck_market_price_snapshot_xpt_positive"),
        CheckConstraint("xpd_usd > 0", name="ck_market_price_snapshot_xpd_positive"),
        CheckConstraint("usd_chf > 0", name="ck_market_price_snapshot_usd_chf_positive"),
    )

    source_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    xau_usd: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    xag_usd: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    xpt_usd: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    xpd_usd: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    usd_chf: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
