"""add doctor_conclusion, reviewed_by, reviewed_at to appointment_lab_summaries

Revision ID: 004_add_doctor_conclusion
Revises: 003_add_raw_input_json
Create Date: 2026-05-05

Rationale: Let the attending doctor add a short clinical conclusion to the
AI-generated holistic summary without overwriting the AI text.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "004_add_doctor_conclusion"
down_revision = "003_add_raw_input_json"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointment_lab_summaries",
        sa.Column("doctor_conclusion", sa.Text, nullable=True),
    )
    op.add_column(
        "appointment_lab_summaries",
        sa.Column("reviewed_by", PGUUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "appointment_lab_summaries",
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("appointment_lab_summaries", "reviewed_at")
    op.drop_column("appointment_lab_summaries", "reviewed_by")
    op.drop_column("appointment_lab_summaries", "doctor_conclusion")
