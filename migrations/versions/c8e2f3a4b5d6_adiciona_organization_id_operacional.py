"""Add tenant ownership to operational entities.

Revision ID: c8e2f3a4b5d6
Revises: b7f1d2e3c4a5
"""

from alembic import op
import sqlalchemy as sa


revision = "c8e2f3a4b5d6"
down_revision = "b7f1d2e3c4a5"
branch_labels = None
depends_on = None

TEMPORARY_ORGANIZATION_NAME = "MIGRAÇÃO - organização temporária"


def upgrade():
    for table in ("produtos", "vendedores", "vendas"):
        op.add_column(
            table,
            sa.Column("organization_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            f"ix_{table}_organization_id", table, ["organization_id"]
        )
        op.create_foreign_key(
            f"fk_{table}_organization_id",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
        )

    connection = op.get_bind()
    temporary_organization_id = connection.execute(
        sa.text(
            "SELECT id FROM organizations "
            "WHERE name = :name ORDER BY id LIMIT 1"
        ),
        {"name": TEMPORARY_ORGANIZATION_NAME},
    ).scalar_one_or_none()

    entity_count = connection.execute(
        sa.text(
            "SELECT (SELECT COUNT(*) FROM produtos) + "
            "(SELECT COUNT(*) FROM vendedores) + "
            "(SELECT COUNT(*) FROM vendas)"
        )
    ).scalar_one()

    if entity_count and temporary_organization_id is None:
        raise RuntimeError(
            "A organização temporária de migração não foi encontrada; "
            "não é seguro fazer o backfill operacional."
        )

    if temporary_organization_id is not None:
        for table in ("produtos", "vendedores", "vendas"):
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET organization_id = :organization_id "
                    "WHERE organization_id IS NULL"
                ),
                {"organization_id": temporary_organization_id},
            )

    for table in ("produtos", "vendedores", "vendas"):
        op.alter_column(
            table,
            "organization_id",
            existing_type=sa.Integer(),
            nullable=False,
        )


def downgrade():
    for table in ("vendas", "vendedores", "produtos"):
        op.drop_constraint(f"fk_{table}_organization_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        op.drop_column(table, "organization_id")
