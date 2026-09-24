"""Add lifecycle fields to products."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("produtos", sa.Column("ativo", sa.Boolean(), nullable=True, server_default=sa.true()))
    op.add_column("produtos", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.execute(sa.text("UPDATE produtos SET ativo = TRUE WHERE ativo IS NULL"))
    op.execute(sa.text("UPDATE produtos SET updated_at = COALESCE(update_at, CURRENT_TIMESTAMP) WHERE updated_at IS NULL"))
    op.alter_column("produtos", "ativo", nullable=False, server_default=sa.true())
    op.alter_column("produtos", "updated_at", nullable=False)
    op.create_index("ix_produtos_ativo", "produtos", ["ativo"])


def downgrade():
    op.drop_index("ix_produtos_ativo", table_name="produtos")
    op.drop_column("produtos", "updated_at")
    op.drop_column("produtos", "ativo")
