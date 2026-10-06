import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from aip.core.db import Base, utcnow


class PolicyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class Policy(Base):
    __tablename__ = "policy"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    product_code: Mapped[str] = mapped_column(String(20))
    holder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("party.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default=PolicyStatus.ACTIVE)
    start_date: Mapped[date]
    end_date: Mapped[date]
    tariff_version: Mapped[str] = mapped_column(String(40))
    conditions_version: Mapped[str] = mapped_column(String(40))
    # The exact risk factors used for pricing, so the premium is reproducible later.
    risk: Mapped[dict[str, Any]]
    net_premium: Mapped[Decimal]
    tax: Mapped[Decimal]
    gross_premium: Mapped[Decimal]
    issued_at: Mapped[datetime] = mapped_column(default=utcnow)
