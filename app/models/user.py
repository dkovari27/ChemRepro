from datetime import datetime, timezone
from sqlalchemy import Boolean, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

CAREER_STAGES = [
    "PhD student",
    "Postdoc",
    "Industry / CRO chemist",
    "Academic PI",
    "Independent researcher",
    "Prefer not to say",
    "Data curation agent",
]


class User(Base):
    __tablename__ = "users"

    orcid_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    nickname: Mapped[str | None] = mapped_column(String(60), nullable=True)
    notification_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    career_stage: Mapped[str | None] = mapped_column(String(60), nullable=True)
    career_stage_set: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    pledge_accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    linkedin_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    orcid_real: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    # Site-wide posting block, set automatically after 3 logged warnings on any
    # one paper (see app.models.submission_warning.SubmissionWarning). Cleared
    # only by an admin, from /admin/submission-warnings.
    submission_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    ratings: Mapped[list["Rating"]] = relationship(  # noqa: F821
        "Rating", back_populates="user", cascade="all, delete-orphan"
    )
