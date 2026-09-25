from io import BytesIO
import time

from flask import Blueprint, g, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import login_required
import pandas as pd
from app.models import Compra, CompraItem, Venda, VendaItem, VendaPagamento, Vendedor
from sqlalchemy import and_, func, case
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from app import db
from app.models.pages.gerenciamento_vendas import Produto
from . import main
from app.core.tenancy import get_current_organization


def _period_bounds():
    end = request.args.get("data_final")
    start = request.args.get("data_inicial")
    now = datetime.now(timezone.utc)
    if not start or not end:
        start = (now - timedelta(days=6)).date().isoformat()
        end = now.date().isoformat()
    start_date = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_date = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=1)
    return start_date, end_date


def _restaurant_dashboard(organization):
    start, end = _period_bounds()
    sales_filter = (Venda.organization_id == organization.id, Venda.data_venda >= start, Venda.data_venda < end)
    payment_filter = (VendaPagamento.organization_id == organization.id, VendaPagamento.status == "confirmado")
    sales = db.session.query(Venda.id, Venda.valor_total).filter(*sales_filter).subquery()
    received = db.session.query(func.coalesce(func.sum(VendaPagamento.valor), 0)).join(sales, sales.c.id == VendaPagamento.venda_id).filter(*payment_filter).scalar() or 0
    billing = db.session.query(func.coalesce(func.sum(sales.c.valor_total), 0)).scalar() or 0
    sale_count = db.session.query(func.count(sales.c.id)).scalar() or 0
    paid_by_sale = db.session.query(VendaPagamento.venda_id, func.sum(VendaPagamento.valor).label("paid")).join(sales, sales.c.id == VendaPagamento.venda_id).filter(*payment_filter).group_by(VendaPagamento.venda_id).subquery()
    statuses = db.session.query(
        func.sum(case((func.coalesce(paid_by_sale.c.paid, 0) >= sales.c.valor_total, 1), else_=0)),
        func.sum(case((and_(func.coalesce(paid_by_sale.c.paid, 0) > 0, func.coalesce(paid_by_sale.c.paid, 0) < sales.c.valor_total), 1), else_=0)),
        func.sum(case((func.coalesce(paid_by_sale.c.paid, 0) == 0, 1), else_=0)),
    ).select_from(sales).outerjoin(paid_by_sale, paid_by_sale.c.venda_id == sales.c.id).one()
    expenses = db.session.query(func.coalesce(func.sum(Compra.valor_total), 0)).filter(Compra.organization_id == organization.id, Compra.status == "pago", Compra.data_compra >= start, Compra.data_compra < end).scalar() or 0
    daily_sales = db.session.query(func.date(Venda.data_venda), func.sum(Venda.valor_total)).filter(*sales_filter).group_by(func.date(Venda.data_venda)).order_by(func.date(Venda.data_venda)).all()
    daily_expenses = db.session.query(func.date(Compra.data_compra), func.sum(Compra.valor_total)).filter(Compra.organization_id == organization.id, Compra.status == "pago", Compra.data_compra >= start, Compra.data_compra < end).group_by(func.date(Compra.data_compra)).order_by(func.date(Compra.data_compra)).all()
    products = db.session.query(Produto.nome, func.sum(VendaItem.quantidade)).join(VendaItem, VendaItem.produto_id == Produto.id).join(Venda, Venda.id == VendaItem.venda_id).filter(*sales_filter, VendaItem.organization_id == organization.id, Produto.organization_id == organization.id).group_by(Produto.nome).order_by(func.sum(VendaItem.quantidade).desc()).limit(5).all()
    categories = db.session.query(Compra.categoria, func.sum(Compra.valor_total)).filter(Compra.organization_id == organization.id, Compra.status == "pago", Compra.data_compra >= start, Compra.data_compra < end).group_by(Compra.categoria).order_by(func.sum(Compra.valor_total).desc()).all()
    payment_methods = db.session.query(VendaPagamento.forma_pagamento, func.sum(VendaPagamento.valor)).join(sales, sales.c.id == VendaPagamento.venda_id).filter(*payment_filter).group_by(VendaPagamento.forma_pagamento).order_by(func.sum(VendaPagamento.valor).desc()).first()
    last_sales = Venda.query.filter(*sales_filter).order_by(Venda.data_venda.desc()).limit(5).all()
    last_expenses = Compra.query.filter(Compra.organization_id == organization.id, Compra.data_compra >= start, Compra.data_compra < end).order_by(Compra.data_compra.desc()).limit(5).all()
    billing = Decimal(str(billing)); received = Decimal(str(received)); expenses = Decimal(str(expenses))
    return {
        "period": {"start": start.date().isoformat(), "end": (end - timedelta(days=1)).date().isoformat()},
        "cards": {"billing": str(billing), "received": str(received), "receivable": str(max(billing - received, Decimal("0"))), "expenses": str(expenses), "result": str(received - expenses), "sales_count": sale_count, "ticket_average": str((billing / sale_count).quantize(Decimal("0.01")) if sale_count else Decimal("0")), "paid_sales": int(statuses[0] or 0), "partial_sales": int(statuses[1] or 0), "pending_sales": int(statuses[2] or 0)},
        "daily": {"sales": [[str(day), float(value or 0)] for day, value in daily_sales], "expenses": [[str(day), float(value or 0)] for day, value in daily_expenses]},
        "products": [[name, int(value or 0)] for name, value in products], "categories": [[name, float(value or 0)] for name, value in categories], "payment_method": {"name": payment_methods[0], "value": float(payment_methods[1])} if payment_methods else None,
        "last_sales": [{"date": sale.data_venda.isoformat(), "value": float(sale.valor_total)} for sale in last_sales], "last_expenses": [{"date": expense.data_compra.isoformat(), "value": float(expense.valor_total), "category": expense.categoria} for expense in last_expenses],
    }


def _payment_totals(vendas, organization):
    ids = [v.id for v in vendas]
    if not ids:
        return {}
    rows = db.session.query(
        VendaPagamento.venda_id,
        func.coalesce(func.sum(
            case((VendaPagamento.status == "confirmado", VendaPagamento.valor), else_=0)
        ), 0),
    ).filter(
        VendaPagamento.organization_id == organization.id,
        VendaPagamento.venda_id.in_(ids),
    ).group_by(VendaPagamento.venda_id).all()
    return {sale_id: float(value or 0) for sale_id, value in rows}


def _financial_status(total, paid):
    if paid <= 0:
        return "Pendente"
    if paid < total:
        return "Parcial"
    return "Pago"

@main.route("/")
@main.route('/portal', methods=['GET', 'POST'])
@login_required
def index():
    organization = get_current_organization()
    if g.organization_settings.get("dashboard_mode") == "restaurant" and g.organization_settings.get("show_financial_dashboard"):
        return render_template("base/dashboard_restaurante.html", app_display_name=g.organization_settings.get("app_display_name", organization.name))
    # Últimos 7 dias
    hoje = datetime.now(timezone.utc)
    dias = [hoje - timedelta(days=i) for i in range(6, -1, -1)]

    vendas_dias = []
    for dia in dias:
        # Garantimos que o retorno seja 0.0 caso não haja vendas
        # total = db.session.query(func.sum(Venda.valor_total))\
        #     .filter(func.date(Venda.data_venda) == dia.date()).scalar()
        total = db.session.query(func.sum(Venda.valor_total))\
            .filter(
                func.date(Venda.data_venda) == dia.date(),
                Venda.organization_id == organization.id,
            ).scalar()
        
        # Forçamos o tipo float para evitar erros de divisão no template
        vendas_dias.append((float(total) if total else 0.0, dia))

    # Calculamos o valor máximo para escala do gráfico
    valores_apenas = [v[0] for v in vendas_dias]
    max_val = max(valores_apenas) if valores_apenas and max(valores_apenas) > 0 else 1.0

    # Totais
    #total_vendido = db.session.query(func.sum(Venda.valor_total)).scalar() or 0

    total_vendido = db.session.query(func.sum(Venda.valor_total))\
    .filter(Venda.organization_id == organization.id)\
    .scalar() or 0


    # Ajustado: removido os parênteses extras/listas de dentro do case
    # total_pago = db.session.query(
    #     func.sum(
    #         case(
    #             (Venda.status_pagamento == "Pago", Venda.valor_total), 
    #             else_=0
    #         )
    #     )
    # ).scalar() or 0

    dashboard_sales = Venda.query.filter_by(organization_id=organization.id).all()
    dashboard_paid = _payment_totals(dashboard_sales, organization)
    total_pago = sum(dashboard_paid.values())


    # Ajustado: removido os parênteses extras/listas de dentro do case
    # total_pendente = db.session.query(
    #     func.sum(
    #         case(
    #             (Venda.status_pagamento != "Pago", Venda.valor_total), 
    #             else_=0
    #         )
    #     )
    # ).scalar() or 0

    total_pendente = sum(max(float(v.valor_total) - dashboard_paid.get(v.id, 0), 0) for v in dashboard_sales)


    percentual_pago = round(total_pago / total_vendido * 100) if total_vendido else 0
    percentual_pendente = round(total_pendente / total_vendido * 100) if total_vendido else 0

    # qtd_faturas = db.session.query(func.sum(
    #         case((Venda.status_pagamento == "Pendente", 1), else_=0)
    #     ).label("pendente")).first() or 0

    qtd_faturas = sum(
        1 for v in dashboard_sales
        if _financial_status(float(v.valor_total), dashboard_paid.get(v.id, 0)) == "Pendente"
    )

    

    # Ranking de vendedores
    # Ajustado: removido os colchetes [] de dentro dos cases no query
    ranking_query = db.session.query(
        Venda.vendedor_id,
        # Somamos a quantidade de quentinhas (2, 3, 4...) em vez de contar linhas
        func.sum(Venda.quantidade).label("qtde_vendida"), 
        func.sum(case((Venda.status_pagamento == "Pago", Venda.valor_total), else_=0)).label("total_pago"),
        func.sum(case((Venda.status_pagamento != "Pago", Venda.valor_total), else_=0)).label("total_pendente"),
        func.sum(Venda.valor_total).label("total")
    ).filter(Venda.organization_id == organization.id,
             Venda.tipo_vendedor == "Jovem",
             ) \
    .group_by(Venda.vendedor_id) \
    .order_by(func.sum(Venda.valor_total).desc()) \
    .all()

    ranking = []
    for r in ranking_query:
        # Como a query só dá o ID, pegamos o nome do vendedor aqui
        vendedor = Vendedor.query.filter_by(
            id=r.vendedor_id, organization_id=organization.id
        ).first()
        
        ranking.append({
            "nome": str(vendedor.nome).title() if vendedor else "Desconhecido",
            "qtde_vendida": int(r.qtde_vendida or 0), # Total de quentinhas somadas
            "total_pago": r.total_pago or 0,
            "total_pendente": r.total_pendente or 0,
            "total": r.total or 0
        })

    return render_template(
        "base/painel_vendas.html",
        vendas_dias=vendas_dias,
        max_val=max_val,
        total_vendido=total_vendido,
        total_pago=total_pago,
        total_pendente=total_pendente,
        qtd_faturas=qtd_faturas,
        percentual_pago=percentual_pago,
        percentual_pendente=percentual_pendente,
        ranking=ranking
    )


@main.route("/api/dashboard-financeiro")
@login_required
def api_dashboard_financeiro():
    organization = get_current_organization()
    if g.organization_settings.get("dashboard_mode") != "restaurant" or not g.organization_settings.get("show_financial_dashboard"):
        return jsonify({"error": "Dashboard financeiro indisponível"}), 403
    return jsonify(_restaurant_dashboard(organization))


@main.route("/api/vendas-semanais")
@login_required
def api_vendas_semanais():
    organization = get_current_organization()
    hoje = datetime.utcnow()
    dias_semana = {
        'Mon': 'Seg', 'Tue': 'Ter', 'Wed': 'Qua', 
        'Thu': 'Qui', 'Fri': 'Sex', 'Sat': 'Sáb', 'Sun': 'Dom'
    }
    
    # Gerar os últimos 7 dias
    datas = [hoje - timedelta(days=i) for i in range(6, -1, -1)]
    
    labels = []
    valores = []
    
    for dia in datas:
        total = db.session.query(func.sum(Venda.valor_total))\
            .filter(
                func.date(Venda.data_venda) == dia.date(),
                Venda.organization_id == organization.id,
            ).scalar()
        
        # Traduz o dia da semana
        dia_en = dia.strftime('%a')
        labels.append(dias_semana.get(dia_en, dia_en))
        valores.append(float(total) if total else 0.0)
    
    # Calculamos o máximo para o JS não se perder
    max_val = max(valores) if valores and max(valores) > 0 else 1.0
    
    return jsonify({
        "labels": labels,
        "valores": valores,
        "max_val": max_val
    })


@main.route("/relatorios")
@login_required
def relatorios():

    return render_template(
        "base/dashboard.html"
    )



@main.route("/api/relatorios")
@login_required
def api_relatorios():
    organization = get_current_organization()

    vendedor_nome = request.args.get("vendedor")

    query = db.session.query(Venda).join(Vendedor)\
    .filter(Venda.organization_id == organization.id,
            Vendedor.organization_id == organization.id,
            )

    if vendedor_nome:
        query = query.filter(Vendedor.nome.ilike(f"%{vendedor_nome}%"))

    vendas = query.all()

    # totais
    total_vendas = sum(v.quantidade for v in vendas )
    total_valor = sum(v.valor_total for v in vendas)
    total_entregues = sum(1 for v in vendas if v.status_entrega == "Entregue")

    paid_by_sale = _payment_totals(vendas, organization)
    pagos = sum(v.quantidade for v in vendas if _financial_status(float(v.valor_total), paid_by_sale.get(v.id, 0)) == "Pago")
    parciais = sum(v.quantidade for v in vendas if _financial_status(float(v.valor_total), paid_by_sale.get(v.id, 0)) == "Parcial")
    pendentes = sum(v.quantidade for v in vendas if _financial_status(float(v.valor_total), paid_by_sale.get(v.id, 0)) == "Pendente")
    total_pago = sum(paid_by_sale.values())
    saldo_pendente = sum(max(float(v.valor_total) - paid_by_sale.get(v.id, 0), 0) for v in vendas)

    # vendas por dia (usando quantidade)
    vendas_por_dia = (
        db.session.query(
            func.date(Venda.data_venda),
            func.sum(Venda.quantidade)
        )
        .join(Vendedor)
        .filter(
            Venda.organization_id == organization.id,
            Vendedor.organization_id == organization.id,
            Vendedor.nome.ilike(f"%{vendedor_nome}%") if vendedor_nome else True
        )
        .group_by(func.date(Venda.data_venda))
        .order_by(func.date(Venda.data_venda))
        .all()
    )

    labels_dia = [str(v[0]) for v in vendas_por_dia]
    valores_dia = [int(v[1]) for v in vendas_por_dia]

    # ranking vendedores (somando quantidade)
    ranking = (
        db.session.query(
            Vendedor.nome,
            func.sum(Venda.quantidade).label("total")
        )
        .select_from(Vendedor)
        .join(Venda, Venda.vendedor_id == Vendedor.id)
        .group_by(Vendedor.nome)
        .filter(
            Venda.organization_id == organization.id,
            Vendedor.organization_id == organization.id,
        )
        .order_by(func.sum(Venda.quantidade).desc())
        .limit(5)
        .all()
    )

    ranking_data = [
        {"nome": r[0].title(), "total": int(r[1])}
        for r in ranking
    ]

    return jsonify({
        "total_vendas": total_vendas,
        "total_valor": total_valor,
        "total_entregues":total_entregues,
        "pagos": pagos,
        "parciais": parciais,
        "pendentes": pendentes,
        "total_pago": total_pago,
        "saldo_pendente": saldo_pendente,
        "vendas_dia_labels": labels_dia,
        "vendas_dia_valores": valores_dia,
        "ranking": ranking_data
    })

@main.route("/ranking")
@login_required
def ranking_completo():
    return render_template("base/ranking.html")

@main.route("/api/ranking")
@login_required
def api_ranking():
    organization = get_current_organization()

    vendedor = request.args.get("vendedor")
    tipo = request.args.get("tipo")

    limit = int(request.args.get("limit", 5))
    offset = int(request.args.get("offset", 0))

    payment_totals = db.session.query(
        VendaPagamento.venda_id,
        func.coalesce(func.sum(case((VendaPagamento.status == "confirmado", VendaPagamento.valor), else_=0)), 0).label("paid"),
    ).filter(VendaPagamento.organization_id == organization.id).group_by(VendaPagamento.venda_id).subquery()

    query = (
        db.session.query(
            Vendedor.nome,
            Venda.tipo_vendedor,
            func.sum(Venda.quantidade).label("quantidade"),
            func.sum(Venda.valor_total).label("valor_total"),

            func.sum(func.coalesce(payment_totals.c.paid, 0)).label("valor_pago"),
            func.sum(Venda.valor_total - func.coalesce(payment_totals.c.paid, 0)).label("valor_pendente"),

            func.sum(
                case((func.coalesce(payment_totals.c.paid, 0) >= Venda.valor_total, Venda.quantidade), else_=0)
            ).label("quantidade_paga"),
        )
        .select_from(Vendedor)
        .join(Venda, Venda.vendedor_id == Vendedor.id)
        .outerjoin(payment_totals, payment_totals.c.venda_id == Venda.id)
        .filter(Venda.organization_id == organization.id,
                Vendedor.organization_id == organization.id,
                )
    )

    if vendedor:
        query = query.filter(Vendedor.nome.ilike(f"%{vendedor}%"))

    if tipo and tipo != "todos":
        query = query.filter(Venda.tipo_vendedor == tipo)

    ranking = (
        query.group_by(Vendedor.nome, Venda.tipo_vendedor)
        .order_by(func.sum(Venda.quantidade).desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    data = [{
        "nome": r[0].title(),
        "tipo": r[1],
        "quantidade": int(r[2] or 0),
        "valor_total": float(r[3] or 0),
        "valor_pago": float(r[4] or 0),
        "valor_pendente": float(r[5] or 0),
        "quantidade_paga": int(r[6] or 0)   # ✅ CORRETO AGORA
    } for r in ranking]

    return jsonify(data)

@main.route("/relatorios/exportar/pdf")
@login_required
def exportar_pdf():

    vendedor = request.args.get("vendedor")

    return redirect(url_for("main.relatorios", vendedor=vendedor, print="1"))



@main.route("/relatorios/exportar/excel")
@login_required
def exportar_excel():
    organization = get_current_organization()

    payment_totals = db.session.query(
        VendaPagamento.venda_id,
        func.coalesce(func.sum(case((VendaPagamento.status == "confirmado", VendaPagamento.valor), else_=0)), 0).label("paid"),
    ).filter(VendaPagamento.organization_id == organization.id).group_by(VendaPagamento.venda_id).subquery()

    vendedor = request.args.get("vendedor")

    query = (
        db.session.query(
            Venda.id,
            Venda.comprador_nome,
            Vendedor.nome,
            Venda.quantidade,
            Venda.valor_total,
            Venda.status_pagamento,
            func.coalesce(payment_totals.c.paid, 0).label("total_pago"),
            Venda.data_venda
        )
        .join(Venda)
        .join(Produto)
        .outerjoin(payment_totals, payment_totals.c.venda_id == Venda.id)
        .filter(Venda.organization_id == organization.id,
                Vendedor.organization_id == organization.id,
                Produto.organization_id == organization.id,
                )
        .order_by(Venda.id.asc())
    )

    if vendedor:
        query = query.filter(Vendedor.nome.ilike(f"%{vendedor}%"))

    vendas = query.all()

    dados = [
        {
            "ID": v.id,
            "Cliente": str(v.comprador_nome).title(),
            "Vendedor": str(v.nome).title(),
            "Quantidade": v.quantidade,
            "Valor Total": float(v.valor_total),
            "Status Pagamento": v.status_pagamento,
            "Total Pago": float(v.total_pago),
            "Saldo Pendente": max(float(v.valor_total) - float(v.total_pago), 0),
            "Status Financeiro": _financial_status(float(v.valor_total), float(v.total_pago)),
            "Data da Venda": v.data_venda.strftime("%d/%m/%Y")
        }
        for v in vendas
    ]

    df = pd.DataFrame(dados)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

        df.to_excel(writer, sheet_name="Relatório", index=False)

        workbook = writer.book
        worksheet = writer.sheets["Relatório"]

        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#f6a50e",
            "font_color": "white"
        })

        for col_num, value in enumerate(df.columns):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, 20)

    output.seek(0)

    return send_file(
        output,
        download_name=f"{time.time()}_relatorio_vendas.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
