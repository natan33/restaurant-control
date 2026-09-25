"""Configure tenant dashboard mode and display names."""
from alembic import op
import sqlalchemy as sa

revision = "i9d0e1f2a3b4"
down_revision = "h8c9d0e1f2a3"
branch_labels = None
depends_on = None

def upgrade():
    organizations = sa.table("organizations", sa.column("id", sa.Integer()), sa.column("name", sa.String()), sa.column("settings", sa.JSON()))
    connection = op.get_bind()
    for row in connection.execute(sa.select(organizations.c.id, organizations.c.name, organizations.c.settings)).mappings():
        is_restaurant = row["name"] == "Graças na Mesa"
        settings = dict(row["settings"] or {})
        settings.setdefault("dashboard_mode", "restaurant" if is_restaurant else "church")
        settings.setdefault("show_financial_dashboard", is_restaurant)
        settings.setdefault("app_display_name", row["name"] or "Restaurant Control")
        connection.execute(organizations.update().where(organizations.c.id == row["id"]).values(settings=settings))

def downgrade():
    # Preserve settings values: users may have changed them after this migration.
    pass
