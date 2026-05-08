"""add reviewer_doctor_id and required_specialty to lab_results

Revision ID: 001_add_reviewer_routing
Revises:
Create Date: 2026-05-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision = "001_add_reviewer_routing"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lab_results",
        sa.Column("reviewer_doctor_id", PGUUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "lab_results",
        sa.Column("required_specialty", sa.String(50), nullable=True),
    )
    op.create_index(
        "idx_results_reviewer_doctor_id", "lab_results", ["reviewer_doctor_id"]
    )
    op.create_index(
        "idx_results_required_specialty", "lab_results", ["required_specialty"]
    )


def downgrade() -> None:
    op.drop_index("idx_results_required_specialty", table_name="lab_results")
    op.drop_index("idx_results_reviewer_doctor_id", table_name="lab_results")
    op.drop_column("lab_results", "required_specialty")
    op.drop_column("lab_results", "reviewer_doctor_id")
