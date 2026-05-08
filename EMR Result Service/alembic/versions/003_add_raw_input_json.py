"""add raw_input_json to lab_results for retry safety

Revision ID: 003_add_raw_input_json
Revises: 002_appointment_lab_summaries
Create Date: 2026-05-05

Rationale: ai_draft_text is overwritten by the AI pipeline with the analysis text,
which destroys the original manual entries.  raw_input_json stores those entries
permanently so retry-ai always has the data it needs.
"""
from alembic import op
import sqlalchemy as sa

revision = "003_add_raw_input_json"
down_revision = "002_appointment_lab_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lab_results",
        sa.Column("raw_input_json", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lab_results", "raw_input_json")
