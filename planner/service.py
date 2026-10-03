"""Stateful planner used by both the fast sim and the live PX4 loop.

The live loop (Day 4-5) feeds it telemetry and confirmations and asks it for waypoints;
it never talks to MAVSDK directly — fleet/ turns waypoints into MAVSDK calls.
"""
from __future__ import annotations

import time

import numpy as np

from planner.allocate import assign
from planner.bayes import bayes_update, on_confirmed_find, pod_from_sweep, top_cells
from planner.nofly import DEFAULT_ZONES, nofly_mask, route
from planner.prior import prior_from_scenario
from sim.world import CELL_M, cell_centers_xy, cell_to_xy

SENSOR_STRIP_M = 50.0
_CENTERS = cell_centers_xy()


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


class Planner:
    def __init__(self, n_drones, zones=DEFAULT_ZONES, alpha=1.0, pod=None):
        self.n = n_drones
        self.zones = zones
        self.nofly = nofly_mask(zones)
        self.alpha = alpha
        self.pod = pod if pod is not None else float(pod_from_sweep(SENSOR_STRIP_M, CELL_M, CELL_M ** 2))
        self.P = None
        self.version = 0
        self.targets = [None] * n_drones

    # --- inputs -------------------------------------------------------------
    def set_prior(self, obs, shift_m=None):
        self.P = prior_from_scenario(obs, shift_m)
        self.P[self.nofly] = 0.0
        self.P /= self.P.sum()
        self.targets = [None] * self.n
        self.version += 1

    def observe_pass(self, newly_swept):
        """Negative-information update for cells swept with no detection."""
        if newly_swept.any():
            self.P = bayes_update(self.P, newly_swept, self.pod)
            self.version += 1

    def confirm(self, row, col):
        self.P = on_confirmed_find(self.P, row, col)
        self.version += 1

    # --- outputs ------------------------------------------------------------
    def next_route(self, i, drone_xy):
        """Pick drone i's next target cell and return the routed waypoints to it (local metres)."""
        others = [t for j, t in enumerate(self.targets) if j != i]
        # never re-pick the cells right under the drone, or a hovering drone would stall
        blocked = self.nofly | swept_cells(drone_xy, drone_xy)
        self.targets[i] = assign(self.P, drone_xy, others, blocked, self.alpha)
        return route(drone_xy, cell_to_xy(*self.targets[i]), self.zones)

    def map_update(self, k=500):
        return {"type": "map_update", "ts": time.time(), "version": self.version, "top_cells": top_cells(self.P, k)}
