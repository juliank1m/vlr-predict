"""Add map_vetos table and picked_by column to maps.

Revision ID: 003
Revises: 002
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "map_vetos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("match_id", sa.Integer, sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("map_name", sa.String(50), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("veto_order", sa.SmallInteger, nullable=False),
    )
    op.create_index("ix_map_vetos_match_id", "map_vetos", ["match_id"])
    op.add_column("maps", sa.Column("picked_by", sa.Integer, sa.ForeignKey("teams.id"), nullable=True))


def downgrade():
    op.drop_column("maps", "picked_by")
    op.drop_index("ix_map_vetos_match_id")
    op.drop_table("map_vetos")
