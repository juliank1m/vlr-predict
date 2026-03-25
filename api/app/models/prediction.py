"""Prediction model — stores model outputs for evaluation."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_correct", "correct"),
        Index("ix_predictions_match_id", "match_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    map_id: Mapped[int | None] = mapped_column(ForeignKey("maps.id"), nullable=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    team1_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team2_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    map_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    team1_win_prob: Mapped[float] = mapped_column(Float)
    predicted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    model_version: Mapped[str] = mapped_column(String(50))
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    team1 = relationship("Team", foreign_keys=[team1_id])
    team2 = relationship("Team", foreign_keys=[team2_id])
