from app import db
from datetime import datetime, timezone


class Produto(db.Model):
    __tablename__ = "produtos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    preco = db.Column(db.Float, nullable=False)

    vendas = db.relationship("Venda", backref="produto", lazy=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

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


    def __repr__(self):
        return f"<Venda {self.id}>"