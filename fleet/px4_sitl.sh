#!/usr/bin/env bash
# Launch N headless PX4 SITL instances (SIH: no Gazebo, fits 8 GB laptops).
#   PX4_DIR=~/PX4-Autopilot ./fleet/px4_sitl.sh 3
# Instance i sends MAVLink (offboard/API link) to UDP 14540+i  ->  fleet/adapter.py connects there.
# Build once first:  cd $PX4_DIR && make px4_sitl_default
set -euo pipefail

N="${1:-3}"
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
BUILD="$PX4_DIR/build/px4_sitl_default"
WORK="${WORK_DIR:-$(pwd)/px4_instances}"

# World origin: grid centre near Ooty (sim/world.py). Drones spawn a few metres apart.
export PX4_HOME_LAT="${PX4_HOME_LAT:-11.40100}"   # southern edge of the grid (HOME_XY)
export PX4_HOME_LON="${PX4_HOME_LON:-76.70000}"
export PX4_HOME_ALT="${PX4_HOME_ALT:-2240}"
# NOTE: some PX4 versions' SIH ignores PX4_HOME_*; if QGroundControl shows the drones elsewhere,
# set the SIH_LOC_LAT0 / SIH_LOC_LON0 params instead (older PX4) — check on Day 1 and fix here.

[ -x "$BUILD/bin/px4" ] || { echo "PX4 not built at $BUILD (run: make px4_sitl_default)"; exit 1; }
pkill -x px4 || true
mkdir -p "$WORK"

for ((i = 0; i < N; i++)); do
  mkdir -p "$WORK/$i"
  (
    cd "$WORK/$i"
    PX4_SYS_AUTOSTART=10040 PX4_SIM_MODEL=sihsim_quadx \
      "$BUILD/bin/px4" -i "$i" -d "$BUILD/etc" >out.log 2>err.log &
  )
  echo "started PX4 instance $i -> MAVLink UDP $((14540 + i)), mavsdk gRPC $((50051 + i))"
done
echo "logs in $WORK/<i>/out.log;  stop with: pkill -x px4"
wait
