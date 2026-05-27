"""create budgets table

Revision ID: e7c8f4a92d50
Revises: d1e9a2c5b7f3
Create Date: 2026-05-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c8f4a92d50'
down_revision: Union[str, Sequence[str], None] = 'd1e9a2c5b7f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'budgets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['owner_id'], ['users.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['category_id'], ['categories.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'owner_id', 'category_id', name='uq_budgets_owner_category'
        ),
        sa.CheckConstraint('amount > 0', name='ck_budgets_amount_positive'),
    )
    op.create_index(
        op.f('ix_budgets_owner_id'), 'budgets', ['owner_id'], unique=False
    )
    op.create_index(
        op.f('ix_budgets_category_id'), 'budgets', ['category_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_budgets_category_id'), table_name='budgets')
    op.drop_index(op.f('ix_budgets_owner_id'), table_name='budgets')
    op.drop_table('budgets')
