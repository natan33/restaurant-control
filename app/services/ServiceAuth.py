import random
from flask import flash, redirect, render_template, session, url_for
from flask_login import login_user, logout_user
from app.models.auth.user import User
from app import db
import logging

from app.utils.api_response import ApiResponse

# Este logger usará o TraceIdFilter definido no seu setup_logger
logger = logging.getLogger(__name__)

class ServiceAutentication:
    def __init__(self, request=None, forms=None):
        self.request = request
        self.form = forms

    def autentication(self):
        if self.request.method == 'POST': # Verifica se é uma tentativa de envio
            if self.form.validate_on_submit():
                user = User.query.filter_by(email=str(self.form.email.data).lower()).first()

                if user and user.check_password(self.form.password.data):
                    login_user(user, remember=self.form.remember_me.data)
                    logger.info(f"Usuário {user.email} logado via sessão.")
                    next_page = self.request.args.get('next')
                    return redirect(next_page or url_for('main.index'))
                
                # Caso falhe a senha ou usuário
                logger.warning(f"Falha de login para o email: {self.form.email.data}")
                flash('E-mail ou senha inválidos. Tente novamente.', 'danger')
            else:
                # Caso o formulário falhe na validação (ex: e-mail vazio)
                if self.form.errors:
                    flash('Por favor, preencha os campos corretamente.', 'warning')
        
        return None

    def logout(self):
        logout_user()
        session.pop("organization_id", None)
        logger.info("Usuário realizou logout.")
        return redirect(url_for('auth.login'))
    
    @staticmethod
    def request_password_reset(email):
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return {"code": "ERROR", "message": "E-mail não encontrado"}
        
        # 1. Gerar e salvar código
        code = str(random.randint(100000, 999999))
        user.reset_code = code
        db.session.commit()
        
        subject="Studio Fun - Código de Recuperação"
        # 2. Disparar Task Celery
        template_info = {
            'username': user.username,
            'code': code,
            'template': 'emails/reset_password.html'
        }
        #from app.tasks.email_tasks import send_async_email
        #send_async_email.delay(subject, user.email, template_info)
        
        return {"code": "SUCCESS", "message": "Código enviado com sucesso!"}

    @staticmethod
    def reset_password(email=None, code=None, new_password_hash=None):
        user = User.query.filter_by(email=email, reset_code=code).first()
        
        if not user:
            return {"code": "ERROR", "message": "Código inválido ou e-mail incorreto."}
        
        # 3. Atualizar senha e limpar código
        user.set_password(new_password_hash)
        user.reset_code = None
        db.session.commit()

        return {"code": "SUCCESS", "message": "Senha alterada com sucesso!"}
