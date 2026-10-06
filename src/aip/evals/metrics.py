"""Metrics with uncertainty. Small golden sets make point estimates misleading, so every
rate is reported with a bootstrap 95% confidence interval over documents."""

import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Rate:
    hits: int
    total: int
    low: float
    high: float

    @property
    def value(self) -> float:
        return self.hits / self.total if self.total else float("nan")

    def __str__(self) -> str:
        if not self.total:
            return "n/a"
        return f"{self.value:.1%} [{self.low:.1%}–{self.high:.1%}] (n={self.total})"


def bootstrap_rate(
    per_unit: Sequence[tuple[int, int]], iterations: int = 2000, seed: int = 0
) -> Rate:
    """per_unit: (hits, total) per document. Resampling documents, not fields, respects that
    fields of one document are correlated."""
    hits = sum(h for h, _ in per_unit)
    total = sum(t for _, t in per_unit)
    if not per_unit or total == 0:
        return Rate(hits, total, float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(per_unit)
    samples = []
    for _ in range(iterations):
        pick = [per_unit[rng.randrange(n)] for _ in range(n)]
        t = sum(x[1] for x in pick)
        if t:
            samples.append(sum(x[0] for x in pick) / t)
    samples.sort()
    return Rate(
        hits, total, samples[int(0.025 * len(samples))], samples[int(0.975 * len(samples)) - 1]
    )
