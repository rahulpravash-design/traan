"""Replay mapper: the simulated world's "camera". Works the same with the mock fleet and PX4 SITL.

It owns the scenario's hidden victims, which no other process sees. It listens to drone
telemetry on the API's WebSocket and, whenever a drone's thermal footprint newly covers a victim,
asks the perception service to run the detector on a HIT-UAV frame that contains a person.
Otherwise it sends a person-free frame every few seconds per drone, so false alarms happen too.
Whether a victim is actually detected is up to the detector: the miss rate is the model's own.

    python -m sim.replay_mapper --seed 1                 # also sends the scenario's alert + pings
    python -m sim.replay_mapper --seed 1 --wait-for-pin  # the operator drops the pin instead

On screen this is "thermal frame replay (HIT-UAV)", never a live camera (CLAUDE.md §7).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass

import httpx
import numpy as np

from planner.sweep import SEARCH_ALT_M, SweepTracker
from sim.fastsim import reachable_victims
from sim.scenario import make_scenario
from sim.world import latlon_to_xy, xy_to_latlon

API = os.environ.get("TRAAN_API", "http://localhost:8000")
PERCEPTION = os.environ.get("TRAAN_PERCEPTION", "http://localhost:8001")
SEARCHING_ALT_M = 0.8 * SEARCH_ALT_M
GEOLOC_SIGMA_M = 8.0   # simulated error of turning a box in the frame into a ground position


@dataclass
class Observation:
    """One frame to hand to the perception service (the body of POST /observe)."""
    drone: str
    lat: float
    lon: float
    step: int
    victim_in_view: bool

    def body(self):
        return self.__dict__.copy()


class ReplayMapper:
    """Pure logic, no I/O: telemetry events in, observations out. Easy to test."""

    def __init__(self, scn, n_drones=3, empty_every_s=10.0):
        self.scn = scn
        self.victims, self.n_unreachable = reachable_victims(scn)
        self.n = n_drones
        self.empty_every_s = empty_every_s
        self.tracker = SweepTracker(n_drones)
        self.step = [0] * n_drones
        self.last_frame_ts = [-np.inf] * n_drones
        self.rng = np.random.default_rng([scn.seed, 31])

    def on_telemetry(self, e) -> list[Observation]:
        try:
            i = int(e["drone"].lstrip("d")) - 1
        except ValueError:
            return []
        if not 0 <= i < self.n:
            return []
        xy = latlon_to_xy(e["lat"], e["lon"])
        xy = (float(xy[0]), float(xy[1]))
        if e["alt"] < SEARCHING_ALT_M:          # climbing or landing: camera not searching
            self.tracker.lift(i)
            return []
        newly = self.tracker.move_to(i, xy)
        out = []
        for k, (r, c) in self.victims:
            if newly[r, c]:
                self.step[i] += 1
                vx, vy = self.scn.victims_xy[k] + self.rng.normal(0, GEOLOC_SIGMA_M, 2)
                lat, lon = xy_to_latlon(vx, vy)
                out.append(Observation(e["drone"], float(lat), float(lon), self.step[i], True))
        if not out and e["ts"] - self.last_frame_ts[i] >= self.empty_every_s:
            self.step[i] += 1
            out.append(Observation(e["drone"], e["lat"], e["lon"], self.step[i], False))
        if out:
            self.last_frame_ts[i] = e["ts"]
        return out


async def send_alert(client, scn):
    lat, lon = xy_to_latlon(*scn.alert_xy)
    pings = []
    for x, y, acc in scn.pings:
        plat, plon = xy_to_latlon(x, y)
        pings.append({"lat": float(plat), "lon": float(plon), "acc_m": acc})
    r = await client.post(f"{API}/commands/alert",
                          json={"lat": float(lat), "lon": float(lon), "pings": pings, "by": "mock-reporter"})
    r.raise_for_status()


async def run(seed, n_drones, wait_for_pin, empty_every_s):
    import websockets  # installed with uvicorn[standard]

    scn = make_scenario(seed)
    mapper = ReplayMapper(scn, n_drones, empty_every_s)
    print(f"scenario seed={seed}: {len(mapper.victims)} reachable hidden victims "
          f"({mapper.n_unreachable} in no-fly), {len(scn.pings)} pings")
    async with httpx.AsyncClient(timeout=10.0) as client:
        if not wait_for_pin:
            await send_alert(client, scn)
        ws_url = API.replace("http", "ws", 1) + "/ws"
        while True:
            try:
                async with websockets.connect(ws_url, max_size=None) as ws:
                    async for msg in ws:
                        e = json.loads(msg)
                        if e.get("type") != "telemetry":
                            continue
                        for obs in mapper.on_telemetry(e):
                            try:
                                r = await client.post(f"{PERCEPTION}/observe", json=obs.body())
                                ev = r.json().get("event") if r.status_code == 200 else None
                                if obs.victim_in_view or ev:
                                    tag = "victim" if obs.victim_in_view else "empty"
                                    print(f"{obs.drone} {tag} frame -> {'DETECTION' if ev else 'missed'}")
                            except httpx.HTTPError as err:
                                print("perception unreachable:", err)
            except (OSError, websockets.ConnectionClosed) as err:
                print("API socket lost, retrying:", err)
                await asyncio.sleep(2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--drones", type=int, default=3)
    ap.add_argument("--wait-for-pin", action="store_true")
    ap.add_argument("--empty-every", type=float, default=10.0,
                    help="seconds between person-free frames per drone (each is a 1.8%% false-alarm chance at conf 0.6)")
    a = ap.parse_args()
    asyncio.run(run(a.seed, a.drones, a.wait_for_pin, a.empty_every))
