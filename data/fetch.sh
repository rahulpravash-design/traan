#!/usr/bin/env bash
# Fetch TRAAN's external data. Nothing in data/ is committed except this script,
# prepare_dem.py and README.md.
#   ./data/fetch.sh            # DEM + OSM (small, no account needed)
#   ./data/fetch.sh hituav     # also HIT-UAV (needs a Kaggle API token in ~/.kaggle/kaggle.json)
set -euo pipefail
cd "$(dirname "$0")"

# 1. SRTM 1-arc-second tile covering Ooty (public AWS terrain tiles, NASA SRTM, public domain)
if [ ! -f N11E076.hgt ]; then
  echo "DEM: downloading N11E076.hgt"
  curl -fL --retry 3 -o N11E076.hgt.gz https://s3.amazonaws.com/elevation-tiles-prod/skadi/N11/N11E076.hgt.gz
  gunzip -f N11E076.hgt.gz
fi
python3 prepare_dem.py N11E076.hgt dem_grid.npy

# 2. OpenStreetMap buildings, roads, waterways for the 2 x 2 km grid (+ margin). ODbL: attribute OSM.
if [ ! -f osm.json ]; then
  echo "OSM: querying Overpass"
  BBOX="11.395,76.685,11.425,76.715"   # south,west,north,east
  curl -fL --retry 3 -o osm.json https://overpass-api.de/api/interpreter --data-urlencode \
    "data=[out:json][timeout:60];(way[building]($BBOX);way[highway]($BBOX);way[waterway]($BBOX););out geom;"
fi

# 3. HIT-UAV thermal dataset (CC0). ~2.9k images; train 2029 / val 290 / test 579.
if [ "${1:-}" = "hituav" ] && [ ! -d hit-uav ]; then
  if command -v kaggle >/dev/null; then
    kaggle datasets download -d pandrii000/hituav-a-highaltitude-infrared-thermal-dataset -p . --unzip
    # normalise folder name to data/hit-uav/{images,labels}/{train,val,test}
    found=$(dirname "$(find . -type d -path '*images/train' | head -1)")
    [ -n "$found" ] && [ "$found" != "./hit-uav" ] && mv "$found" hit-uav
  else
    echo "HIT-UAV: install the Kaggle CLI (pip install kaggle) or download manually from"
    echo "  https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset"
    echo "and unpack to data/hit-uav/{images,labels}/{train,val,test}"
    exit 1
  fi
  (cd .. && python3 -m perception.prepare_hituav --src data/hit-uav --dst data/hituav_person)
fi
echo "data ready: $(ls)"
