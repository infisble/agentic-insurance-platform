from decimal import Decimal

import pytest

from aip.core.money import money


def test_rounds_half_up_to_cents():
    assert money(Decimal("1.005")) == Decimal("1.01")
    assert money("2.344") == Decimal("2.34")


def test_float_is_rejected():
    with pytest.raises(TypeError):
        money(0.1)  # type: ignore[arg-type]
