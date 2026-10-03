"""Scenario generator: synthetic landslide incidents on the Nilgiris grid.

Benchmark rule (see CLAUDE.md): TRUE victim positions come from a different model
(debris runout down the steepest slope + people in buildings) than the planner's
prior (alert pin + phone pings + slope/building heuristics). The planner only ever
sees `Scenario.observable()`; `victims_xy` is ground truth for scoring and frame replay.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sim.terrain import downhill_step, load_dem
from sim.world import CELL_M, N_CELLS, SIZE_M, cell_to_xy, xy_to_cell

PING_MISSING = 0.30          # 30% of victims have no phone ping
PING_ERR_M = (50.0, 300.0)   # reported accuracy radius range
ALERT_ERR_M = 150.0          # how far off the reporter's alert pin is


@dataclass
class Scenario:
    seed: int
    dem: np.ndarray
    buildings: np.ndarray                 # bool (80, 80)
    alert_xy: np.ndarray                  # (2,) local metres
    pings: list = field(default_factory=list)   # [(x, y, accuracy_m)]
    victims_xy: np.ndarray = None         # (k, 2) ground truth, hidden from the planner
    runout: list = field(default_factory=list)  # [(row, col)] ground truth debris path

    def observable(self):
        """Everything the planner is allowed to see."""
        return {"dem": self.dem, "buildings": self.buildings, "alert_xy": self.alert_xy, "pings": self.pings}


def _buildings(rng):
    """A few hamlets, biased to the lower (southern) half where roads run."""
    b = np.zeros((N_CELLS, N_CELLS), dtype=bool)
    for _ in range(rng.integers(4, 8)):
        r0, c0 = rng.integers(30, N_CELLS - 4), rng.integers(4, N_CELLS - 4)
        for _ in range(rng.integers(4, 14)):
            r = int(np.clip(r0 + rng.integers(-3, 4), 0, N_CELLS - 1))
            c = int(np.clip(c0 + rng.integers(-3, 4), 0, N_CELLS - 1))
            b[r, c] = True
    return b


def _runout(rng, dem):
    r, c = int(rng.integers(6, 36)), int(rng.integers(10, N_CELLS - 10))
    path = [(r, c)]
    for _ in range(int(rng.integers(20, 45))):
        nr, nc = downhill_step(dem, r, c)
        if (nr, nc) == (r, c) or rng.random() < 0.25:  # debris spreads, not a perfect gradient walk
            nr = int(np.clip(r + 1, 0, N_CELLS - 1))
            nc = int(np.clip(c + rng.integers(-1, 2), 0, N_CELLS - 1))
        r, c = nr, nc
        path.append((r, c))
    return path


def make_scenario(seed: int, n_victims: tuple = (3, 7)) -> Scenario:
    rng = np.random.default_rng(seed)
    dem = load_dem(seed)
    buildings = _buildings(rng)
    runout = _runout(rng, dem)
    run_xy = np.array([cell_to_xy(r, c) for r, c in runout], dtype=float)

    victims = []
    b_rows, b_cols = np.nonzero(buildings)
    b_xy = np.stack(cell_to_xy(b_rows, b_cols), axis=-1) if len(b_rows) else np.zeros((0, 2))
    for _ in range(int(rng.integers(*n_victims))):
        near_b = b_xy[np.min(np.linalg.norm(b_xy[:, None] - run_xy[None], axis=-1), axis=1) < 300] if len(b_xy) else b_xy
        if rng.random() < 0.3 and len(near_b):
            p = near_b[rng.integers(len(near_b))]
        else:
            # deposition: victims end up mostly in the lower half of the runout
            i = int(np.clip(rng.triangular(0, len(run_xy) - 1, len(run_xy) - 1), 0, len(run_xy) - 1))
            p = run_xy[i]
        victims.append(np.clip(p + rng.normal(0, 30.0, 2), 1, SIZE_M - 1))
    victims = np.array(victims)

    alert = np.clip(run_xy.mean(axis=0) + rng.normal(0, ALERT_ERR_M, 2), 1, SIZE_M - 1)

    pings = []
    for v in victims:
        if rng.random() < PING_MISSING:
            continue
        acc = rng.uniform(*PING_ERR_M)
        ang = rng.uniform(0, 2 * np.pi)
        off = acc * rng.uniform(0, 1) * np.array([np.cos(ang), np.sin(ang)])
        x, y = np.clip(v + off, 1, SIZE_M - 1)
        pings.append((float(x), float(y), float(acc)))

    return Scenario(seed=seed, dem=dem, buildings=buildings, alert_xy=alert, pings=pings,
                    victims_xy=victims, runout=runout)


def victim_cells(scn: Scenario):
    rows, cols = xy_to_cell(scn.victims_xy[:, 0], scn.victims_xy[:, 1])
    return list(zip(rows.tolist(), cols.tolist()))


__all__ = ["Scenario", "make_scenario", "victim_cells", "CELL_M"]
