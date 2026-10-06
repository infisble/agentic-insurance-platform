import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aip.core.claims.state_machine import ClaimStatus
from aip.core.db import Base, utcnow


class Claim(Base):
    __tablename__ = "claim"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default=ClaimStatus.RECEIVED, index=True)
    peril: Mapped[str] = mapped_column(String(32))
    event_date: Mapped[date]
    reported_at: Mapped[datetime] = mapped_column(default=utcnow)
    channel: Mapped[str] = mapped_column(String(16))  # portal | email | phone
    description: Mapped[str] = mapped_column(Text)
    claimed_amount: Mapped[Decimal]
    payable_amount: Mapped[Decimal | None]  # proposed by the coverage engine
    approved_amount: Mapped[Decimal | None]  # set by a human on approval
    coverage: Mapped[dict[str, Any] | None]  # last coverage result: decision, reasons, clauses
    queue: Mapped[str | None] = mapped_column(String(32))  # set by triage
    # Agent drafts (proposals, never decisions); see aip/core/claims/agent_runs.py
    extraction: Mapped[dict[str, Any] | None]
    triage: Mapped[dict[str, Any] | None]
    summary: Mapped[dict[str, Any] | None]
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    events: Mapped[list["ClaimEvent"]] = relationship(
        back_populates="claim", order_by="ClaimEvent.seq", lazy="raise"
    )

    # Optimistic locking: concurrent updates (e.g. an agent and a handler) fail instead of
    # silently overwriting each other.
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class ClaimEvent(Base):
    """Append-only audit trail: one row per status change, with the actor."""

    __tablename__ = "claim_event"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    seq: Mapped[int]  # order within the claim
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(default=utcnow)

    claim: Mapped[Claim] = relationship(back_populates="events")
