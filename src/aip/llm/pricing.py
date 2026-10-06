"""List prices in USD per million tokens (Anthropic first-party API, as of 2026-09).

Thinking tokens are billed as output and are included in `output_tokens`.
Cache writes (5-minute TTL) cost 1.25x input; cache reads are listed separately.
"""

from dataclasses import dataclass
from decimal import Decimal

M = Decimal(1_000_000)


@dataclass(frozen=True)
class Price:
    input: Decimal
    output: Decimal
    cache_read: Decimal

    @property
    def cache_write(self) -> Decimal:
        return self.input * Decimal("1.25")


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(Decimal("4"), Decimal("20"), Decimal("0.20")),
    "claude-sonnet-5-5": Price(Decimal("2"), Decimal("10"), Decimal("0.20")),
    "claude-haiku-4-5": Price(Decimal("1"), Decimal("5"), Decimal("0.10")),
}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens


def cost_usd(model: str, usage: Usage) -> Decimal:
    price = PRICES.get(model)
    if price is None:
        return Decimal("0")  # unknown model: cost is reported as 0, never guessed
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    ) / M
    return total.quantize(Decimal("0.000001"))
