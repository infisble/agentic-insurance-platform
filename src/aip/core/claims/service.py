import uuid
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aip.core.claims.models import Claim, ClaimEvent
from aip.core.claims.state_machine import ActorType, ClaimStatus, check_transition
from aip.core.coverage import ClaimFacts, CoverageResult, check_coverage
from aip.core.errors import NotFound, ValidationFailed
from aip.core.money import ZERO, money
from aip.core.policy.service import get_policy, snapshot
from aip.core.products import Peril


class Actor(BaseModel):
    # Phase 1: supplied by the caller. Phase 3: derived from the authenticated identity
    # (ADR 0013), never trusted from the request body.
    type: ActorType
    id: str = Field(min_length=1, max_length=100)


class ClaimCreate(BaseModel):
    policy_id: uuid.UUID
    peril: Peril
    event_date: date
    description: str = Field(min_length=1, max_length=5000)
    claimed_amount: Decimal = Field(gt=0)
    channel: str = Field(default="portal", pattern="^(portal|email|phone)$")


def _claim_number(on: date) -> str:
    return f"SKD-{on.year}-{uuid.uuid4().hex[:8].upper()}"


async def _next_seq(session: AsyncSession, claim_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(ClaimEvent.seq)).where(ClaimEvent.claim_id == claim_id)
    )
    return (current or 0) + 1


async def _record(
    session: AsyncSession,
    claim: Claim,
    from_status: ClaimStatus | None,
    to_status: ClaimStatus,
    actor: Actor,
    reason: str | None,
) -> None:
    session.add(
        ClaimEvent(
            seq=await _next_seq(session, claim.id),
            claim_id=claim.id,
            from_status=from_status,
            to_status=to_status,
            actor_type=actor.type,
            actor_id=actor.id,
            reason=reason,
        )
    )


async def report_claim(
    session: AsyncSession,
    data: ClaimCreate,
    actor: Actor,
    reported_at: datetime | None = None,
) -> Claim:
    """Register a first notice of loss. `reported_at` is only for data import and seeding;
    the API always uses the current time."""
    if actor.type is ActorType.AGENT:
        # Agents create claims only through intake drafts confirmed by the customer (phase 4).
        raise ValidationFailed("Agents cannot report claims directly")
    policy = await get_policy(session, data.policy_id)
    if data.event_date > date.today():
        raise ValidationFailed("Event date cannot be in the future")
    claim = Claim(
        number=_claim_number(date.today()),
        policy_id=policy.id,
        status=ClaimStatus.RECEIVED,
        peril=data.peril,
        event_date=data.event_date,
        channel=data.channel,
        description=data.description,
        claimed_amount=money(data.claimed_amount),
    )
    if reported_at is not None:
        claim.reported_at = reported_at
    session.add(claim)
    await session.flush()
    await _record(session, claim, None, ClaimStatus.RECEIVED, actor, "Claim reported")
    await session.flush()
    return claim


async def get_claim(session: AsyncSession, claim_id: uuid.UUID) -> Claim:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise NotFound(f"Claim {claim_id} not found")
    return claim


async def list_claims(
    session: AsyncSession, status: ClaimStatus | None = None, limit: int = 100
) -> list[Claim]:
    query = select(Claim).order_by(Claim.created_at.desc()).limit(limit)
    if status is not None:
        query = query.where(Claim.status == status)
    return list(await session.scalars(query))


async def list_claims_for_policy(session: AsyncSession, policy_id: uuid.UUID) -> list[Claim]:
    await get_policy(session, policy_id)
    result = await session.scalars(
        select(Claim).where(Claim.policy_id == policy_id).order_by(Claim.event_date)
    )
    return list(result)


async def claim_events(session: AsyncSession, claim_id: uuid.UUID) -> list[ClaimEvent]:
    await get_claim(session, claim_id)
    result = await session.scalars(
        select(ClaimEvent).where(ClaimEvent.claim_id == claim_id).order_by(ClaimEvent.seq)
    )
    return list(result)


async def evaluate_coverage(session: AsyncSession, claim_id: uuid.UUID) -> CoverageResult:
    """Run the deterministic coverage engine and store the result on the claim.
    Does not change the claim status: moving the claim forward is a separate transition."""
    claim = await get_claim(session, claim_id)
    policy = await get_policy(session, claim.policy_id)
    result = check_coverage(
        snapshot(policy),
        ClaimFacts(
            peril=Peril(claim.peril),
            event_date=claim.event_date,
            reported_date=claim.reported_at.date(),
            claimed_amount=claim.claimed_amount,
        ),
    )
    claim.payable_amount = result.payable_amount
    claim.coverage = {
        "decision": result.decision.value,
        "payable_amount": str(result.payable_amount),
        "reasons": [asdict(r) for r in result.reasons],
    }
    await session.flush()
    return result


async def transition_claim(
    session: AsyncSession,
    claim_id: uuid.UUID,
    target: ClaimStatus,
    actor: Actor,
    reason: str | None = None,
    approved_amount: Decimal | None = None,
    queue: str | None = None,
) -> Claim:
    claim = await get_claim(session, claim_id)
    current = ClaimStatus(claim.status)
    check_transition(current, target, actor.type)

    if target is ClaimStatus.APPROVED:
        if claim.payable_amount is None:
            raise ValidationFailed("Run the coverage check before approving")
        if approved_amount is None or approved_amount <= ZERO:
            raise ValidationFailed("Approval requires a positive approved_amount")
        if approved_amount > claim.claimed_amount:
            raise ValidationFailed("Approved amount cannot exceed the claimed amount")
        claim.approved_amount = money(approved_amount)
    is_escalation = (
        target is ClaimStatus.AWAITING_REVIEW and current is not ClaimStatus.COVERAGE_CHECKED
    )
    if (target in (ClaimStatus.REJECTED, ClaimStatus.NEEDS_INFO) or is_escalation) and not reason:
        raise ValidationFailed(f"A reason is required for {current} → {target}")
    if queue is not None:
        claim.queue = queue

    claim.status = target
    await _record(session, claim, current, target, actor, reason)
    await session.flush()
    return claim
