from datetime import datetime, timezone
from sqlalchemy import Boolean, String, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doi: Mapped[str] = mapped_column(String(255), ForeignKey("papers.doi"), nullable=False)
    rating_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("ratings.id"), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("comments.id"), nullable=True, index=True)
    orcid_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.orcid_id"), nullable=False)
    content: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    ai_flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    user: Mapped["User"] = relationship("User")  # noqa: F821
    replies: Mapped[list["Comment"]] = relationship("Comment", foreign_keys=[parent_id])


class CommentLike(Base):
    __tablename__ = "comment_likes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(Integer, ForeignKey("comments.id"), nullable=False, index=True)
    orcid_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (UniqueConstraint("comment_id", "orcid_id", name="uq_comment_like"),)
