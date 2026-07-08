import uuid
from datetime import datetime, timezone
from sqlalchemy import String, LargeBinary, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UploadedImage(Base):
    __tablename__ = "uploaded_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False,
                                      default=lambda: str(uuid.uuid4()))
    uploader_orcid_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
