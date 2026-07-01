from datetime import datetime, timezone
from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reporter_orcid_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.orcid_id"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "review" | "comment" | "user"
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)   # rating_id, comment_id, or orcid_id
    reason: Mapped[str | None] = mapped_column(String(500))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
