# data/

Nothing here is committed except `fetch.sh`, `prepare_dem.py` and this file. Run `./data/fetch.sh`.

| File | Source | Licence |
|---|---|---|
| `N11E076.hgt` → `dem_grid.npy` | NASA SRTM 1″ via AWS Terrain Tiles | Public domain |
| `osm.json` | OpenStreetMap via Overpass API | ODbL — attribute "© OpenStreetMap contributors" |
| `hit-uav/` → `hituav_person/` | HIT-UAV (Suo et al., 2023) | CC0 |

Until `dem_grid.npy` exists, `sim/terrain.py` uses a seeded synthetic hillside.
