"""Team Elo snapshot model — one row per team per map."""

from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TeamElo(Base):
    __tablename__ = "team_elo"
    __table_args__ = (
        Index("ix_team_elo_team_id_map_id", "team_id", "map_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id"), index=True)
    elo: Mapped[float] = mapped_column(Float)
    elo_delta: Mapped[float] = mapped_column(Float)
    map_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    team = relationship("Team")
    map = relationship("Map")
