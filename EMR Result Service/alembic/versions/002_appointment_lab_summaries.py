"""create appointment_lab_summaries table

Revision ID: 002_appointment_lab_summaries
Revises: 001_add_reviewer_routing
Create Date: 2026-05-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision = "002_appointment_lab_summaries"
down_revision = "001_add_reviewer_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "appointment_lab_summaries",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("appointment_id", PGUUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("patient_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("ai_holistic_text", sa.Text, nullable=True),
        sa.Column("total_results", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_appt_summary_patient_id", "appointment_lab_summaries", ["patient_id"])
    op.create_index("idx_appt_summary_status", "appointment_lab_summaries", ["status"])


def downgrade() -> None:
    op.drop_index("idx_appt_summary_status", table_name="appointment_lab_summaries")
    op.drop_index("idx_appt_summary_patient_id", table_name="appointment_lab_summaries")
    op.drop_table("appointment_lab_summaries")
