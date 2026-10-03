"""OpenStreetMap buildings on the 80 x 80 grid.

Reads data/osm.json (Overpass JSON with `out geom`, made by data/fetch.sh). A cell counts as a
building cell if its centre lies inside a building footprint, or if a footprint smaller than a
cell has its centroid there. Returns None when the file is missing, so callers fall back to the
synthetic hamlets in sim/scenario.py. © OpenStreetMap contributors, ODbL.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from matplotlib.path import Path as Polygon

from sim.world import N_CELLS, cell_centers_xy, latlon_to_xy, xy_to_cell

OSM_PATH = Path(__file__).resolve().parent.parent / "data" / "osm.json"


def buildings_from_overpass(doc: dict) -> np.ndarray:
    centers = cell_centers_xy().reshape(-1, 2)
    mask = np.zeros(N_CELLS * N_CELLS, bool)
    for el in doc.get("elements", []):
        if el.get("type") != "way" or "building" not in el.get("tags", {}) or not el.get("geometry"):
            continue
        lat = np.array([g["lat"] for g in el["geometry"]])
        lon = np.array([g["lon"] for g in el["geometry"]])
        x, y = latlon_to_xy(lat, lon)
        xy = np.stack([x, y], axis=-1)
        if len(xy) >= 3:
            mask |= Polygon(xy).contains_points(centers)
        cx, cy = xy.mean(axis=0)
        if 0 <= cx < N_CELLS * 25 and 0 <= cy < N_CELLS * 25:
            r, c = xy_to_cell(cx, cy)
            mask[int(r) * N_CELLS + int(c)] = True
    return mask.reshape(N_CELLS, N_CELLS)


@lru_cache(maxsize=1)
def load_buildings():
    if not OSM_PATH.exists():
        return None
    return buildings_from_overpass(json.loads(OSM_PATH.read_text()))
