"""add celery_task_id to training_tasks

Revision ID: d4a2b3c5e6f7
Revises: c3f1a2b4d5e6
Create Date: 2026-05-22 18:13:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a2b3c5e6f7'
down_revision: Union[str, None] = 'c3f1a2b4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'training_tasks',
        sa.Column('celery_task_id', sa.String(length=128), nullable=True,
                  comment='Celery AsyncResult.id returned by delay()/apply_async()'),
    )
    op.create_index('ix_training_tasks_celery_task_id', 'training_tasks', ['celery_task_id'])


def downgrade() -> None:
    op.drop_index('ix_training_tasks_celery_task_id', table_name='training_tasks')
    op.drop_column('training_tasks', 'celery_task_id')
