"""Prior probability map from what an operator actually knows at alert time.

Inputs are only the observable parts of a scenario: alert pin, phone pings, terrain, buildings.
"""
from __future__ import annotations

import numpy as np

from sim.terrain import slope_deg
from sim.world import CELL_M, N_CELLS, cell_centers_xy

ALERT_SIGMA_M = 400.0
UNIFORM_FLOOR = 0.05   # share of mass spread evenly so no cell is ever impossible
W_ALERT, W_PINGS = 0.4, 0.6


def _gauss(centers, xy, sigma):
    d2 = np.sum((centers - np.asarray(xy)) ** 2, axis=-1)
    g = np.exp(-0.5 * d2 / sigma ** 2)
    return g / g.sum()


def build_prior(alert_xy, pings=(), dem=None, buildings=None):
    """Return an (80, 80) grid summing to 1."""
    centers = cell_centers_xy()
    P = W_ALERT * _gauss(centers, alert_xy, ALERT_SIGMA_M)
    if pings:
        ping_mass = sum(_gauss(centers, (x, y), max(acc, CELL_M)) for x, y, acc in pings)
        P = P + W_PINGS * ping_mass / len(pings)
    else:
        P = P / W_ALERT

    if dem is not None:
        s = slope_deg(dem)
        # debris and people settle on gentle-to-moderate ground, not on cliffs
        P = P * np.clip(1.2 - s / 45.0, 0.3, 1.2)
    if buildings is not None:
        P = P * np.where(buildings, 2.0, 1.0)

    P = P / P.sum()
    P = (1 - UNIFORM_FLOOR) * P + UNIFORM_FLOOR / (N_CELLS * N_CELLS)
    return P / P.sum()


def shift_prior(P, dx_m, dy_m):
    """Wrong-prior test: move the whole map by (dx, dy) metres; vacated cells get the floor."""
    dc, dr = int(round(dx_m / CELL_M)), -int(round(dy_m / CELL_M))
    out = np.full_like(P, P.min())
    src = P[max(0, -dr):N_CELLS - max(0, dr), max(0, -dc):N_CELLS - max(0, dc)]
    out[max(0, dr):max(0, dr) + src.shape[0], max(0, dc):max(0, dc) + src.shape[1]] = src
    return out / out.sum()


def prior_from_scenario(obs, shift_m=None):
    P = build_prior(obs["alert_xy"], obs["pings"], obs["dem"], obs["buildings"])
    if shift_m is not None:
        P = shift_prior(P, *shift_m)
    return P
