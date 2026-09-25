from flask import abort, current_app, g, request, session
from flask_login import current_user

from app import db
from app.models.tenancy import Organization, OrganizationUser

DEFAULT_TENANCY_EXEMPT_ENDPOINTS = {
    "auth.login",
    "auth.logout",
    "auth.perfil",
    "auth.redefinir_senha",
    "tenancy.select_organization",
    "auth.selecionar_organizacao",
    "tenancy.onboarding",
}


def get_current_organization():
    """Return the validated organization for the current request."""
    return getattr(g, "current_organization", None)


def _active_memberships():
    return (
        OrganizationUser.query.join(Organization)
        .filter(
            OrganizationUser.user_id == current_user.id,
            OrganizationUser.active.is_(True),
            Organization.is_active.is_(True),
        )
        .order_by(Organization.id)
        .all()
    )


def resolve_current_organization():
    memberships = _active_memberships()
    if not memberships:
        session.pop("organization_id", None)
        abort(403)

    selected_id = session.get("organization_id")
    membership = next(
        (item for item in memberships if item.organization_id == selected_id), None
    )
    if membership is None:
        session.pop("organization_id", None)
        if len(memberships) > 1:
            abort(409)
        membership = memberships[0]
        session["organization_id"] = membership.organization_id

    g.current_organization = membership.organization
    g.current_organization_membership = membership
    from app.core.organization_settings import get_organization_settings
    g.organization_settings = get_organization_settings(membership.organization)
    return membership.organization


def select_current_organization(organization_id):
    """Select an organization only when the user has an active membership."""
    membership = (
        OrganizationUser.query.join(Organization)
        .filter(
            OrganizationUser.user_id == current_user.id,
            OrganizationUser.organization_id == organization_id,
            OrganizationUser.active.is_(True),
            Organization.is_active.is_(True),
        )
        .first()
    )
    if membership is None:
        abort(403)

    session["organization_id"] = membership.organization_id
    g.current_organization = membership.organization
    g.current_organization_membership = membership
    from app.core.organization_settings import get_organization_settings
    g.organization_settings = get_organization_settings(membership.organization)
    return membership.organization


def register_tenancy_context(app):
    app.config.setdefault(
        "TENANCY_EXEMPT_ENDPOINTS", DEFAULT_TENANCY_EXEMPT_ENDPOINTS.copy()
    )

    @app.before_request
    def load_tenancy_context():
        if (
            not current_user.is_authenticated
            or request_is_tenancy_exempt()
        ):
            return None
        resolve_current_organization()
        return None


def request_is_tenancy_exempt():
    exempt_endpoints = current_app.config.get("TENANCY_EXEMPT_ENDPOINTS", set())
    return request.endpoint in exempt_endpoints
