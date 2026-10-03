"""Fixed no-fly zones and routing around them.

50% build: zones are rectangles (defined in WGS84, converted to local metres). Routing is a
visibility graph over the zone corners, so a straight leg that would clip a zone detours around it.
Live re-planning with zones added mid-mission is post-50%.
"""
from __future__ import annotations

import heapq

import numpy as np

from sim.world import N_CELLS, cell_centers_xy, latlon_to_xy, xy_to_latlon

MARGIN_M = 15.0


class Zone:
    def __init__(self, name, x0, y0, x1, y1):
        self.name = name
        self.x0, self.y0, self.x1, self.y1 = min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    @classmethod
    def from_latlon(cls, name, south, west, north, east):
        xa, ya = latlon_to_xy(south, west)
        xb, yb = latlon_to_xy(north, east)
        return cls(name, float(xa), float(ya), float(xb), float(yb))

    def contains(self, x, y, pad=0.0):
        return (self.x0 - pad <= x <= self.x1 + pad) and (self.y0 - pad <= y <= self.y1 + pad)

    def corners(self, pad):
        return [(self.x0 - pad, self.y0 - pad), (self.x1 + pad, self.y0 - pad),
                (self.x1 + pad, self.y1 + pad), (self.x0 - pad, self.y1 + pad)]

    def to_geojson(self):
        ring = [list(xy_to_latlon(x, y))[::-1] for x, y in self.corners(0)]
        ring = [[float(a), float(b)] for a, b in ring]
        return {"type": "Feature", "properties": {"name": self.name},
                "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}}

    def segment_hits(self, a, b):
        """Liang-Barsky: does segment a->b pass through the zone interior?"""
        (ax, ay), (bx, by) = a, b
        dx, dy = bx - ax, by - ay
        t0, t1 = 0.0, 1.0
        for p, q in ((-dx, ax - self.x0), (dx, self.x1 - ax), (-dy, ay - self.y0), (dy, self.y1 - ay)):
            if abs(p) < 1e-12:
                if q < 0:
                    return False
            else:
                t = q / p
                if p < 0:
                    t0 = max(t0, t)
                else:
                    t1 = min(t1, t)
                if t0 > t1:
                    return False
        return t1 - t0 > 1e-9


# A fixed zone in the north-east of the grid (stand-in for a helipad / HT line corridor).
# Replace with the real zone from the district authority when F has it.
DEFAULT_ZONES = [Zone("helipad-corridor", 1350.0, 1250.0, 1650.0, 1550.0)]


def nofly_mask(zones=DEFAULT_ZONES):
    centers = cell_centers_xy()
    m = np.zeros((N_CELLS, N_CELLS), dtype=bool)
    for z in zones:
        m |= ((centers[..., 0] >= z.x0) & (centers[..., 0] <= z.x1) &
              (centers[..., 1] >= z.y0) & (centers[..., 1] <= z.y1))
    return m


def _clear(a, b, zones):
    return not any(z.segment_hits(a, b) for z in zones)


def route(a, b, zones=DEFAULT_ZONES):
    """Shortest list of waypoints from a to b (excluding a, including b) that avoids every zone."""
    a, b = tuple(map(float, a)), tuple(map(float, b))
    if _clear(a, b, zones):
        return [b]
    nodes = [a, b] + [c for z in zones for c in z.corners(MARGIN_M)
                      if not any(o.contains(*c) for o in zones)]
    dist = {0: 0.0}
    prev = {}
    pq = [(0.0, 0)]
    while pq:
        d, i = heapq.heappop(pq)
        if i == 1:
            break
        if d > dist.get(i, np.inf):
            continue
        for j in range(len(nodes)):
            if j != i and _clear(nodes[i], nodes[j], zones):
                nd = d + float(np.hypot(nodes[j][0] - nodes[i][0], nodes[j][1] - nodes[i][1]))
                if nd < dist.get(j, np.inf):
                    dist[j], prev[j] = nd, i
                    heapq.heappush(pq, (nd, j))
    if 1 not in prev:
        return [b]  # target unreachable (e.g. inside a zone) — callers must not target zone cells
    path, i = [], 1
    while i != 0:
        path.append(nodes[i])
        i = prev[i]
    return path[::-1]
