"""add signal publications

Revision ID: b8e2f4a6c901
Revises: f4a7b8c9d012
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e2f4a6c901"
down_revision: Union[str, Sequence[str], None] = "f4a7b8c9d012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def portable_enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    op.create_table(
        "subscriber_signals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "status",
            portable_enum(
                "draft",
                "approved",
                "cancelled",
                name="subscriber_signal_status",
            ),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=100), nullable=False),
        sa.Column(
            "direction",
            portable_enum("buy", "sell", name="subscriber_signal_direction"),
            nullable=False,
        ),
        sa.Column("entry", sa.Text(), nullable=False),
        sa.Column("stop_loss", sa.Text(), nullable=False),
        sa.Column("take_profit_targets", sa.JSON(), nullable=False),
        sa.Column("analysis", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_admin_user_id", sa.String(), nullable=True),
        sa.Column("approved_by_admin_user_id", sa.String(), nullable=True),
        sa.Column("cancelled_by_admin_user_id", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(symbol)) > 0",
            name="ck_subscriber_signal_symbol_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(entry)) > 0",
            name="ck_subscriber_signal_entry_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(stop_loss)) > 0",
            name="ck_subscriber_signal_stop_loss_nonempty",
        ),
        sa.CheckConstraint(
            "approved_at IS NULL OR approved_at >= created_at",
            name="ck_subscriber_signal_approved_after_creation",
        ),
        sa.CheckConstraint(
            "cancelled_at IS NULL OR cancelled_at >= created_at",
            name="ck_subscriber_signal_cancelled_after_creation",
        ),
        sa.ForeignKeyConstraint(["approved_by_admin_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["cancelled_by_admin_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_admin_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_subscriber_signals_status",
        "subscriber_signals",
        ["status"],
    )
    op.create_index(
        "ix_subscriber_signals_status_created",
        "subscriber_signals",
        ["status", "created_at"],
    )

    op.create_table(
        "subscriber_signal_plan_targets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("signal_id", sa.String(), nullable=False),
        sa.Column("plan_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["subscriber_signals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "signal_id",
            "plan_id",
            name="uq_subscriber_signal_plan_target_identity",
        ),
        sa.UniqueConstraint(
            "signal_id",
            "plan_id",
            name="uq_subscriber_signal_plan_target",
        ),
    )
    op.create_index(
        "ix_subscriber_signal_plan_targets_plan_id",
        "subscriber_signal_plan_targets",
        ["plan_id"],
    )
    op.create_index(
        "ix_subscriber_signal_plan_targets_signal_id",
        "subscriber_signal_plan_targets",
        ["signal_id"],
    )

    op.create_table(
        "subscriber_signal_publications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("subscriber_signal_id", sa.String(), nullable=False),
        sa.Column("signal_plan_target_id", sa.String(), nullable=False),
        sa.Column("plan_channel_mapping_id", sa.String(), nullable=False),
        sa.Column("subscription_plan_id", sa.String(), nullable=False),
        sa.Column("telegram_channel_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            portable_enum(
                "pending",
                "processing",
                "published",
                "retryable_failure",
                "terminal_failure",
                "cancelled",
                name="signal_publication_status",
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_claim_id", sa.String(length=64), nullable=True),
        sa.Column("provider_message_reference", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_signal_publication_attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "processing_claim_id IS NULL OR length(trim(processing_claim_id)) > 0",
            name="ck_signal_publication_claim_id_nonempty",
        ),
        sa.CheckConstraint(
            "provider_message_reference IS NULL OR length(trim(provider_message_reference)) > 0",
            name="ck_signal_publication_message_reference_nonempty",
        ),
        sa.CheckConstraint(
            "last_error_code IS NULL OR length(trim(last_error_code)) > 0",
            name="ck_signal_publication_error_code_nonempty",
        ),
        sa.CheckConstraint(
            "next_attempt_at IS NULL OR next_attempt_at >= created_at",
            name="ck_signal_publication_next_attempt_after_creation",
        ),
        sa.CheckConstraint(
            "processing_started_at IS NULL OR processing_started_at >= created_at",
            name="ck_signal_publication_processing_after_creation",
        ),
        sa.CheckConstraint(
            "published_at IS NULL OR published_at >= created_at",
            name="ck_signal_publication_published_after_creation",
        ),
        sa.CheckConstraint(
            "failed_at IS NULL OR failed_at >= created_at",
            name="ck_signal_publication_failed_after_creation",
        ),
        sa.ForeignKeyConstraint(["plan_channel_mapping_id"], ["plan_channel_mappings.id"]),
        sa.ForeignKeyConstraint(["subscriber_signal_id"], ["subscriber_signals.id"]),
        sa.ForeignKeyConstraint(["signal_plan_target_id"], ["subscriber_signal_plan_targets.id"]),
        sa.ForeignKeyConstraint(["subscription_plan_id"], ["subscription_plans.id"]),
        sa.ForeignKeyConstraint(["telegram_channel_id"], ["telegram_channels.id"]),
        sa.ForeignKeyConstraint(
            [
                "signal_plan_target_id",
                "subscriber_signal_id",
                "subscription_plan_id",
            ],
            [
                "subscriber_signal_plan_targets.id",
                "subscriber_signal_plan_targets.signal_id",
                "subscriber_signal_plan_targets.plan_id",
            ],
            name="fk_signal_publication_target_identity",
        ),
        sa.ForeignKeyConstraint(
            [
                "plan_channel_mapping_id",
                "subscription_plan_id",
                "telegram_channel_id",
            ],
            [
                "plan_channel_mappings.id",
                "plan_channel_mappings.plan_id",
                "plan_channel_mappings.channel_id",
            ],
            name="fk_signal_publication_mapping_identity",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscriber_signal_id",
            "plan_channel_mapping_id",
            name="uq_signal_publication_signal_mapping",
        ),
    )
    op.create_index(
        "ix_subscriber_signal_publications_plan_channel_mapping_id",
        "subscriber_signal_publications",
        ["plan_channel_mapping_id"],
    )
    op.create_index(
        "ix_subscriber_signal_publications_signal_plan_target_id",
        "subscriber_signal_publications",
        ["signal_plan_target_id"],
    )
    op.create_index(
        "ix_subscriber_signal_publications_subscriber_signal_id",
        "subscriber_signal_publications",
        ["subscriber_signal_id"],
    )
    op.create_index(
        "ix_subscriber_signal_publications_subscription_plan_id",
        "subscriber_signal_publications",
        ["subscription_plan_id"],
    )
    op.create_index(
        "ix_subscriber_signal_publications_telegram_channel_id",
        "subscriber_signal_publications",
        ["telegram_channel_id"],
    )
    op.create_index(
        "ix_subscriber_signal_publications_status",
        "subscriber_signal_publications",
        ["status"],
    )
    op.create_index(
        "ix_subscriber_signal_publications_next_attempt_at",
        "subscriber_signal_publications",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_signal_publications_due",
        "subscriber_signal_publications",
        ["status", "next_attempt_at", "processing_started_at"],
    )
    op.create_index(
        "ix_signal_publications_admin_status",
        "subscriber_signal_publications",
        ["status", "updated_at"],
    )
    op.create_index(
        "ix_signal_publications_signal_status",
        "subscriber_signal_publications",
        ["subscriber_signal_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_signal_publications_signal_status",
        table_name="subscriber_signal_publications",
    )
    op.drop_index(
        "ix_signal_publications_admin_status",
        table_name="subscriber_signal_publications",
    )
    op.drop_index(
        "ix_signal_publications_due",
        table_name="subscriber_signal_publications",
    )
    op.drop_index(
        "ix_subscriber_signal_publications_next_attempt_at",
        table_name="subscriber_signal_publications",
    )
    op.drop_index(
        "ix_subscriber_signal_publications_status",
        table_name="subscriber_signal_publications",
    )
    op.drop_index(
        "ix_subscriber_signal_publications_telegram_channel_id",
        table_name="subscriber_signal_publications",
    )
    op.drop_index(
        "ix_subscriber_signal_publications_subscription_plan_id",
        table_name="subscriber_signal_publications",
    )
    op.drop_index(
        "ix_subscriber_signal_publications_subscriber_signal_id",
        table_name="subscriber_signal_publications",
    )
    op.drop_index(
        "ix_subscriber_signal_publications_signal_plan_target_id",
        table_name="subscriber_signal_publications",
    )
    op.drop_index(
        "ix_subscriber_signal_publications_plan_channel_mapping_id",
        table_name="subscriber_signal_publications",
    )
    op.drop_table("subscriber_signal_publications")
    op.drop_index(
        "ix_subscriber_signal_plan_targets_signal_id",
        table_name="subscriber_signal_plan_targets",
    )
    op.drop_index(
        "ix_subscriber_signal_plan_targets_plan_id",
        table_name="subscriber_signal_plan_targets",
    )
    op.drop_table("subscriber_signal_plan_targets")
    op.drop_index("ix_subscriber_signals_status_created", table_name="subscriber_signals")
    op.drop_index("ix_subscriber_signals_status", table_name="subscriber_signals")
    op.drop_table("subscriber_signals")
