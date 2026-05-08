"""add pending_booking to triage_sessions

Revision ID: 001_add_pending_booking
Revises:
Create Date: 2026-05-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_add_pending_booking'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'triage_sessions',
        sa.Column('pending_booking', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('triage_sessions', 'pending_booking')
