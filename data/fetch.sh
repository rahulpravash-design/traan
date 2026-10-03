#!/usr/bin/env bash
# Fetch TRAAN's external data. Nothing in data/ is committed except this script,
# prepare_dem.py and README.md.
#   ./data/fetch.sh            # DEM + OSM (small, no account needed)
#   ./data/fetch.sh hituav     # also HIT-UAV (~1.3 GB git clone of the dataset's official repo; no account)
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
  curl -fL --retry 3 -o osm.json.tmp https://overpass-api.de/api/interpreter --data-urlencode \
    "data=[out:json][timeout:60];(way[building]($BBOX);way[highway]($BBOX);way[waterway]($BBOX););out geom;" \
    && mv osm.json.tmp osm.json \
    || { rm -f osm.json.tmp; echo "OSM: Overpass unreachable; scenarios keep synthetic buildings"; }
fi

# 3. HIT-UAV thermal dataset (Suo et al., Scientific Data 2023; CC BY 4.0, cite the paper).
#    2898 images, 640x512; train 2029 / val 290 / test 579. The official repo ships images + YOLO labels.
if [ "${1:-}" = "hituav" ]; then
  if [ ! -d hit-uav-src ]; then
    echo "HIT-UAV: cloning the official repository (~1.3 GB)"
    GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset hit-uav-src
  fi
  # normalise to data/hit-uav/{images,labels}/{train,val,test} (symlinks, nothing copied)
  for split in train val test; do
    mkdir -p hit-uav/images hit-uav/labels
    ln -sfn "../../hit-uav-src/normal_json/$split" "hit-uav/images/$split"
    ln -sfn "../../hit-uav-src/yolo_labels/$split" "hit-uav/labels/$split"
  done
  (cd .. && python3 -m perception.prepare_hituav --src data/hit-uav --dst data/hituav_person)
fi
echo "data ready: $(ls)"
