"""Player map stat model — one row per player per map."""

from sqlalchemy import Float, ForeignKey, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PlayerMapStat(Base):
    __tablename__ = "player_map_stats"
    __table_args__ = (
        Index("ix_player_map_stats_team_id_map_id", "team_id", "map_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    agent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    acs: Mapped[float | None] = mapped_column(Float, nullable=True)
    kills: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    deaths: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    assists: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    kast: Mapped[float | None] = mapped_column(Float, nullable=True)
    adr: Mapped[float | None] = mapped_column(Float, nullable=True)
    hs_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_kills: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    first_deaths: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    map = relationship("Map", back_populates="player_stats")
    player = relationship("Player")
    team = relationship("Team")
