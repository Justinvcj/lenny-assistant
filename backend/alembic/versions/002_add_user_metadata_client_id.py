"""add user_metadata and client_id to sessions

Revision ID: 002_add_user_metadata
Revises: 001_initial_schema
Create Date: 2026-10-11 11:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002_add_user_metadata'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sessions',
        sa.Column('client_id', sa.Text(), nullable=True)
    )
    op.add_column(
        'sessions',
        sa.Column(
            'user_metadata',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False
        )
    )


def downgrade() -> None:
    op.drop_column('sessions', 'user_metadata')
    op.drop_column('sessions', 'client_id')
