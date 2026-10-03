"""Terrain on the 80 x 80 grid.

Uses data/dem_grid.npy (made by data/prepare_dem.py from the SRTM tile) when it exists,
otherwise a seeded synthetic hillside so everything runs before the data is fetched.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from sim.world import CELL_M, N_CELLS

DEM_PATH = Path(__file__).resolve().parent.parent / "data" / "dem_grid.npy"


def _smooth_noise(rng, n, octaves=4):
    out = np.zeros((n, n))
    for o in range(octaves):
        k = 2 ** (o + 2)
        coarse = rng.standard_normal((k + 1, k + 1))
        # bilinear upsample coarse -> n x n
        xs = np.linspace(0, k, n)
        x0 = np.floor(xs).astype(int).clip(0, k - 1)
        t = xs - x0
        a = coarse[x0][:, x0] * (1 - t)[None, :] + coarse[x0][:, x0 + 1] * t[None, :]
        b = coarse[x0 + 1][:, x0] * (1 - t)[None, :] + coarse[x0 + 1][:, x0 + 1] * t[None, :]
        out += (a * (1 - t)[:, None] + b * t[:, None]) / (2 ** o)
    return out


def synthetic_dem(seed=0):
    """Elevation in metres: a ridge to the north falling ~300 m to a valley in the south."""
    rng = np.random.default_rng(seed)
    rows = np.arange(N_CELLS)[:, None]
    base = 2300.0 - 300.0 * (rows / (N_CELLS - 1))  # row 0 = north = high
    return base + 60.0 * _smooth_noise(rng, N_CELLS) + np.zeros((1, N_CELLS))


def load_dem(seed=0):
    if DEM_PATH.exists():
        dem = np.load(DEM_PATH)
        assert dem.shape == (N_CELLS, N_CELLS), f"{DEM_PATH} must be {N_CELLS}x{N_CELLS}"
        return dem.astype(float)
    return synthetic_dem(seed)


def slope_deg(dem):
    """Slope in degrees. Note row 0 is north, so d/drow is -d/dy."""
    dz_drow, dz_dcol = np.gradient(dem, CELL_M)
    return np.degrees(np.arctan(np.hypot(dz_drow, dz_dcol)))


def downhill_step(dem, row, col):
    """Neighbour cell with the steepest descent, or the same cell at a local minimum."""
    best, best_rc = dem[row, col], (row, col)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            r, c = row + dr, col + dc
            if (dr or dc) and 0 <= r < N_CELLS and 0 <= c < N_CELLS and dem[r, c] < best:
                best, best_rc = dem[r, c], (r, c)
    return best_rc
