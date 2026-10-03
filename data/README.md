# data/

Nothing here is committed except `fetch.sh`, `prepare_dem.py` and this file. Run `./data/fetch.sh`.

| File | Source | Licence |
|---|---|---|
| `N11E076.hgt` → `dem_grid.npy` | NASA SRTM 1″ via AWS Terrain Tiles | Public domain |
| `osm.json` | OpenStreetMap via Overpass API | ODbL — attribute "© OpenStreetMap contributors" |
| `hit-uav-src/` → `hit-uav/` → `hituav_person/` | HIT-UAV official repo (Suo et al., Scientific Data 2023), git clone | CC BY 4.0, cite the paper |

Until `dem_grid.npy` exists, `sim/terrain.py` uses a seeded synthetic hillside.
