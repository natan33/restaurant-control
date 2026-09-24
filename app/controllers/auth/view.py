from flask import flash, render_template, request, redirect, url_for
from flask_login import login_required
from flask_login import current_user

from app.controllers.forms.form_auth import LoginForm, RedefinirSenhaForm
from app import db
from app.models.tenancy import Organization, OrganizationUser
from app.core.tenancy import select_current_organization

from werkzeug.security import generate_password_hash, check_password_hash

from . import auth


TEMPORARY_ORGANIZATION_NAME = "MIGRAÇÃO - organização temporária"


def available_organization_memberships(user_id):
    return OrganizationUser.query.join(OrganizationUser.organization).filter(
        OrganizationUser.user_id == user_id,
        OrganizationUser.active.is_(True),
        OrganizationUser.organization.has(is_active=True),
        OrganizationUser.organization.has(Organization.name != TEMPORARY_ORGANIZATION_NAME),
    ).order_by(OrganizationUser.organization_id).all()


@auth.route('/login', methods=['GET', 'POST'])
def login():
    
    if current_user.is_authenticated:
        return redirect(url_for('main.index')) 
    
    from app.services import ServiceAutentication
    form = LoginForm()
    
    # Instancia o serviço
    auth_service = ServiceAutentication(request=request, forms=form)
    
    # Tenta a autenticação
    response = auth_service.autentication()
    
    # Se o serviço retornar um redirect (sucesso), a view obedece
    if response:
        return response


    return render_template('auth/login.html',form=form) 

@auth.route("/perfil")
@login_required
def perfil():

    usuario = {
        "nome": f'{str(current_user.username).title()}'
    }

    return render_template("auth/perfil.html", usuario=usuario)


@auth.route("/selecionar-organizacao", methods=["GET", "POST"])
@login_required
def selecionar_organizacao():
    memberships = available_organization_memberships(current_user.id)
    if request.method == "POST":
        try:
            select_current_organization(int(request.form.get("organization_id", "")))
        except (TypeError, ValueError):
            flash("Organização inválida.", "danger")
            return render_template("auth/selecionar_organizacao.html", memberships=memberships), 400
        return redirect(url_for("main.index"))
    return render_template("auth/selecionar_organizacao.html", memberships=memberships)

@auth.route('/logout')
def logout():
    from app.services import ServiceAutentication
    auth_service = ServiceAutentication()
    return auth_service.logout()


@auth.route("/redefinir-senha", methods=["GET", "POST"])
@login_required
def redefinir_senha():

    form = RedefinirSenhaForm()

    if form.validate_on_submit():

        if not check_password_hash(current_user.senha, form.senha_atual.data):
            flash("Senha atual incorreta", "danger")
            return redirect(url_for("auth.redefinir_senha"))

        current_user.password_hash = generate_password_hash(form.nova_senha.data)

        db.session.commit()

        flash("Senha alterada com sucesso", "success")

        return redirect(url_for("main.perfil"))

    return render_template("auth/redefinir_senha.html", form=form)
