"""add signal delivery attempt history

Revision ID: c3d9e1f7a204
Revises: b8e2f4a6c901
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d9e1f7a204"
down_revision: Union[str, Sequence[str], None] = "b8e2f4a6c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def portable_enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    with op.batch_alter_table("subscriber_signal_publications") as batch_op:
        batch_op.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("telegram_chat_id", sa.BigInteger()))
        batch_op.add_column(sa.Column("telegram_message_id", sa.BigInteger()))
        batch_op.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("last_error_message", sa.String(length=500)))
        batch_op.create_check_constraint(
            "ck_signal_publication_last_attempt_after_creation",
            "last_attempt_at IS NULL OR last_attempt_at >= created_at",
        )
        batch_op.create_check_constraint(
            "ck_signal_publication_cancelled_after_creation",
            "cancelled_at IS NULL OR cancelled_at >= created_at",
        )
        batch_op.create_check_constraint(
            "ck_signal_publication_error_message_nonempty",
            "last_error_message IS NULL OR length(trim(last_error_message)) > 0",
        )

    op.create_table(
        "subscriber_signal_delivery_attempts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("signal_publication_id", sa.String(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("processing_claim_id", sa.String(length=64), nullable=False),
        sa.Column(
            "outcome",
            portable_enum(
                "processing",
                "delivered",
                "transient_failure",
                "permanent_failure",
                "abandoned",
                name="signal_delivery_attempt_outcome",
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("telegram_chat_id", sa.BigInteger()),
        sa.Column("telegram_message_id", sa.BigInteger()),
        sa.Column("provider_message_reference", sa.String(length=255)),
        sa.Column("error_code", sa.String(length=100)),
        sa.Column("error_message", sa.String(length=500)),
        sa.Column("is_retryable", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_number > 0",
            name="ck_signal_delivery_attempt_number_positive",
        ),
        sa.CheckConstraint(
            "length(trim(processing_claim_id)) > 0",
            name="ck_signal_delivery_attempt_claim_nonempty",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_signal_delivery_attempt_completed_after_start",
        ),
        sa.CheckConstraint(
            "provider_message_reference IS NULL OR length(trim(provider_message_reference)) > 0",
            name="ck_signal_delivery_attempt_reference_nonempty",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR length(trim(error_code)) > 0",
            name="ck_signal_delivery_attempt_error_code_nonempty",
        ),
        sa.CheckConstraint(
            "error_message IS NULL OR length(trim(error_message)) > 0",
            name="ck_signal_delivery_attempt_error_message_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["signal_publication_id"],
            ["subscriber_signal_publications.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "signal_publication_id",
            "attempt_number",
            name="uq_signal_delivery_attempt_number",
        ),
        sa.UniqueConstraint(
            "signal_publication_id",
            "processing_claim_id",
            name="uq_signal_delivery_attempt_claim",
        ),
    )
    op.create_index(
        "ix_subscriber_signal_delivery_attempts_signal_publication_id",
        "subscriber_signal_delivery_attempts",
        ["signal_publication_id"],
    )
    op.create_index(
        "ix_subscriber_signal_delivery_attempts_outcome",
        "subscriber_signal_delivery_attempts",
        ["outcome"],
    )
    op.create_index(
        "ix_signal_delivery_attempts_publication_started",
        "subscriber_signal_delivery_attempts",
        ["signal_publication_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_signal_delivery_attempts_publication_started",
        table_name="subscriber_signal_delivery_attempts",
    )
    op.drop_index(
        "ix_subscriber_signal_delivery_attempts_outcome",
        table_name="subscriber_signal_delivery_attempts",
    )
    op.drop_index(
        "ix_subscriber_signal_delivery_attempts_signal_publication_id",
        table_name="subscriber_signal_delivery_attempts",
    )
    op.drop_table("subscriber_signal_delivery_attempts")

    with op.batch_alter_table("subscriber_signal_publications") as batch_op:
        batch_op.drop_constraint(
            "ck_signal_publication_error_message_nonempty",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_signal_publication_cancelled_after_creation",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_signal_publication_last_attempt_after_creation",
            type_="check",
        )
        batch_op.drop_column("last_error_message")
        batch_op.drop_column("cancelled_at")
        batch_op.drop_column("telegram_message_id")
        batch_op.drop_column("telegram_chat_id")
        batch_op.drop_column("last_attempt_at")
