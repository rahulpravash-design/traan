"""Stateful planner used by both the fast sim and the live loop (API + fleet).

The fleet asks it for waypoints and feeds it positions; operators feed it alerts and
confirmations. It never talks to MAVSDK — fleet/ turns waypoints into MAVSDK calls.
"""
from __future__ import annotations

import time

import numpy as np

from planner.allocate import assign, assign_leg
from planner.bayes import bayes_update, on_confirmed_find, pod_from_sweep, top_cells
from planner.nofly import DEFAULT_ZONES, nofly_mask, route
from planner.prior import prior_from_scenario
from planner.sweep import SENSOR_STRIP_M, SweepTracker, swept_cells  # noqa: F401  (re-exported)
from sim.world import CELL_M, cell_to_xy

MODES = ("path", "cell")


class Planner:
    def __init__(self, n_drones, zones=DEFAULT_ZONES, alpha=1.0, pod=None, mode="path"):
        assert mode in MODES
        self.n = n_drones
        self.zones = zones
        self.nofly = nofly_mask(zones)
        self.alpha = alpha
        self.mode = mode
        self.pod = pod if pod is not None else float(pod_from_sweep(SENSOR_STRIP_M, CELL_M, CELL_M ** 2))
        self.P = None
        self.version = 0
        self._reset_drones()

    def _reset_drones(self):
        self.targets = [None] * self.n
        self.paths = [None] * self.n
        self.tracker = SweepTracker(self.n)

    @property
    def ready(self):
        return self.P is not None

    # --- inputs -------------------------------------------------------------
    def set_prior(self, obs, shift_m=None):
        self.P = prior_from_scenario(obs, shift_m)
        self.P[self.nofly] = 0.0
        self.P /= self.P.sum()
        self._reset_drones()
        self.version += 1

    def observe_pass(self, newly_swept):
        """Negative-information update for cells swept with no detection."""
        if newly_swept.any():
            self.P = bayes_update(self.P, newly_swept, self.pod)
            self.version += 1

    def on_position(self, i, xy, searching=True):
        """Live loop: drone i reports its position. Sweeps since the last report count as a pass.
        `searching=False` (on the ground, climbing) moves the drone without updating the map."""
        if not searching:
            self.tracker.lift(i, xy)
            return None
        newly = self.tracker.move_to(i, xy)
        if self.ready:
            self.observe_pass(newly)
        return newly

    def confirm(self, row, col):
        self.P = on_confirmed_find(self.P, row, col)
        self.version += 1

    # --- outputs ------------------------------------------------------------
    def next_route(self, i, drone_xy):
        """Pick drone i's next leg and return its waypoints (local metres, routed around no-fly zones)."""
        drone_xy = np.asarray(drone_xy, float)
        if self.mode == "cell":
            others = [t for j, t in enumerate(self.targets) if j != i]
            blocked = self.nofly | swept_cells(drone_xy, drone_xy)
            self.targets[i] = assign(self.P, drone_xy, others, blocked, self.alpha)
            return route(drone_xy, cell_to_xy(*self.targets[i]), self.zones)
        others = [m for j, m in enumerate(self.paths) if j != i]
        self.targets[i], wps, self.paths[i] = assign_leg(self.P, drone_xy, self.nofly, self.zones, self.pod, others)
        return wps

    def map_update(self, k=500):
        return {"type": "map_update", "ts": time.time(), "version": self.version, "top_cells": top_cells(self.P, k)}
