"""Inequality measures. Shared by the Gini Calculator (#4) and later PolicySim/TaxSim.

All functions accept an array of non-negative incomes (or wealth) and optional
weights (e.g. household size or survey weights).
"""

from __future__ import annotations

import numpy as np


def _prepare(values, weights=None) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(values, dtype=float).ravel()
    w = np.ones_like(x) if weights is None else np.asarray(weights, dtype=float).ravel()
    if x.shape != w.shape:
        raise ValueError("values and weights must have the same length")
    keep = ~(np.isnan(x) | np.isnan(w))
    x, w = x[keep], w[keep]
    if x.size == 0:
        raise ValueError("no valid observations")
    if (x < 0).any():
        raise ValueError("negative values are not supported")
    if (w <= 0).any():
        raise ValueError("weights must be positive")
    order = np.argsort(x, kind="stable")
    return x[order], w[order]


def lorenz_curve(values, weights=None) -> tuple[np.ndarray, np.ndarray]:
    """Return (population share, income share) points of the Lorenz curve, starting at (0, 0)."""
    x, w = _prepare(values, weights)
    total = (x * w).sum()
    if total == 0:
        raise ValueError("total income is zero; the Lorenz curve is undefined")
    pop = np.concatenate([[0.0], np.cumsum(w) / w.sum()])
    inc = np.concatenate([[0.0], np.cumsum(x * w) / total])
    return pop, inc


def gini(values, weights=None) -> float:
    """Gini coefficient in [0, 1): 0 = perfect equality. Trapezoid area under the Lorenz curve."""
    pop, inc = lorenz_curve(values, weights)
    area = np.trapezoid(inc, pop)
    return float(1.0 - 2.0 * area)


def group_shares(values, weights=None, groups: int = 5) -> np.ndarray:
    """Share of total income held by each of ``groups`` equal-population groups (quintiles by default)."""
    pop, inc = lorenz_curve(values, weights)
    edges = np.linspace(0.0, 1.0, groups + 1)
    return np.diff(np.interp(edges, pop, inc))


def top_share(values, weights=None, top: float = 0.1) -> float:
    """Share of total income held by the richest ``top`` fraction of the population."""
    if not 0 < top < 1:
        raise ValueError("top must be between 0 and 1")
    pop, inc = lorenz_curve(values, weights)
    return float(1.0 - np.interp(1.0 - top, pop, inc))


def palma_ratio(values, weights=None) -> float:
    """Income share of the top 10% divided by that of the bottom 40%."""
    pop, inc = lorenz_curve(values, weights)
    bottom40 = float(np.interp(0.4, pop, inc))
    top10 = float(1.0 - np.interp(0.9, pop, inc))
    return top10 / bottom40
