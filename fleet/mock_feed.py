"""Mock fleet: point-mass drones that fly the API's planner exactly like the PX4 fleet will.

Same contract as the real thing — POST /planner/next for waypoints, POST /events for telemetry
and detections — so swapping this for fleet/adapter.py changes nothing upstream. It also plays
the "reporter" (sends the scenario's alert pin + phone pings) and fakes detections from the
scenario's hidden victims ("mock frame": not YOLO, not a camera).

    python -m fleet.mock_feed --seed 1 --speedup 5
    python -m fleet.mock_feed --wait-for-pin      # don't auto-alert; the operator drops the pin
"""
from __future__ import annotations

import argparse
import os
import time

import httpx
import numpy as np

from api.schemas import Detection, Telemetry
from planner.sweep import SEARCH_ALT_M, SweepTracker
from sim.fastsim import POD_TRUE, SPEED_MPS, _advance, reachable_victims
from sim.scenario import make_scenario
from sim.world import HOME_XY, latlon_to_xy, xy_to_latlon

API = os.environ.get("TRAAN_API", "http://localhost:8000")
CLIMB_MPS = 3.0
ENDURANCE_S = 2400.0


def _wait_for_api(client):
    while True:
        try:
            return client.get("/health").json()
        except httpx.HTTPError:
            print(f"waiting for API at {API} ...")
            time.sleep(2)


def _alert(client, scn):
    lat, lon = xy_to_latlon(*scn.alert_xy)
    pings = [{"lat": float(a), "lon": float(b), "acc_m": acc} for (x, y, acc) in scn.pings
             for a, b in [xy_to_latlon(x, y)]]
    client.post("/commands/alert", json={"lat": float(lat), "lon": float(lon), "pings": pings,
                                         "by": "mock-reporter"}).raise_for_status()


def fly_scenario(client, seed, speedup, hz, n_drones, auto_alert):
    scn = make_scenario(seed)
    if auto_alert:
        _alert(client, scn)
    else:
        print("waiting for the operator to drop an alert pin ...")
        while not _wait_for_api(client)["planner"]["ready"]:
            time.sleep(1)
    victims, n_unreach = reachable_victims(scn)
    print(f"scenario seed={seed}: {len(victims)} reachable hidden victims ({n_unreach} in no-fly), "
          f"{len(scn.pings)} pings")

    luck = np.random.default_rng([seed, 7]).random((len(scn.victims_xy), 4096))
    passes = np.zeros(len(scn.victims_xy), int)
    truth = SweepTracker(n_drones)                    # what the camera really saw
    pos = [HOME_XY.astype(float).copy() for _ in range(n_drones)]
    alt = [0.0] * n_drones
    queues = [[] for _ in range(n_drones)]
    # ids must stay unique across restarts: the event store outlives this process
    found, det_id, t_sim = set(), int(time.time() * 1000) % 2_000_000_000, 0.0
    dt = speedup / hz

    while t_sim < 3600 and len(found) < len(victims):
        t_sim += dt
        for i in range(n_drones):
            name = f"d{i + 1}"
            if alt[i] < SEARCH_ALT_M:                 # climb out first; not searching yet
                alt[i] = min(SEARCH_ALT_M, alt[i] + CLIMB_MPS * dt)
                newly = None
            else:
                if not queues[i]:
                    lat, lon = xy_to_latlon(*pos[i])
                    r = client.post("/planner/next", json={"drone": name, "lat": float(lat), "lon": float(lon)})
                    if r.status_code == 200:
                        queues[i] = [np.array(latlon_to_xy(a, b), float) for a, b in r.json()["waypoints"]]
                pos[i], pts = _advance(pos[i], queues[i], SPEED_MPS * dt)
                newly = truth.track(i, pts)
            lat, lon = xy_to_latlon(*pos[i])
            battery = max(0.0, 1.0 - t_sim / ENDURANCE_S)
            client.post("/events", json=Telemetry(ts=time.time(), drone=name, lat=float(lat), lon=float(lon),
                                                  alt=round(alt[i], 1), battery=round(battery, 3)).model_dump())
            if newly is None:
                continue
            for k, (r_, c_) in victims:
                if k not in found and newly[r_, c_]:
                    hit = luck[k, passes[k]] < POD_TRUE
                    passes[k] += 1
                    if hit:
                        found.add(k)
                        det_id += 1
                        vlat, vlon = xy_to_latlon(*scn.victims_xy[k])
                        client.post("/events", json=Detection(
                            ts=time.time(), id=det_id, drone=name, lat=float(vlat), lon=float(vlon),
                            conf=round(float(np.random.default_rng([seed, k]).uniform(0.55, 0.95)), 2),
                            frame=f"mock/person_{k:04d}.jpg").model_dump())
        time.sleep(1.0 / hz)
    print(f"scenario seed={seed} done at t={t_sim:.0f} s sim: {len(found)}/{len(victims)} detected")


def main(seed, speedup, hz=2.0, n_drones=3, loop=True, auto_alert=True):
    client = httpx.Client(base_url=API, timeout=5.0)
    _wait_for_api(client)
    while True:
        fly_scenario(client, seed, speedup, hz, n_drones, auto_alert)
        if not loop:
            return
        seed += 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--speedup", type=float, default=5.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--wait-for-pin", action="store_true")
    a = ap.parse_args()
    main(a.seed, a.speedup, loop=not a.once, auto_alert=not a.wait_for_pin)
