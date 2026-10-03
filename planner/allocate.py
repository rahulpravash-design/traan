"""Greedy multi-drone allocation: high probability, short flight, no double-booking."""
from __future__ import annotations

import numpy as np

from sim.world import cell_centers_xy, cell_to_xy

CLAIM_RADIUS_M = 75.0  # cells this close to another drone's target are taken
_CENTERS = cell_centers_xy()


def next_cell(P, drone_xy, cell_xy, claimed, alpha=1.0):
    """Greedy pick: high probability, short flight; skip cells another drone already claimed."""
    dist = np.linalg.norm(cell_xy - drone_xy, axis=-1) + 25.0
    score = P / dist**alpha
    score[claimed] = -np.inf
    return np.unravel_index(np.argmax(score), P.shape)


def claimed_mask(other_targets, blocked=None):
    m = np.zeros(_CENTERS.shape[:2], dtype=bool) if blocked is None else blocked.copy()
    for t in other_targets:
        if t is not None:
            m |= np.linalg.norm(_CENTERS - np.asarray(cell_to_xy(*t)), axis=-1) <= CLAIM_RADIUS_M
    return m


def assign(P, drone_xy, other_targets, nofly, alpha=1.0):
    """Target cell for one drone, given the cells the other drones are already heading to."""
    r, c = next_cell(P, np.asarray(drone_xy, float), _CENTERS, claimed_mask(other_targets, nofly), alpha)
    return int(r), int(c)
