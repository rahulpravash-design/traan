"""Day 1 check: arm, take off to 20 m, hover, land — on every running PX4 instance.

    python -m fleet.smoke_test --drones 1
"""
from __future__ import annotations

import argparse
import asyncio

from fleet.adapter import DroneAdapter


async def one(i):
    d = DroneAdapter(i)
    print(f"[{d.name}] connecting on {d.mavlink_url} (gRPC {50051 + i}) ...")
    await d.connect()
    print(f"[{d.name}] connected, home AMSL {d.home_amsl:.1f} m; arming + takeoff")
    await d.takeoff(20.0)
    print(f"[{d.name}] at {d.rel_alt:.1f} m, hovering 5 s")
    await asyncio.sleep(5)
    await d.land()
    while d.rel_alt is not None and d.rel_alt > 0.5:
        await asyncio.sleep(0.5)
    print(f"[{d.name}] landed — PASS")


async def main(n):
    await asyncio.gather(*(one(i) for i in range(n)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--drones", type=int, default=1)
    asyncio.run(main(ap.parse_args().drones))
