from flask import flash, render_template, request, redirect, url_for
from flask_login import login_required
from flask_login import current_user

from app.controllers.forms.form_auth import LoginForm, RedefinirSenhaForm
from app import db

from werkzeug.security import generate_password_hash, check_password_hash

from . import auth


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