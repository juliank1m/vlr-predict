"""Add rounds table for round-by-round data."""

revision = "005"
down_revision = "004"

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "rounds",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("map_id", sa.Integer, sa.ForeignKey("maps.id"), nullable=False),
        sa.Column("round_number", sa.SmallInteger, nullable=False),
        sa.Column("winner_team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("team1_side", sa.String(5), nullable=True),
        sa.Column("win_type", sa.String(10), nullable=True),
        sa.Column("team1_score_after", sa.SmallInteger, nullable=False),
        sa.Column("team2_score_after", sa.SmallInteger, nullable=False),
    )
    op.create_index("ix_rounds_map_id", "rounds", ["map_id"])


def downgrade() -> None:
    op.drop_index("ix_rounds_map_id")
    op.drop_table("rounds")
