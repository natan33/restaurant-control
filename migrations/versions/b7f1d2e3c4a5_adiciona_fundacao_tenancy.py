"""Add the tenancy foundation.

Revision ID: b7f1d2e3c4a5
Revises: 07d4343cd8ee
"""

from alembic import op
import sqlalchemy as sa


revision = "b7f1d2e3c4a5"
down_revision = "07d4343cd8ee"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "organization_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False, server_default="member"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_user"),
    )
    with op.batch_alter_table("organization_users", schema=None) as batch_op:
        batch_op.create_index("ix_organization_users_organization_id", ["organization_id"])
        batch_op.create_index("ix_organization_users_user_id", ["user_id"])

    connection = op.get_bind()
    organization_id = connection.execute(
        sa.text(
            "INSERT INTO organizations (name, is_active, created_at) "
            "VALUES (:name, true, CURRENT_TIMESTAMP) RETURNING id"
        ),
        {"name": "MIGRAÇÃO - organização temporária"},
    ).scalar_one()
    connection.execute(
        sa.text(
            "INSERT INTO organization_users "
            "(organization_id, user_id, role, active, created_at) "
            "SELECT :organization_id, id, 'member', true, CURRENT_TIMESTAMP FROM users"
        ),
        {"organization_id": organization_id},
    )


def downgrade():
    with op.batch_alter_table("organization_users", schema=None) as batch_op:
        batch_op.drop_index("ix_organization_users_user_id")
        batch_op.drop_index("ix_organization_users_organization_id")
    op.drop_table("organization_users")
    op.drop_table("organizations")
