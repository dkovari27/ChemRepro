from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Paper(Base):
    __tablename__ = "papers"

    doi: Mapped[str] = mapped_column(String(255), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    journal: Mapped[str | None] = mapped_column(String(500))
    year: Mapped[int | None] = mapped_column()
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    # Counters added 2026-08-11 for the admin papers table. Both start at 0 for
    # existing rows; there's no way to backfill history for lookups that
    # happened before these columns existed.
    search_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    ratings: Mapped[list["Rating"]] = relationship(  # noqa: F821
        "Rating", back_populates="paper", cascade="all, delete-orphan"
    )
