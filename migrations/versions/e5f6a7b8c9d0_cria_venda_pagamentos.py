"""Create payments and migrate legacy paid sales."""

from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d9f4a5b6c7e8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "venda_pagamentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("venda_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("forma_pagamento", sa.String(length=20), nullable=False),
        sa.Column("valor", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "forma_pagamento IN ('pix', 'dinheiro', 'credito', 'debito', 'outro', 'legado')",
            name="ck_venda_pagamento_forma",
        ),
        sa.CheckConstraint("status IN ('pendente', 'confirmado', 'cancelado')", name="ck_venda_pagamento_status"),
        sa.CheckConstraint("valor > 0", name="ck_venda_pagamento_valor_positivo"),
        sa.ForeignKeyConstraint(["venda_id"], ["vendas.id"], name="fk_venda_pagamentos_venda_id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_venda_pagamentos_organization_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venda_pagamentos_venda_id", "venda_pagamentos", ["venda_id"])
    op.create_index("ix_venda_pagamentos_organization_id", "venda_pagamentos", ["organization_id"])
    op.execute(sa.text(
        "INSERT INTO venda_pagamentos "
        "(venda_id, organization_id, forma_pagamento, valor, status, created_at) "
        "SELECT id, organization_id, 'legado', CAST(valor_total AS NUMERIC(18, 6)), "
        "'confirmado', CURRENT_TIMESTAMP FROM vendas WHERE status_pagamento = 'Pago'"
    ))


def downgrade():
    op.drop_index("ix_venda_pagamentos_organization_id", table_name="venda_pagamentos")
    op.drop_index("ix_venda_pagamentos_venda_id", table_name="venda_pagamentos")
    op.drop_table("venda_pagamentos")
