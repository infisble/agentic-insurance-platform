"""Durable job queue on the core database (ADR 0004).

A job is inserted in the same transaction as the change that makes it necessary (a document
uploaded to a RECEIVED claim, a claim returned from NEEDS_INFO), so there is no dual write: the
job exists if and only if the change was committed. Workers lease jobs through the core API,
retries back off exponentially, and a job that keeps failing ends as `dead` with the claim
escalated to a human. Nothing is lost silently.

Postgres claims a job with `FOR UPDATE SKIP LOCKED`; SQLite (local development) serialises
writers, and the conditional update below keeps both correct with several workers.
"""

import uuid
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import ForeignKey, String, Text, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from aip.core.claims.models import Claim
from aip.core.claims.service import Actor, transition_claim
from aip.core.claims.state_machine import ActorType, ClaimStatus
from aip.core.db import Base, utcnow
from aip.core.errors import DomainError, NotFound, ValidationFailed

PROCESS_CLAIM = "process_claim"
SWEEPER = Actor(type=ActorType.SYSTEM, id="job-sweeper")
# Claims that sit in a mid-pipeline status longer than this were abandoned by a worker.
STUCK_AFTER = timedelta(minutes=15)
_MID_PIPELINE = (ClaimStatus.EXTRACTED, ClaimStatus.TRIAGED, ClaimStatus.COVERAGE_CHECKED)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    DEAD = "dead"  # failed max_attempts times; the claim was escalated to a human


class Job(Base):
    __tablename__ = "job"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32))
    queue: Mapped[str] = mapped_column(String(16), default="llm")
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claim.id"), index=True)
    status: Mapped[str] = mapped_column(String(12), default=JobStatus.QUEUED, index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    run_after: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    locked_by: Mapped[str | None] = mapped_column(String(100))
    locked_until: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class LeaseRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)
    lease_seconds: int = Field(default=300, ge=10, le=3600)


class JobResult(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)
    error: str | None = Field(default=None, max_length=4000)


def backoff(attempts: int) -> timedelta:
    """10 s, 40 s, 160 s, … capped at 30 minutes."""
    return min(timedelta(seconds=10 * 4 ** max(attempts - 1, 0)), timedelta(minutes=30))


def _naive(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; compare everything in naive UTC.
    return dt.replace(tzinfo=None)


async def enqueue_claim(
    session: AsyncSession, claim_id: uuid.UUID, delay: timedelta = timedelta(0)
) -> Job:
    """Queue processing for a claim. Idempotent: while a job for the claim is still queued,
    a new request only pushes its start back (debounce, e.g. several documents uploaded)."""
    run_after = utcnow() + delay
    pending = await session.scalar(
        select(Job).where(
            Job.claim_id == claim_id, Job.kind == PROCESS_CLAIM, Job.status == JobStatus.QUEUED
        )
    )
    if pending is not None:
        if _naive(pending.run_after) < _naive(run_after):
            pending.run_after = run_after
        await session.flush()
        return pending
    job = Job(kind=PROCESS_CLAIM, claim_id=claim_id, run_after=run_after)
    session.add(job)
    await session.flush()
    return job


async def lease_next(session: AsyncSession, req: LeaseRequest) -> Job | None:
    now = utcnow()
    for _ in range(5):  # another worker may win the race for a row; try the next one
        job_id = await session.scalar(
            select(Job.id)
            .where(Job.status == JobStatus.QUEUED, Job.run_after <= now)
            .order_by(Job.run_after)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job_id is None:
            return None
        result = await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
            .values(
                status=JobStatus.RUNNING,
                attempts=Job.attempts + 1,
                locked_by=req.worker_id,
                locked_until=now + timedelta(seconds=req.lease_seconds),
                updated_at=now,
            )
        )
        if result.rowcount == 1:  # type: ignore[attr-defined]
            job = await session.get(Job, job_id, populate_existing=True)
            return job
    return None


async def _owned(session: AsyncSession, job_id: uuid.UUID, worker_id: str) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise NotFound(f"Job {job_id} not found")
    if job.status != JobStatus.RUNNING or job.locked_by != worker_id:
        raise ValidationFailed(f"Job {job_id} is not leased by {worker_id}")
    return job


async def complete(session: AsyncSession, job_id: uuid.UUID, res: JobResult) -> Job:
    job = await _owned(session, job_id, res.worker_id)
    job.status, job.locked_by, job.locked_until = JobStatus.DONE, None, None
    await session.flush()
    return job


async def _escalate(session: AsyncSession, claim_id: uuid.UUID | None, reason: str) -> bool:
    if claim_id is None:
        return False
    claim = await session.get(Claim, claim_id)
    if claim is None:
        return False
    try:
        await transition_claim(session, claim_id, ClaimStatus.AWAITING_REVIEW, SWEEPER, reason)
    except DomainError:
        return False  # already with a human, decided, or waiting for the customer
    return True


async def _retry_or_bury(session: AsyncSession, job: Job, error: str) -> None:
    job.last_error = error[:4000]
    job.locked_by, job.locked_until = None, None
    if job.attempts < job.max_attempts:
        job.status = JobStatus.QUEUED
        job.run_after = utcnow() + backoff(job.attempts)
    else:
        job.status = JobStatus.DEAD
        await _escalate(
            session,
            job.claim_id,
            f"Automatic processing failed {job.attempts}× ({error[:300]}); please handle manually",
        )
    await session.flush()


async def fail(session: AsyncSession, job_id: uuid.UUID, res: JobResult) -> Job:
    job = await _owned(session, job_id, res.worker_id)
    await _retry_or_bury(session, job, res.error or "unknown error")
    return job


async def sweep(session: AsyncSession, stuck_after: timedelta = STUCK_AFTER) -> dict[str, int]:
    """Reconciliation: recover jobs whose worker died, and hand claims abandoned mid-pipeline
    to a human. Safe to run from any number of workers at any time."""
    now = utcnow()
    expired = list(
        await session.scalars(
            select(Job).where(Job.status == JobStatus.RUNNING, Job.locked_until < now)
        )
    )
    for job in expired:
        await _retry_or_bury(session, job, f"lease expired (worker {job.locked_by})")

    active = select(Job.claim_id).where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
    stuck = await session.scalars(
        select(Claim.id).where(
            Claim.status.in_(_MID_PIPELINE),
            Claim.updated_at < now - stuck_after,
            Claim.id.not_in(active.where(Job.claim_id.is_not(None))),
        )
    )
    escalated = 0
    for claim_id in list(stuck):
        reason = f"Stuck in processing for more than {int(stuck_after.total_seconds() // 60)} min"
        escalated += await _escalate(session, claim_id, reason)
    return {"requeued_or_dead": len(expired), "escalated": escalated}


async def list_jobs(
    session: AsyncSession, status: JobStatus | None = None, limit: int = 100
) -> list[Job]:
    query = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if status is not None:
        query = query.where(Job.status == status)
    return list(await session.scalars(query))


async def stats(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(select(Job.status, func.count()).group_by(Job.status))
    counts = {s.value: 0 for s in JobStatus}
    counts.update({status: n for status, n in rows.all()})
    return counts
