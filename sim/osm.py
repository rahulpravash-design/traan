"""Real building footprints on the 80 x 80 grid.

Sources, in order of preference (both made by data/fetch.sh):
  1. data/osm.json — OpenStreetMap buildings via Overpass (`out geom`). © OpenStreetMap contributors, ODbL.
  2. data/open_buildings_ooty.csv — Google Open Buildings v3 polygons for the grid's bounding box
     (Sirko et al. 2021; CC BY 4.0 / ODbL), kept at confidence >= MIN_CONFIDENCE. Used when Overpass
     is unreachable (it is from the cloud build environment).
A cell counts as a building cell if its centre lies inside a footprint, or if a footprint smaller
than a cell has its centroid there. With neither file, callers fall back to the synthetic hamlets
in sim/scenario.py. `buildings_source()` names what was used, so results can say so.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from matplotlib.path import Path as Polygon

from sim.world import N_CELLS, SIZE_M, cell_centers_xy, latlon_to_xy, xy_to_cell

DATA = Path(__file__).resolve().parent.parent / "data"
OSM_PATH = DATA / "osm.json"
GOB_PATH = DATA / "open_buildings_ooty.csv"
MIN_CONFIDENCE = 0.70   # Google Open Buildings' own precision-oriented threshold band starts here


def _rasterise(rings_latlon) -> np.ndarray:
    centers = cell_centers_xy().reshape(-1, 2)
    mask = np.zeros(N_CELLS * N_CELLS, bool)
    for lat, lon in rings_latlon:
        x, y = latlon_to_xy(np.asarray(lat), np.asarray(lon))
        xy = np.stack([x, y], axis=-1)
        if len(xy) >= 3:
            mask |= Polygon(xy).contains_points(centers)
        cx, cy = xy.mean(axis=0)
        if 0 <= cx < SIZE_M and 0 <= cy < SIZE_M:
            r, c = xy_to_cell(cx, cy)
            mask[int(r) * N_CELLS + int(c)] = True
    return mask.reshape(N_CELLS, N_CELLS)


def rings_from_overpass(doc: dict):
    return [([g["lat"] for g in el["geometry"]], [g["lon"] for g in el["geometry"]])
            for el in doc.get("elements", [])
            if el.get("type") == "way" and "building" in el.get("tags", {}) and el.get("geometry")]


def buildings_from_overpass(doc: dict) -> np.ndarray:
    return _rasterise(rings_from_overpass(doc))


_RING = re.compile(r"\(\(([^()]+)\)")


def rings_from_open_buildings(rows, min_confidence=MIN_CONFIDENCE):
    rings = []
    for row in rows:
        if float(row["confidence"]) < min_confidence:
            continue
        m = _RING.search(row["geometry"])            # outer ring of the POLYGON
        if not m:
            continue
        pts = [p.split() for p in m.group(1).split(",")]
        rings.append(([float(p[1]) for p in pts], [float(p[0]) for p in pts]))
    return rings


def buildings_from_open_buildings(rows, min_confidence=MIN_CONFIDENCE) -> np.ndarray:
    """rows: dicts with Google Open Buildings columns (confidence, geometry as WKT POLYGON)."""
    return _rasterise(rings_from_open_buildings(rows, min_confidence))


@lru_cache(maxsize=1)
def _load():
    """(cell mask, footprint rings as (lats, lons), source name)"""
    if OSM_PATH.exists():
        rings = rings_from_overpass(json.loads(OSM_PATH.read_text()))
        return _rasterise(rings), rings, "osm"
    if GOB_PATH.exists():
        csv.field_size_limit(sys.maxsize)
        with open(GOB_PATH, newline="") as f:
            rings = rings_from_open_buildings(csv.DictReader(f))
        return _rasterise(rings), rings, "open-buildings"
    return None, [], "synthetic"


def load_buildings():
    return _load()[0]


def building_rings():
    return _load()[1]


def buildings_source():
    return _load()[2]
