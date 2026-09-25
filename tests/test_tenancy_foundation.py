import unittest
import importlib.util
import json
from decimal import Decimal
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile
from datetime import date, datetime, timezone
from jinja2 import FileSystemLoader

from flask import Flask, g, session
from flask_login import LoginManager, login_user, logout_user

from app import db
from app.core.tenancy import register_tenancy_context
from app.models.auth.user import User
from app.models.pages.gerenciamento_vendas import Produto, Venda, VendaItem, VendaPagamento, Vendedor
from app.models.pages.financeiro import Compra, CompraItem
from app.models.tenancy import Organization, OrganizationUser
from app.core.timezone import period_local_naive_bounds, period_utc_naive_bounds


class TenancyFoundationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.app.jinja_loader = FileSystemLoader("app/templates")
        self.login_manager = LoginManager(self.app)
        self.user_counter = 0

        @self.login_manager.user_loader
        def load_user(user_id):
            return db.session.get(User, int(user_id))

        register_tenancy_context(self.app)
        from app.controllers.main import main as main_blueprint
        self.app.register_blueprint(main_blueprint)
        self.app.add_url_rule("/protected", "protected", self.protected)
        self.app.add_url_rule("/logout", "logout", self.logout)
        self.app.add_url_rule("/account", "auth.perfil", self.account)

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    @staticmethod
    def protected():
        return g.current_organization.name

    @staticmethod
    def logout():
        logout_user()
        session.pop("organization_id", None)
        return "ok"

    @staticmethod
    def account():
        return "account"

    def create_user_with_memberships(self, membership_count=1):
        with self.app.app_context():
            self.user_counter += 1
            user = User(
                username=f"person{self.user_counter}",
                email=f"person{self.user_counter}@example.com",
                password_hash="x",
            )
            db.session.add(user)
            for index in range(membership_count):
                organization = Organization(name=f"Organization {index}")
                db.session.add(organization)
                db.session.flush()
                db.session.add(OrganizationUser(
                    organization_id=organization.id,
                    user_id=user.id,
                    role="member",
                    active=True,
                ))
            db.session.commit()
            return user.id

    def login(self, user_id):
        with self.app.test_request_context():
            user = db.session.get(User, user_id)
            login_user(user)
            return self.app.full_dispatch_request()

    def test_single_membership_is_selected_and_exposed_centrally(self):
        user_id = self.create_user_with_memberships()
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
            response = client.get("/protected")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "Organization 0")

    def test_invalid_session_organization_is_replaced_by_active_membership(self):
        user_id = self.create_user_with_memberships(membership_count=1)
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = 999999
            response = client.get("/protected")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "Organization 0")

    def test_multiple_memberships_require_explicit_selection(self):
        user_id = self.create_user_with_memberships(membership_count=2)
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = 999999
            response = client.get("/protected")

        self.assertEqual(response.status_code, 409)

    def test_organization_selection_excludes_temporary_and_inactive(self):
        user_id = self.create_user_with_memberships(membership_count=0)
        with self.app.app_context():
            operational = Organization(name="Igreja Batista em Vista Alegre")
            graças = Organization(name="Graças na Mesa")
            temporary = Organization(name="MIGRAÇÃO - organização temporária")
            inactive = Organization(name="Inativa", is_active=False)
            db.session.add_all([operational, graças, temporary, inactive])
            db.session.flush()
            db.session.add_all([
                OrganizationUser(organization_id=operational.id, user_id=user_id, role="admin", active=True),
                OrganizationUser(organization_id=graças.id, user_id=user_id, role="admin", active=True),
                OrganizationUser(organization_id=temporary.id, user_id=user_id, role="admin", active=True),
                OrganizationUser(organization_id=inactive.id, user_id=user_id, role="admin", active=True),
            ])
            db.session.commit()
            from app.controllers.auth.view import available_organization_memberships
            names = [membership.organization.name for membership in available_organization_memberships(user_id)]
        self.assertEqual(names, ["Igreja Batista em Vista Alegre", "Graças na Mesa"])

    def test_organization_selection_form_includes_csrf_and_expected_field(self):
        with open("app/templates/auth/selecionar_organizacao.html", encoding="utf-8") as template:
            source = template.read()
        self.assertIn('name="csrf_token"', source)
        self.assertIn('name="organization_id"', source)

    def test_gracas_catalog_is_idempotent_and_tenant_scoped(self):
        with self.app.app_context():
            gracas = Organization(name="Graças na Mesa")
            igreja = Organization(name="Igreja Batista em Vista Alegre")
            db.session.add_all([gracas, igreja])
            db.session.flush()
            from app.bootstrap_data import GRACAS_NA_MESA_PRODUCTS, sync_gracas_products
            first = sync_gracas_products(gracas, Produto, db.session)
            second = sync_gracas_products(gracas, Produto, db.session)
            products = Produto.query.filter_by(organization_id=gracas.id).all()
            church_products = Produto.query.filter_by(organization_id=igreja.id).all()
        self.assertEqual(len(first["created"]), 10)
        self.assertEqual(len(second["created"]), 0)
        self.assertEqual(len(second["existing"]), 10)
        self.assertEqual(len(products), len(GRACAS_NA_MESA_PRODUCTS))
        self.assertEqual(len(church_products), 0)
        self.assertEqual(
            {product.nome: round(product.preco, 2) for product in products},
            dict(GRACAS_NA_MESA_PRODUCTS),
        )

    def test_gracas_catalog_sync_updates_price_without_duplicates(self):
        with self.app.app_context():
            gracas = Organization(name="Graças na Mesa")
            db.session.add(gracas)
            db.session.flush()
            db.session.add(Produto(organization_id=gracas.id, nome="Combo 1 - Moqueca + Pepsi 1L", preco=1))
            db.session.commit()
            from app.bootstrap_data import sync_gracas_products
            result = sync_gracas_products(gracas, Produto, db.session)
            combo = Produto.query.filter_by(organization_id=gracas.id, nome="Combo 1 - Moqueca + Pepsi 1L").all()
        self.assertEqual(len(combo), 1)
        self.assertEqual(combo[0].preco, 37.90)
        self.assertEqual(result["updated"], [("Combo 1 - Moqueca + Pepsi 1L", 1.0, 37.9)])

    def test_admin_product_management_is_tenant_scoped_and_validates(self):
        self.app.jinja_loader = FileSystemLoader("app/templates")
        self.app.jinja_env.globals["csrf_token"] = lambda: "test-token"
        user_id = self.create_user_with_memberships(membership_count=2)
        with self.app.app_context():
            memberships = OrganizationUser.query.filter_by(user_id=user_id).order_by(OrganizationUser.organization_id).all()
            first_id, second_id = memberships[0].organization_id, memberships[1].organization_id
            memberships[0].role = memberships[1].role = "admin"
            other = Produto(organization_id=second_id, nome="Somente B", preco=9)
            db.session.add(other)
            db.session.commit()
            other_id = other.id
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = first_id
            products_page = client.get("/produtos")
            self.assertEqual(products_page.status_code, 200)
            self.assertIn(b"+ Novo produto", products_page.data)
            self.assertIn(b"Produtos", products_page.data)
            self.assertIn(b"Organization 0", products_page.data)
            self.assertNotIn(b"Somente B", products_page.data)
            created = client.post("/produtos/novo", data={"nome": "Produto A", "preco": "12", "organization_id": second_id})
            self.assertEqual(created.status_code, 302)
            duplicate = client.post("/produtos/novo", data={"nome": "  Produto A ", "preco": "13"})
            self.assertEqual(duplicate.status_code, 200)
            foreign_edit = client.post(f"/produtos/{other_id}/editar", data={"nome": "Alterado", "preco": "10"})
            self.assertEqual(foreign_edit.status_code, 404)
            invalid_price = client.post("/produtos/novo", data={"nome": "Inválido", "preco": "0"})
            self.assertEqual(invalid_price.status_code, 200)
        with self.app.app_context():
            self.assertIsNotNone(Produto.query.filter_by(organization_id=first_id, nome="Produto A").one_or_none())
            self.assertIsNone(Produto.query.filter_by(organization_id=second_id, nome="Produto A").one_or_none())

    def test_member_cannot_manage_products(self):
        self.app.jinja_loader = FileSystemLoader("app/templates")
        self.app.jinja_env.globals["csrf_token"] = lambda: "test-token"
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization_id = Organization.query.one().id
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = organization_id
            self.assertNotIn(b"+ Novo produto", client.get("/produtos").data)
            self.assertEqual(client.post("/produtos/novo", data={"nome": "Bloqueado", "preco": "10"}).status_code, 403)

    def test_inactive_organization_is_not_accepted(self):
        user_id = self.create_user_with_memberships(membership_count=2)
        with self.app.app_context():
            inactive = Organization.query.filter_by(name="Organization 1").one()
            inactive_id = inactive.id
            inactive.is_active = False
            db.session.commit()
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = inactive_id
            response = client.get("/protected")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "Organization 0")

    def test_inactive_membership_is_not_accepted(self):
        user_id = self.create_user_with_memberships(membership_count=2)
        with self.app.app_context():
            inactive = OrganizationUser.query.join(Organization).filter(
                Organization.name == "Organization 1"
            ).one()
            inactive_organization_id = inactive.organization_id
            inactive.active = False
            db.session.commit()
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = inactive_organization_id
            response = client.get("/protected")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "Organization 0")

    def test_membership_selection_rejects_organization_owned_by_other_user(self):
        user_id = self.create_user_with_memberships()
        other_user_id = self.create_user_with_memberships()
        with self.app.app_context():
            other_membership = OrganizationUser.query.filter_by(user_id=other_user_id).one()
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
            with self.app.test_request_context():
                from flask_login import login_user
                from app.core.tenancy import select_current_organization
                login_user(db.session.get(User, user_id))
                with self.assertRaises(Exception) as error:
                    select_current_organization(other_membership.organization_id)

        self.assertEqual(error.exception.code, 403)

    def test_user_without_active_membership_is_denied(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            OrganizationUser.query.update({OrganizationUser.active: False})
            db.session.commit()
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
            response = client.get("/protected")

        self.assertEqual(response.status_code, 403)

    def test_logout_clears_organization_from_session(self):
        user_id = self.create_user_with_memberships()
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = 1
            response = client.get("/logout")
            with client.session_transaction() as browser_session:
                self.assertNotIn("organization_id", browser_session)

        self.assertEqual(response.status_code, 200)

    def test_account_route_is_available_without_an_active_membership(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            OrganizationUser.query.update({OrganizationUser.active: False})
            db.session.commit()
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
            response = client.get("/account")

        self.assertEqual(response.status_code, 200)

    def test_operational_entities_persist_with_the_current_organization(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization = Organization.query.one()
            organization_id = organization.id
            product = Produto(
                organization_id=organization_id, nome="Produto", preco=10
            )
            seller = Vendedor(
                organization_id=organization.id, nome="Vendedor"
            )
            db.session.add_all([product, seller])
            db.session.flush()
            sale = Venda(
                organization_id=organization.id,
                produto_id=product.id,
                vendedor_id=seller.id,
                comprador_nome="Comprador",
                quantidade=1,
                tipo_vendedor="Membro",
                status_pagamento="Pendente",
                valor_total=10,
            )
            db.session.add(sale)
            db.session.commit()

            self.assertEqual(product.organization_id, organization.id)
            self.assertEqual(seller.organization_id, organization.id)
            self.assertEqual(sale.organization_id, organization.id)

    def test_venda_items_preserve_tenant_and_relationships(self):
        self.create_user_with_memberships()
        with self.app.app_context():
            organization = Organization.query.one()
            product = Produto(
                organization_id=organization.id, nome="Produto", preco=12
            )
            seller = Vendedor(
                organization_id=organization.id, nome="Vendedor"
            )
            sale = Venda(
                organization_id=organization.id,
                produto_id=1,
                vendedor_id=1,
                comprador_nome="Cliente",
                quantidade=2,
                tipo_vendedor="Membro",
                status_pagamento="Pendente",
                valor_total=24,
            )
            db.session.add_all([product, seller])
            db.session.flush()
            sale.produto_id = product.id
            sale.vendedor_id = seller.id
            db.session.add(sale)
            db.session.flush()
            item = VendaItem(
                venda=sale,
                produto=product,
                organization_id=organization.id,
                quantidade=2,
                preco_unitario="12.000000",
                subtotal="24.000000",
            )
            db.session.add(item)
            db.session.commit()

            self.assertEqual(sale.items, [item])
            self.assertIs(item.venda, sale)
            self.assertIs(item.produto, product)

    def test_payment_summary_supports_partial_and_multiple_payments(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization = Organization.query.one()
            product = Produto(organization_id=organization.id, nome="Produto", preco=50)
            seller = Vendedor(organization_id=organization.id, nome="Vendedor")
            db.session.add_all([product, seller])
            db.session.flush()
            sale = Venda(
                organization_id=organization.id, produto_id=product.id,
                vendedor_id=seller.id, comprador_nome="Cliente", quantidade=1,
                tipo_vendedor="Membro", status_pagamento="Pendente", valor_total=50,
            )
            sale.pagamentos.extend([
                VendaPagamento(organization_id=organization.id, forma_pagamento="pix", valor="20", status="confirmado"),
                VendaPagamento(organization_id=organization.id, forma_pagamento="dinheiro", valor="30", status="confirmado"),
            ])
            db.session.add(sale)
            db.session.commit()
            from app.controllers.main.painel_vendas import _payment_summary
            self.assertEqual(_payment_summary(sale)[2], "Pago")
            sale.pagamentos[0].status = "cancelado"
            self.assertEqual(_payment_summary(sale)[2], "Parcial")
            sale.pagamentos[1].status = "cancelado"
            self.assertEqual(_payment_summary(sale)[2], "Pendente")

    def test_payment_endpoint_rejects_excess_and_cross_tenant(self):
        records = self.create_read_isolation_fixture()
        user_id, organization_id, own_sale_id = records[0]
        foreign_sale_id = records[1][2]
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = organization_id
            excess = client.post(
                f"/api/vendas/{own_sale_id}/pagamentos",
                json={"forma_pagamento": "pix", "valor": 11},
            )
            zero = client.post(
                f"/api/vendas/{own_sale_id}/pagamentos",
                json={"forma_pagamento": "dinheiro", "valor": 0},
            )
            foreign = client.post(
                f"/api/vendas/{foreign_sale_id}/pagamentos",
                json={"forma_pagamento": "pix", "valor": 1},
            )
        self.assertEqual(excess.status_code, 400)
        self.assertEqual(zero.status_code, 400)
        self.assertEqual(foreign.status_code, 404)

    def test_payment_writes_are_idempotent_and_never_exceed_sale_total(self):
        user_id = self.create_user_with_memberships(membership_count=2)
        with self.app.app_context():
            organizations = Organization.query.order_by(Organization.id).all()
            first, second = organizations
            product = Produto(organization_id=first.id, nome="Prato", preco=90)
            seller = Vendedor(organization_id=first.id, nome="Vendedor")
            db.session.add_all([product, seller])
            db.session.flush()
            sale = Venda(
                organization_id=first.id, produto_id=product.id, vendedor_id=seller.id,
                comprador_nome="Cliente", quantidade=1, tipo_vendedor="Membro",
                status_pagamento="Pendente", valor_total=90,
            )
            db.session.add(sale)
            db.session.commit()
            sale_id = sale.id
            foreign_product = Produto(organization_id=second.id, nome="Outro", preco=90)
            foreign_seller = Vendedor(organization_id=second.id, nome="Outro")
            db.session.add_all([foreign_product, foreign_seller])
            db.session.flush()
            foreign_sale = Venda(
                organization_id=second.id, produto_id=foreign_product.id,
                vendedor_id=foreign_seller.id, comprador_nome="Outro", quantidade=1,
                tipo_vendedor="Membro", status_pagamento="Pendente", valor_total=90,
            )
            db.session.add(foreign_sale)
            db.session.commit()
            foreign_sale_id = foreign_sale.id
            first_organization_id = first.id

        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = first_organization_id
            first_payment = client.post(
                f"/api/vendas/{sale_id}/pagamentos",
                json={"forma_pagamento": "pix", "valor": "90"},
            )
            second_payment = client.post(
                f"/api/vendas/{sale_id}/pagamentos",
                json={"forma_pagamento": "pix", "valor": "90"},
            )
            repeated_legacy = client.post(f"/api/vendas/{sale_id}/status/pagamento")
            foreign = client.post(
                f"/api/vendas/{foreign_sale_id}/pagamentos",
                json={"forma_pagamento": "pix", "valor": "1"},
            )

        self.assertEqual(first_payment.status_code, 201)
        self.assertEqual(second_payment.status_code, 400)
        self.assertEqual(repeated_legacy.status_code, 200)
        self.assertIsNone(repeated_legacy.json["id"])
        self.assertEqual(foreign.status_code, 404)
        with self.app.app_context():
            sale = db.session.get(Venda, sale_id)
            self.assertEqual(sum((p.valor for p in sale.pagamentos if p.status == "confirmado"), Decimal("0")), Decimal("90.000000"))

    def test_legacy_payment_settles_only_remaining_balance(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization = Organization.query.one()
            product = Produto(organization_id=organization.id, nome="Prato", preco=90)
            seller = Vendedor(organization_id=organization.id, nome="Vendedor")
            db.session.add_all([product, seller])
            db.session.flush()
            sale = Venda(
                organization_id=organization.id, produto_id=product.id, vendedor_id=seller.id,
                comprador_nome="Cliente", quantidade=2, tipo_vendedor="Membro",
                status_pagamento="Pendente", valor_total=90,
            )
            sale.items = [
                VendaItem(organization_id=organization.id, produto_id=product.id, quantidade=1, preco_unitario=45, subtotal=45),
                VendaItem(organization_id=organization.id, produto_id=product.id, quantidade=1, preco_unitario=45, subtotal=45),
            ]
            sale.pagamentos = [VendaPagamento(organization_id=organization.id, forma_pagamento="pix", valor=30, status="confirmado")]
            db.session.add(sale)
            db.session.commit()
            sale_id = sale.id
            organization_id = organization.id
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = organization_id
            response = client.post(f"/api/vendas/{sale_id}/status/pagamento")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["total_pago"], 90.0)
        with self.app.app_context():
            sale = db.session.get(Venda, sale_id)
            payments = [p for p in sale.pagamentos if p.status == "confirmado"]
            self.assertEqual(len(payments), 2)
            self.assertEqual(sum((p.valor for p in payments), Decimal("0")), Decimal("90.000000"))

    def test_payment_model_rejects_non_positive_value_and_foreign_sale(self):
        with self.app.app_context():
            first, second = Organization(name="A"), Organization(name="B")
            db.session.add_all([first, second])
            db.session.flush()
            product = Produto(organization_id=first.id, nome="P", preco=10)
            seller = Vendedor(organization_id=first.id, nome="S")
            db.session.add_all([product, seller])
            db.session.flush()
            sale = Venda(organization_id=first.id, produto_id=product.id, vendedor_id=seller.id,
                         comprador_nome="C", quantidade=1, tipo_vendedor="Membro",
                         status_pagamento="Pendente", valor_total=10)
            db.session.add(sale)
            db.session.flush()
            sale.pagamentos.append(VendaPagamento(organization_id=second.id, forma_pagamento="pix", valor=1, status="confirmado"))
            with self.assertRaises(ValueError):
                db.session.commit()
            db.session.rollback()

    def test_venda_item_rejects_foreign_tenant_product(self):
        self.create_user_with_memberships(membership_count=1)
        with self.app.app_context():
            first_org, second_org = Organization(name="A"), Organization(name="B")
            db.session.add_all([first_org, second_org])
            db.session.flush()
            product_a = Produto(organization_id=first_org.id, nome="A", preco=10)
            product_b = Produto(organization_id=second_org.id, nome="B", preco=10)
            seller = Vendedor(organization_id=first_org.id, nome="Seller")
            db.session.add_all([product_a, product_b, seller])
            db.session.flush()
            sale = Venda(
                organization_id=first_org.id,
                produto_id=product_a.id,
                vendedor_id=seller.id,
                comprador_nome="Cliente",
                quantidade=1,
                tipo_vendedor="Membro",
                status_pagamento="Pendente",
                valor_total=10,
            )
            db.session.add(sale)
            db.session.flush()
            db.session.add(VendaItem(
                venda=sale,
                produto=product_b,
                organization_id=first_org.id,
                quantidade=1,
                preco_unitario="10",
                subtotal="10",
            ))
            with self.assertRaises(ValueError):
                db.session.commit()
            db.session.rollback()

    def test_legacy_price_reconstruction_rejects_invalid_quantities(self):
        module_path = "migrations/versions/d9f4a5b6c7e8_cria_venda_itens.py"
        spec = importlib.util.spec_from_file_location("venda_item_migration", module_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        self.assertEqual(str(migration.validate_legacy_values(2, 10)), "5")
        for quantity, total in ((None, 10), (0, 10), (-1, 10), (1, None)):
            with self.assertRaises(ValueError):
                migration.validate_legacy_values(quantity, total)

    def test_sale_write_ignores_request_organization_id(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization = Organization.query.one()
            organization_id = organization.id
            product = Produto(
                organization_id=organization_id, nome="Produto", preco=10
            )
            db.session.add(product)
            db.session.commit()
            product_id = product.id

        fake_form = SimpleNamespace(
            produto_id=SimpleNamespace(data=str(product_id), choices=[]),
            vendedor_id=SimpleNamespace(data=""),
            quantidade=SimpleNamespace(data=1),
            vendedor_nome=SimpleNamespace(data=""),
            comprador_nome=SimpleNamespace(data="Comprador"),
            tipo_vendedor=SimpleNamespace(data="Membro"),
            status_pagamento=SimpleNamespace(data="Pendente"),
            observacao=SimpleNamespace(data=""),
            data_venda=SimpleNamespace(data=None),
            validate_on_submit=lambda: True,
        )

        from app.controllers.main import painel_vendas
        from flask_login import login_user

        with self.app.test_request_context(
            "/nova-venda",
            method="POST",
            data={"vendedor_nome": "Vendedor", "organization_id": 999999},
        ):
            login_user(db.session.get(User, user_id))
            with self.app.app_context():
                from app.core.tenancy import resolve_current_organization
                resolve_current_organization()
                with patch.object(painel_vendas, "VendaForm", return_value=fake_form):
                    painel_vendas.nova_venda()
                sale = Venda.query.one()
                item_count = VendaItem.query.filter_by(venda_id=sale.id).count()
                item_product_id = VendaItem.query.filter_by(venda_id=sale.id).one().produto_id

        self.assertEqual(sale.organization_id, organization_id)
        self.assertEqual(item_count, 1)
        self.assertEqual(item_product_id, product_id)

    def test_items_payload_rejects_empty_and_invalid_quantities(self):
        from app.controllers.main import painel_vendas

        form = self.multi_item_form()
        for payload in ([], [{"produto_id": 1, "quantidade": 0}],
                        [{"produto_id": 1, "quantidade": -1}],
                        [{"produto_id": 1}],):
            with self.app.test_request_context(
                "/nova-venda", method="POST", json={"items": payload}
            ):
                with self.assertRaises(ValueError):
                    painel_vendas._request_items(form)

    def test_duplicate_products_are_consolidated(self):
        from app.controllers.main import painel_vendas

        with self.app.test_request_context(
            "/nova-venda", method="POST",
            json={"items": [
                {"produto_id": 7, "quantidade": 2},
                {"produto_id": 7, "quantidade": 3},
            ]},
        ):
            items = painel_vendas._request_items(self.multi_item_form())
        self.assertEqual(items, [{"produto_id": 7, "quantidade": 5}])

    @staticmethod
    def multi_item_form():
        return SimpleNamespace(
            produto_id=SimpleNamespace(data=""),
            vendedor_id=SimpleNamespace(data=""),
            quantidade=SimpleNamespace(data=None),
            comprador_nome=SimpleNamespace(data="Comprador"),
            tipo_vendedor=SimpleNamespace(data="Membro"),
            status_pagamento=SimpleNamespace(data="Pendente"),
            observacao=SimpleNamespace(data=""),
            data_venda=SimpleNamespace(data=None),
            validate=lambda: True,
            validate_on_submit=lambda: True,
        )

    def test_create_sale_with_multiple_items_calculates_and_snapshots_prices(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization_id = Organization.query.one().id
            products = [
                Produto(organization_id=organization_id, nome="A", preco=10.25),
                Produto(organization_id=organization_id, nome="B", preco=3.50),
            ]
            db.session.add_all(products)
            db.session.commit()
            product_ids = [product.id for product in products]

        from app.controllers.main import painel_vendas
        from flask_login import login_user

        with self.app.test_request_context(
            "/nova-venda", method="POST",
            data={
                "items": json.dumps([
                    {"produto_id": product_ids[0], "quantidade": 2},
                    {"produto_id": product_ids[1], "quantidade": 3},
                ]),
                "vendedor_nome": "Vendedor",
            },
        ):
            login_user(db.session.get(User, user_id))
            with self.app.app_context():
                from app.core.tenancy import resolve_current_organization
                resolve_current_organization()
                with patch.object(
                    painel_vendas, "VendaForm", return_value=self.multi_item_form()
                ):
                    response = painel_vendas.nova_venda()
                sale = Venda.query.one()
                items = sorted(sale.items, key=lambda item: item.produto_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sale.quantidade, 5)
        self.assertAlmostEqual(sale.valor_total, 31.0)
        self.assertEqual(len(items), 2)
        self.assertEqual([item.quantidade for item in items], [2, 3])
        self.assertEqual([float(item.preco_unitario) for item in items], [10.25, 3.5])

    def test_gracas_sale_without_seller_type_persists_in_current_tenant(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization = Organization.query.one()
            organization.settings = {"show_seller_type": False, "theme_key": "gracas-na-mesa"}
            product = Produto(organization_id=organization.id, nome="Prato", preco=20)
            db.session.add(product)
            db.session.commit()
            product_id, organization_id = product.id, organization.id

        from app.controllers.main import painel_vendas
        from flask_login import login_user

        form = self.multi_item_form()
        form.tipo_vendedor.data = None
        with self.app.test_request_context(
            "/nova-venda", method="POST",
            data={"items": json.dumps([{"produto_id": product_id, "quantidade": 1}]),
                  "vendedor_nome": "Vendedor"},
        ):
            login_user(db.session.get(User, user_id))
            from app.core.tenancy import resolve_current_organization
            resolve_current_organization()
            with patch.object(painel_vendas, "VendaForm", return_value=form):
                response = painel_vendas.nova_venda()

        with self.app.app_context():
            sale = Venda.query.one()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(sale.organization_id, organization_id)
            self.assertEqual(sale.tipo_vendedor, "Membro")
            self.assertEqual(VendaItem.query.filter_by(venda_id=sale.id).count(), 1)

    def test_purchase_calculates_decimal_totals_for_multiple_items(self):
        with self.app.app_context():
            organization = Organization(name="Graças na Mesa")
            db.session.add(organization)
            db.session.flush()
            purchase = Compra(organization_id=organization.id, categoria="ingredientes")
            purchase.items = [
                CompraItem(organization_id=organization.id, nome="Quiabo", quantidade="3", unidade="kg", preco_unitario="14.99"),
                CompraItem(organization_id=organization.id, nome="Dendê", quantidade="2", unidade="litro", preco_unitario="9.50"),
            ]
            db.session.add(purchase)
            db.session.commit()

            self.assertEqual(purchase.valor_total, Decimal("63.970000"))
            self.assertEqual(purchase.items[0].subtotal, Decimal("44.970000"))
            self.assertIsInstance(purchase.valor_total, Decimal)

    def test_purchase_rejects_invalid_values_and_cross_tenant_items(self):
        with self.app.app_context():
            first = Organization(name="First")
            second = Organization(name="Second")
            db.session.add_all([first, second])
            db.session.flush()

            purchase = Compra(organization_id=first.id, categoria="ingredientes")
            purchase.items = [CompraItem(organization_id=second.id, nome="Quiabo", quantidade=1, unidade="kg", preco_unitario=1)]
            db.session.add(purchase)
            with self.assertRaises(ValueError):
                db.session.commit()
            db.session.rollback()

            invalid = Compra(organization_id=first.id, categoria="ingredientes")
            invalid.items = [CompraItem(organization_id=first.id, nome="Quiabo", quantidade=0, unidade="kg", preco_unitario=1)]
            db.session.add(invalid)
            with self.assertRaises(ValueError):
                db.session.commit()
            db.session.rollback()

            invalid_price = Compra(organization_id=first.id, categoria="ingredientes")
            invalid_price.items = [CompraItem(organization_id=first.id, nome="Quiabo", quantidade=1, unidade="kg", preco_unitario=0)]
            db.session.add(invalid_price)
            with self.assertRaises(ValueError):
                db.session.commit()
            db.session.rollback()

    def test_expense_settings_backfill_preserves_existing_keys(self):
        spec = importlib.util.spec_from_file_location(
            "expense_migration",
            "migrations/versions/h8c9d0e1f2a3_cria_compras_despesas.py",
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        settings = migration._merge_expense_settings(
            {"show_seller_type": False, "theme_key": "custom"}, True
        )
        self.assertEqual(settings["show_seller_type"], False)
        self.assertEqual(settings["theme_key"], "custom")
        self.assertTrue(settings["show_expenses"])
        self.assertTrue(settings["show_financial_dashboard"])

    def test_multi_item_error_rolls_back_the_entire_sale(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization_id = Organization.query.one().id
            product = Produto(organization_id=organization_id, nome="A", preco=10)
            other_org = Organization(name="Other")
            db.session.add_all([product, other_org])
            db.session.flush()
            foreign_product = Produto(
                organization_id=other_org.id, nome="Foreign", preco=20
            )
            db.session.add(foreign_product)
            db.session.commit()
            product_ids = product.id, foreign_product.id

        from app.controllers.main import painel_vendas
        from flask_login import login_user

        with self.app.test_request_context(
            "/nova-venda", method="POST",
            data={
                "items": json.dumps([
                    {"produto_id": product_ids[0], "quantidade": 1},
                    {"produto_id": product_ids[1], "quantidade": 1},
                ]),
                "vendedor_nome": "Vendedor",
            },
        ):
            login_user(db.session.get(User, user_id))
            with self.app.app_context():
                from app.core.tenancy import resolve_current_organization
                resolve_current_organization()
                with patch.object(
                    painel_vendas, "VendaForm", return_value=self.multi_item_form()
                ):
                    response = painel_vendas.nova_venda()
                self.assertEqual(response[1], 400)
                self.assertEqual(Venda.query.count(), 0)
                self.assertEqual(VendaItem.query.count(), 0)

    def test_edit_preserves_existing_price_and_supports_add_and_remove(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization_id = Organization.query.one().id
            products = [
                Produto(organization_id=organization_id, nome="A", preco=10),
                Produto(organization_id=organization_id, nome="B", preco=20),
            ]
            seller = Vendedor(organization_id=organization_id, nome="Vendedor")
            db.session.add_all([*products, seller])
            db.session.flush()
            sale = Venda(
                organization_id=organization_id, produto_id=products[0].id,
                vendedor_id=seller.id, comprador_nome="Cliente", quantidade=1,
                tipo_vendedor="Membro", status_pagamento="Pendente", valor_total=10,
            )
            db.session.add(sale)
            db.session.flush()
            sale.items.append(VendaItem(
                produto=products[0], organization_id=organization_id,
                quantidade=1, preco_unitario="8.000000", subtotal="8.000000",
            ))
            db.session.commit()
            sale_id, first_id, second_id, seller_id = (
                sale.id, products[0].id, products[1].id, seller.id
            )

        from app.controllers.main import painel_vendas
        from flask_login import login_user

        def edit(items):
            with self.app.test_request_context(
                f"/editar-venda/{sale_id}", method="POST",
                data={"items": json.dumps(items), "vendedor_id": str(seller_id)},
            ):
                login_user(db.session.get(User, user_id))
                with self.app.app_context():
                    from app.core.tenancy import resolve_current_organization
                    resolve_current_organization()
                    form = self.multi_item_form()
                    form.vendedor_id.data = str(seller.id)
                    with patch.object(painel_vendas, "VendaForm", return_value=form):
                        return painel_vendas.editar_venda(sale_id)

        edit([
            {"produto_id": first_id, "quantidade": 2},
            {"produto_id": second_id, "quantidade": 1},
        ])
        with self.app.app_context():
            sale = db.session.get(Venda, sale_id)
            self.assertEqual(len(sale.items), 2)
            self.assertEqual(float(next(i for i in sale.items if i.produto_id == first_id).preco_unitario), 8.0)
            self.assertEqual(float(next(i for i in sale.items if i.produto_id == second_id).preco_unitario), 20.0)
            self.assertAlmostEqual(sale.valor_total, 36.0)

        edit([{ "produto_id": first_id, "quantidade": 1 }])
        with self.app.app_context():
            sale = db.session.get(Venda, sale_id)
            self.assertEqual(len(sale.items), 1)
            self.assertEqual(sale.items[0].produto_id, first_id)

    def create_read_isolation_fixture(self):
        records = []
        with self.app.app_context():
            for index in (1, 2):
                user = User(
                    username=f"tenant{index}",
                    email=f"tenant{index}@example.com",
                    password_hash="x",
                )
                organization = Organization(name=f"Tenant {index}")
                db.session.add_all([user, organization])
                db.session.flush()
                membership = OrganizationUser(
                    organization_id=organization.id,
                    user_id=user.id,
                    role="member",
                    active=True,
                )
                product = Produto(
                    organization_id=organization.id,
                    nome=f"Produto {index}",
                    preco=10,
                )
                seller = Vendedor(
                    organization_id=organization.id,
                    nome=f"Vendedor {index}",
                )
                db.session.add_all([membership, product, seller])
                db.session.flush()
                sale = Venda(
                    organization_id=organization.id,
                    produto_id=product.id,
                    vendedor_id=seller.id,
                    comprador_nome=f"Cliente {index}",
                    quantidade=index,
                    tipo_vendedor="Jovem",
                    status_pagamento="Pago",
                    valor_total=10 * index,
                )
                db.session.add(sale)
                db.session.flush()
                records.append((user.id, organization.id, sale.id))
            db.session.commit()
        return records

    def test_read_apis_return_only_the_current_organization(self):
        records = self.create_read_isolation_fixture()
        user_id, organization_id, own_sale_id = records[0]
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = organization_id

            products = client.get("/buscar-produtos?q=Produto")
            sellers = client.get("/buscar-vendedores?q=Vendedor")
            sales = client.get("/api/vendas")
            foreign_detail = client.get(f"/api/vendas/{records[1][2]}")

        self.assertEqual([item["nome"] for item in products.json], ["Produto 1"])
        self.assertEqual([item["nome"] for item in sellers.json], ["Vendedor 1"])
        self.assertEqual([item["id"] for item in sales.json], [own_sale_id])
        self.assertEqual(foreign_detail.status_code, 404)

    def test_dashboard_and_reports_use_only_the_current_organization(self):
        records = self.create_read_isolation_fixture()
        user_id, organization_id, _ = records[0]
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = organization_id

            report = client.get("/api/relatorios")
            ranking = client.get("/api/ranking")
            weekly = client.get("/api/vendas-semanais")

        self.assertEqual(report.json["total_valor"], 10)
        self.assertEqual(report.json["total_vendas"], 1)
        self.assertEqual(report.json["ranking"][0]["nome"], "Vendedor 1")
        self.assertEqual(sum(weekly.json["valores"]), 10)

    def test_foreign_sale_mutations_and_exports_are_blocked(self):
        records = self.create_read_isolation_fixture()
        user_id, organization_id, _ = records[0]
        foreign_sale_id = records[1][2]
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = organization_id

            edit = client.get(f"/editar-venda/{foreign_sale_id}")
            delete = client.delete(f"/api/vendas/{foreign_sale_id}")
            payment = client.post(
                f"/api/vendas/{foreign_sale_id}/status/pagamento"
            )
            delivery = client.post(f"/api/vendas/{foreign_sale_id}/entrega")
            export_response = client.get("/exportar-vendas")

        self.assertEqual(edit.status_code, 404)
        self.assertEqual(delete.status_code, 404)
        self.assertEqual(payment.status_code, 404)
        self.assertEqual(delivery.status_code, 404)
        self.assertEqual(export_response.status_code, 200)
        with ZipFile(BytesIO(export_response.data)) as workbook:
            shared_strings = workbook.read("xl/sharedStrings.xml")
        self.assertIn(b"Cliente 1", shared_strings)
        self.assertNotIn(b"Cliente 2", shared_strings)

    def test_admin_crud_expenses_is_tenant_scoped_and_atomic(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization = Organization.query.one()
            organization.settings = {"show_expenses": True}
            OrganizationUser.query.one().role = "admin"
            db.session.commit()
            organization_id = organization.id
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
            response = client.post("/despesas/nova", json={"categoria": "ingredientes", "status": "pago", "fornecedor": "Fornecedor A", "organization_id": 999, "items": [{"nome": "Quiabo", "quantidade": "3", "unidade": "kg", "preco_unitario": "14.99"}, {"nome": "Dendê", "quantidade": "2", "unidade": "litro", "preco_unitario": "9.50"}]})
            self.assertEqual(response.status_code, 201)
            purchase_id = response.json["id"]
            self.assertEqual(response.json["valor_total"], "63.970000")
            invalid = client.post("/despesas/nova", json={"categoria": "ingredientes", "items": [{"nome": "Erro", "quantidade": "0", "unidade": "kg", "preco_unitario": "1"}]})
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(Compra.query.count(), 1)
            self.assertEqual(client.get(f"/despesas/{purchase_id}").status_code, 200)
            cancelled = client.post(f"/despesas/{purchase_id}/cancelar")
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(cancelled.json["status"], "cancelado")
            self.assertEqual(client.get("/despesas?status=cancelado", headers={"Accept": "application/json"}).json[0]["id"], purchase_id)
            self.assertEqual(Compra.query.one().organization_id, organization_id)

    def test_expense_member_and_cross_tenant_access_are_blocked(self):
        user_id = self.create_user_with_memberships(membership_count=2)
        with self.app.app_context():
            organizations = Organization.query.order_by(Organization.id).all()
            for organization in organizations:
                organization.settings = {"show_expenses": True}
            db.session.commit()
            foreign = Compra(organization_id=organizations[1].id, categoria="outros")
            foreign.items = [CompraItem(organization_id=organizations[1].id, nome="Material", quantidade=1, unidade="unidade", preco_unitario=1)]
            db.session.add(foreign)
            db.session.commit()
            foreign_id = foreign.id
            current_organization_id = organizations[0].id
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = current_organization_id
            self.assertEqual(client.post("/despesas/nova", json={"categoria": "outros", "items": []}).status_code, 403)
            self.assertEqual(client.get(f"/despesas/{foreign_id}").status_code, 404)

    def test_expense_filters_and_disabled_setting(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization = Organization.query.one()
            OrganizationUser.query.one().role = "admin"
            organization.settings = {"show_expenses": True}
            db.session.commit()
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
            for supplier, category, status, date in (("A", "ingredientes", "pago", "2026-09-01T00:00:00+00:00"), ("B", "limpeza", "pendente", "2026-08-01T00:00:00+00:00")):
                response = client.post("/despesas/nova", json={"fornecedor": supplier, "categoria": category, "status": status, "data_compra": date, "items": [{"nome": "X", "quantidade": 1, "unidade": "unidade", "preco_unitario": 1}]})
                self.assertEqual(response.status_code, 201)
            headers = {"Accept": "application/json"}
            self.assertEqual(len(client.get("/despesas?categoria=ingredientes", headers=headers).json), 1)
            self.assertEqual(len(client.get("/despesas?fornecedor=A", headers=headers).json), 1)
            self.assertEqual(len(client.get("/despesas?status=pendente", headers=headers).json), 1)
            self.assertEqual(len(client.get("/despesas?data_inicial=2026-09-01&data_final=2026-09-30", headers=headers).json), 1)
            organization = Organization.query.one()
            organization.settings = {"show_expenses": False}
            db.session.commit()
            self.assertEqual(client.get("/despesas").status_code, 403)

    def test_expense_ui_respects_tenant_setting_and_role(self):
        user_id = self.create_user_with_memberships(membership_count=2)
        with self.app.app_context():
            organizations = Organization.query.order_by(Organization.id).all()
            organizations[0].settings = {"show_expenses": True}
            organizations[1].settings = {"show_expenses": False}
            db.session.commit()
            enabled_id, disabled_id = organizations[0].id, organizations[1].id
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = enabled_id
            enabled = client.get("/despesas")
            self.assertEqual(enabled.status_code, 200)
            self.assertIn(b"Despesas", enabled.data)
            self.assertNotIn(b"+ Nova despesa", enabled.data)
            with client.session_transaction() as browser_session:
                browser_session["organization_id"] = disabled_id
            self.assertEqual(client.get("/despesas").status_code, 403)

    def test_price_history_normalizes_names_keeps_units_and_excludes_cancelled(self):
        user_id = self.create_user_with_memberships(membership_count=2)
        with self.app.app_context():
            organizations = Organization.query.order_by(Organization.id).all()
            organizations[0].settings = {"show_expenses": True}
            organizations[1].settings = {"show_expenses": True}
            db.session.commit()
            current_id = organizations[0].id
            for name, unit, price, date, status in (
                ("Quiabo", "kg", "5.00", "2026-09-10T00:00:00+00:00", "pago"),
                (" QUIABO ", "kg", "8.90", "2026-09-17T00:00:00+00:00", "pago"),
                ("quiabo", "kg", "14.99", "2026-09-24T00:00:00+00:00", "pago"),
                ("Quiabo", "unidade", "3.50", "2026-09-24T00:00:00+00:00", "pago"),
                ("QUIABO", "kg", "99.00", "2026-09-25T00:00:00+00:00", "cancelado"),
            ):
                purchase = Compra(organization_id=current_id, data_compra=datetime.fromisoformat(date), categoria="ingredientes", status=status)
                purchase.items = [CompraItem(organization_id=current_id, nome=name, quantidade=1, unidade=unit, preco_unitario=price)]
                db.session.add(purchase)
            foreign = Compra(organization_id=organizations[1].id, categoria="ingredientes")
            foreign.items = [CompraItem(organization_id=organizations[1].id, nome="Quiabo", quantidade=1, unidade="kg", preco_unitario=1)]
            db.session.add(foreign)
            db.session.commit()
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
                browser_session["organization_id"] = current_id
            response = client.get("/despesas/historico?material=quiabo&unidade=kg", headers={"Accept": "application/json"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json), 1)
        result = response.json[0]
        self.assertEqual(result["ultimo_preco"], "14.990000")
        self.assertEqual(result["menor_preco"], "5.000000")
        self.assertEqual(result["maior_preco"], "14.990000")
        self.assertEqual(result["preco_medio"], "9.63")
        self.assertEqual(result["variacao_percentual"], "68.43")
        self.assertEqual(len(result["registros"]), 3)

    def test_restaurant_dashboard_aggregates_sales_payments_and_paid_expenses(self):
        user_id = self.create_user_with_memberships()
        with self.app.app_context():
            organization = Organization.query.one()
            organization.settings = {"dashboard_mode": "restaurant", "show_financial_dashboard": True, "theme_key": "gracas-na-mesa", "app_display_name": "Graças na Mesa"}
            OrganizationUser.query.one().role = "admin"
            product = Produto(organization_id=organization.id, nome="Prato", preco=20)
            seller = Vendedor(organization_id=organization.id, nome="Vendedor")
            db.session.add_all([product, seller])
            db.session.flush()
            sale = Venda(organization_id=organization.id, produto_id=product.id, vendedor_id=seller.id, comprador_nome="Cliente", quantidade=2, tipo_vendedor="Membro", status_pagamento="Pendente", valor_total=40)
            sale.items = [VendaItem(organization_id=organization.id, produto_id=product.id, quantidade=2, preco_unitario=20, subtotal=40)]
            sale.pagamentos = [VendaPagamento(organization_id=organization.id, forma_pagamento="pix", valor=20, status="confirmado")]
            expense = Compra(organization_id=organization.id, categoria="ingredientes", status="pago")
            expense.items = [CompraItem(organization_id=organization.id, nome="Quiabo", quantidade=1, unidade="kg", preco_unitario=7)]
            db.session.add_all([sale, expense])
            db.session.commit()
        with self.app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session["_user_id"] = str(user_id)
            response = client.get("/api/dashboard-financeiro?data_inicial=2026-01-01&data_final=2026-12-31")
            home = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["cards"]["billing"], "40.0")
        self.assertEqual(response.json["cards"]["received"], "20.000000")
        self.assertEqual(response.json["cards"]["receivable"], "20.000000")
        self.assertEqual(response.json["cards"]["expenses"], "7.000000")
        self.assertEqual(response.json["cards"]["result"], "13.000000")
        self.assertEqual(home.status_code, 200)
        self.assertIn("Graças na Mesa".encode(), home.data)
        self.assertIn('data-theme="gracas-na-mesa"'.encode(), home.data)

    def test_restaurant_dashboard_filter_script_handles_empty_and_repeated_ranges(self):
        with open("app/static/js/base/dashboard_restaurante.js", encoding="utf-8") as script:
            source = script.read()
        self.assertIn('period.value === "previous"', source)
        self.assertIn('period.value === "custom"', source)
        self.assertIn('charts.get(id)?.destroy()', source)
        self.assertNotIn("chart.canvas.id", source)
        self.assertIn('data.daily || { sales: [], expenses: [] }', source)

    def test_operational_period_converts_salvador_midnight_to_utc(self):
        local_start, local_end = period_local_naive_bounds(date(2026, 9, 24), date(2026, 9, 24))
        utc_start, utc_end = period_utc_naive_bounds(date(2026, 9, 24), date(2026, 9, 24))
        self.assertEqual((local_start, local_end), (datetime(2026, 9, 24), datetime(2026, 9, 25)))
        self.assertEqual((utc_start, utc_end), (datetime(2026, 9, 24, 3), datetime(2026, 9, 25, 3)))
        self.assertTrue(local_start <= datetime(2026, 9, 24, 23, 59) < local_end)
        self.assertFalse(local_start <= datetime(2026, 9, 25, 0, 1) < local_end)
        self.assertTrue(utc_start <= datetime(2026, 9, 25, 1, 33) < utc_end)
        self.assertFalse(utc_start <= datetime(2026, 9, 25, 3, 1) < utc_end)

if __name__ == "__main__":
    unittest.main()
