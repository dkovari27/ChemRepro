from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SubmissionWarning(Base):
    """Append-only evidence log for the repeated-violation warning system.

    One row per blocked submit attempt (not per paper/user aggregate), so an
    admin can later audit whether a warning or a resulting block was fair.
    The live count per (orcid_id, doi) is derived with COUNT(*), never stored
    as a mutable running total, so this table is never rewritten after insert.

    `orcid_id` follows the same generic-identity convention used by Rating
    and Comment: a real ORCID for ORCID logins, "linkedin:xxx" for
    LinkedIn-only accounts, "local:uuid" for guests. All are covered.
    """
    __tablename__ = "submission_warnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    orcid_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.orcid_id"), nullable=False, index=True)
    doi: Mapped[str] = mapped_column(String(255), ForeignKey("papers.doi"), nullable=False, index=True)

    # "review" | "comment" | "reply"
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # The specific banned word/phrase that triggered this warning
    matched_term: Mapped[str] = mapped_column(String(200), nullable=False)
    # Snippet of the offending text, kept as evidence (truncated, not full content)
    content_snippet: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
