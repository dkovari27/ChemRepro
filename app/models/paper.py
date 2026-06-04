from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Paper(Base):
    __tablename__ = "papers"

    doi: Mapped[str] = mapped_column(String(255), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    journal: Mapped[str | None] = mapped_column(String(500))
    year: Mapped[int | None] = mapped_column()
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    ratings: Mapped[list["Rating"]] = relationship(  # noqa: F821
        "Rating", back_populates="paper", cascade="all, delete-orphan"
    )
