"""add processing_status to datasets

Revision ID: e5f3c4d6a7b8
Revises: d4a2b3c5e6f7
Create Date: 2026-05-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f3c4d6a7b8'
down_revision: Union[str, None] = 'd4a2b3c5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'datasets',
        sa.Column('processing_status', sa.String(length=32), nullable=False,
                  server_default='pending',
                  comment='预处理状态: pending/processing/completed/failed'),
    )


def downgrade() -> None:
    op.drop_column('datasets', 'processing_status')
