from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuthorNotification(Base):
    __tablename__ = "author_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doi: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    opt_out_token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    global_opted_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
