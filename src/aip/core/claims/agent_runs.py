"""Agent outputs on a claim: drafts (extraction, triage, summary) and the run log.

Agent outputs are stored as *proposals* next to the claim. They never change amounts or
decisions; a handler sees them in the CRM and accepts, edits or rejects them.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import ForeignKey, Numeric, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from aip.core.claims.service import Actor, get_claim
from aip.core.claims.state_machine import ActorType
from aip.core.db import Base, utcnow
from aip.core.errors import ValidationFailed

DraftKind = Literal["extraction", "triage", "summary"]


class AgentRun(Base):
    """One agent execution: what ran, on which model and prompt version, at what cost."""

    __tablename__ = "agent_run"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id"), index=True)
    agent: Mapped[str] = mapped_column(String(50))
    agent_version: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(16))  # ok | failed
    turns: Mapped[int]
    tool_calls: Mapped[int]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    cache_read_tokens: Mapped[int]
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int]
    cache_hit: Mapped[bool]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AgentRunCreate(BaseModel):
    agent: str = Field(max_length=50)
    agent_version: str = Field(max_length=20)
    model: str = Field(max_length=60)
    status: Literal["ok", "failed"]
    turns: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    latency_ms: int = 0
    cache_hit: bool = False
    error: str | None = None


class DraftUpdate(BaseModel):
    actor: Actor
    payload: dict[str, Any]


async def save_draft(
    session: AsyncSession, claim_id: uuid.UUID, kind: DraftKind, update: DraftUpdate
) -> None:
    if update.actor.type is ActorType.CUSTOMER:
        raise ValidationFailed("Customers cannot write agent drafts")
    claim = await get_claim(session, claim_id)
    setattr(claim, kind, {**update.payload, "_by": f"{update.actor.type}:{update.actor.id}"})
    await session.flush()


async def record_run(session: AsyncSession, claim_id: uuid.UUID, data: AgentRunCreate) -> AgentRun:
    await get_claim(session, claim_id)
    run = AgentRun(claim_id=claim_id, **data.model_dump())
    session.add(run)
    await session.flush()
    return run


async def list_runs(session: AsyncSession, claim_id: uuid.UUID) -> list[AgentRun]:
    result = await session.scalars(
        select(AgentRun).where(AgentRun.claim_id == claim_id).order_by(AgentRun.created_at)
    )
    return list(result)
