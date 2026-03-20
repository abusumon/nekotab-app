"""Score normalization utilities for cross-chamber comparison.

When legislators are spread across multiple chambers, raw scores from
different scorers (with different baselines) need normalization.

Two methods supported:
- Z-SCORE: (x - mean) / std within each chamber
- PERCENTILE: rank-based percentile within each chamber
"""

from __future__ import annotations

import math


def zscore_normalize(scores: list[float]) -> list[float]:
    """Normalize scores to z-scores.

    Returns a list of z-scores in the same order as input.
    If all scores are the same (std=0), returns all zeros.

    O(n).
    """
    n = len(scores)
    if n == 0:
        return []
    mean = sum(scores) / n
    variance = sum((x - mean) ** 2 for x in scores) / n
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return [0.0] * n
    return [(x - mean) / std for x in scores]


def percentile_normalize(scores: list[float]) -> list[float]:
    """Normalize scores to percentiles (0-100).

    Uses the "less-than" percentile: what % of other scores are below this one.
    If all scores are tied, returns 50.0 for all.

    O(n log n) for sorting.
    """
    n = len(scores)
    if n == 0:
        return []
    if n == 1:
        return [50.0]

    # Create (score, original_index) pairs, sort by score
    indexed = sorted(enumerate(scores), key=lambda x: x[1])
    result = [0.0] * n

    i = 0
    while i < n:
        # Handle ties: find range of tied scores
        j = i
        while j < n and indexed[j][1] == indexed[i][1]:
            j += 1
        # Average rank for tied values
        avg_rank = (i + j - 1) / 2.0
        percentile = (avg_rank / (n - 1)) * 100.0
        for k in range(i, j):
            result[indexed[k][0]] = percentile
        i = j

    return result


def normalize_scores(
    scores: list[float], method: str = "ZSCORE"
) -> list[float]:
    """Normalize scores using the specified method.

    Args:
        scores: Raw scores to normalize.
        method: "ZSCORE" or "PERCENTILE".

    Returns:
        Normalized scores in the same order as input.
    """
    if method == "PERCENTILE":
        return percentile_normalize(scores)
    return zscore_normalize(scores)
