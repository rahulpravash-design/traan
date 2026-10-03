"""Mock fleet: point-mass drones flown by the real planner, posting real-format events to the API.

Lets the dashboard (E) and API (B) work before PX4 is up. Uses the fast-sim kinematics and a
scenario's hidden victims to fake detections ("mock frame" — not YOLO, not a camera).

    python -m fleet.mock_feed --seed 1 --speedup 5
"""
from __future__ import annotations

import argparse
import os
import time

import httpx
import numpy as np

from api.schemas import Detection, MapUpdate, Telemetry
from planner.service import Planner, swept_cells
from sim.fastsim import POD_TRUE, SPEED_MPS, _advance
from sim.scenario import make_scenario, victim_cells
from sim.world import HOME_XY, N_CELLS, xy_to_latlon

API = os.environ.get("TRAAN_API", "http://localhost:8000")


def _post(client, event):
    try:
        client.post("/events", json=event)
    except httpx.HTTPError as e:
        print("post failed:", e)


def main(seed, speedup, n_drones=3, hz=2.0, loop=True):
    client = httpx.Client(base_url=API, timeout=2.0)
    while True:
        try:
            client.get("/health")
            break
        except httpx.HTTPError:
            print(f"waiting for API at {API} ...")
            time.sleep(2)

    while True:
        scn = make_scenario(seed)
        rng = np.random.default_rng([seed, 99])
        planner = Planner(n_drones)
        planner.set_prior(scn.observable())
        _post(client, MapUpdate(**planner.map_update()).model_dump())
        pos = [HOME_XY.astype(float).copy() for _ in range(n_drones)]
        battery = [1.0] * n_drones
        prev = [np.zeros((N_CELLS, N_CELLS), bool) for _ in range(n_drones)]
        queues = [planner.next_route(i, pos[i]) for i in range(n_drones)]
        vcells, found, det_id = victim_cells(scn), set(), seed * 1000
        t_sim, tick = 0.0, 0
        print(f"scenario seed={seed}: {len(vcells)} hidden victims, {len(scn.pings)} pings")

        while t_sim < 3600 and len(found) < len(vcells):
            dt = speedup / hz
            t_sim += dt
            tick += 1
            newly_all = np.zeros((N_CELLS, N_CELLS), bool)
            for i in range(n_drones):
                pos[i], pts = _advance(pos[i], queues[i], SPEED_MPS * dt)
                swept = np.zeros_like(newly_all)
                for a, b in zip(pts[:-1], pts[1:]):
                    swept |= swept_cells(a, b)
                newly_all |= swept & ~prev[i]
                prev[i] = swept
                if not queues[i]:
                    queues[i] = planner.next_route(i, pos[i])
                battery[i] = max(0.0, battery[i] - dt / 2400.0)  # ~40 min endurance
                lat, lon = xy_to_latlon(*pos[i])
                _post(client, Telemetry(ts=time.time(), drone=f"d{i + 1}", lat=float(lat), lon=float(lon),
                                        alt=60.0, battery=round(battery[i], 3)).model_dump())

            for k, (r, c) in enumerate(vcells):
                if k not in found and newly_all[r, c] and rng.random() < POD_TRUE:
                    found.add(k)
                    det_id += 1
                    lat, lon = xy_to_latlon(*scn.victims_xy[k])
                    drone = int(np.argmin([np.linalg.norm(p - scn.victims_xy[k]) for p in pos]))
                    _post(client, Detection(ts=time.time(), id=det_id, drone=f"d{drone + 1}", lat=float(lat),
                                            lon=float(lon), conf=round(float(rng.uniform(0.55, 0.95)), 2),
                                            frame=f"mock/person_{k:04d}.jpg").model_dump())
            planner.observe_pass(newly_all)
            if tick % 4 == 0:
                _post(client, MapUpdate(**planner.map_update()).model_dump())
            time.sleep(1.0 / hz)

        print(f"scenario done at t={t_sim:.0f}s sim, {len(found)}/{len(vcells)} found")
        if not loop:
            return
        seed += 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--speedup", type=float, default=5.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    main(a.seed, a.speedup, loop=not a.once)
