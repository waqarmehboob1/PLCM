"""add progress column to project table

Revision ID: b7e4a1c2d3f5
Revises: 9c15f8b4c7af
Create Date: 2026-06-21 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e4a1c2d3f5'
down_revision: Union[str, Sequence[str], None] = '9c15f8b4c7af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('project', sa.Column('progress', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('project', 'progress')
