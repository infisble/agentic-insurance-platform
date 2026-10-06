from datetime import date
from decimal import Decimal

from aip.core.coverage import ClaimFacts, CoverageDecision, PolicySnapshot, check_coverage
from aip.core.products import Peril, ProductCode

HOUSEHOLD = PolicySnapshot(
    product=ProductCode.HOUSEHOLD,
    start_date=date(2026, 1, 1),
    end_date=date(2026, 12, 31),
    conditions_version="VPP-DOM-2026-01",
    sum_insured=Decimal("50000"),
    deductible=Decimal("100"),
    flood_zone=2,
)
MOTOR = PolicySnapshot(
    product=ProductCode.MOTOR_TPL,
    start_date=date(2026, 1, 1),
    end_date=date(2026, 12, 31),
    conditions_version="VPP-PZP-2026-01",
)


def facts(
    peril=Peril.WATER_LEAK, event=date(2026, 5, 10), reported=date(2026, 5, 12), amount="1200"
) -> ClaimFacts:
    return ClaimFacts(peril, event, reported, Decimal(amount))


def codes(result) -> set[str]:
    return {r.code for r in result.reasons}


def test_covered_claim_pays_amount_minus_deductible():
    r = check_coverage(HOUSEHOLD, facts())
    assert r.decision is CoverageDecision.COVERED
    assert r.payable_amount == Decimal("1100.00")
    assert {"covered", "deductible_applied"} <= codes(r)


def test_event_outside_policy_period_is_not_covered():
    r = check_coverage(HOUSEHOLD, facts(event=date(2025, 12, 31), reported=date(2026, 1, 2)))
    assert r.decision is CoverageDecision.NOT_COVERED
    assert r.payable_amount == Decimal("0.00")
    assert codes(r) == {"outside_policy_period"}


def test_peril_not_in_product_is_not_covered():
    r = check_coverage(MOTOR, facts(peril=Peril.THEFT))
    assert r.decision is CoverageDecision.NOT_COVERED
    assert codes(r) == {"peril_not_insured"}


def test_flood_zone_4_exclusion():
    zone4 = PolicySnapshot(**{**HOUSEHOLD.__dict__, "flood_zone": 4})
    r = check_coverage(zone4, facts(peril=Peril.FLOOD))
    assert r.decision is CoverageDecision.NOT_COVERED
    assert codes(r) == {"flood_zone_exclusion"}


def test_amount_below_deductible_is_not_covered():
    r = check_coverage(HOUSEHOLD, facts(amount="80"))
    assert r.decision is CoverageDecision.NOT_COVERED
    assert codes(r) == {"below_deductible"}


def test_theft_is_capped_at_20_percent_of_sum_insured():
    # limit 50 000 × 0.2 = 10 000; above the auto-limit, so referred, but amount still computed
    r = check_coverage(HOUSEHOLD, facts(peril=Peril.THEFT, amount="14000"))
    assert r.payable_amount == Decimal("10000.00")
    assert "limit_applied" in codes(r)


def test_late_reporting_is_referred_not_rejected():
    r = check_coverage(HOUSEHOLD, facts(event=date(2026, 3, 1), reported=date(2026, 4, 20)))
    assert r.decision is CoverageDecision.REFER
    assert "late_reporting" in codes(r)
    assert r.payable_amount == Decimal("1100.00")


def test_large_claim_is_referred():
    r = check_coverage(HOUSEHOLD, facts(peril=Peril.FIRE, amount="7000"))
    assert r.decision is CoverageDecision.REFER
    assert "above_auto_limit" in codes(r)


def test_every_reason_cites_a_clause():
    for f in [
        facts(),
        facts(peril=Peril.FLOOD),
        facts(amount="80"),
        facts(event=date(2026, 3, 1), reported=date(2026, 4, 20)),
    ]:
        r = check_coverage(HOUSEHOLD, f)
        assert r.reasons
        assert all(reason.clause for reason in r.reasons)


def test_coverage_is_deterministic():
    assert check_coverage(HOUSEHOLD, facts()) == check_coverage(HOUSEHOLD, facts())
