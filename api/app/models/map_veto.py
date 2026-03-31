"""MapVeto model — one row per pick/ban action in a match."""

from sqlalchemy import ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MapVeto(Base):
    __tablename__ = "map_vetos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    map_name: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(10))  # "pick" or "ban"
    veto_order: Mapped[int] = mapped_column(SmallInteger)
