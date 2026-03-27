"""Add logo_url column to teams table.

Revision ID: 002
Revises: 001
Create Date: 2026-03-26

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("teams", sa.Column("logo_url", sa.String(500), nullable=True))


def downgrade():
    op.drop_column("teams", "logo_url")
