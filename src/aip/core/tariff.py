"""Tariff engine: versioned, explainable premium calculation.

Pure functions only. Every factor applied to the base premium is returned in the
breakdown, so a handler or a customer can see exactly why a premium is what it is,
and base × factors reproduces the net premium.

Rates are illustrative mock values, not a real insurer's tariff.
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from aip.core.errors import UnderwritingReferral, ValidationFailed
from aip.core.money import money
from aip.core.products import ProductCode, Region

INSURANCE_TAX_RATE = Decimal("0.08")


class PropertyType(StrEnum):
    FLAT = "FLAT"
    HOUSE = "HOUSE"


class MotorRisk(BaseModel):
    model_config = ConfigDict(frozen=True)

    product: Literal["MOTOR_TPL"] = "MOTOR_TPL"
    engine_kw: int = Field(gt=0, le=1000)
    holder_age: int = Field(ge=18, le=110)
    region: Region
    # Bonus-malus level: negative = malus (claims history), positive = claim-free years.
    bonus_malus_level: int = Field(ge=-3, le=10)


class HouseholdRisk(BaseModel):
    model_config = ConfigDict(frozen=True)

    product: Literal["HOUSEHOLD"] = "HOUSEHOLD"
    sum_insured: Decimal = Field(gt=0)
    property_type: PropertyType
    region: Region
    flood_zone: int = Field(ge=1, le=4)
    deductible: Decimal

    @property
    def flood_excluded(self) -> bool:
        return self.flood_zone == 4


Risk = Annotated[MotorRisk | HouseholdRisk, Field(discriminator="product")]


@dataclass(frozen=True)
class Factor:
    name: str
    value: Decimal
    explanation: str


@dataclass(frozen=True)
class PremiumBreakdown:
    product: ProductCode
    tariff_version: str
    base: Decimal
    factors: tuple[Factor, ...]
    net_premium: Decimal
    tax: Decimal
    gross_premium: Decimal


@dataclass(frozen=True)
class MotorTariff:
    version: str
    effective_from: date
    base_premium: Decimal
    # (upper bound inclusive, factor); the last bound is None = open-ended.
    kw_bands: tuple[tuple[int | None, Decimal], ...]
    age_bands: tuple[tuple[int | None, Decimal], ...]  # upper bound exclusive
    region_factors: dict[Region, Decimal]
    malus_step: Decimal
    bonus_step: Decimal
    bonus_floor: Decimal


@dataclass(frozen=True)
class HouseholdTariff:
    version: str
    effective_from: date
    rate_per_mille: dict[PropertyType, Decimal]
    region_factors: dict[Region, Decimal]
    flood_zone_factors: dict[int, Decimal]
    deductible_factors: dict[Decimal, Decimal]
    minimum_net_premium: Decimal
    max_auto_sum_insured: Decimal
    min_sum_insured: Decimal


_MOTOR_2026 = MotorTariff(
    version="MTPL-2026-01",
    effective_from=date(2026, 1, 1),
    base_premium=Decimal("120"),
    kw_bands=(
        (55, Decimal("1.00")),
        (80, Decimal("1.25")),
        (110, Decimal("1.55")),
        (150, Decimal("1.90")),
        (None, Decimal("2.40")),
    ),
    age_bands=(
        (25, Decimal("1.60")),
        (30, Decimal("1.25")),
        (65, Decimal("1.00")),
        (None, Decimal("1.15")),
    ),
    region_factors={
        Region.BA: Decimal("1.30"),
        Region.TT: Decimal("1.05"),
        Region.TN: Decimal("0.95"),
        Region.NR: Decimal("1.00"),
        Region.ZA: Decimal("0.95"),
        Region.BB: Decimal("0.90"),
        Region.PO: Decimal("0.85"),
        Region.KE: Decimal("1.05"),
    },
    malus_step=Decimal("0.15"),
    bonus_step=Decimal("0.05"),
    bonus_floor=Decimal("0.50"),
)
# Previous year: same structure, lower base premium. Policies keep the version they were
# priced with, so a 2025 policy is reproducible after the 2026 tariff change.
MOTOR_TARIFFS: tuple[MotorTariff, ...] = (
    replace(
        _MOTOR_2026,
        version="MTPL-2025-01",
        effective_from=date(2025, 1, 1),
        base_premium=Decimal("110"),
    ),
    _MOTOR_2026,
)

_HOUSEHOLD_2026 = HouseholdTariff(
    version="DOM-2026-01",
    effective_from=date(2026, 1, 1),
    rate_per_mille={PropertyType.FLAT: Decimal("0.9"), PropertyType.HOUSE: Decimal("1.4")},
    region_factors={
        Region.BA: Decimal("1.10"),
        Region.TT: Decimal("1.00"),
        Region.TN: Decimal("1.00"),
        Region.NR: Decimal("1.00"),
        Region.ZA: Decimal("1.00"),
        Region.BB: Decimal("0.95"),
        Region.PO: Decimal("0.95"),
        Region.KE: Decimal("1.05"),
    },
    flood_zone_factors={
        1: Decimal("1.00"),
        2: Decimal("1.15"),
        3: Decimal("1.50"),
        4: Decimal("0.95"),  # flood is excluded in zone 4, so the premium is lower
    },
    deductible_factors={
        Decimal("50"): Decimal("1.00"),
        Decimal("100"): Decimal("0.92"),
        Decimal("200"): Decimal("0.85"),
    },
    minimum_net_premium=Decimal("25"),
    max_auto_sum_insured=Decimal("500000"),
    min_sum_insured=Decimal("5000"),
)
HOUSEHOLD_TARIFFS: tuple[HouseholdTariff, ...] = (
    replace(
        _HOUSEHOLD_2026,
        version="DOM-2025-01",
        effective_from=date(2025, 1, 1),
        rate_per_mille={PropertyType.FLAT: Decimal("0.85"), PropertyType.HOUSE: Decimal("1.3")},
    ),
    _HOUSEHOLD_2026,
)


def _select[T: (MotorTariff, HouseholdTariff)](tariffs: tuple[T, ...], on: date) -> T:
    valid = [t for t in tariffs if t.effective_from <= on]
    if not valid:
        raise ValidationFailed(f"No tariff in force on {on.isoformat()}")
    return max(valid, key=lambda t: t.effective_from)


def _band(bands: tuple[tuple[int | None, Decimal], ...], value: int, *, inclusive: bool) -> Decimal:
    for upper, factor in bands:
        if upper is None or (value <= upper if inclusive else value < upper):
            return factor
    raise AssertionError("bands must end with an open-ended entry")


def _finish(
    product: ProductCode,
    version: str,
    base: Decimal,
    factors: list[Factor],
    minimum: Decimal | None = None,
) -> PremiumBreakdown:
    raw = base
    for f in factors:
        raw *= f.value
    if minimum is not None and raw < minimum:
        factors.append(
            Factor("minimum_premium", minimum / raw, f"Minimum net premium {minimum} EUR applied")
        )
        raw = minimum
    net = money(raw)
    tax = money(net * INSURANCE_TAX_RATE)
    return PremiumBreakdown(
        product=product,
        tariff_version=version,
        base=money(base),
        factors=tuple(factors),
        net_premium=net,
        tax=tax,
        gross_premium=net + tax,
    )


def price_motor(risk: MotorRisk, on: date) -> PremiumBreakdown:
    t = _select(MOTOR_TARIFFS, on)
    level = risk.bonus_malus_level
    if level < 0:
        bm = 1 + t.malus_step * -level
        bm_text = f"Malus level {level}"
    else:
        bm = max(t.bonus_floor, 1 - t.bonus_step * level)
        bm_text = f"Bonus level {level} ({level} claim-free years)"
    factors = [
        Factor(
            "engine_power",
            _band(t.kw_bands, risk.engine_kw, inclusive=True),
            f"Engine power {risk.engine_kw} kW",
        ),
        Factor(
            "holder_age",
            _band(t.age_bands, risk.holder_age, inclusive=False),
            f"Policyholder age {risk.holder_age}",
        ),
        Factor("region", t.region_factors[risk.region], f"Region {risk.region}"),
        Factor("bonus_malus", bm, bm_text),
    ]
    return _finish(ProductCode.MOTOR_TPL, t.version, t.base_premium, factors)


def price_household(risk: HouseholdRisk, on: date) -> PremiumBreakdown:
    t = _select(HOUSEHOLD_TARIFFS, on)
    if risk.sum_insured < t.min_sum_insured:
        raise ValidationFailed(f"Sum insured must be at least {t.min_sum_insured} EUR")
    if risk.sum_insured > t.max_auto_sum_insured:
        raise UnderwritingReferral(
            f"Sum insured above {t.max_auto_sum_insured} EUR requires an underwriter"
        )
    if risk.deductible not in t.deductible_factors:
        allowed = ", ".join(str(d) for d in t.deductible_factors)
        raise ValidationFailed(f"Deductible must be one of: {allowed}")

    base = risk.sum_insured * t.rate_per_mille[risk.property_type] / 1000
    zone_text = f"Flood zone {risk.flood_zone}" + (
        " (flood excluded)" if risk.flood_excluded else ""
    )
    factors = [
        Factor("region", t.region_factors[risk.region], f"Region {risk.region}"),
        Factor("flood_zone", t.flood_zone_factors[risk.flood_zone], zone_text),
        Factor(
            "deductible", t.deductible_factors[risk.deductible], f"Deductible {risk.deductible} EUR"
        ),
    ]
    return _finish(ProductCode.HOUSEHOLD, t.version, base, factors, t.minimum_net_premium)


def price(risk: Risk, on: date) -> PremiumBreakdown:
    if isinstance(risk, MotorRisk):
        return price_motor(risk, on)
    return price_household(risk, on)
