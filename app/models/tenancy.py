from datetime import datetime, timezone

from app import db


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    settings = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    memberships = db.relationship(
        "OrganizationUser", back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationUser(db.Model):
    __tablename__ = "organization_users"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "user_id", name="uq_organization_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    role = db.Column(db.String(40), nullable=False, default="member")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    organization = db.relationship("Organization", back_populates="memberships")
    user = db.relationship("User", backref="organization_memberships")
