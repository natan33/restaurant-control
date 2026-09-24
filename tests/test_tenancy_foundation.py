import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from flask import Flask, g, session
from flask_login import LoginManager, login_user, logout_user

from app import db
from app.core.tenancy import register_tenancy_context
from app.models.auth.user import User
from app.models.pages.gerenciamento_vendas import Produto, Venda, Vendedor
from app.models.tenancy import Organization, OrganizationUser


class TenancyFoundationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
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
        with client.session_transaction() as browser_session:
            self.assertNotIn("organization_id", browser_session)

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

        self.assertEqual(sale.organization_id, organization_id)

    def create_read_isolation_fixture(self):
        records = []
        with self.app.app_context():
            for index, product_id in enumerate((5, 6), start=1):
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
                    id=product_id,
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


if __name__ == "__main__":
    unittest.main()
