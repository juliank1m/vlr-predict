"""Add map_name column to team_elo for per-map Elo ratings.

Revision ID: 004
Revises: 003
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("team_elo", sa.Column("map_name", sa.String(50), nullable=True))
    op.create_index("ix_team_elo_team_map_name", "team_elo", ["team_id", "map_name"])


def downgrade():
    op.drop_index("ix_team_elo_team_map_name")
    op.drop_column("team_elo", "map_name")
