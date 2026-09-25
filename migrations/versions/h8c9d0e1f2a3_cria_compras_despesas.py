"""Create tenant-scoped purchases and enable expense features."""

from alembic import op
import sqlalchemy as sa


revision = "h8c9d0e1f2a3"
down_revision = "g7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _merge_expense_settings(settings, enabled):
    merged = dict(settings or {})
    merged.setdefault("show_expenses", enabled)
    merged.setdefault("show_financial_dashboard", enabled)
    return merged


def upgrade():
    op.create_table(
        "compras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("data_compra", sa.DateTime(), nullable=False),
        sa.Column("fornecedor", sa.String(length=160), nullable=True),
        sa.Column("categoria", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("valor_total", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('pendente', 'pago', 'cancelado')", name="ck_compras_status"),
        sa.CheckConstraint("valor_total >= 0", name="ck_compras_valor_total_nao_negativo"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_compras_organization_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compras_organization_id", "compras", ["organization_id"])
    op.create_index("ix_compras_data_compra", "compras", ["data_compra"])
    op.create_index("ix_compras_status", "compras", ["status"])
    op.create_index("ix_compras_categoria", "compras", ["categoria"])

    op.create_table(
        "compra_itens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("compra_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=160), nullable=False),
        sa.Column("quantidade", sa.Numeric(18, 6), nullable=False),
        sa.Column("unidade", sa.String(length=20), nullable=False),
        sa.Column("preco_unitario", sa.Numeric(18, 6), nullable=False),
        sa.Column("subtotal", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("quantidade > 0", name="ck_compra_itens_quantidade_positiva"),
        sa.CheckConstraint("preco_unitario > 0", name="ck_compra_itens_preco_positivo"),
        sa.CheckConstraint("subtotal >= 0", name="ck_compra_itens_subtotal_nao_negativo"),
        sa.ForeignKeyConstraint(["compra_id"], ["compras.id"], name="fk_compra_itens_compra_id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_compra_itens_organization_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compra_itens_compra_id", "compra_itens", ["compra_id"])
    op.create_index("ix_compra_itens_organization_id", "compra_itens", ["organization_id"])
    op.create_index("ix_compra_itens_nome", "compra_itens", ["nome"])

    organizations = sa.table(
        "organizations",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("settings", sa.JSON()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(organizations.c.id, organizations.c.name, organizations.c.settings)).mappings()
    for row in rows:
        enabled = row["name"] == "Graças na Mesa"
        settings = _merge_expense_settings(row["settings"], enabled)
        connection.execute(
            organizations.update().where(organizations.c.id == row["id"]).values(settings=settings)
        )


def downgrade():
    op.drop_index("ix_compra_itens_nome", table_name="compra_itens")
    op.drop_index("ix_compra_itens_organization_id", table_name="compra_itens")
    op.drop_index("ix_compra_itens_compra_id", table_name="compra_itens")
    op.drop_table("compra_itens")
    op.drop_index("ix_compras_categoria", table_name="compras")
    op.drop_index("ix_compras_status", table_name="compras")
    op.drop_index("ix_compras_data_compra", table_name="compras")
    op.drop_index("ix_compras_organization_id", table_name="compras")
    op.drop_table("compras")
