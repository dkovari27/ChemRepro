from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SavedPaper(Base):
    __tablename__ = "saved_papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    orcid_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    doi: Mapped[str] = mapped_column(String(255), ForeignKey("papers.doi"), nullable=False)
    collection_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("collections.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    paper: Mapped["Paper"] = relationship("Paper")  # noqa: F821
    collection: Mapped["Collection | None"] = relationship(  # noqa: F821
        "Collection", back_populates="saved_papers"
    )

    __table_args__ = (UniqueConstraint("orcid_id", "doi", name="uq_saved_paper"),)
