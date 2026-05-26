"""fix enable_dp column type from integer to boolean

Revision ID: f6a5d7b8c9e0
Revises: e5f3c4d6a7b8
Create Date: 2026-05-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a5d7b8c9e0'
down_revision: Union[str, None] = 'e5f3c4d6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE federated_tasks ALTER COLUMN enable_dp DROP DEFAULT")
    op.execute(
        "ALTER TABLE federated_tasks ALTER COLUMN enable_dp TYPE boolean USING enable_dp::int::boolean"
    )
    op.execute("ALTER TABLE federated_tasks ALTER COLUMN enable_dp SET DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE federated_tasks ALTER COLUMN enable_dp DROP DEFAULT")
    op.execute(
        "ALTER TABLE federated_tasks ALTER COLUMN enable_dp TYPE integer USING enable_dp::boolean::int"
    )
    op.execute("ALTER TABLE federated_tasks ALTER COLUMN enable_dp SET DEFAULT 1")
