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

# World origin: HOME_XY in sim/world.py = middle of the grid's southern edge, near Ooty.
HOME_LAT="${HOME_LAT:-11.40096}"
HOME_LON="${HOME_LON:-76.70000}"
# PX4 v1.15 SIH: px4-rc.simulator copies PX4_HOME_LAT/LON verbatim into SIH_LOC_LAT0/LON0, which are
# INT32 in 1e-7 degrees. Passing "11.401" silently puts the drone at ~(0, 0). So export 1e-7 units.
# (Verified on v1.15.4: drone spawns at 11.40096 N, 76.70000 E.)
export PX4_HOME_LAT="$(awk -v d="$HOME_LAT" 'BEGIN { printf "%d", d * 1e7 }')"
export PX4_HOME_LON="$(awk -v d="$HOME_LON" 'BEGIN { printf "%d", d * 1e7 }')"

[ -x "$BUILD/bin/px4" ] || { echo "PX4 not built at $BUILD (run: make px4_sitl_default)"; exit 1; }
pkill -x px4 || true
mkdir -p "$WORK"

for ((i = 0; i < N; i++)); do
  # fresh instance dir every launch: params saved by an earlier run (e.g. a different origin) made
  # the simulated baro/compass drop out right after takeoff -> "blind land" failsafe
  rm -rf "${WORK:?}/$i" && mkdir -p "$WORK/$i"
  (
    cd "$WORK/$i"
    PX4_SYS_AUTOSTART=10040 PX4_SIM_MODEL=sihsim_quadx \
      "$BUILD/bin/px4" -i "$i" -d "$BUILD/etc" >out.log 2>err.log &
  )
  echo "started PX4 instance $i -> MAVLink UDP $((14540 + i)), mavsdk gRPC $((50051 + i))"
done
echo "logs in $WORK/<i>/out.log;  stop with: pkill -x px4"
wait
