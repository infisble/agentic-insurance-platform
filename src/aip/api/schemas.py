"""API response schemas. Request schemas live next to their services."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aip.core.claims.service import Actor
from aip.core.claims.state_machine import ClaimStatus
from aip.core.tariff import Risk


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PartyOut(ORM):
    id: uuid.UUID
    kind: str
    first_name: str | None
    last_name: str
    birth_date: date | None
    email: str | None
    city: str | None
    country: str
    language: str
    # national_id is deliberately not returned by default: least exposure of PII.


class FactorOut(BaseModel):
    name: str
    value: Decimal
    explanation: str


class PremiumOut(BaseModel):
    product: str
    tariff_version: str
    base: Decimal
    factors: list[FactorOut]
    net_premium: Decimal
    tax: Decimal
    gross_premium: Decimal


class QuoteRequest(BaseModel):
    risk: Risk
    start_date: date


class PolicyCreate(BaseModel):
    holder_id: uuid.UUID
    risk: Risk
    start_date: date


class PolicyOut(ORM):
    id: uuid.UUID
    number: str
    product_code: str
    holder_id: uuid.UUID
    status: str
    start_date: date
    end_date: date
    tariff_version: str
    conditions_version: str
    risk: dict[str, Any]
    net_premium: Decimal
    tax: Decimal
    gross_premium: Decimal


class PolicyIssued(BaseModel):
    policy: PolicyOut
    premium: PremiumOut


class CancelRequest(BaseModel):
    on: date


class ClaimOut(ORM):
    id: uuid.UUID
    number: str
    policy_id: uuid.UUID
    status: ClaimStatus
    peril: str
    event_date: date
    reported_at: datetime
    channel: str
    description: str
    claimed_amount: Decimal
    payable_amount: Decimal | None
    approved_amount: Decimal | None
    coverage: dict[str, Any] | None
    queue: str | None
    extraction: dict[str, Any] | None
    triage: dict[str, Any] | None
    summary: dict[str, Any] | None
    version: int


class ReasonOut(BaseModel):
    code: str
    clause: str
    message: str


class CoverageOut(BaseModel):
    decision: str
    payable_amount: Decimal
    reasons: list[ReasonOut]


class TransitionRequest(BaseModel):
    target: ClaimStatus
    actor: Actor
    reason: str | None = Field(default=None, max_length=2000)
    approved_amount: Decimal | None = None
    queue: str | None = Field(default=None, max_length=32)


class ClaimEventOut(ORM):
    seq: int
    from_status: str | None
    to_status: str
    actor_type: str
    actor_id: str
    reason: str | None
    at: datetime


class AllowedTransitionsOut(BaseModel):
    current: ClaimStatus
    actor_type: str
    targets: list[ClaimStatus]


class DocumentOut(ORM):
    id: uuid.UUID
    claim_id: uuid.UUID
    filename: str
    content_type: str
    sha256: str
    size: int
    page_count: int | None
    created_at: datetime


class DocumentTextOut(DocumentOut):
    text: str


class AgentRunOut(ORM):
    id: uuid.UUID
    agent: str
    agent_version: str
    model: str
    status: str
    turns: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: Decimal
    latency_ms: int
    cache_hit: bool
    error: str | None
    created_at: datetime


class ReviewOut(ORM):
    id: uuid.UUID
    kind: str
    agent: str
    verdict: str
    corrections: dict[str, Any]
    comment: str | None
    reviewer: str
    at: datetime


class JobOut(ORM):
    id: uuid.UUID
    kind: str
    queue: str
    claim_id: uuid.UUID | None
    status: str
    attempts: int
    max_attempts: int
    run_after: datetime
    locked_by: str | None
    last_error: str | None
    created_at: datetime


class HolderPII(ORM):
    """Only for the agent orchestrator, which needs the values to mask them (ADR 0012).
    Phase 3: restricted to the orchestrator's service identity."""

    first_name: str | None
    last_name: str
    birth_date: date | None
    national_id: str | None
    email: str | None
    phone: str | None
    street: str | None
    city: str | None
    language: str


class ClaimContextOut(BaseModel):
    claim: ClaimOut
    policy: PolicyOut
    holder: HolderPII
    documents: list[DocumentOut]
