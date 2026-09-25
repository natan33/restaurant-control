import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import abort, g, jsonify, render_template, request
from flask_login import current_user, login_required

from app import db
from app.core.tenancy import get_current_organization
from app.models.pages.financeiro import (
    COMPRA_CATEGORIAS,
    COMPRA_STATUS,
    COMPRA_UNIDADES,
    Compra,
    CompraItem,
    as_decimal,
)

from . import main


def _expenses_enabled():
    if not g.organization_settings.get("show_expenses", False):
        abort(403)


def _wants_json():
    return request.is_json or request.headers.get("Accept", "").lower() == "application/json"


def _admin_required():
    membership = getattr(g, "current_organization_membership", None)
    if membership is None or membership.role != "admin" or membership.user_id != current_user.id:
        abort(403)


def _payload():
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    data = request.form.to_dict(flat=True)
    raw_items = data.get("items")
    if raw_items:
        try:
            data["items"] = json.loads(raw_items)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("items deve ser uma lista JSON válida") from error
    return data


def _date(value):
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Data da compra inválida") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _items(raw_items, organization_id):
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("A compra deve possuir ao menos um item")
    result = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("Item de compra inválido")
        nome = " ".join(str(raw.get("nome") or "").split())
        if not nome:
            raise ValueError("Nome do material é obrigatório")
        unidade = str(raw.get("unidade") or "").strip().lower()
        if unidade not in COMPRA_UNIDADES:
            raise ValueError("Unidade de compra inválida")
        quantidade = as_decimal(raw.get("quantidade"), "Quantidade")
        preco = as_decimal(raw.get("preco_unitario"), "Preço unitário")
        if quantidade <= 0 or preco <= 0:
            raise ValueError("Quantidade e preço unitário devem ser maiores que zero")
        result.append(CompraItem(
            organization_id=organization_id,
            nome=nome,
            quantidade=quantidade,
            unidade=unidade,
            preco_unitario=preco,
            subtotal=(quantidade * preco).quantize(Decimal("0.000001")),
        ))
    return result


def _apply_payload(purchase, data, organization_id):
    categoria = str(data.get("categoria") or "").strip().lower()
    status = str(data.get("status") or "pendente").strip().lower()
    if categoria not in COMPRA_CATEGORIAS:
        raise ValueError("Categoria de compra inválida")
    if status not in COMPRA_STATUS:
        raise ValueError("Status de compra inválido")
    items = _items(data.get("items"), organization_id)
    purchase.data_compra = _date(data.get("data_compra"))
    purchase.fornecedor = str(data.get("fornecedor") or "").strip() or None
    purchase.categoria = categoria
    purchase.status = status
    purchase.observacao = str(data.get("observacao") or "").strip() or None
    purchase.organization_id = organization_id
    purchase.items = items
    return purchase


def _serialize(purchase):
    return {
        "id": purchase.id,
        "organization_id": purchase.organization_id,
        "data_compra": purchase.data_compra.isoformat(),
        "fornecedor": purchase.fornecedor,
        "categoria": purchase.categoria,
        "status": purchase.status,
        "observacao": purchase.observacao,
        "valor_total": str(purchase.valor_total),
        "items": [{
            "id": item.id,
            "nome": item.nome,
            "quantidade": str(item.quantidade),
            "unidade": item.unidade,
            "preco_unitario": str(item.preco_unitario),
            "subtotal": str(item.subtotal),
        } for item in purchase.items],
    }


def _filters(query, organization_id):
    query = query.filter(Compra.organization_id == organization_id)
    start = request.args.get("data_inicial")
    end = request.args.get("data_final")
    if start:
        query = query.filter(Compra.data_compra >= _date(start))
    if end:
        query = query.filter(Compra.data_compra < _date(end))
    if request.args.get("categoria"):
        query = query.filter(Compra.categoria == request.args["categoria"].strip().lower())
    if request.args.get("fornecedor"):
        query = query.filter(Compra.fornecedor.ilike(f"%{request.args['fornecedor'].strip()}%"))
    if request.args.get("status"):
        query = query.filter(Compra.status == request.args["status"].strip().lower())
    return query


@main.route("/despesas", methods=["GET"])
@login_required
def despesas():
    _expenses_enabled()
    organization = get_current_organization()
    purchases = _filters(Compra.query, organization.id).order_by(Compra.data_compra.desc()).all()
    data = [_serialize(purchase) for purchase in purchases]
    if _wants_json():
        return jsonify(data)
    return render_template("base/despesas.html", despesas=data)


@main.route("/despesas/nova", methods=["GET", "POST"])
@login_required
def nova_despesa():
    _expenses_enabled()
    _admin_required()
    if request.method == "GET":
        return render_template(
            "base/despesa_form.html", compra=None, categorias=COMPRA_CATEGORIAS,
            status=COMPRA_STATUS, unidades=COMPRA_UNIDADES, can_manage=True,
        )
    organization = get_current_organization()
    try:
        purchase = _apply_payload(Compra(), _payload(), organization.id)
        db.session.add(purchase)
        db.session.commit()
        return jsonify(_serialize(purchase)), 201
    except (ValueError, InvalidOperation, TypeError) as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400


@main.route("/despesas/<int:purchase_id>", methods=["GET"])
@login_required
def detalhe_despesa(purchase_id):
    _expenses_enabled()
    organization = get_current_organization()
    purchase = Compra.query.filter_by(id=purchase_id, organization_id=organization.id).first_or_404()
    return jsonify(_serialize(purchase))


@main.route("/despesas/<int:purchase_id>/editar", methods=["GET", "POST"])
@login_required
def editar_despesa(purchase_id):
    _expenses_enabled()
    _admin_required()
    organization = get_current_organization()
    purchase = Compra.query.filter_by(id=purchase_id, organization_id=organization.id).first_or_404()
    if request.method == "GET":
        return render_template(
            "base/despesa_form.html", compra=_serialize(purchase),
            categorias=COMPRA_CATEGORIAS, status=COMPRA_STATUS,
            unidades=COMPRA_UNIDADES, can_manage=True,
        )
    try:
        _apply_payload(purchase, _payload(), organization.id)
        db.session.commit()
        return jsonify(_serialize(purchase))
    except (ValueError, InvalidOperation, TypeError) as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400


@main.route("/despesas/<int:purchase_id>/cancelar", methods=["POST"])
@login_required
def cancelar_despesa(purchase_id):
    _expenses_enabled()
    _admin_required()
    organization = get_current_organization()
    purchase = Compra.query.filter_by(id=purchase_id, organization_id=organization.id).first_or_404()
    purchase.status = "cancelado"
    db.session.commit()
    return jsonify(_serialize(purchase))
