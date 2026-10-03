"""Grid-sweep (lawnmower) baseline: the area is split into one vertical strip per drone,
each flown as back-and-forth lanes one sensor-width apart. Ignores the probability map."""
from __future__ import annotations

import numpy as np

from planner.nofly import DEFAULT_ZONES, MARGIN_M, route
from sim.world import SIZE_M


def lawnmower(n_drones, strip_w_m=50.0, zones=DEFAULT_ZONES, start_xy=None):
    """Returns one waypoint list per drone, already routed around no-fly zones."""
    plans = []
    edges = np.linspace(0, SIZE_M, n_drones + 1)
    for i in range(n_drones):
        width = edges[i + 1] - edges[i]
        n_lanes = int(np.ceil(width / strip_w_m))   # lanes <= one strip apart: no gaps at strip borders
        lanes = edges[i] + (np.arange(n_lanes) + 0.5) * width / n_lanes
        raw = []
        for k, x in enumerate(lanes):
            ys = (strip_w_m / 2, SIZE_M - strip_w_m / 2)
            if k % 2:
                ys = ys[::-1]
            raw.append((float(x), ys[0]))
            # a lane that crosses a zone flies straight up to it and resumes on the far side
            crossings = sorted((z.y0 - MARGIN_M, z.y1 + MARGIN_M) for z in zones if z.x0 - MARGIN_M <= x <= z.x1 + MARGIN_M)
            if k % 2:
                crossings = [c[::-1] for c in crossings[::-1]]
            for y_in, y_out in crossings:
                raw += [(float(x), y_in), (float(x), y_out)]
            raw.append((float(x), ys[1]))
        pos = tuple(start_xy) if start_xy is not None else raw[0]
        wps = []
        for p in raw:
            if any(z.contains(*p) for z in zones):
                continue
            wps += route(pos, p, zones)
            pos = p
        plans.append(wps)
    return plans
