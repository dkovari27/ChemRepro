from datetime import datetime, timezone
from sqlalchemy import Boolean, String, Integer, ForeignKey, DateTime, CheckConstraint, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Outcome values — describes what the reviewer actually attempted
OUTCOME_VALUES = [
    "no_repro",               # Did not work on original
    "no_extension",           # Did not work on extension
    "reproduced",             # Reproduced original
    "repro_extension_failed", # Reproduced original, extension failed
    "extended",               # Extended
]

OUTCOME_LABELS = {
    "no_repro":               "Did not work on original",
    "no_extension":           "Did not work on extension",
    "reproduced":             "Reproduced original",
    "repro_extension_failed": "Reproduced original, extension failed",
    "extended":               "Extended",
}

# Which outcome values trigger which section of the form
OUTCOME_SHOWS_REPRO = {"no_repro", "reproduced", "repro_extension_failed"}
OUTCOME_SHOWS_SCOPE = {"no_extension", "repro_extension_failed", "extended"}

SCOPE_LEVELS = ["minor", "medium", "major"]
SCOPE_LEVEL_LABELS = {
    "minor":  "Minor extension",
    "medium": "Medium extension",
    "major":  "Major extension",
}


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("doi", "orcid_id", "scoring_mode", name="uq_one_rating_per_mode_per_paper"),
        # Scores are nullable — only filled when the relevant section is shown
        CheckConstraint(
            "reproducibility_score IS NULL OR reproducibility_score BETWEEN 1 AND 5",
            name="ck_repro_score",
        ),
        CheckConstraint(
            "generalisability_score IS NULL OR generalisability_score BETWEEN 1 AND 5",
            name="ck_gen_score",
        ),
        CheckConstraint(
            "nd_star IS NULL OR nd_star BETWEEN 1 AND 5",
            name="ck_nd_star",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doi: Mapped[str] = mapped_column(String(255), ForeignKey("papers.doi"), nullable=False)
    orcid_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.orcid_id"), nullable=False)

    outcome: Mapped[str | None] = mapped_column(String(30))

    # Reproducibility section (shown when OUTCOME_SHOWS_REPRO)
    reproducibility_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reproducibility_observation: Mapped[str | None] = mapped_column(Text)

    # Scope extension section (shown when OUTCOME_SHOWS_SCOPE)
    # generalisability_score kept for future numeric use; scope_level is the active field
    generalisability_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_level: Mapped[str | None] = mapped_column(String(20))  # minor / medium / major
    scope_observation: Mapped[str | None] = mapped_column(String(1000))
    modification_details: Mapped[str | None] = mapped_column(String(1000))

    # ChemRepro rating columns (scoring_mode == "new_design")
    nd_star: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nd_failure_context: Mapped[str | None] = mapped_column(String(20), nullable=True)
    career_stage_snapshot: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Scraper provenance (bot reviews only; null for human reviews)
    citing_author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_multi_target: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    source_doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # "standard" = single outcome-based score | "classic" = repro stars + outcome | "new_design" = 1-5 star
    scoring_mode: Mapped[str] = mapped_column(String(10), default="standard", server_default="standard")

    linkedin_post_draft: Mapped[str | None] = mapped_column(Text, nullable=True)

    ai_flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    pending_admin_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    substantiation_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    substantiation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    paper: Mapped["Paper"] = relationship("Paper", back_populates="ratings")  # noqa: F821
    user: Mapped["User"] = relationship("User", back_populates="ratings")  # noqa: F821
