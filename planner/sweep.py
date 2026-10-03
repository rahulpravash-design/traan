"""Sensor-strip geometry: which cells a drone's thermal footprint covers as it flies.

Shared by the planner (negative-information updates), the fast sim (detection draws) and the
mock fleet, so the benchmark measures exactly the sweep model the live loop uses.
"""
from __future__ import annotations

import numpy as np

from sim.world import N_CELLS, cell_centers_xy

SEARCH_ALT_M = 60.0                         # search altitude above home
SENSOR_STRIP_M = 50.0                       # footprint width at that altitude
_CENTERS = cell_centers_xy()
_FLAT = _CENTERS.reshape(-1, 2)


def swept_cells(a, b, half_width=SENSOR_STRIP_M / 2):
    """Cells whose centre is within half the sensor strip of the flown segment a->b."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ab = b - a
    L2 = float(ab @ ab)
    if L2 < 1e-9:
        d = np.linalg.norm(_CENTERS - a, axis=-1)
    else:
        t = np.clip(((_CENTERS - a) @ ab) / L2, 0.0, 1.0)
        d = np.linalg.norm(_CENTERS - (a + t[..., None] * ab), axis=-1)
    return d <= half_width


def swept_polyline(pts, half_width=SENSOR_STRIP_M / 2):
    pts = [np.asarray(p, float) for p in pts]
    if len(pts) == 1:
        return swept_cells(pts[0], pts[0], half_width)
    m = np.zeros((N_CELLS, N_CELLS), bool)
    for a, b in zip(pts[:-1], pts[1:]):
        m |= swept_cells(a, b, half_width)
    return m


def swept_fan(a, ends, half_width=SENSOR_STRIP_M / 2):
    """Vectorised swept masks for K straight legs a->ends[k]. Returns bool (K, N_CELLS*N_CELLS)."""
    a = np.asarray(a, float)
    ab = np.asarray(ends, float) - a                      # (K, 2)
    L2 = np.maximum((ab ** 2).sum(-1), 1e-9)               # (K,)
    C = _FLAT - a                                          # (M, 2)
    t = np.clip((C @ ab.T) / L2, 0.0, 1.0)                 # (M, K)
    dx = C[:, 0:1] - t * ab[:, 0]
    dy = C[:, 1:2] - t * ab[:, 1]
    return (dx * dx + dy * dy <= half_width ** 2).T        # (K, M)


class SweepTracker:
    """Per-drone record of what the strip has covered, so a cell counts once per PASS:
    it has to leave the strip before a later pass over it counts again."""

    def __init__(self, n):
        self.prev = [np.zeros((N_CELLS, N_CELLS), bool) for _ in range(n)]
        self.last = [None] * n

    def track(self, i, pts):
        """Drone i flew the polyline pts since the last call. Returns the newly swept cells."""
        swept = swept_polyline(pts)
        newly = swept & ~self.prev[i]
        self.prev[i] = swept
        self.last[i] = np.asarray(pts[-1], float)
        return newly

    def move_to(self, i, xy):
        """Live telemetry: drone i is now at xy."""
        return self.track(i, [xy] if self.last[i] is None else [self.last[i], xy])

    def lift(self, i):
        """Drone i is on the ground / climbing: its camera isn't searching. Forget the track, so the
        first searching fix counts only its own footprint, not a segment from where it climbed."""
        self.prev[i][:] = False
        self.last[i] = None
