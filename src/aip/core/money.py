"""Money helpers. All amounts are Decimal in EUR, rounded half-up to cents."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: Decimal | int | str) -> Decimal:
    """Convert to a cent-rounded Decimal. Floats are rejected to avoid binary rounding errors."""
    if isinstance(value, float):
        raise TypeError("Use Decimal or str for money, never float")
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
