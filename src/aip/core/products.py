"""Product catalogue.

The two products are simplified mock products *inspired by* Slovak motor third-party
liability (PZP) and household insurance. Limits, clauses and rules are illustrative,
not legal terms of any real insurer.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class ProductCode(StrEnum):
    MOTOR_TPL = "MOTOR_TPL"  # povinné zmluvné poistenie (PZP)
    HOUSEHOLD = "HOUSEHOLD"  # poistenie domácnosti


class Peril(StrEnum):
    MOTOR_TP_PROPERTY = "MOTOR_TP_PROPERTY"  # damage to a third party's property
    MOTOR_TP_INJURY = "MOTOR_TP_INJURY"  # bodily injury of a third party
    FIRE = "FIRE"
    WATER_LEAK = "WATER_LEAK"
    FLOOD = "FLOOD"
    STORM = "STORM"
    THEFT = "THEFT"


class Region(StrEnum):
    """Slovak self-governing regions (kraje)."""

    BA = "BA"
    TT = "TT"
    TN = "TN"
    NR = "NR"
    ZA = "ZA"
    BB = "BB"
    PO = "PO"
    KE = "KE"


@dataclass(frozen=True)
class Coverage:
    peril: Peril
    clause: str
    # Exactly one of the two limits is set.
    fixed_limit: Decimal | None = None
    share_of_sum_insured: Decimal | None = None


@dataclass(frozen=True)
class Product:
    code: ProductCode
    name_sk: str
    name_de: str
    conditions_version: str
    coverages: dict[Peril, Coverage]
    reporting_deadline_days: int
    # Claims above this amount always go to a senior handler.
    auto_limit: Decimal
    term_months: int = 12


MOTOR_TPL = Product(
    code=ProductCode.MOTOR_TPL,
    name_sk="Povinné zmluvné poistenie",
    name_de="Kfz-Haftpflichtversicherung",
    conditions_version="VPP-PZP-2026-01",
    coverages={
        Peril.MOTOR_TP_PROPERTY: Coverage(
            Peril.MOTOR_TP_PROPERTY, "VPP-PZP-2026-01 čl. 4 ods. 1", fixed_limit=Decimal("1300000")
        ),
        Peril.MOTOR_TP_INJURY: Coverage(
            Peril.MOTOR_TP_INJURY, "VPP-PZP-2026-01 čl. 4 ods. 2", fixed_limit=Decimal("6450000")
        ),
    },
    reporting_deadline_days=15,
    auto_limit=Decimal("10000"),
)

HOUSEHOLD = Product(
    code=ProductCode.HOUSEHOLD,
    name_sk="Poistenie domácnosti",
    name_de="Haushaltsversicherung",
    conditions_version="VPP-DOM-2026-01",
    coverages={
        Peril.FIRE: Coverage(
            Peril.FIRE, "VPP-DOM-2026-01 čl. 5 ods. 1", share_of_sum_insured=Decimal("1")
        ),
        Peril.WATER_LEAK: Coverage(
            Peril.WATER_LEAK, "VPP-DOM-2026-01 čl. 5 ods. 2", share_of_sum_insured=Decimal("1")
        ),
        Peril.FLOOD: Coverage(
            Peril.FLOOD, "VPP-DOM-2026-01 čl. 5 ods. 3", share_of_sum_insured=Decimal("0.5")
        ),
        Peril.STORM: Coverage(
            Peril.STORM, "VPP-DOM-2026-01 čl. 5 ods. 4", share_of_sum_insured=Decimal("1")
        ),
        Peril.THEFT: Coverage(
            Peril.THEFT, "VPP-DOM-2026-01 čl. 5 ods. 5", share_of_sum_insured=Decimal("0.2")
        ),
    },
    reporting_deadline_days=30,
    auto_limit=Decimal("5000"),
)

# Clause references for rules that are not tied to a single peril.
CLAUSE_POLICY_PERIOD = "čl. 3 Poistná doba"
CLAUSE_REPORTING = "čl. 8 Povinnosti poisteného — oznámenie poistnej udalosti"
CLAUSE_FLOOD_ZONE_EXCLUSION = "VPP-DOM-2026-01 čl. 6 ods. 2 — výluka: povodňová zóna 4"
CLAUSE_DEDUCTIBLE = "čl. 7 Spoluúčasť"

PRODUCTS: dict[ProductCode, Product] = {p.code: p for p in (MOTOR_TPL, HOUSEHOLD)}


def get_product(code: ProductCode) -> Product:
    return PRODUCTS[code]
