from datetime import datetime, timezone
from sqlalchemy import String, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (
        UniqueConstraint("rating_id", "orcid_id", name="uq_one_like_per_user_per_rating"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rating_id: Mapped[int] = mapped_column(Integer, ForeignKey("ratings.id"), nullable=False)
    orcid_id: Mapped[str] = mapped_column(String(20), ForeignKey("users.orcid_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
