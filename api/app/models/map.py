"""Map model — one row per map played within a match."""

from sqlalchemy import ForeignKey, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Map(Base):
    __tablename__ = "maps"
    __table_args__ = (
        Index("ix_maps_match_id_map_name", "match_id", "map_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    map_number: Mapped[int] = mapped_column(SmallInteger)
    map_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    team1_score: Mapped[int] = mapped_column(SmallInteger)
    team2_score: Mapped[int] = mapped_column(SmallInteger)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)

    match = relationship("Match", back_populates="maps")
    winner = relationship("Team", foreign_keys=[winner_id])
    player_stats = relationship("PlayerMapStat", back_populates="map")
