from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    orcid_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("collections.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    parent: Mapped["Collection | None"] = relationship(
        "Collection", remote_side="Collection.id", back_populates="children"
    )
    children: Mapped[list["Collection"]] = relationship(
        "Collection", back_populates="parent"
    )
    saved_papers: Mapped[list["SavedPaper"]] = relationship(  # noqa: F821
        "SavedPaper", back_populates="collection"
    )
