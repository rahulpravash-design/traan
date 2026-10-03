"""World frame for TRAAN. Single source of truth for grid geometry and coordinates.

Contract (see CLAUDE.md):
  * Internally everything is metres in UTM zone 43N (EPSG:32643).
  * On the wire everything is WGS84 lat/lon (EPSG:4326).
  * Grid: 80 x 80 cells of 25 m, a 2 x 2 km square centred on Ooty (11.41 N, 76.70 E).
  * Cell index (row, col): row 0 is the NORTHERN edge, col 0 is the WESTERN edge
    (image convention, so a probability array can be saved as a PNG as-is).
"""
from __future__ import annotations

import numpy as np
from pyproj import Transformer

CENTER_LAT = 11.41
CENTER_LON = 76.70
CELL_M = 25.0
N_CELLS = 80
SIZE_M = CELL_M * N_CELLS  # 2000 m

UTM_EPSG = 32643
WGS84_EPSG = 4326

_to_utm = Transformer.from_crs(WGS84_EPSG, UTM_EPSG, always_xy=True)
_to_wgs = Transformer.from_crs(UTM_EPSG, WGS84_EPSG, always_xy=True)

CENTER_E, CENTER_N = _to_utm.transform(CENTER_LON, CENTER_LAT)
# South-west corner of the grid in UTM metres.
ORIGIN_E = CENTER_E - SIZE_M / 2
ORIGIN_N = CENTER_N - SIZE_M / 2

# Where drones launch and return to: middle of the southern edge (road access).
HOME_XY = np.array([SIZE_M / 2, 0.0])


def latlon_to_utm(lat, lon):
    e, n = _to_utm.transform(lon, lat)
    return e, n


def utm_to_latlon(e, n):
    lon, lat = _to_wgs.transform(e, n)
    return lat, lon


def latlon_to_xy(lat, lon):
    """Lat/lon -> local metres (x east, y north) from the grid's SW corner."""
    e, n = latlon_to_utm(lat, lon)
    return np.asarray(e) - ORIGIN_E, np.asarray(n) - ORIGIN_N


def xy_to_latlon(x, y):
    return utm_to_latlon(np.asarray(x) + ORIGIN_E, np.asarray(y) + ORIGIN_N)


def xy_to_cell(x, y):
    """Local metres -> (row, col). Values outside the grid are clipped to the edge."""
    col = np.clip(np.floor(np.asarray(x) / CELL_M), 0, N_CELLS - 1).astype(int)
    row = np.clip(N_CELLS - 1 - np.floor(np.asarray(y) / CELL_M), 0, N_CELLS - 1).astype(int)
    return row, col


def cell_to_xy(row, col):
    """(row, col) -> local metres of the cell centre."""
    x = (np.asarray(col) + 0.5) * CELL_M
    y = (N_CELLS - 1 - np.asarray(row) + 0.5) * CELL_M
    return x, y


def latlon_to_cell(lat, lon):
    return xy_to_cell(*latlon_to_xy(lat, lon))


def cell_to_latlon(row, col):
    return xy_to_latlon(*cell_to_xy(row, col))


def in_grid(x, y):
    return (0 <= x < SIZE_M) and (0 <= y < SIZE_M)


def cell_centers_xy():
    """(N, N, 2) array of cell-centre local metres, indexed [row, col]."""
    rows, cols = np.mgrid[0:N_CELLS, 0:N_CELLS]
    x, y = cell_to_xy(rows, cols)
    return np.stack([x, y], axis=-1)


def corners_latlon():
    """Grid corners as WGS84, for the dashboard: {"nw": [lat, lon], ...}."""
    out = {}
    for name, (x, y) in {"sw": (0, 0), "se": (SIZE_M, 0), "ne": (SIZE_M, SIZE_M), "nw": (0, SIZE_M)}.items():
        lat, lon = xy_to_latlon(x, y)
        out[name] = [float(lat), float(lon)]
    return out
