"""Odds model — one row per (match, bookmaker)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Odds(Base):
    __tablename__ = "odds"

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    bookmaker: Mapped[str] = mapped_column(String(50), primary_key=True)
    team1_decimal: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    team2_decimal: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
