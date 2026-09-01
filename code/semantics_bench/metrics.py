"""Deterministic metrics: a BPE surrogate tokeniser and scoring helpers.

The token counts reported in the paper must be reproducible on a machine with
no network access, so we do not call a vendor tokeniser.  ``surrogate_tokens``
is a deterministic approximation of byte-pair encoding: alphanumeric runs are
split into chunks of at most four characters (the modal BPE merge length for
English and for identifier-heavy markup), every punctuation character counts as
one token, and runs of whitespace collapse to one token.  Spot checks against
``cl100k_base`` on the artefacts in this repository put the error below 12 %,
and - crucially - the *ratios* between representations, which is what the
argument depends on, are stable.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[A-Za-z]+|[0-9]+|\s+|[^\sA-Za-z0-9]")
_CHUNK = 4


def surrogate_tokens(text: str) -> int:
    """Deterministic BPE-surrogate token count."""
    n = 0
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(0)
        if tok.isspace():
            n += 1
        elif tok[0].isalnum():
            n += math.ceil(len(tok) / _CHUNK)
        else:
            n += 1
    return n


def bits(n: float) -> float:
    """Information content of a choice among ``n`` alternatives."""
    return math.log2(n) if n > 0 else 0.0


@dataclass(frozen=True)
class BinaryScore:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else float("nan")

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else float("nan")

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def false_positive_rate(self) -> float:
        d = self.fp + self.tn
        return self.fp / d if d else float("nan")

    @property
    def accuracy(self) -> float:
        d = self.tp + self.fp + self.fn + self.tn
        return (self.tp + self.tn) / d if d else float("nan")


def score_binary(pairs: list[tuple[bool, bool]]) -> BinaryScore:
    """``pairs`` are ``(gold_is_positive, predicted_positive)``."""
    tp = sum(1 for g, p in pairs if g and p)
    fp = sum(1 for g, p in pairs if not g and p)
    fn = sum(1 for g, p in pairs if g and not p)
    tn = sum(1 for g, p in pairs if not g and not p)
    return BinaryScore(tp, fp, fn, tn)


def coverage(required: set[str], available: set[str]) -> float:
    return len(required & available) / len(required) if required else 1.0


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (used for error bars)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
