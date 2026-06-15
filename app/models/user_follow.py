from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class UserFollow(Base):
    __tablename__ = "user_follows"
    __table_args__ = (UniqueConstraint("follower_orcid_id", "followed_orcid_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    follower_orcid_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.orcid_id"), nullable=False, index=True
    )
    followed_orcid_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.orcid_id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
