"""phase4 billing columns + billing_events table

Revision ID: c91ee52f4a01
Revises: 7b56e110bec9
Create Date: 2026-05-07 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c91ee52f4a01"
down_revision: str | None = "7b56e110bec9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("stripe_customer_id", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column(
                "subscription_tier",
                sa.String(length=16),
                nullable=False,
                server_default="free",
            )
        )
        batch.add_column(
            sa.Column(
                "subscription_status",
                sa.String(length=32),
                nullable=False,
                server_default="inactive",
            )
        )
        batch.add_column(
            sa.Column(
                "subscription_current_period_end",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch.create_unique_constraint("uq_users_stripe_customer_id", ["stripe_customer_id"])

    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_billing_events_user_id", "billing_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_events_user_id", table_name="billing_events")
    op.drop_table("billing_events")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_stripe_customer_id", type_="unique")
        batch.drop_column("subscription_current_period_end")
        batch.drop_column("subscription_status")
        batch.drop_column("subscription_tier")
        batch.drop_column("stripe_customer_id")
