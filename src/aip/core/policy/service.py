import uuid
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aip.core.coverage import PolicySnapshot
from aip.core.errors import NotFound, ValidationFailed
from aip.core.money import ZERO
from aip.core.party.service import get_party
from aip.core.policy.models import Policy, PolicyStatus
from aip.core.products import ProductCode, get_product
from aip.core.tariff import HouseholdRisk, MotorRisk, PremiumBreakdown, Risk, price

_risk_adapter: TypeAdapter[Risk] = TypeAdapter(Risk)


def parse_risk(data: dict) -> Risk:
    return _risk_adapter.validate_python(data)


def _policy_number(product: ProductCode, on: date) -> str:
    prefix = {ProductCode.MOTOR_TPL: "PZP", ProductCode.HOUSEHOLD: "DOM"}[product]
    return f"{prefix}-{on.year}-{uuid.uuid4().hex[:8].upper()}"


def quote(risk: Risk, start_date: date) -> PremiumBreakdown:
    return price(risk, start_date)


async def issue_policy(
    session: AsyncSession,
    holder_id: uuid.UUID,
    risk: Risk,
    start_date: date,
    number: str | None = None,
) -> tuple[Policy, PremiumBreakdown]:
    """Issue a policy. The premium is always recomputed here; client-supplied amounts are
    never trusted. `number` is only for data import and seeding (not exposed in the API)."""
    await get_party(session, holder_id)
    product = get_product(ProductCode(risk.product))
    breakdown = price(risk, start_date)
    policy = Policy(
        number=number or _policy_number(product.code, start_date),
        product_code=product.code,
        holder_id=holder_id,
        status=PolicyStatus.ACTIVE,
        start_date=start_date,
        end_date=start_date + relativedelta(months=product.term_months, days=-1),
        tariff_version=breakdown.tariff_version,
        conditions_version=product.conditions_version,
        risk=risk.model_dump(mode="json"),
        net_premium=breakdown.net_premium,
        tax=breakdown.tax,
        gross_premium=breakdown.gross_premium,
    )
    session.add(policy)
    await session.flush()
    return policy, breakdown


async def get_policy(session: AsyncSession, policy_id: uuid.UUID) -> Policy:
    policy = await session.get(Policy, policy_id)
    if policy is None:
        raise NotFound(f"Policy {policy_id} not found")
    return policy


async def list_policies_for_party(session: AsyncSession, party_id: uuid.UUID) -> list[Policy]:
    result = await session.scalars(select(Policy).where(Policy.holder_id == party_id))
    return list(result)


async def cancel_policy(session: AsyncSession, policy_id: uuid.UUID, on: date) -> Policy:
    policy = await get_policy(session, policy_id)
    if policy.status != PolicyStatus.ACTIVE:
        raise ValidationFailed(f"Policy is {policy.status}, only ACTIVE can be cancelled")
    if not policy.start_date <= on <= policy.end_date:
        raise ValidationFailed("Cancellation date must be within the policy period")
    policy.status = PolicyStatus.CANCELLED
    policy.end_date = on
    await session.flush()
    return policy


def snapshot(policy: Policy) -> PolicySnapshot:
    risk = parse_risk(policy.risk)
    sum_insured: Decimal | None = None
    deductible = ZERO
    flood_zone: int | None = None
    if isinstance(risk, HouseholdRisk):
        sum_insured, deductible, flood_zone = risk.sum_insured, risk.deductible, risk.flood_zone
    else:
        assert isinstance(risk, MotorRisk)
    return PolicySnapshot(
        product=ProductCode(policy.product_code),
        start_date=policy.start_date,
        end_date=policy.end_date,
        conditions_version=policy.conditions_version,
        sum_insured=sum_insured,
        deductible=deductible,
        flood_zone=flood_zone,
    )
