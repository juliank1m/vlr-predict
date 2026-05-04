"""Match model — one row per series (Bo1/Bo3/Bo5)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    team1_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    team2_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    team1_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    team2_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    event: Mapped[str | None] = mapped_column(String(300), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(300), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    team1 = relationship("Team", foreign_keys=[team1_id])
    team2 = relationship("Team", foreign_keys=[team2_id])
    winner = relationship("Team", foreign_keys=[winner_id])
    maps = relationship("Map", back_populates="match")
