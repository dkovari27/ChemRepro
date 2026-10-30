import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LibraryNote(Base):
    """One private note on a saved paper. A saved paper can have many."""
    __tablename__ = "library_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    saved_paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("saved_papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orcid_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    saved_paper: Mapped["SavedPaper"] = relationship(  # noqa: F821
        "SavedPaper", back_populates="library_notes"
    )


class LibraryFile(Base):
    """A private uploaded file (PDF or image) attached to a saved paper.

    The bytes live on disk under settings.LIBRARY_DIR as <uuid><ext>; only
    metadata is in the database. The client-supplied name is display-only and
    never used to build a path.
    """
    __tablename__ = "library_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4())
    )
    saved_paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("saved_papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orcid_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # "pdf" | "image"
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    original_name: Mapped[str] = mapped_column(String(200), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(60), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    saved_paper: Mapped["SavedPaper"] = relationship(  # noqa: F821
        "SavedPaper", back_populates="library_files"
    )
