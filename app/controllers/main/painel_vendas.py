from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import time

from flask import abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import login_required
import pandas as pd
from io import BytesIO
from sqlalchemy import case, func

from app.controllers.forms.venda_form import VendaForm
from app.models.pages.gerenciamento_vendas import Produto, Venda, VendaItem, VendaPagamento, Vendedor
from app.core.tenancy import get_current_organization

from datetime import datetime, timedelta
from . import main
from app import db


def _request_items(form):
    payload = request.get_json(silent=True)
    raw_items = payload.get("items") if isinstance(payload, dict) else None
    if raw_items is None:
        raw_items = request.form.get("items")
        if raw_items:
            try:
                raw_items = json.loads(raw_items)
            except (TypeError, json.JSONDecodeError) as error:
                raise ValueError("items deve ser uma lista JSON válida") from error
    if raw_items is None:
        raw_items = [{
            "produto_id": form.produto_id.data,
            "quantidade": form.quantidade.data,
        }]
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Venda deve possuir ao menos um item")

    consolidated = {}
    order = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("Item de venda inválido")
        product_id, quantity = item.get("produto_id"), item.get("quantidade")
        if isinstance(product_id, bool) or isinstance(quantity, bool):
            raise ValueError("Produto e quantidade devem ser válidos")
        try:
            product_id, quantity = int(product_id), int(quantity)
        except (TypeError, ValueError) as error:
            raise ValueError("Produto e quantidade devem ser inteiros") from error
        if product_id <= 0 or quantity <= 0:
            raise ValueError("Produto e quantidade devem ser maiores que zero")
        if product_id not in consolidated:
            consolidated[product_id] = 0
            order.append(product_id)
        consolidated[product_id] += quantity
    return [{"produto_id": product_id, "quantidade": consolidated[product_id]}
            for product_id in order]


def _validate_form_for_items(form, items):
    form.produto_id.data = items[0]["produto_id"]
    form.quantidade.data = items[0]["quantidade"]
    return form.validate()


def _products_for_items(items, organization):
    product_ids = [item["produto_id"] for item in items]
    products = Produto.query.filter(
        Produto.organization_id == organization.id,
        Produto.id.in_(product_ids),
    ).all()
    by_id = {product.id: product for product in products}
    if len(by_id) != len(product_ids):
        raise ValueError("Produto inexistente ou pertencente a outra organização")
    return by_id


def _money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise InvalidOperation
        return amount.quantize(Decimal("0.000001"))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Preço de produto inválido") from error


def _item_values(items, products, existing_items=None):
    existing_by_product = {item.produto_id: item for item in (existing_items or [])}
    values = []
    total = Decimal("0")
    for item in items:
        product = products[item["produto_id"]]
        historical = existing_by_product.get(product.id)
        unit_price = _money(historical.preco_unitario) if historical else _money(product.preco)
        subtotal = unit_price * item["quantidade"]
        total += subtotal
        values.append({
            "produto": product,
            "quantidade": item["quantidade"],
            "preco_unitario": unit_price,
            "subtotal": subtotal,
        })
    return values, total


def _replace_venda_items(venda, values, organization):
    venda.items = [
        VendaItem(
            venda=venda,
            produto=value["produto"],
            organization_id=organization.id,
            quantidade=value["quantidade"],
            preco_unitario=value["preco_unitario"],
            subtotal=value["subtotal"],
        )
        for value in values
    ]


def _serialize_items(venda):
    return [
        {
            "id": item.id,
            "produto_id": item.produto_id,
            "produto_nome": item.produto.nome,
            "quantidade": item.quantidade,
            "preco_unitario": float(item.preco_unitario),
            "subtotal": float(item.subtotal),
        }
        for item in venda.items
    ]


def _payment_summary(venda):
    confirmed = sum(
        (Decimal(str(payment.valor)) for payment in venda.pagamentos
         if payment.status == "confirmado"), Decimal("0")
    )
    total = _money(venda.valor_total)
    if confirmed == 0:
        status = "Pendente"
    elif confirmed < total:
        status = "Parcial"
    else:
        status = "Pago"
    return confirmed, max(total - confirmed, Decimal("0")), status


def _locked_sale(venda_id, organization_id):
    """Load the tenant-scoped sale while serializing payment writers."""
    return (
        Venda.query.filter_by(id=venda_id, organization_id=organization_id)
        .with_for_update()
        .first_or_404()
    )


def _financial_status(total, paid):
    if paid <= 0:
        return "Pendente"
    if paid < total:
        return "Parcial"
    return "Pago"


def _payment_totals_for_sales(sales, organization):
    sale_ids = [sale.id for sale in sales]
    if not sale_ids:
        return {}
    rows = db.session.query(
        VendaPagamento.venda_id,
        func.coalesce(func.sum(
            case((VendaPagamento.status == "confirmado", VendaPagamento.valor), else_=0)
        ), 0),
    ).filter(
        VendaPagamento.organization_id == organization.id,
        VendaPagamento.venda_id.in_(sale_ids),
    ).group_by(VendaPagamento.venda_id).all()
    return {sale_id: Decimal(str(value or 0)) for sale_id, value in rows}


def _serialize_payments(venda):
    paid, pending, status = _payment_summary(venda)
    return {
        "total_pago": float(paid),
        "saldo_pendente": float(pending),
        "status_financeiro": status,
        "pagamentos": [
            {
                "id": payment.id,
                "forma_pagamento": payment.forma_pagamento,
                "valor": float(payment.valor),
                "status": payment.status,
                "observacao": payment.observacao,
            }
            for payment in venda.pagamentos
        ],
    }


def _add_legacy_payment(venda):
    if venda.status_pagamento != "Pago":
        return
    if any(payment.status == "confirmado" for payment in venda.pagamentos):
        return
    venda.pagamentos.append(VendaPagamento(
        organization_id=venda.organization_id,
        forma_pagamento="legado",
        valor=_money(venda.valor_total),
        status="confirmado",
        observacao="Migrado do status legado da venda",
    ))


def _add_requested_payment(venda, organization):
    forma = request.form.get("forma_pagamento", "").strip().lower()
    raw_value = request.form.get("pagamento_valor", "").strip()
    if not forma and not raw_value:
        return
    if forma not in {"pix", "dinheiro", "credito", "debito", "outro"}:
        raise ValueError("Forma de pagamento inválida")
    value = _money(raw_value)
    if value <= 0 or value > _money(venda.valor_total):
        raise ValueError("Valor de pagamento inválido ou acima do total")
    venda.pagamentos.append(VendaPagamento(
        organization_id=organization.id, forma_pagamento=forma,
        valor=value, status="confirmado",
    ))
    venda.status_pagamento = "Pago" if _payment_summary(venda)[2] == "Pago" else "Pendente"


@main.route('/gestao-vendas', methods=['GET', 'POST'])
@login_required
def gestao_vendas():
    return render_template('base/gestao_vendas.html')




@main.route('/nova-venda', methods=['GET', 'POST'])
@login_required
def nova_venda():
    form = VendaForm()
    organization = get_current_organization()
    show_seller_type = g.organization_settings["show_seller_type"]
    if not show_seller_type:
        form.tipo_vendedor.validators = []
        form.tipo_vendedor.data = "Membro"

    # carregar produtos
    produtos = Produto.query.filter_by(organization_id=organization.id, ativo=True).all()
    form.produto_id.choices = [(p.id, p.nome) for p in produtos]
    form.produto_precos = {p.id: p.preco for p in produtos}

    if request.method == "POST":
        has_items_payload = (
            request.form.get("items") is not None
            or isinstance(request.get_json(silent=True), dict)
            and "items" in request.get_json(silent=True)
        )
        try:
            items = _request_items(form)
            valid_form = (
                _validate_form_for_items(form, items)
                if has_items_payload else form.validate_on_submit()
            )
            if not valid_form:
                return render_template(
                    "base/nova_venda.html", form=form, venda=None,
                    produto_nome=None, vendedor_nome=None
                )

            products = _products_for_items(items, organization)
            values, total = _item_values(items, products)
            vendedor_nome = request.form.get("vendedor_nome", "").strip().lower()
            vendedor_id = form.vendedor_id.data
            if not vendedor_id:
                vendedor = Vendedor.query.filter_by(
                    nome=vendedor_nome, organization_id=organization.id
                ).first()
                if not vendedor:
                    vendedor = Vendedor(
                        nome=vendedor_nome, organization_id=organization.id
                    )
                    db.session.add(vendedor)
                    db.session.flush()
                vendedor_id = vendedor.id
            else:
                vendedor = Vendedor.query.filter_by(
                    id=vendedor_id, organization_id=organization.id
                ).first()
                if vendedor is None:
                    raise ValueError("Vendedor inexistente ou de outra organização")

            venda = Venda(
                organization_id=organization.id,
                produto_id=items[0]["produto_id"],
                vendedor_id=vendedor_id,
                comprador_nome=form.comprador_nome.data.strip(),
                quantidade=sum(item["quantidade"] for item in items),
                tipo_vendedor=form.tipo_vendedor.data if show_seller_type else "Membro",
                status_pagamento=form.status_pagamento.data,
                valor_total=float(total),
                observacao=form.observacao.data.strip() if form.observacao.data else None,
                data_venda=form.data_venda.data or datetime.now(timezone.utc),
            )
            _replace_venda_items(venda, values, organization)
            _add_requested_payment(venda, organization)
            _add_legacy_payment(venda)
            db.session.add(venda)
            db.session.commit()
            return jsonify({"success": True})
        except (ValueError, TypeError) as error:
            db.session.rollback()
            return jsonify({"success": False, "error": str(error)}), 400
        except Exception:
            db.session.rollback()
            raise

    return render_template(
        "base/nova_venda.html",
        form=form,
        venda=None,
        produto_nome=None,
        vendedor_nome=None
    )
       




@main.route("/buscar-vendedores")
@login_required
def buscar_vendedores():

    termo = request.args.get("q", "")
    organization = get_current_organization()

    vendedores = (
        Vendedor.query
        .filter(
            Vendedor.organization_id == organization.id,
            Vendedor.nome.ilike(f"%{termo}%"),
        )
        .limit(10)
        .all()
    )

    return jsonify([
        {"id": v.id, "nome": str(v.nome).title()}
        for v in vendedores
    ])



@main.route('/buscar-produtos')
@login_required
def buscar_produtos():
    query = request.args.get('q', '')
    organization = get_current_organization()
    produtos = Produto.query.filter(
        Produto.organization_id == organization.id,
        Produto.nome.ilike(f'%{query}%'),
    ).all()
    return jsonify([{'id': p.id, 'nome': p.nome, 'preco':p.preco} for p in produtos])



@main.route('/api/vendas', methods=['GET'])
@login_required
def api_vendas():
    search = request.args.get('q', '').strip()
    filtro = request.args.get('filtro', '').strip().lower()
    limit = int(request.args.get('limit', 5))  # número de registros por requisição
    offset = int(request.args.get('offset', 0))  # índice inicial

    organization = get_current_organization()
    query = Venda.query.join(Vendedor).join(Produto).filter(
        Venda.organization_id == organization.id,
        Vendedor.organization_id == organization.id,
        Produto.organization_id == organization.id,
    )


    # =========================
    # FILTRO ESPECÍFICO: DATA
    # =========================

    
    if filtro == "data" and search:
        try:
            data_filtro = datetime.strptime(search, "%d/%m/%Y")
            inicio = datetime.combine(data_filtro.date(), datetime.min.time())
            fim = inicio + timedelta(days=1)
            query = query.filter(Venda.data_venda >= inicio, Venda.data_venda < fim)
        except ValueError:
            return jsonify([])

    # =========================
    # FILTRO ESPECÍFICO: STATUS DE PAGAMENTO
    # =========================
    elif filtro == "cliente" and search:
        print(search)
        query = query.filter(Venda.comprador_nome.ilike(f"%{search}%"))


    elif filtro == "status pagamento" and search:
        if search.lower() in ["1", "pendente"]:
            query = query.filter(Venda.status_pagamento == "Pendente")
        elif search.lower() in ["2", "pago"]:
            query = query.filter(Venda.status_pagamento == "Pago")
        else:
            query = query.filter(Venda.status_pagamento.ilike(f"%{search}%"))

    elif filtro == "status entrega" and search:
        valor = search.lower()
        
        if valor in ["1", "pendente", "não", "nao", ""]:
            # Inclui registros que estão pendentes ou com status vazio
            query = query.filter(
                db.or_(
                    Venda.status_entrega == "Pendente",
                    Venda.status_entrega.is_(None)
                )
            )
        elif valor in ["2", "entregue", "sim"]:
            query = query.filter(Venda.status_entrega == "Entregue")
        else:
            # fallback: pesquisa textual em status_pagamento
            query = query.filter(Venda.status_pagamento.ilike(f"%{search}%"))


    # =========================
    # PESQUISA TEXTUAL NORMAL (quando não for filtro específico)
    # =========================
    elif search:
        search_lower = search.lower()
        query = query.filter(
            db.or_(
                Venda.comprador_nome.ilike(f"%{search_lower}%"),
                Vendedor.nome.ilike(f"%{search_lower}%"),
                Produto.nome.ilike(f"%{search_lower}%")
            )
        )

    # =========================
    # Ordenação
    # =========================
    if filtro == "id":
        query = query.order_by(Venda.id.desc())
    elif filtro == "cliente":
        query = query.order_by(Venda.comprador_nome.asc())
    elif filtro == "vendedor":
        query = query.order_by(Vendedor.nome.asc())
    elif filtro == "data":
        query = query.order_by(Venda.data_venda.desc())
    else:
        query = query.order_by(Venda.data_venda.desc())

    vendas = query.offset(offset).limit(limit).all()

    results = [
        {
            "id": v.id,
            "comprador_nome": str(v.comprador_nome).title(),
            "produto": v.produto.nome,
            "vendedor": str(v.vendedor.nome).title(),
            "quantidade": v.quantidade,
            "status_pagamento": v.status_pagamento,
            "status_entregada":status_entrega_row(v.status_entrega),
            "valor_total": v.valor_total,
            "items": _serialize_items(v),
            **_serialize_payments(v),
            "data_venda": v.data_venda.strftime("%d/%m/%Y %H:%M")
        }
        for v in vendas
    ]
   
    return jsonify(results)

def status_entrega_row(valor=None):
    """
    Retorna 'Sim' se a venda estiver entregue, 'Não' caso contrário.
    """
    if valor == "Entregue":
        return "Sim"
    return "Não"


@main.route('/api/cards/gestao', methods=['GET'])
@login_required
def api_cards_gestao():
    organization = get_current_organization()

    vendas = Venda.query.filter_by(organization_id=organization.id).all()
    paid_by_sale = _payment_totals_for_sales(vendas, organization)

    total = sum(v.quantidade for v in vendas)
    pagos = sum(v.quantidade for v in vendas if _financial_status(float(v.valor_total), float(paid_by_sale.get(v.id, 0))) == "Pago")
    parciais = sum(v.quantidade for v in vendas if _financial_status(float(v.valor_total), float(paid_by_sale.get(v.id, 0))) == "Parcial")
    pendentes = sum(v.quantidade for v in vendas if _financial_status(float(v.valor_total), float(paid_by_sale.get(v.id, 0))) == "Pendente")
    pendentes_entrega = sum(v.quantidade for v in vendas if v.status_entrega == "Entregue")

    return jsonify({
        "total": total or 0,
        "pago": pagos or 0,
        "parcial": parciais or 0,
        "pendente": pendentes or 0,
        'pendentes_entrega':pendentes_entrega or 0,
    })

@main.route('/api/vendas/<int:id>', methods=['DELETE'])
@login_required
def api_deletar_venda(id):
    organization = get_current_organization()

    venda = Venda.query.filter_by(
        id=id, organization_id=organization.id
    ).first_or_404()

    db.session.delete(venda)
    db.session.commit()

    return jsonify({"success": True})

@main.route('/editar-venda/<int:venda_id>', methods=['GET', 'POST'])
@login_required
def editar_venda(venda_id):
    form = VendaForm()
    organization = get_current_organization()
    show_seller_type = g.organization_settings["show_seller_type"]
    if not show_seller_type:
        form.tipo_vendedor.validators = []
        form.tipo_vendedor.data = "Membro"

    venda = Venda.query.filter_by(
        id=venda_id, organization_id=organization.id
    ).first_or_404()
    existing_product_ids = [item.produto_id for item in venda.items]
    produtos = Produto.query.filter(
        Produto.organization_id == organization.id,
        db.or_(Produto.ativo.is_(True), Produto.id.in_(existing_product_ids or [-1])),
    ).all()
    form.produto_id.choices = [(p.id, p.nome) for p in produtos]
    form.produto_precos = {p.id: p.preco for p in produtos}

    produto_nome = None
    vendedor_nome = None

    if request.method == "GET":
        form.produto_id.data = venda.produto_id
        form.vendedor_id.data = venda.vendedor_id
        form.comprador_nome.data = venda.comprador_nome
        form.quantidade.data = venda.quantidade
        form.tipo_vendedor.data = venda.tipo_vendedor
        form.status_pagamento.data = venda.status_pagamento
        form.observacao.data = venda.observacao
        form.data_venda.data = venda.data_venda

        produto = Produto.query.filter_by(
            id=venda.produto_id, organization_id=organization.id
        ).first()
        vendedor = Vendedor.query.filter_by(
            id=venda.vendedor_id, organization_id=organization.id
        ).first()

        if produto:
            produto_nome = produto.nome

        if vendedor:
            vendedor_nome = vendedor.nome

    if request.method == "POST":
        has_items_payload = (
            request.form.get("items") is not None
            or isinstance(request.get_json(silent=True), dict)
            and "items" in request.get_json(silent=True)
        )
        try:
            items = _request_items(form)
            valid_form = (
                _validate_form_for_items(form, items)
                if has_items_payload else form.validate_on_submit()
            )
            if not valid_form:
                return render_template(
                    "base/nova_venda.html", form=form, venda=venda,
                    produto_nome=produto_nome, vendedor_nome=vendedor_nome
                )
            products = _products_for_items(items, organization)
            values, total = _item_values(items, products, venda.items)

            vendedor_nome = request.form.get("vendedor_nome", "").strip().lower()
            vendedor_id = form.vendedor_id.data
            if not vendedor_id:
                vendedor = Vendedor.query.filter_by(
                    nome=vendedor_nome, organization_id=organization.id
                ).first()
                if not vendedor:
                    vendedor = Vendedor(
                        nome=vendedor_nome, organization_id=organization.id
                    )
                    db.session.add(vendedor)
                    db.session.flush()
                vendedor_id = vendedor.id
            else:
                vendedor = Vendedor.query.filter_by(
                    id=vendedor_id, organization_id=organization.id
                ).first()
                if vendedor is None:
                    raise ValueError("Vendedor inexistente ou de outra organização")

            venda.produto_id = items[0]["produto_id"]
            venda.vendedor_id = vendedor_id
            venda.comprador_nome = form.comprador_nome.data.strip()
            venda.quantidade = sum(item["quantidade"] for item in items)
            venda.tipo_vendedor = form.tipo_vendedor.data if show_seller_type else "Membro"
            venda.status_pagamento = form.status_pagamento.data
            venda.valor_total = float(total)
            venda.observacao = form.observacao.data.strip() if form.observacao.data else None
            venda.data_venda = form.data_venda.data or datetime.now(timezone.utc)
            _replace_venda_items(venda, values, organization)
            _add_requested_payment(venda, organization)
            _add_legacy_payment(venda)
            db.session.commit()
            return jsonify({"success": True})
        except (ValueError, TypeError) as error:
            db.session.rollback()
            return jsonify({"success": False, "error": str(error)}), 400
        except Exception:
            db.session.rollback()
            raise

    return render_template(
        "base/nova_venda.html",
        form=form,
        venda=venda,
        produto_nome=produto_nome,
        vendedor_nome=vendedor_nome
    )

@main.route('/api/vendas/<int:id>', methods=['GET'])
@login_required
def api_venda_detalhe(id):
    organization = get_current_organization()

    venda = Venda.query.filter_by(
        id=id, organization_id=organization.id
    ).first_or_404()

    return jsonify({
        "id": venda.id,
        "comprador_nome": venda.comprador_nome,
        "produto": venda.produto.nome,
        "produto_id": venda.produto_id,
        "vendedor": venda.vendedor.nome,
        "vendedor_id": venda.vendedor_id,
        "quantidade": venda.quantidade,
        "status_pagamento": venda.status_pagamento,
        "valor_total": venda.valor_total,
        "items": _serialize_items(venda),
        **_serialize_payments(venda),
        "data_venda": venda.data_venda.strftime("%Y-%m-%d %H:%M")
    })



@main.route('/exportar-vendas', methods=['GET'])
@login_required
def exportar_vendas():
    organization = get_current_organization()
    # 1. Query original com Join e Ordenação
    query = Venda.query.join(Vendedor).join(Produto).filter(
        Venda.organization_id == organization.id,
        Vendedor.organization_id == organization.id,
        Produto.organization_id == organization.id,
    ).order_by(Vendedor.nome.asc(), Venda.id.asc())
    
    q = request.args.get('q', '').strip()
    if q:
        q_lower = q.lower()
        query = query.filter(
            db.or_(
                Venda.comprador_nome.ilike(f"%{q_lower}%"),
                Vendedor.nome.ilike(f"%{q_lower}%"),
                Produto.nome.ilike(f"%{q_lower}%")
            )
        )

    vendas = query.all()
    financeiros = {v.id: _payment_summary(v) for v in vendas}
    
    # 2. Dados da aba principal
    data = [
        {
            "ID": v.id,
            "Vendedor": str(v.vendedor.nome).title(),
            "Cliente": str(v.comprador_nome).title(),
            "Produto": v.produto.nome,
            "Quantidade": v.quantidade,
            "Status Pagamento": v.status_pagamento,
            "Status Financeiro": financeiros[v.id][2],
            "Valor Total a Pagar": v.valor_total, # Removi o "R$" aqui para o Excel tratar como número
            "Total Pago": float(financeiros[v.id][0]),
            "Saldo Pendente": float(financeiros[v.id][1]),
            "Data Venda": v.data_venda.strftime("%d/%m/%Y %H:%M")
        }
        for v in vendas
    ]

    df_vendas = pd.DataFrame(data)

    # 3. Gerar a "Tabela Dinâmica" (Resumo por Vendedor)
    # Agrupamos por Vendedor e somamos a coluna Quantidade
    df_resumo = df_vendas.groupby("Vendedor")["Quantidade"].sum().reset_index()
    df_resumo.columns = ["Vendedor", "Quantidade Vendida Total"]

    # Criar arquivo Excel em memória
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # --- ABA 1: RELATÓRIO DETALHADO ---
        df_vendas.to_excel(writer, index=False, sheet_name="Relatório de Vendas")
        
        workbook = writer.book
        worksheet1 = writer.sheets["Relatório de Vendas"]
        
        # Formatos
        header_format = workbook.add_format({"bold": True, "bg_color": "#f6a50e", "font_color": "white", "border": 1})
        money_format = workbook.add_format({'num_format': 'R$ #,##0.00'})

        # Ajustes na Aba 1
        for col_num, value in enumerate(df_vendas.columns):
            worksheet1.write(0, col_num, value, header_format)
            if value == "Valor Total a Pagar":
                worksheet1.set_column(col_num, col_num, 20, money_format)
            else:
                worksheet1.set_column(col_num, col_num, 20)

        # --- ABA 2: RESUMO POR VENDEDOR ---
        df_resumo.to_excel(writer, index=False, sheet_name="Resumo por Vendedor")
        worksheet2 = writer.sheets["Resumo por Vendedor"]

        # Ajustes na Aba 2
        for col_num, value in enumerate(df_resumo.columns):
            worksheet2.write(0, col_num, value, header_format)
            worksheet2.set_column(col_num, col_num, 25)

    output.seek(0)

    return send_file(
        output,
        download_name=f"vendas_quentinhas_{int(time.time())}.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@main.route('/api/vendas/<int:venda_id>/entrega', methods=['POST'])
@login_required
def atualizar_entrega(venda_id):
    organization = get_current_organization()
    venda = Venda.query.filter_by(
        id=venda_id, organization_id=organization.id
    ).first_or_404()

    # Toggle: se já está entregue, volta para pendente; senão, marca como entregue
    if venda.status_entrega == "Entregue":
        venda.status_entrega = "Pendente"
        venda.data_entrega = None
    else:
        venda.status_entrega = "Entregue"
        venda.data_entrega = datetime.now(timezone.utc)

    db.session.commit()
    
    return jsonify({
        "id": venda.id,
        "status_entrega": venda.status_entrega,
        "data_entrega": venda.data_entrega.strftime("%d/%m/%Y %H:%M") if venda.data_entrega else ""
    })

@main.route('/api/vendas/<int:venda_id>/status/pagamento', methods=['POST'])
@login_required
def atualizar_pagamento(venda_id):
    """Compatibilidade: settle only the remaining balance, idempotently."""
    organization = get_current_organization()
    venda = _locked_sale(venda_id, organization.id)
    confirmed, balance, status = _payment_summary(venda)
    payment = None
    if balance > 0:
        payment = VendaPagamento(
            venda=venda, organization_id=organization.id,
            forma_pagamento="legado", valor=balance, status="confirmado",
            observacao="Registrado pelo atalho de pagamento legado",
        )
        db.session.add(payment)
        venda.status_pagamento = "Pago"
    else:
        # Repeating the legacy action must not cancel real receipts.
        venda.status_pagamento = "Pago"

    db.session.commit()
    return jsonify({"id": payment.id if payment else None, **_serialize_payments(venda),
                    "status_pagamento": venda.status_pagamento})


@main.route('/api/vendas/<int:venda_id>/pagamentos', methods=['POST'])
@login_required
def criar_pagamento(venda_id):
    organization = get_current_organization()
    data = request.get_json(silent=True) or request.form
    forma = str(data.get("forma_pagamento", "")).lower().strip()
    status = str(data.get("status", "confirmado")).lower().strip()
    if forma not in {"pix", "dinheiro", "credito", "debito", "outro"}:
        return jsonify({"error": "Forma de pagamento inválida"}), 400
    if status not in {"pendente", "confirmado", "cancelado"}:
        return jsonify({"error": "Status de pagamento inválido"}), 400
    try:
        value = _money(data.get("valor"))
    except (ValueError, TypeError):
        return jsonify({"error": "Valor de pagamento inválido"}), 400
    if value <= 0:
        return jsonify({"error": "Valor de pagamento inválido"}), 400
    venda = _locked_sale(venda_id, organization.id)
    confirmed, balance, _ = _payment_summary(venda)
    if status == "confirmado" and confirmed + value > _money(venda.valor_total):
        db.session.rollback()
        return jsonify({"error": "Pagamento confirmado excede o valor da venda"}), 400
    payment = VendaPagamento(
        venda=venda, organization_id=organization.id, forma_pagamento=forma,
        valor=value, status=status, observacao=data.get("observacao")
    )
    db.session.add(payment)
    venda.status_pagamento = "Pago" if _payment_summary(venda)[2] == "Pago" else "Pendente"
    db.session.commit()
    return jsonify({"id": payment.id, **_serialize_payments(venda), "status_pagamento": venda.status_pagamento}), 201


@main.route('/api/vendas/<int:venda_id>/pagamentos/<int:pagamento_id>/cancelar', methods=['POST'])
@login_required
def cancelar_pagamento(venda_id, pagamento_id):
    organization = get_current_organization()
    payment = VendaPagamento.query.join(Venda).filter(
        Venda.id == venda_id, Venda.organization_id == organization.id,
        VendaPagamento.id == pagamento_id,
        VendaPagamento.organization_id == organization.id,
    ).first_or_404()
    payment.status = "cancelado"
    payment.venda.status_pagamento = "Pago" if _payment_summary(payment.venda)[0] >= _money(payment.venda.valor_total) else "Pendente"
    db.session.commit()
    return jsonify(_serialize_payments(payment.venda))
