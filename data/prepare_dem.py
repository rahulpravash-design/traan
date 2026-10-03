"""Resample an SRTM .hgt tile onto TRAAN's 80 x 80 grid (cell centres, bilinear).

    python3 data/prepare_dem.py N11E076.hgt dem_grid.npy
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim.world import cell_to_latlon, N_CELLS  # noqa: E402


def main(hgt_path, out_path):
    raw = np.fromfile(hgt_path, dtype=">i2")
    n = int(round(np.sqrt(raw.size)))           # 3601 (1") or 1201 (3")
    z = raw.reshape(n, n).astype(float)
    z[z < -1000] = np.nan                        # voids
    name = Path(hgt_path).stem                   # e.g. N11E076: tile's SW corner
    lat0 = int(name[1:3]) * (1 if name[0] == "N" else -1)
    lon0 = int(name[4:7]) * (1 if name[3] == "E" else -1)

    rows, cols = np.mgrid[0:N_CELLS, 0:N_CELLS]
    lat, lon = cell_to_latlon(rows, cols)
    fy = (lat0 + 1 - lat) * (n - 1)              # hgt row 0 is the tile's NORTH edge
    fx = (lon - lon0) * (n - 1)
    y0, x0 = np.floor(fy).astype(int), np.floor(fx).astype(int)
    ty, tx = fy - y0, fx - x0
    dem = (z[y0, x0] * (1 - ty) * (1 - tx) + z[y0, x0 + 1] * (1 - ty) * tx
           + z[y0 + 1, x0] * ty * (1 - tx) + z[y0 + 1, x0 + 1] * ty * tx)
    if np.isnan(dem).any():
        dem[np.isnan(dem)] = np.nanmean(dem)
    np.save(out_path, dem)
    print(f"{out_path}: {dem.shape}, elevation {dem.min():.0f}-{dem.max():.0f} m")


if __name__ == "__main__":
    main(*sys.argv[1:3])
