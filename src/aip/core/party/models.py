import uuid
from datetime import date, datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from aip.core.db import Base, utcnow


class Party(Base):
    """A customer: person or company. Fields marked PII are masked before any LLM call."""

    __tablename__ = "party"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16))  # person | company
    first_name: Mapped[str | None] = mapped_column(String(100))  # PII
    last_name: Mapped[str] = mapped_column(String(200))  # PII (or company name)
    birth_date: Mapped[date | None]  # PII
    national_id: Mapped[str | None] = mapped_column(String(20))  # PII: rodné číslo
    email: Mapped[str | None] = mapped_column(String(200))  # PII
    phone: Mapped[str | None] = mapped_column(String(50))  # PII
    street: Mapped[str | None] = mapped_column(String(200))  # PII
    city: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(2))  # SK | AT
    language: Mapped[str] = mapped_column(String(2))  # sk | de
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
