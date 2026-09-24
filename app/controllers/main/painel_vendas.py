from datetime import datetime, timezone
import time

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import login_required
import pandas as pd
from io import BytesIO
from sqlalchemy import case, func

from app.controllers.forms.venda_form import VendaForm
from app.models.pages.gerenciamento_vendas import Produto, Venda, Vendedor
from app.core.tenancy import get_current_organization

from datetime import datetime, timedelta
from . import main
from app import db


@main.route('/gestao-vendas', methods=['GET', 'POST'])
@login_required
def gestao_vendas():
    return render_template('base/gestao_vendas.html')




@main.route('/nova-venda', methods=['GET', 'POST'])
@login_required
def nova_venda():
    form = VendaForm()
    organization = get_current_organization()

    # carregar produtos
    form.produto_id.choices = [(p.id, p.nome) for p in Produto.query.filter_by(
        organization_id=organization.id
    ).all()]

    if form.validate_on_submit():
        organization = get_current_organization()
        vendedor_nome = request.form.get('vendedor_nome', '').strip().lower()
        vendedor_id = form.vendedor_id.data

        if not vendedor_id:
            vendedor = Vendedor.query.filter_by(
                nome=vendedor_nome, organization_id=organization.id
            ).first()
            if not vendedor:
                vendedor = Vendedor(
                    nome=vendedor_nome,
                    organization_id=organization.id,
                )
                db.session.add(vendedor)
                db.session.commit()
            vendedor_id = vendedor.id
        else:
            vendedor = Vendedor.query.filter_by(
                id=vendedor_id, organization_id=organization.id
            ).first()
            if vendedor is None:
                abort(404)

        produto = Produto.query.filter_by(
            id=form.produto_id.data, organization_id=organization.id
        ).first()
        if produto is None:
            abort(404)
        valor_total = produto.preco * form.quantidade.data
        data_venda = form.data_venda.data or datetime.now(timezone.utc)

        venda = Venda(
            organization_id=organization.id,
            produto_id=form.produto_id.data,
            vendedor_id=vendedor_id,
            comprador_nome=form.comprador_nome.data.strip(),
            quantidade=form.quantidade.data,
            tipo_vendedor=form.tipo_vendedor.data,
            status_pagamento=form.status_pagamento.data,
            valor_total=valor_total,
            observacao=form.observacao.data.strip() if form.observacao.data else None,
            data_venda=data_venda
        )

        db.session.add(venda)
        db.session.commit()

        return jsonify({'success': True})

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

    total = sum(v.quantidade for v in vendas)
    pagos = sum(v.quantidade for v in vendas if v.status_pagamento == "Pago")
    pendentes = sum(v.quantidade for v in vendas if v.status_pagamento != "Pago")
    pendentes_entrega = sum(v.quantidade for v in vendas if v.status_entrega == "Entregue")

    return jsonify({
        "total": total or 0,
        "pago": pagos or 0,
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

    form.produto_id.choices = [(p.id, p.nome) for p in Produto.query.filter_by(
        organization_id=organization.id
    ).all()]

    venda = Venda.query.filter_by(
        id=venda_id, organization_id=organization.id
    ).first_or_404()

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

    if form.validate_on_submit():
        vendedor_nome = request.form.get('vendedor_nome', '').strip().lower()
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
                db.session.commit()
            vendedor_id = vendedor.id
        else:
            vendedor = Vendedor.query.filter_by(
                id=vendedor_id, organization_id=organization.id
            ).first()
            if vendedor is None:
                abort(404)

        produto = Produto.query.filter_by(
            id=form.produto_id.data, organization_id=organization.id
        ).first()
        if produto is None:
            abort(404)
        valor_total = produto.preco * form.quantidade.data
        data_venda = form.data_venda.data or datetime.now(timezone.utc)

        venda.produto_id = form.produto_id.data
        venda.vendedor_id = vendedor_id
        venda.comprador_nome = form.comprador_nome.data.strip()
        venda.quantidade = form.quantidade.data
        venda.tipo_vendedor = form.tipo_vendedor.data
        venda.status_pagamento = form.status_pagamento.data
        venda.valor_total = valor_total
        venda.observacao = form.observacao.data.strip() if form.observacao.data else None
        venda.data_venda = data_venda

        db.session.commit()

        return jsonify({'success': True})

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
    
    # 2. Dados da aba principal
    data = [
        {
            "ID": v.id,
            "Vendedor": str(v.vendedor.nome).title(),
            "Cliente": str(v.comprador_nome).title(),
            "Produto": v.produto.nome,
            "Quantidade": v.quantidade,
            "Status Pagamento": v.status_pagamento,
            "Valor Total a Pagar": v.valor_total, # Removi o "R$" aqui para o Excel tratar como número
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
def atualizar_pagamento(venda_id): # Nome alterado para clareza
    organization = get_current_organization()
    venda = Venda.query.filter_by(
        id=venda_id, organization_id=organization.id
    ).first_or_404()

    if venda.status_pagamento == "Pendente":
        venda.status_pagamento = "Pago"
    else:
        venda.status_pagamento = "Pendente"

    db.session.commit()
    
    return jsonify({
        "id": venda.id,
        "status_pagamento": venda.status_pagamento
    })
