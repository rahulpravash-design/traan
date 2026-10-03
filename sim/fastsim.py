"""Fast 2D benchmark sim: point-mass drones, a sensor strip, no PX4.

Settings follow the benchmark rules in CLAUDE.md: 8 m/s, 60 m altitude (implicit),
50 m sensor strip. Detection of a victim is a coin flip with POD_TRUE each time a drone's
strip newly passes over the victim's cell — deliberately a bit worse than the planner's
own Koopman POD model, so the planner is not scored against its own assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from planner.baseline import lawnmower
from planner.service import Planner, swept_cells
from sim.scenario import Scenario, victim_cells
from sim.world import HOME_XY, N_CELLS

SPEED_MPS = 8.0
DT_S = 4.0
T_MAX_S = 3600.0
POD_TRUE = 0.80
FIND_WINDOW_S = 1200.0  # "% of victims found within 20 minutes"


@dataclass
class RunResult:
    seed: int
    method: str
    prior: str
    n_victims: int
    ttff_s: float          # time to first find; NaN if nothing found before T_MAX_S
    found_20min: int
    found_total: int

    @property
    def frac_20min(self):
        return self.found_20min / self.n_victims


def _advance(pos, queue, budget):
    """Move along the waypoint queue by `budget` metres. Returns new pos and the polyline flown."""
    pts = [pos.copy()]
    while budget > 1e-9 and queue:
        tgt = np.asarray(queue[0], float)
        d = float(np.linalg.norm(tgt - pos))
        if d <= budget:
            pos, budget = tgt, budget - d
            queue.pop(0)
        else:
            pos, budget = pos + (tgt - pos) / d * budget, 0.0
        pts.append(pos.copy())
    return pos, pts


def run(scn: Scenario, method: str, n_drones=3, shift_m=None, prior_label="correct",
        pod_true=POD_TRUE, t_max=T_MAX_S, record=False):
    assert method in ("bayes", "grid")
    rng = np.random.default_rng([scn.seed, 7])  # same detection stream for both methods
    pos = [HOME_XY.astype(float).copy() for _ in range(n_drones)]
    prev = [np.zeros((N_CELLS, N_CELLS), bool) for _ in range(n_drones)]
    vcells = victim_cells(scn)
    found = {}
    track = [] if record else None

    planner = None
    if method == "bayes":
        planner = Planner(n_drones)
        planner.set_prior(scn.observable(), shift_m)
        queues = [planner.next_route(i, pos[i]) for i in range(n_drones)]
    else:
        queues = lawnmower(n_drones, start_xy=HOME_XY)

    t = 0.0
    while t < t_max and len(found) < len(vcells):
        t += DT_S
        newly_all = np.zeros((N_CELLS, N_CELLS), bool)
        for i in range(n_drones):
            pos[i], pts = _advance(pos[i], queues[i], SPEED_MPS * DT_S)
            swept = np.zeros_like(newly_all)
            for a, b in zip(pts[:-1], pts[1:]):
                swept |= swept_cells(a, b)
            newly_all |= swept & ~prev[i]
            prev[i] = swept
            if not queues[i]:
                queues[i] = (planner.next_route(i, pos[i]) if planner
                             else lawnmower(n_drones, start_xy=pos[i])[i])  # grid: start another pass

        new_finds = []
        for k, (r, c) in enumerate(vcells):
            if k not in found and newly_all[r, c] and rng.random() < pod_true:
                found[k] = t
                new_finds.append((r, c))
        if planner:
            planner.observe_pass(newly_all)
            for r, c in new_finds:
                planner.confirm(r, c)
        if record:
            track.append((t, [p.copy() for p in pos], dict(found)))

    times = sorted(found.values())
    res = RunResult(
        seed=scn.seed, method=method, prior=prior_label, n_victims=len(vcells),
        ttff_s=times[0] if times else float("nan"),
        found_20min=sum(1 for x in times if x <= FIND_WINDOW_S),
        found_total=len(times),
    )
    return (res, track, planner) if record else res
