from datetime import datetime, timezone
from sqlalchemy import Boolean, String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuthorReply(Base):
    __tablename__ = "author_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doi: Mapped[str] = mapped_column(String(255), ForeignKey("papers.doi"), nullable=False)
    rating_id: Mapped[int] = mapped_column(Integer, ForeignKey("ratings.id"), nullable=False)
    author_orcid_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.orcid_id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
