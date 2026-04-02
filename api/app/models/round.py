"""Round model — one row per round played within a map."""

from sqlalchemy import ForeignKey, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Round(Base):
    __tablename__ = "rounds"
    __table_args__ = (
        Index("ix_rounds_map_id", "map_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id"))
    round_number: Mapped[int] = mapped_column(SmallInteger)
    winner_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    team1_side: Mapped[str | None] = mapped_column(String(5), nullable=True)
    win_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    team1_score_after: Mapped[int] = mapped_column(SmallInteger)
    team2_score_after: Mapped[int] = mapped_column(SmallInteger)
