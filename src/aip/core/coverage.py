"""Coverage engine: deterministic "is this covered, and how much is payable?".

Agents may *explain* a coverage result or find the relevant clauses, but the
decision and the payable amount always come from this module.

Decisions:
- COVERED      the claim fits the policy; payable_amount is the proposed payout
- NOT_COVERED  a hard rule excludes it (outside policy period, peril not insured, exclusion)
- REFER        it may be covered, but a human must decide (late report, large amount)
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from aip.core.money import ZERO, money
from aip.core.products import (
    CLAUSE_DEDUCTIBLE,
    CLAUSE_FLOOD_ZONE_EXCLUSION,
    CLAUSE_POLICY_PERIOD,
    CLAUSE_REPORTING,
    Peril,
    ProductCode,
    get_product,
)


class CoverageDecision(StrEnum):
    COVERED = "COVERED"
    NOT_COVERED = "NOT_COVERED"
    REFER = "REFER"


@dataclass(frozen=True)
class PolicySnapshot:
    """The policy as it was in force on the event date."""

    product: ProductCode
    start_date: date
    end_date: date
    conditions_version: str
    sum_insured: Decimal | None = None
    deductible: Decimal = ZERO
    flood_zone: int | None = None


@dataclass(frozen=True)
class ClaimFacts:
    peril: Peril
    event_date: date
    reported_date: date
    claimed_amount: Decimal


@dataclass(frozen=True)
class Reason:
    code: str
    clause: str
    message: str


@dataclass(frozen=True)
class CoverageResult:
    decision: CoverageDecision
    payable_amount: Decimal
    reasons: tuple[Reason, ...]


def check_coverage(policy: PolicySnapshot, facts: ClaimFacts) -> CoverageResult:
    product = get_product(policy.product)

    def reject(code: str, clause: str, message: str) -> CoverageResult:
        return CoverageResult(CoverageDecision.NOT_COVERED, ZERO, (Reason(code, clause, message),))

    # Hard rules: any of these means the claim is not covered.
    if not policy.start_date <= facts.event_date <= policy.end_date:
        return reject(
            "outside_policy_period",
            CLAUSE_POLICY_PERIOD,
            f"Event date {facts.event_date} is outside the policy period "
            f"{policy.start_date}–{policy.end_date}",
        )

    coverage = product.coverages.get(facts.peril)
    if coverage is None:
        return reject(
            "peril_not_insured",
            product.conditions_version,
            f"Peril {facts.peril} is not insured under {product.code}",
        )

    if facts.peril is Peril.FLOOD and policy.flood_zone == 4:
        return reject(
            "flood_zone_exclusion",
            CLAUSE_FLOOD_ZONE_EXCLUSION,
            "Flood is excluded for properties in flood zone 4",
        )

    # Amount: claimed minus deductible, capped at the coverage limit.
    if coverage.fixed_limit is not None:
        limit = coverage.fixed_limit
    else:
        assert coverage.share_of_sum_insured is not None and policy.sum_insured is not None
        limit = policy.sum_insured * coverage.share_of_sum_insured
    after_deductible = max(ZERO, facts.claimed_amount - policy.deductible)
    payable = money(min(after_deductible, limit))

    if payable == ZERO:
        return reject(
            "below_deductible",
            CLAUSE_DEDUCTIBLE,
            f"Claimed amount {facts.claimed_amount} does not exceed the deductible "
            f"{policy.deductible}",
        )

    reasons = [Reason("covered", coverage.clause, f"Peril {facts.peril} is insured")]
    if policy.deductible > ZERO:
        reasons.append(
            Reason("deductible_applied", CLAUSE_DEDUCTIBLE, f"Deductible {policy.deductible} EUR")
        )
    if after_deductible > limit:
        reasons.append(
            Reason("limit_applied", coverage.clause, f"Payout capped at limit {money(limit)} EUR")
        )

    # Soft rules: possibly covered, but a human decides.
    refer: list[Reason] = []
    delay = (facts.reported_date - facts.event_date).days
    if delay > product.reporting_deadline_days:
        refer.append(
            Reason(
                "late_reporting",
                CLAUSE_REPORTING,
                f"Reported after {delay} days (deadline {product.reporting_deadline_days}); "
                "late reporting is not an automatic rejection",
            )
        )
    if facts.claimed_amount > product.auto_limit:
        refer.append(
            Reason(
                "above_auto_limit",
                product.conditions_version,
                f"Claimed amount above {product.auto_limit} EUR requires a senior handler",
            )
        )

    decision = CoverageDecision.REFER if refer else CoverageDecision.COVERED
    return CoverageResult(decision, payable, tuple(refer + reasons))
