"""Create VendaItem and migrate legacy single-product sales.

Revision ID: d9f4a5b6c7e8
Revises: c8e2f3a4b5d6
"""

from decimal import Decimal, InvalidOperation

from alembic import op
import sqlalchemy as sa


revision = "d9f4a5b6c7e8"
down_revision = "c8e2f3a4b5d6"
branch_labels = None
depends_on = None


def validate_legacy_values(quantity, total):
    """Validate values before reconstructing a historical unit price."""
    if quantity is None or quantity <= 0:
        raise ValueError("Venda legada possui quantidade nula, zero ou negativa")
    if total is None:
        raise ValueError("Venda legada possui valor_total nulo")
    try:
        return Decimal(str(total)) / Decimal(quantity)
    except (InvalidOperation, ZeroDivisionError) as error:
        raise ValueError("Não foi possível reconstruir o preço unitário") from error


def upgrade():
    op.create_table(
        "venda_itens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("venda_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("produto_id", sa.Integer(), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("preco_unitario", sa.Numeric(18, 6), nullable=False),
        sa.Column("subtotal", sa.Numeric(18, 6), nullable=False),
        sa.CheckConstraint(
            "quantidade > 0", name="ck_venda_item_quantidade_positiva"
        ),
        sa.ForeignKeyConstraint(
            ["venda_id"], ["vendas.id"], name="fk_venda_itens_venda_id"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_venda_itens_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["produto_id"], ["produtos.id"], name="fk_venda_itens_produto_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venda_itens_venda_id", "venda_itens", ["venda_id"])
    op.create_index(
        "ix_venda_itens_organization_id", "venda_itens", ["organization_id"]
    )
    op.create_index("ix_venda_itens_produto_id", "venda_itens", ["produto_id"])

    connection = op.get_bind()
    invalid_values = connection.execute(
        sa.text(
            "SELECT id, quantidade, valor_total FROM vendas "
            "WHERE quantidade IS NULL OR quantidade <= 0 OR valor_total IS NULL "
            "LIMIT 1"
        )
    ).first()
    if invalid_values is not None:
        validate_legacy_values(invalid_values.quantidade, invalid_values.valor_total)

    inconsistent_tenant = connection.execute(
        sa.text(
            "SELECT v.id FROM vendas v "
            "LEFT JOIN produtos p ON p.id = v.produto_id "
            "WHERE p.id IS NULL OR p.organization_id <> v.organization_id "
            "LIMIT 1"
        )
    ).first()
    if inconsistent_tenant is not None:
        raise RuntimeError(
            "Venda legada possui produto inexistente ou de outra organização"
        )

    connection.execute(
        sa.text(
            "INSERT INTO venda_itens "
            "(venda_id, organization_id, produto_id, quantidade, "
            "preco_unitario, subtotal) "
            "SELECT id, organization_id, produto_id, quantidade, "
            "CAST(valor_total AS NUMERIC(18, 6)) / quantidade, "
            "CAST(valor_total AS NUMERIC(18, 6)) "
            "FROM vendas"
        )
    )

    counts = connection.execute(
        sa.text(
            "SELECT "
            "(SELECT COUNT(*) FROM vendas) AS vendas_count, "
            "(SELECT COUNT(*) FROM venda_itens) AS itens_count, "
            "(SELECT COUNT(*) FROM venda_itens WHERE organization_id IS NULL "
            "OR produto_id IS NULL) AS invalid_items"
        )
    ).one()
    if (
        counts.vendas_count != counts.itens_count
        or counts.invalid_items != 0
    ):
        raise RuntimeError("Validação da migração de VendaItem falhou")

    duplicate_or_missing_item = connection.execute(
        sa.text(
            "SELECT v.id FROM vendas v "
            "LEFT JOIN venda_itens i ON i.venda_id = v.id "
            "GROUP BY v.id HAVING COUNT(i.id) <> 1 LIMIT 1"
        )
    ).first()
    if duplicate_or_missing_item is not None:
        raise RuntimeError("Cada Venda legada deve possuir exatamente um VendaItem")

    mismatch = connection.execute(
        sa.text(
            "SELECT v.id FROM vendas v "
            "JOIN venda_itens i ON i.venda_id = v.id "
            "WHERE ABS(CAST(v.valor_total AS NUMERIC(18, 6)) - i.subtotal) > 0.005 "
            "OR i.organization_id <> v.organization_id "
            "OR i.produto_id IS NULL LIMIT 1"
        )
    ).first()
    if mismatch is not None:
        raise RuntimeError("Subtotal ou tenant do item não corresponde à Venda")


def downgrade():
    op.drop_index("ix_venda_itens_produto_id", table_name="venda_itens")
    op.drop_index("ix_venda_itens_organization_id", table_name="venda_itens")
    op.drop_index("ix_venda_itens_venda_id", table_name="venda_itens")
    op.drop_table("venda_itens")
