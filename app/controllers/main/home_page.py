from io import BytesIO
import time

from flask import Blueprint, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import login_required
import pandas as pd
from app.models import Venda, Vendedor
from sqlalchemy import func, case
from datetime import datetime, timedelta, timezone
from app import db
from app.models.pages.gerenciamento_vendas import Produto
from . import main
from app.core.tenancy import get_current_organization

@main.route("/")
@main.route('/portal', methods=['GET', 'POST'])
@login_required
def index():
    organization = get_current_organization()
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

    total_pago = db.session.query(
            func.sum(
                case(
                    (Venda.status_pagamento == "Pago", Venda.valor_total), 
                    else_=0
                )
            )
        ).filter(Venda.organization_id == organization.id).scalar() or 0


    # Ajustado: removido os parênteses extras/listas de dentro do case
    # total_pendente = db.session.query(
    #     func.sum(
    #         case(
    #             (Venda.status_pagamento != "Pago", Venda.valor_total), 
    #             else_=0
    #         )
    #     )
    # ).scalar() or 0

    total_pendente = db.session.query(
            func.sum(
                case(
                    (Venda.status_pagamento != "Pago", Venda.valor_total), 
                    else_=0
                )
            )
        ).filter(Venda.organization_id == organization.id).scalar() or 0


    percentual_pago = round(total_pago / total_vendido * 100) if total_vendido else 0
    percentual_pendente = round(total_pendente / total_vendido * 100) if total_vendido else 0

    # qtd_faturas = db.session.query(func.sum(
    #         case((Venda.status_pagamento == "Pendente", 1), else_=0)
    #     ).label("pendente")).first() or 0

    qtd_faturas = db.session.query(func.sum(
        case((Venda.status_pagamento == "Pendente", 1), else_=0)
        ).label("pendente")
    ).filter(Venda.organization_id == organization.id).first() or 0

    

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
        qtd_faturas=qtd_faturas.pendente,
        percentual_pago=percentual_pago,
        percentual_pendente=percentual_pendente,
        ranking=ranking
    )


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

    pagos = sum(v.quantidade for v in vendas if v.status_pagamento == "Pago")
    pendentes = sum(v.quantidade for v in vendas if v.status_pagamento != "Pago")

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
        .join(Venda)
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
        "pendentes": pendentes,
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

    query = (
        db.session.query(
            Vendedor.nome,
            Venda.tipo_vendedor,
            func.sum(Venda.quantidade).label("quantidade"),
            func.sum(Venda.valor_total).label("valor_total"),

            func.sum(
                case((Venda.status_pagamento == "Pago", Venda.valor_total), else_=0)
            ).label("valor_pago"),

            func.sum(
                case((Venda.status_pagamento != "Pago", Venda.valor_total), else_=0)
            ).label("valor_pendente"),

            func.sum(
                case((Venda.status_pagamento == "Pago", Venda.quantidade), else_=0)
            ).label("quantidade_paga"),
        )
        .join(Venda)
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

    vendedor = request.args.get("vendedor")

    query = (
        db.session.query(
            Venda.id,
            Venda.comprador_nome,
            Vendedor.nome,
            Venda.quantidade,
            Venda.valor_total,
            Venda.status_pagamento,
            Venda.data_venda
        )
        .join(Venda)
        .join(Produto)
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
