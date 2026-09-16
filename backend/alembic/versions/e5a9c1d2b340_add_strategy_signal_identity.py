"""add strategy signal identity

Revision ID: e5a9c1d2b340
Revises: c3d9e1f7a204
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5a9c1d2b340"
down_revision: Union[str, Sequence[str], None] = "c3d9e1f7a204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("subscriber_signals") as batch_op:
        batch_op.add_column(sa.Column("strategy_identifier", sa.String(length=100)))
        batch_op.add_column(sa.Column("strategy_version", sa.String(length=100)))
        batch_op.add_column(sa.Column("strategy_ratio_identifier", sa.String(length=50)))
        batch_op.add_column(sa.Column("strategy_decision_date", sa.String(length=10)))
        batch_op.add_column(sa.Column("strategy_decision_type", sa.String(length=100)))
        batch_op.add_column(sa.Column("strategy_identity", sa.String(length=255)))
        batch_op.create_unique_constraint(
            "uq_subscriber_signal_strategy_identity",
            ["strategy_identity"],
        )
        batch_op.create_check_constraint(
            "ck_subscriber_signal_strategy_identity_nonempty",
            "strategy_identity IS NULL OR length(trim(strategy_identity)) > 0",
        )
        batch_op.create_check_constraint(
            "ck_subscriber_signal_strategy_date_length",
            "strategy_decision_date IS NULL OR length(strategy_decision_date) = 10",
        )
    op.create_index(
        "ix_subscriber_signals_strategy_lookup",
        "subscriber_signals",
        [
            "strategy_identifier",
            "strategy_version",
            "strategy_ratio_identifier",
            "strategy_decision_date",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_subscriber_signals_strategy_lookup", table_name="subscriber_signals")
    with op.batch_alter_table("subscriber_signals") as batch_op:
        batch_op.drop_constraint(
            "ck_subscriber_signal_strategy_date_length",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_subscriber_signal_strategy_identity_nonempty",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_subscriber_signal_strategy_identity",
            type_="unique",
        )
        batch_op.drop_column("strategy_identity")
        batch_op.drop_column("strategy_decision_type")
        batch_op.drop_column("strategy_decision_date")
        batch_op.drop_column("strategy_ratio_identifier")
        batch_op.drop_column("strategy_version")
        batch_op.drop_column("strategy_identifier")
