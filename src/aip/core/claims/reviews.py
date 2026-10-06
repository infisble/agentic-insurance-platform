"""Handler feedback on agent drafts, and the quality metrics derived from it (ADR 0010).

When a handler accepts, edits or rejects an agent's draft, that verdict is the most honest
production quality signal there is: the override rate per agent, and which extracted fields
humans correct most often. Corrections also become candidates for the golden set (ADR 0011).
"""

import uuid
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import ForeignKey, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from aip.core.claims.agent_runs import AgentRun, DraftKind
from aip.core.claims.models import Claim
from aip.core.claims.service import Actor, get_claim
from aip.core.claims.state_machine import ActorType
from aip.core.db import Base, utcnow
from aip.core.errors import ValidationFailed

Verdict = Literal["accept", "edit", "reject"]
AGENT_FOR_KIND: dict[str, str] = {
    "extraction": "extraction-agent",
    "triage": "triage-agent",
    "summary": "summary-agent",
}


class DraftReview(Base):
    __tablename__ = "draft_review"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    agent: Mapped[str] = mapped_column(String(50))
    verdict: Mapped[str] = mapped_column(String(8))
    # field → {"from": agent value, "to": human value}
    corrections: Mapped[dict[str, Any]]
    comment: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(100))
    at: Mapped[datetime] = mapped_column(default=utcnow)


class ReviewCreate(BaseModel):
    kind: DraftKind
    verdict: Verdict
    corrections: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = Field(default=None, max_length=2000)
    actor: Actor


async def add_review(session: AsyncSession, claim_id: uuid.UUID, data: ReviewCreate) -> DraftReview:
    if data.actor.type is not ActorType.HUMAN:
        raise ValidationFailed("Only handlers review agent drafts")
    claim = await get_claim(session, claim_id)
    if getattr(claim, data.kind) is None:
        raise ValidationFailed(f"Claim has no {data.kind} draft to review")
    if data.verdict == "edit" and not data.corrections:
        raise ValidationFailed("An edit needs at least one correction")
    if data.verdict != "accept" and not (data.comment or data.corrections):
        raise ValidationFailed("Say what was wrong: a comment or corrections")
    review = DraftReview(
        claim_id=claim_id,
        kind=data.kind,
        agent=AGENT_FOR_KIND[data.kind],
        verdict=data.verdict,
        corrections=data.corrections,
        comment=data.comment,
        reviewer=data.actor.id,
    )
    session.add(review)
    await session.flush()
    return review


async def list_reviews(session: AsyncSession, claim_id: uuid.UUID) -> list[DraftReview]:
    result = await session.scalars(
        select(DraftReview).where(DraftReview.claim_id == claim_id).order_by(DraftReview.at)
    )
    return list(result)


async def overview(session: AsyncSession) -> dict[str, Any]:
    by_status = dict(
        (await session.execute(select(Claim.status, func.count()).group_by(Claim.status))).all()
    )
    by_queue = dict(
        (
            await session.execute(
                select(Claim.queue, func.count())
                .where(Claim.status == "AWAITING_REVIEW")
                .group_by(Claim.queue)
            )
        ).all()
    )

    runs: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"runs": 0, "failed": 0, "cost_usd": Decimal("0"), "latency_ms": 0, "cache_hits": 0}
    )
    for r in await session.scalars(select(AgentRun)):
        s = runs[r.agent]
        s["runs"] += 1
        s["failed"] += r.status == "failed"
        s["cost_usd"] += r.cost_usd
        s["latency_ms"] += r.latency_ms
        s["cache_hits"] += r.cache_hit

    verdicts: dict[str, Counter[str]] = defaultdict(Counter)
    corrected_fields: Counter[str] = Counter()
    for rv in await session.scalars(select(DraftReview)):
        verdicts[rv.agent][rv.verdict] += 1
        if rv.kind == "extraction":
            corrected_fields.update(rv.corrections.keys())

    agents = []
    for name in sorted(set(runs) | set(verdicts)):
        s, v = runs[name], verdicts[name]
        reviewed = sum(v.values())
        agents.append(
            {
                "agent": name,
                "runs": s["runs"],
                "failed": s["failed"],
                "cache_hits": s["cache_hits"],
                "cost_usd": str(s["cost_usd"]),
                "avg_cost_usd": str((s["cost_usd"] / s["runs"]).quantize(Decimal("0.000001")))
                if s["runs"]
                else "0",
                "avg_latency_ms": s["latency_ms"] // s["runs"] if s["runs"] else 0,
                "reviewed": reviewed,
                "accepted": v["accept"],
                "edited": v["edit"],
                "rejected": v["reject"],
                "override_rate": round((v["edit"] + v["reject"]) / reviewed, 3)
                if reviewed
                else None,
            }
        )
    total_cost = sum((runs[a]["cost_usd"] for a in runs), Decimal("0"))
    return {
        "claims_by_status": by_status,
        "review_queue": {k or "unassigned": v for k, v in by_queue.items()},
        "agents": agents,
        "most_corrected_fields": corrected_fields.most_common(8),
        "total_agent_cost_usd": str(total_cost),
    }
