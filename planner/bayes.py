"""Bayesian search grid updates. Only planner/ code mutates the probability grid."""
from __future__ import annotations

import numpy as np


def pod_from_sweep(sweep_width_m, track_len_m, cell_area_m2):
    """Koopman random-search probability of detection for one pass over a cell."""
    return 1.0 - np.exp(-sweep_width_m * track_len_m / cell_area_m2)


def bayes_update(P, searched, pod):
    """P: probability grid (sums to 1). searched: bool mask of cells swept this pass.
    Called when the pass found nothing; searched cells lose probability, the rest gain."""
    P = P.copy()
    P[searched] *= (1.0 - pod)
    return P / P.sum()


def on_confirmed_find(P, row, col):
    """A victim confirmed in (row, col): that cell is resolved, keep searching for the rest."""
    P = P.copy()
    P[row, col] = 0.0
    s = P.sum()
    return P / s if s > 0 else P


def top_cells(P, k=500):
    """[[row, col, p], ...] sorted by p descending — the `map_update.top_cells` payload."""
    flat = np.argsort(P, axis=None)[::-1][:k]
    rows, cols = np.unravel_index(flat, P.shape)
    return [[int(r), int(c), round(float(P[r, c]), 6)] for r, c in zip(rows, cols)]
