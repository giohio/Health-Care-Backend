"""add payment_status to lab_orders

Revision ID: 005_lab_orders_payment_status
Revises: 004_add_doctor_conclusion
Create Date: 2026-05-07

Rationale: EMR lab order listing expects lab_orders.payment_status. Some existing
DBs were created before this column existed, causing runtime 500 errors.
"""

from alembic import op
import sqlalchemy as sa


revision = "005_lab_orders_payment_status"
down_revision = "004_add_doctor_conclusion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("lab_orders")}

    if "payment_status" not in columns:
        op.add_column(
            "lab_orders",
            sa.Column(
                "payment_status",
                sa.String(length=20),
                nullable=False,
                server_default="UNPAID",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("lab_orders")}

    if "payment_status" in columns:
        op.drop_column("lab_orders", "payment_status")
