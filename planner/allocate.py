"""Multi-drone allocation.

Two strategies, both greedy and both avoiding double-booking:

* ``assign`` (mode "cell", the original): fly to the cell with the best P / distance.
  Simple, but once the map flattens it crawls in short overlapping hops and covers only
  ~40% of the area in an hour (see bench/ ablation), which is what sinks it when the prior is wrong.
* ``assign_leg`` (mode "path", default): score every candidate LEG by the probability its
  sensor strip sweeps per metre flown, P(swept) * POD / (length + 25 m). It still races to a
  confident hotspot, but on a flat map it prefers long legs through unsearched ground.
"""
from __future__ import annotations

import numpy as np

from planner.nofly import route
from planner.sweep import _CENTERS, swept_cells, swept_fan, swept_polyline
from sim.world import N_CELLS, cell_to_xy

CLAIM_RADIUS_M = 75.0  # mode "cell": cells this close to another drone's target are taken
N_NEAR, N_RICH = 48, 24  # mode "path": candidate endpoints (best P/distance, best P)
_STANDOFF_M = 25.0       # keeps the score finite and stops very short hops from winning


def next_cell(P, drone_xy, cell_xy, claimed, alpha=1.0):
    """Greedy pick: high probability, short flight; skip cells another drone already claimed."""
    dist = np.linalg.norm(cell_xy - drone_xy, axis=-1) + _STANDOFF_M
    score = P / dist**alpha
    score[claimed] = -np.inf
    return np.unravel_index(np.argmax(score), P.shape)


def claimed_mask(other_targets, blocked=None):
    m = np.zeros(_CENTERS.shape[:2], dtype=bool) if blocked is None else blocked.copy()
    for t in other_targets:
        if t is not None:
            m |= np.linalg.norm(_CENTERS - np.asarray(cell_to_xy(*t)), axis=-1) <= CLAIM_RADIUS_M
    return m


def assign(P, drone_xy, other_targets, blocked, alpha=1.0):
    """Mode "cell": target cell for one drone, given the cells the other drones are heading to."""
    r, c = next_cell(P, np.asarray(drone_xy, float), _CENTERS, claimed_mask(other_targets, blocked), alpha)
    return int(r), int(c)


def assign_leg(P, drone_xy, blocked, zones, pod, other_paths=()):
    """Mode "path": returns (target_cell, waypoints, swept_mask) for one drone.

    other_paths: swept masks of the legs the other drones are already committed to; that
    probability is treated as spoken for, so drones spread out instead of shadowing each other.
    """
    xy = np.asarray(drone_xy, float)
    Pv = P.copy()
    for m in other_paths:
        if m is not None:
            Pv[m] = 0.0
    here = swept_cells(xy, xy)                      # cells in the footprint right now: being seen already,
    Pv[here] = 0.0                                   # so no leg gets credit for them (else short hops win)
    ok = ~(blocked | here)                           # and never re-pick them as an endpoint
    if not ok.any():
        ok = ~blocked
    d = np.linalg.norm(_CENTERS - xy, axis=-1)
    near = np.where(ok, Pv / (d + _STANDOFF_M), -1.0).ravel()
    rich = np.where(ok, Pv, -1.0).ravel()
    cand = np.unique(np.concatenate([np.argsort(near)[-N_NEAR:], np.argsort(rich)[-N_RICH:]]))
    cand = cand[ok.ravel()[cand]]
    rows, cols = np.unravel_index(cand, P.shape)
    ends = np.stack(cell_to_xy(rows, cols), axis=-1)

    masks = swept_fan(xy, ends)                      # straight legs, all candidates at once
    lengths = np.linalg.norm(ends - xy, axis=-1)
    legs = [[tuple(e)] for e in ends]
    for k, e in enumerate(ends):                     # the few legs that clip a no-fly zone get routed
        if any(z.segment_hits(xy, e) for z in zones):
            wps = route(xy, e, zones)
            pts = [xy] + [np.asarray(w) for w in wps]
            masks[k] = swept_polyline(pts).ravel()
            lengths[k] = sum(float(np.linalg.norm(b - a)) for a, b in zip(pts[:-1], pts[1:]))
            legs[k] = wps
    score = (masks @ Pv.ravel()) * pod / (lengths + _STANDOFF_M)
    k = int(np.argmax(score))
    return (int(rows[k]), int(cols[k])), legs[k], masks[k].reshape(N_CELLS, N_CELLS)
