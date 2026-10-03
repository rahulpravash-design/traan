"""Live fleet loop on PX4 SITL: the real-drone counterpart of fleet/mock_feed.py.

    python -m fleet.run --drones 3

Per drone: connect (UDP 14540+N, gRPC 50051+N) -> take off to 60 m -> stream telemetry at 2 Hz
-> repeatedly ask the API planner for the next leg (POST /planner/next) and fly it.
Needs an alert pin first (dashboard, or POST /commands/alert); until then drones hover.
Written against the MAVSDK-Python API but not yet run against SITL (that is the Day 4 check).
"""
from __future__ import annotations

import argparse
import asyncio

import httpx

from fleet.adapter import API, DroneAdapter


async def mission(i):
    d = DroneAdapter(i)
    await d.connect()
    print(f"[{d.name}] connected; taking off")
    asyncio.create_task(d.stream_telemetry())
    await d.takeoff()
    async with httpx.AsyncClient(base_url=API, timeout=5.0) as api:
        while True:
            r = await api.post("/planner/next", json={"drone": d.name, "lat": d.lat, "lon": d.lon})
            if r.status_code == 409:          # no alert pin yet: hover and ask again
                await asyncio.sleep(2)
                continue
            r.raise_for_status()
            leg = r.json()
            print(f"[{d.name}] map v{leg['version']}: leg to cell {leg['target']} ({len(leg['waypoints'])} wp)")
            await d.fly(leg["waypoints"])


async def main(n):
    await asyncio.gather(*(mission(i) for i in range(n)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--drones", type=int, default=3)
    asyncio.run(main(ap.parse_args().drones))
