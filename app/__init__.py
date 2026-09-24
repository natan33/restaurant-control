import logging
import click
import time
from datetime import timedelta

from flask import Flask, redirect, session, url_for, jsonify
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, login_required
from flask_mail import Mail
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect
from flask_session import Session
from flask_executor import Executor

# Imports internos

from config import config  # Importando o dicionário de instâncias
from app.core.trace import register_trace_id
from app.core.logger import setup_logger

# Instâncias das Extensões (Singleton Pattern)
db = SQLAlchemy()
bootstrap = Bootstrap()
csrf = CSRFProtect()
mail = Mail()
cache = Cache()
executor = Executor()
flask_session = Session()  # RENOMEADO para evitar conflito com flask.session
login_manager = LoginManager()

# Configuração do Login Manager
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = 'info'

# Configura o Logger Global antes da criação do App
setup_logger()

def create_app(config_name: str):
    app = Flask(__name__)

    # Carrega a configuração do dicionário
    app.config.from_object(config[config_name])
    app.config.setdefault(
        "TENANCY_EXEMPT_ENDPOINTS",
        {
            "auth.login",
            "auth.logout",
            "auth.perfil",
            "auth.redefinir_senha",
            "tenancy.select_organization",
            "auth.selecionar_organizacao",
            "tenancy.onboarding",
        },
    )

    # Inicializa lógica personalizada da classe de config
    config[config_name].init_app(app)

    # Configuração de logging do Flask
    app.logger.setLevel(logging.INFO)

    # Inicialização das Extensões
    bootstrap.init_app(app)
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    cache.init_app(app)
    flask_session.init_app(app)  # Usando a instância renomeada
    executor.init_app(app)

    # Registro do user_loader para o Flask-Login
    # from app.models.auth.user import User
    from app.models.auth.user import User
    from app.models import tenancy  # noqa: F401 - register tenancy models in metadata
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.core.tenancy import register_tenancy_context
    register_tenancy_context(app)

    # Inicializa o Celery
    # celery = make_celery(app)

    # Middleware de Rastreabilidade (Trace ID)
    register_trace_id(app)

    # Registro de Blueprints
    from app.controllers.auth import auth as auth_blueprint
    from app.controllers.main import main as main_blueprint
    # from app.controllers.api import api as api_blueprint

    app.register_blueprint(auth_blueprint)
    app.register_blueprint(main_blueprint)

    @app.cli.command("bootstrap-organizations")
    @click.option("--user-id", type=int, required=True, help="ID do usuário administrador")
    def bootstrap_organizations(user_id):
        """Cria as organizações iniciais e associa o administrador idempotentemente."""
        from app.models.auth.user import User
        from app.models.pages.gerenciamento_vendas import Produto, Venda, VendaItem, VendaPagamento, Vendedor
        from app.models.tenancy import Organization, OrganizationUser

        user = db.session.get(User, user_id)
        if user is None:
            raise click.ClickException(f"Usuário não encontrado: {user_id}")
        organizations = []
        for name in ("Igreja Batista em Vista Alegre", "Graças na Mesa"):
            organization = Organization.query.filter_by(name=name).one_or_none()
            if organization is None:
                organization = Organization(name=name, is_active=True)
                db.session.add(organization)
                db.session.flush()
            else:
                organization.is_active = True
            membership = OrganizationUser.query.filter_by(
                organization_id=organization.id, user_id=user.id
            ).one_or_none()
            if membership is None:
                db.session.add(OrganizationUser(
                    organization_id=organization.id, user_id=user.id,
                    role="admin", active=True,
                ))
            else:
                membership.role = "admin"
                membership.active = True
            organizations.append(organization)
        db.session.commit()

        temporary = Organization.query.filter_by(name="MIGRAÇÃO - organização temporária").one_or_none()
        click.echo(f"Administrador: {user.id} ({user.username})")
        for organization in organizations:
            click.echo(f"{organization.id}: {organization.name} (admin ativo)")
        if temporary is not None:
            for model, label in ((Venda, "Venda"), (VendaItem, "VendaItem"),
                                 (VendaPagamento, "VendaPagamento"), (Produto, "Produto"),
                                 (Vendedor, "Vendedor")):
                click.echo(f"Temporária - {label}: {model.query.filter_by(organization_id=temporary.id).count()}")

    @app.cli.command("bootstrap-church-data")
    @click.option("--user-id", type=int, required=True, help="ID do administrador autorizado")
    def bootstrap_church_data(user_id):
        """Cadastra o produto inicial da Igreja Batista de forma idempotente."""
        from app.models.auth.user import User
        from app.models.pages.gerenciamento_vendas import Produto, Vendedor
        from app.models.tenancy import Organization, OrganizationUser

        user = db.session.get(User, user_id)
        organization = Organization.query.filter_by(
            name="Igreja Batista em Vista Alegre", is_active=True
        ).one_or_none()
        if user is None:
            raise click.ClickException(f"Usuário não encontrado: {user_id}")
        if organization is None:
            raise click.ClickException("Organização Igreja Batista em Vista Alegre não encontrada ou inativa")
        membership = OrganizationUser.query.filter_by(
            user_id=user.id, organization_id=organization.id, role="admin", active=True
        ).one_or_none()
        if membership is None:
            raise click.ClickException("Usuário não possui membership admin ativa na Igreja")

        product = Produto.query.filter_by(
            organization_id=organization.id, nome="Xinxim"
        ).one_or_none()
        if product is None:
            product = Produto(organization_id=organization.id, nome="Xinxim", preco=20.00)
            db.session.add(product)
            db.session.commit()
            click.echo("Criado: Xinxim — R$ 20,00")
        else:
            click.echo(f"Já existente: Xinxim (id={product.id}, preço=R$ {product.preco:.2f})")

        sellers = Vendedor.query.filter_by(organization_id=organization.id).order_by(Vendedor.nome).all()
        if sellers:
            click.echo("Vendedores existentes: " + ", ".join(seller.nome for seller in sellers))
        else:
            click.echo("Nenhum vendedor cadastrado; o nome será criado no primeiro lançamento de venda.")
    # app.register_blueprint(api_blueprint)


    # @app.before_request
    # def check_timeout():
    #     if current_user.is_authenticated:
    #         now = time.time()
    #         last_activity = session.get('last_activity', now)
    #         timeout_duration = app.config.get('PERMANENT_SESSION_LIFETIME', 900).total_seconds()

    #         if now - last_activity > timeout_duration:
    #             from flask_login import logout_user
    #             logout_user()
    #             return redirect(url_for('auth.login'))

    #         session['last_activity'] = now
    #     session.permanent = True
    #     app.permanent_session_lifetime = timedelta(minutes=15)
    #     session.modified = True

    # from sqlalchemy import event
    # @event.listens_for(db.Session, "before_flush")
    # def receive_before_flush(session, flush_context, instances):
    #     # Percorre tudo que é novo ou foi alterado
    #     for obj in list(session.new) + list(session.dirty):
    #         # Se o objeto tiver o método update_audit (que vem do Mixin)
    #         if hasattr(obj, 'update_audit'):
    #             obj.update_audit() #

    return app
