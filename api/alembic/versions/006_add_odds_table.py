"""Add odds table and make match scores nullable for upcoming matches."""

revision = "006"
down_revision = "005"

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "odds",
        sa.Column("match_id", sa.Integer, sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bookmaker", sa.String(50), nullable=False),
        sa.Column("team1_decimal", sa.Numeric(6, 3), nullable=False),
        sa.Column("team2_decimal", sa.Numeric(6, 3), nullable=False),
        sa.Column("fetched_at", sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint("match_id", "bookmaker"),
    )
    op.alter_column("matches", "team1_score", existing_type=sa.SmallInteger, nullable=True)
    op.alter_column("matches", "team2_score", existing_type=sa.SmallInteger, nullable=True)


def downgrade() -> None:
    op.alter_column("matches", "team2_score", existing_type=sa.SmallInteger, nullable=False)
    op.alter_column("matches", "team1_score", existing_type=sa.SmallInteger, nullable=False)
    op.drop_table("odds")
