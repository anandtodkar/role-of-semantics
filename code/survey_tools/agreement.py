"""Inter-rater agreement for screening decisions and AUF scores."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Hashable, Sequence


def percent_agreement(first: Sequence[Hashable], second: Sequence[Hashable]) -> float:
    pairs = _paired(first, second)
    return sum(a == b for a, b in pairs) / len(pairs)


def _paired(first, second):
    if len(first) != len(second):
        raise ValueError("Raters must code the same units.")
    pairs = [(a, b) for a, b in zip(first, second) if a is not None and b is not None]
    if not pairs:
        raise ValueError("No units coded by both raters.")
    return pairs


def cohen_kappa(first: Sequence[Hashable], second: Sequence[Hashable],
                weights: str | None = None) -> float:
    """Cohen's kappa; weights None (nominal), 'linear' or 'quadratic' (ordinal numeric codes)."""
    pairs = _paired(first, second)
    categories = sorted({value for pair in pairs for value in pair})
    n, k = len(pairs), len(categories)
    position = {value: index for index, value in enumerate(categories)}
    observed = [[0.0] * k for _ in range(k)]
    for a, b in pairs:
        observed[position[a]][position[b]] += 1 / n
    rows = [sum(row) for row in observed]
    cols = [sum(observed[i][j] for i in range(k)) for j in range(k)]

    def weight(i: int, j: int) -> float:
        if weights is None:
            return 0.0 if i == j else 1.0
        span = (categories[-1] - categories[0]) or 1
        distance = abs(categories[i] - categories[j]) / span
        return distance if weights == "linear" else distance ** 2

    disagreement_observed = sum(weight(i, j) * observed[i][j] for i in range(k) for j in range(k))
    disagreement_expected = sum(weight(i, j) * rows[i] * cols[j] for i in range(k) for j in range(k))
    if disagreement_expected == 0:
        return 1.0
    return 1 - disagreement_observed / disagreement_expected


def krippendorff_alpha(units: Sequence[Sequence[Hashable | None]], level: str = "nominal") -> float:
    """Krippendorff's alpha; ``units`` lists each unit's codes (None for missing)."""
    values = [[value for value in unit if value is not None] for unit in units]
    values = [unit for unit in values if len(unit) >= 2]
    coincidence = Counter()
    for unit in values:
        m = len(unit)
        for a, b in combinations(range(m), 2):
            coincidence[(unit[a], unit[b])] += 1 / (m - 1)
            coincidence[(unit[b], unit[a])] += 1 / (m - 1)
    marginals = Counter()
    for (a, _), count in coincidence.items():
        marginals[a] += count
    n = sum(marginals.values())
    categories = sorted(marginals)

    def delta(a, b) -> float:
        if level == "nominal":
            return 0.0 if a == b else 1.0
        if level == "interval":
            return float(a - b) ** 2
        if level == "ordinal":
            low, high = sorted((categories.index(a), categories.index(b)))
            between = sum(marginals[categories[g]] for g in range(low, high + 1))
            return (between - (marginals[a] + marginals[b]) / 2) ** 2
        raise ValueError(f"Unknown level: {level}")

    observed = sum(count * delta(a, b) for (a, b), count in coincidence.items())
    expected = sum(marginals[a] * marginals[b] * delta(a, b)
                   for a in categories for b in categories) / (n - 1)
    if expected == 0:
        return 1.0
    return 1 - observed / expected


def disagreements(unit_ids: Sequence[str], first: Sequence[Hashable],
                  second: Sequence[Hashable]) -> list[dict]:
    return [{"unit": unit, "rater_1": a, "rater_2": b}
            for unit, a, b in zip(unit_ids, first, second)
            if a is not None and b is not None and a != b]
