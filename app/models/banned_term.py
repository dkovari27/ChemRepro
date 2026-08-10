from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class BannedTerm(Base):
    """Admin-curated word/phrase blocklist. Checked alongside the hardcoded
    regex in app.utils.moderation.is_clean() and fed into the Haiku
    moderation prompt in app.utils.ai_moderation._check_content()."""
    __tablename__ = "banned_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    added_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
