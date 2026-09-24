from app import db
from datetime import datetime, timezone
from sqlalchemy import event
from sqlalchemy.orm import object_session


class Produto(db.Model):
    __tablename__ = "produtos"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    nome = db.Column(db.String(120), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true(), index=True)

    vendas = db.relationship("Venda", backref="produto", lazy=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    update_at = db.Column(
        db.DateTime, 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<Produto {self.nome}>"



class Vendedor(db.Model):
    __tablename__ = "vendedores"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    nome = db.Column(db.String(120), nullable=False)

    vendas = db.relationship("Venda", backref="vendedor", lazy=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    update_at = db.Column(
        db.DateTime, 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<Vendedor {self.nome}>"



class Venda(db.Model):
    __tablename__ = "vendas"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )

    produto_id = db.Column(
        db.Integer,
        db.ForeignKey("produtos.id"),
        nullable=False
    )

    vendedor_id = db.Column(
        db.Integer,
        db.ForeignKey("vendedores.id"),
        nullable=False
    )

    comprador_nome = db.Column(
        db.String(120),
        nullable=False
    )

    quantidade = db.Column(db.Integer, nullable=False)

    tipo_vendedor = db.Column(
        db.String(50),
        nullable=False
    )

    status_pagamento = db.Column(
        db.String(20),
        nullable=False
    )

    observacao = db.Column(
        db.Text,
        nullable=True
    )

    valor_total = db.Column(
        db.Float,
        nullable=False
    )

    data_venda = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    update_at = db.Column(
        db.DateTime, 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )


    status_entrega = db.Column(db.String(20), default="Pendente")  # "Pendente" ou "Entregue"
    data_entrega = db.Column(db.DateTime, nullable=True)

    items = db.relationship(
        "VendaItem",
        back_populates="venda",
        cascade="all, delete-orphan",
    )

    pagamentos = db.relationship(
        "VendaPagamento",
        back_populates="venda",
        cascade="all, delete-orphan",
    )


    def __repr__(self):
        return f"<Venda {self.id}>"


class VendaItem(db.Model):
    __tablename__ = "venda_itens"
    __table_args__ = (
        db.CheckConstraint("quantidade > 0", name="ck_venda_item_quantidade_positiva"),
    )

    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(
        db.Integer, db.ForeignKey("vendas.id"), nullable=False, index=True
    )
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    produto_id = db.Column(
        db.Integer, db.ForeignKey("produtos.id"), nullable=False, index=True
    )
    quantidade = db.Column(db.Integer, nullable=False)
    preco_unitario = db.Column(db.Numeric(18, 6), nullable=False)
    subtotal = db.Column(db.Numeric(18, 6), nullable=False)

    venda = db.relationship("Venda", back_populates="items")
    produto = db.relationship("Produto")


@event.listens_for(VendaItem, "before_insert")
@event.listens_for(VendaItem, "before_update")
def validate_venda_item_tenant(mapper, connection, target):
    session = object_session(target)
    venda = target.venda or (session.get(Venda, target.venda_id) if session else None)
    produto = target.produto or (session.get(Produto, target.produto_id) if session else None)
    if venda is None or produto is None:
        return
    if target.organization_id != venda.organization_id:
        raise ValueError("VendaItem e Venda devem pertencer à mesma organização")
    if produto.organization_id != target.organization_id:
        raise ValueError("Produto deve pertencer à organização da VendaItem")


class VendaPagamento(db.Model):
    __tablename__ = "venda_pagamentos"
    __table_args__ = (
        db.CheckConstraint(
            "forma_pagamento IN ('pix', 'dinheiro', 'credito', 'debito', 'outro', 'legado')",
            name="ck_venda_pagamento_forma",
        ),
        db.CheckConstraint(
            "status IN ('pendente', 'confirmado', 'cancelado')",
            name="ck_venda_pagamento_status",
        ),
        db.CheckConstraint("valor > 0", name="ck_venda_pagamento_valor_positivo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(
        db.Integer, db.ForeignKey("vendas.id"), nullable=False, index=True
    )
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    forma_pagamento = db.Column(db.String(20), nullable=False)
    valor = db.Column(db.Numeric(18, 6), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pendente")
    observacao = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    venda = db.relationship("Venda", back_populates="pagamentos")


@event.listens_for(VendaPagamento, "before_insert")
@event.listens_for(VendaPagamento, "before_update")
def validate_venda_pagamento_tenant(mapper, connection, target):
    session = object_session(target)
    venda = target.venda or (session.get(Venda, target.venda_id) if session else None)
    if venda is None:
        return
    if target.organization_id != venda.organization_id:
        raise ValueError("Pagamento e Venda devem pertencer à mesma organização")
