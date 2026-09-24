import unittest

from flask import Flask, g, session
from flask_login import LoginManager, login_user, logout_user

from app import db
from app.core.tenancy import register_tenancy_context
from app.models.auth.user import User
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


if __name__ == "__main__":
    unittest.main()
