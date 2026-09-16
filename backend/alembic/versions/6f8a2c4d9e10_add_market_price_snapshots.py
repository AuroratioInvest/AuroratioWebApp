"""add market price snapshots

Revision ID: 6f8a2c4d9e10
Revises: 4d2a7151abb7
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f8a2c4d9e10"
down_revision: Union[str, Sequence[str], None] = "4d2a7151abb7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_price_snapshots",
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("xau_usd", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("xag_usd", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("xpt_usd", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("xpd_usd", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("usd_chf", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("xau_usd > 0", name="ck_market_price_snapshot_xau_positive"),
        sa.CheckConstraint("xag_usd > 0", name="ck_market_price_snapshot_xag_positive"),
        sa.CheckConstraint("xpt_usd > 0", name="ck_market_price_snapshot_xpt_positive"),
        sa.CheckConstraint("xpd_usd > 0", name="ck_market_price_snapshot_xpd_positive"),
        sa.CheckConstraint("usd_chf > 0", name="ck_market_price_snapshot_usd_chf_positive"),
        sa.PrimaryKeyConstraint("source_timestamp"),
    )


def downgrade() -> None:
    op.drop_table("market_price_snapshots")
