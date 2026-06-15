from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class NameSuggestion(Base):
    __tablename__ = "name_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    votes: Mapped[list["NameVote"]] = relationship("NameVote", back_populates="suggestion", passive_deletes=True)


class NameVote(Base):
    __tablename__ = "name_votes"
    __table_args__ = (UniqueConstraint("suggestion_id", "voter_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    suggestion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("name_suggestions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    voter_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    suggestion: Mapped["NameSuggestion"] = relationship("NameSuggestion", back_populates="votes")
