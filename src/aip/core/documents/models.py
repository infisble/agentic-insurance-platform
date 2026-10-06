import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aip.core.db import Base, utcnow


class Document(Base):
    """A file attached to a claim. Text is extracted once at upload and cached by content hash
    (ADR 0005 L4): re-uploading the same file returns the existing record."""

    __tablename__ = "document"
    __table_args__ = (UniqueConstraint("claim_id", "sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int]
    storage_path: Mapped[str] = mapped_column(String(500))
    page_count: Mapped[int | None]
    text: Mapped[str] = mapped_column(Text)  # PII: raw document text
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
