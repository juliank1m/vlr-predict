"""Team model."""

from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    first_seen: Mapped[date | None] = mapped_column(Date, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
