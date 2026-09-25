"""Add centralized organization settings."""
from alembic import op
import sqlalchemy as sa

revision = "g7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("organizations", sa.Column("settings", sa.JSON(), nullable=True))
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE organizations SET settings = :default WHERE settings IS NULL"), {"default": '{"show_seller_type": true, "theme_key": "default"}'})
    connection.execute(sa.text("UPDATE organizations SET settings = :gracas WHERE name = :name"), {"gracas": '{"show_seller_type": false, "theme_key": "gracas-na-mesa"}', "name": "Graças na Mesa"})
    op.alter_column("organizations", "settings", nullable=False)

def downgrade():
    op.drop_column("organizations", "settings")
