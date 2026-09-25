from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import event
from sqlalchemy.orm import Session

from app import db


COMPRA_STATUS = ("pendente", "pago", "cancelado")
COMPRA_CATEGORIAS = (
    "ingredientes", "bebidas", "embalagens", "limpeza",
    "transporte", "equipamentos", "outros",
)
COMPRA_UNIDADES = ("kg", "g", "litro", "ml", "unidade", "pacote", "caixa", "outro")
DECIMAL_SCALE = Decimal("0.000001")


def as_decimal(value, label):
    try:
        result = Decimal(str(value)).quantize(DECIMAL_SCALE)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{label} inválido") from error
    if not result.is_finite():
        raise ValueError(f"{label} inválido")
    return result


class Compra(db.Model):
    __tablename__ = "compras"
    __table_args__ = (
        db.CheckConstraint("status IN ('pendente', 'pago', 'cancelado')", name="ck_compras_status"),
        db.CheckConstraint("valor_total >= 0", name="ck_compras_valor_total_nao_negativo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    data_compra = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    fornecedor = db.Column(db.String(160), nullable=True)
    categoria = db.Column(db.String(30), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pendente", index=True)
    observacao = db.Column(db.Text, nullable=True)
    valor_total = db.Column(db.Numeric(18, 6), nullable=False, default=Decimal("0"))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    items = db.relationship("CompraItem", back_populates="compra", cascade="all, delete-orphan")


class CompraItem(db.Model):
    __tablename__ = "compra_itens"
    __table_args__ = (
        db.CheckConstraint("quantidade > 0", name="ck_compra_itens_quantidade_positiva"),
        db.CheckConstraint("preco_unitario > 0", name="ck_compra_itens_preco_positivo"),
        db.CheckConstraint("subtotal >= 0", name="ck_compra_itens_subtotal_nao_negativo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    compra_id = db.Column(db.Integer, db.ForeignKey("compras.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    nome = db.Column(db.String(160), nullable=False, index=True)
    quantidade = db.Column(db.Numeric(18, 6), nullable=False)
    unidade = db.Column(db.String(20), nullable=False)
    preco_unitario = db.Column(db.Numeric(18, 6), nullable=False)
    subtotal = db.Column(db.Numeric(18, 6), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    compra = db.relationship("Compra", back_populates="items")


@event.listens_for(Session, "before_flush")
def validate_and_totalize_compras(session, flush_context, instances):
    purchases = {obj for obj in session.new.union(session.dirty) if isinstance(obj, Compra)}
    items = {obj for obj in session.new.union(session.dirty) if isinstance(obj, CompraItem)}
    purchases.update(item.compra for item in items if item.compra is not None)

    for item in items:
        quantity = as_decimal(item.quantidade, "Quantidade")
        unit_price = as_decimal(item.preco_unitario, "Preço unitário")
        if quantity <= 0:
            raise ValueError("Quantidade deve ser maior que zero")
        if unit_price <= 0:
            raise ValueError("Preço unitário deve ser maior que zero")
        if item.unidade not in COMPRA_UNIDADES:
            raise ValueError("Unidade de compra inválida")
        if item.compra is not None and item.organization_id != item.compra.organization_id:
            raise ValueError("CompraItem e Compra devem pertencer à mesma organização")
        item.quantidade = quantity
        item.preco_unitario = unit_price
        item.subtotal = (quantity * unit_price).quantize(DECIMAL_SCALE)

    for purchase in purchases:
        if purchase.status is None:
            purchase.status = "pendente"
        if purchase.status not in COMPRA_STATUS:
            raise ValueError("Status de compra inválido")
        if purchase.categoria not in COMPRA_CATEGORIAS:
            raise ValueError("Categoria de compra inválida")
        total = sum((as_decimal(item.subtotal, "Subtotal") for item in purchase.items), Decimal("0"))
        purchase.valor_total = total.quantize(DECIMAL_SCALE)
