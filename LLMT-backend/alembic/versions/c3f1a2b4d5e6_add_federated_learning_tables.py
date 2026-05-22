"""add federated learning tables

Revision ID: c3f1a2b4d5e6
Revises: 0e7223948611
Create Date: 2026-05-22 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f1a2b4d5e6'
down_revision: Union[str, None] = '0e7223948611'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create federated_tasks table
    op.create_table(
        'federated_tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_name', sa.String(length=128), nullable=False),
        sa.Column('task_code', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='created'),
        sa.Column('model_type', sa.String(length=32), server_default='gpt2', nullable=False),
        sa.Column('model_config_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('num_rounds', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('current_round', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('aggregation_strategy', sa.String(length=32), server_default='weighted_fedavg', nullable=False),
        sa.Column('convergence_threshold', sa.Float(), server_default='1e-4', nullable=False),
        sa.Column('enable_dp', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('dp_epsilon', sa.Float(), server_default='8.0'),
        sa.Column('dp_delta', sa.Float(), server_default='1e-5'),
        sa.Column('dp_noise_multiplier', sa.Float(), server_default='1.1'),
        sa.Column('dp_max_grad_norm', sa.Float(), server_default='1.0'),
        sa.Column('config_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('best_loss', sa.Float(), nullable=True),
        sa.Column('final_model_path', sa.String(length=512), nullable=True),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('training_log_json', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('celery_task_id', sa.String(length=128), nullable=True),
        sa.Column('creator_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_federated_tasks_task_name', 'federated_tasks', ['task_name'])
    op.create_index('ix_federated_tasks_task_code', 'federated_tasks', ['task_code'], unique=True)
    op.create_index('ix_federated_tasks_creator_id', 'federated_tasks', ['creator_id'])
    op.create_index('ix_federated_tasks_celery_task_id', 'federated_tasks', ['celery_task_id'])

    # Create federated_participants table
    op.create_table(
        'federated_participants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), server_default='', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
        sa.Column('weight', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('data_size', sa.Integer(), server_default='0', nullable=False),
        sa.Column('local_epochs', sa.Integer(), server_default='1', nullable=False),
        sa.Column('local_batch_size', sa.Integer(), server_default='32', nullable=False),
        sa.Column('local_learning_rate', sa.Float(), server_default='2e-5', nullable=False),
        sa.Column('dataset_id', sa.Integer(), nullable=True),
        sa.Column('last_round_completed', sa.Integer(), nullable=True),
        sa.Column('last_loss', sa.Float(), nullable=True),
        sa.Column('anomaly_score', sa.Float(), nullable=True),
        sa.Column('anomaly_details_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['task_id'], ['federated_tasks.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_federated_participants_task_id', 'federated_participants', ['task_id'])


def downgrade() -> None:
    op.drop_table('federated_participants')
    op.drop_table('federated_tasks')
