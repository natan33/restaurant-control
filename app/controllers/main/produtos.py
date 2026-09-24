from decimal import Decimal, InvalidOperation

from flask import abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.core.tenancy import get_current_organization
from app.models.pages.gerenciamento_vendas import Produto

from . import main


def _admin_required(organization):
    membership = getattr(g, "current_organization_membership", None)
    if membership is None or membership.role != "admin" or membership.user_id != current_user.id:
        abort(403)


def _price(value):
    try:
        price = Decimal(str(value).replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Preço inválido")
    if price <= 0:
        raise ValueError("Preço deve ser maior que zero")
    return price


def _name(value):
    name = " ".join(str(value or "").split())
    if not name:
        raise ValueError("Nome é obrigatório")
    return name


def _duplicate(name, organization, excluded_id=None):
    query = Produto.query.filter(
        Produto.organization_id == organization.id,
        func.lower(Produto.nome) == name.lower(),
    )
    if excluded_id is not None:
        query = query.filter(Produto.id != excluded_id)
    return query.first() is not None


@main.route("/produtos")
@login_required
def produtos():
    organization = get_current_organization()
    search = " ".join(request.args.get("q", "").split())
    query = Produto.query.filter_by(organization_id=organization.id)
    if search:
        query = query.filter(Produto.nome.ilike(f"%{search}%"))
    products = query.order_by(Produto.nome.asc()).all()
    can_manage = getattr(g, "current_organization_membership", None).role == "admin"
    return render_template("base/produtos.html", produtos=products, busca=search, can_manage=can_manage)


@main.route("/produtos/novo", methods=["GET", "POST"])
@login_required
def novo_produto():
    organization = get_current_organization()
    _admin_required(organization)
    if request.method == "POST":
        try:
            name = _name(request.form.get("nome"))
            price = _price(request.form.get("preco"))
            if _duplicate(name, organization):
                raise ValueError("Já existe um produto com esse nome nesta organização")
            product = Produto(organization_id=organization.id, nome=name, preco=price, ativo=request.form.get("ativo") == "on")
            db.session.add(product)
            db.session.commit()
            return redirect(url_for("main.produtos"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
    return render_template("base/produto_form.html", produto=None)


@main.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
@login_required
def editar_produto(produto_id):
    organization = get_current_organization()
    _admin_required(organization)
    product = Produto.query.filter_by(id=produto_id, organization_id=organization.id).first_or_404()
    if request.method == "POST":
        try:
            name = _name(request.form.get("nome"))
            price = _price(request.form.get("preco"))
            if _duplicate(name, organization, product.id):
                raise ValueError("Já existe um produto com esse nome nesta organização")
            product.nome, product.preco = name, price
            product.ativo = request.form.get("ativo") == "on"
            db.session.commit()
            return redirect(url_for("main.produtos"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
    return render_template("base/produto_form.html", produto=product)


@main.route("/produtos/<int:produto_id>/status", methods=["POST"])
@login_required
def alterar_status_produto(produto_id):
    organization = get_current_organization()
    _admin_required(organization)
    product = Produto.query.filter_by(id=produto_id, organization_id=organization.id).first_or_404()
    product.ativo = not product.ativo
    db.session.commit()
    return redirect(url_for("main.produtos"))
