from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from aip.core.errors import UnderwritingReferral, ValidationFailed
from aip.core.money import money
from aip.core.products import Region
from aip.core.tariff import HouseholdRisk, MotorRisk, PropertyType, price

ON = date(2026, 3, 1)


def motor(**overrides) -> MotorRisk:
    base = dict(engine_kw=85, holder_age=40, region=Region.BA, bonus_malus_level=4)
    return MotorRisk(**{**base, **overrides})


def household(**overrides) -> HouseholdRisk:
    base = dict(
        sum_insured=Decimal("60000"),
        property_type=PropertyType.FLAT,
        region=Region.KE,
        flood_zone=2,
        deductible=Decimal("100"),
    )
    return HouseholdRisk(**{**base, **overrides})


class TestMotor:
    def test_reference_premium(self):
        # 120 base × 1.55 (85 kW) × 1.00 (age 40) × 1.30 (BA) × 0.80 (bonus 4) = 193.44
        # tax 8% = 15.4752 → 15.48; gross = 208.92
        b = price(motor(), ON)
        assert b.tariff_version == "MTPL-2026-01"
        assert b.net_premium == Decimal("193.44")
        assert b.tax == Decimal("15.48")
        assert b.gross_premium == Decimal("208.92")

    def test_breakdown_reproduces_net_premium(self):
        b = price(motor(), ON)
        product = b.base
        for f in b.factors:
            product *= f.value
        assert money(product) == b.net_premium

    def test_every_factor_is_explained(self):
        b = price(motor(), ON)
        names = {f.name for f in b.factors}
        assert names == {"engine_power", "holder_age", "region", "bonus_malus"}
        assert all(f.explanation for f in b.factors)

    def test_young_driver_pays_more(self):
        assert price(motor(holder_age=22), ON).net_premium > price(motor(), ON).net_premium

    @pytest.mark.parametrize(
        ("kw", "factor"), [(55, "1.00"), (56, "1.25"), (110, "1.55"), (111, "1.90"), (151, "2.40")]
    )
    def test_engine_band_boundaries_are_inclusive(self, kw, factor):
        b = price(motor(engine_kw=kw), ON)
        assert next(f.value for f in b.factors if f.name == "engine_power") == Decimal(factor)

    def test_malus_increases_premium(self):
        # malus -2 → 1 + 0.15 × 2 = 1.30
        b = price(motor(bonus_malus_level=-2), ON)
        assert next(f.value for f in b.factors if f.name == "bonus_malus") == Decimal("1.30")

    def test_bonus_has_floor(self):
        # bonus 10 → max(0.50, 1 - 0.05 × 10) = 0.50
        b = price(motor(bonus_malus_level=10), ON)
        assert next(f.value for f in b.factors if f.name == "bonus_malus") == Decimal("0.50")

    def test_under_18_is_invalid(self):
        with pytest.raises(ValidationError):
            motor(holder_age=17)

    def test_tariff_version_is_selected_by_start_date(self):
        assert price(motor(), date(2025, 12, 31)).tariff_version == "MTPL-2025-01"
        assert price(motor(), date(2026, 1, 1)).tariff_version == "MTPL-2026-01"

    def test_older_tariff_uses_its_own_base(self):
        # 110 × 1.55 × 1.00 × 1.30 × 0.80 = 177.32
        assert price(motor(), date(2025, 6, 1)).net_premium == Decimal("177.32")

    def test_no_tariff_before_first_version(self):
        with pytest.raises(ValidationFailed):
            price(motor(), date(2024, 12, 31))


class TestHousehold:
    def test_reference_premium(self):
        # 60 000 × 0.9‰ = 54.00 × 1.05 (KE) × 1.15 (zone 2) × 0.92 (deductible 100)
        # = 59.9886 → 59.99; tax 4.7992 → 4.80; gross 64.79
        b = price(household(), ON)
        assert b.net_premium == Decimal("59.99")
        assert b.tax == Decimal("4.80")
        assert b.gross_premium == Decimal("64.79")

    def test_minimum_premium_applies(self):
        b = price(household(sum_insured=Decimal("5000"), deductible=Decimal("200")), ON)
        assert b.net_premium == Decimal("25.00")
        assert b.factors[-1].name == "minimum_premium"

    def test_flood_zone_4_is_cheaper_because_flood_is_excluded(self):
        assert (
            price(household(flood_zone=4), ON).net_premium
            < price(household(flood_zone=1), ON).net_premium
        )

    def test_large_sum_insured_is_referred_to_underwriter(self):
        with pytest.raises(UnderwritingReferral):
            price(household(sum_insured=Decimal("750000")), ON)

    def test_unknown_deductible_is_rejected(self):
        with pytest.raises(ValidationFailed):
            price(household(deductible=Decimal("75")), ON)
