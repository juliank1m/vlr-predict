"""Add performance indexes for feature pipeline queries.

Revision ID: 001
Revises: None
Create Date: 2026-03-25

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Composite indexes for feature pipeline queries
    op.create_index("ix_team_elo_team_map", "team_elo", ["team_id", "map_id"])
    op.create_index("ix_player_map_stats_team_map", "player_map_stats", ["team_id", "map_id"])
    op.create_index("ix_maps_match_mapname", "maps", ["match_id", "map_name"])
    op.create_index("ix_predictions_correct", "predictions", ["correct"])
    op.create_index("ix_predictions_match", "predictions", ["match_id"])


def downgrade():
    op.drop_index("ix_predictions_match", "predictions")
    op.drop_index("ix_predictions_correct", "predictions")
    op.drop_index("ix_maps_match_mapname", "maps")
    op.drop_index("ix_player_map_stats_team_map", "player_map_stats")
    op.drop_index("ix_team_elo_team_map", "team_elo")
