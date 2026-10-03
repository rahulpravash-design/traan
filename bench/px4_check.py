"""Day 10 check: do the fast-sim results hold up when the same planner flies PX4 SITL drones?

    PX4_DIR=~/PX4-Autopilot python -m bench.px4_check --seeds 1 2 3 --speed 4

For each (seed, method) it starts everything from scratch: 3 headless PX4 SIH drones
(fleet/px4_sitl.sh, sped up --speed x), the API with TRAAN_PLANNER_MODE=path (Bayes) or grid,
and fleet/run.py. When all three hover at 60 m it sends the scenario's alert, then scores finds
from live telemetry with the fast sim's own sweep model and per-victim detection luck, so the
ONLY difference from sim/fastsim.py is how the drones actually fly (PX4 dynamics, waypoint
stops, real MAVSDK/telemetry latency). Results: bench/results/px4_check.csv, next to the
fast-sim answer for the same seed.

Times are simulated seconds = wall seconds x speed factor (PX4 lockstep). The script also reports
the effective factor it measured from drone ground speed, in case the CPU couldn't keep up.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np

from planner.sweep import SEARCH_ALT_M, SweepTracker
from sim.fastsim import FIND_WINDOW_S, POD_TRUE, SPEED_MPS, reachable_victims, run as fastsim_run
from sim.scenario import make_scenario
from sim.world import latlon_to_cell, latlon_to_xy, xy_to_latlon

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "bench" / "results" / "px4_check.csv"
PORT = 8100
API = f"http://localhost:{PORT}"
MODE = {"bayes": "path", "grid": "grid"}
FIELDS = ["seed", "method", "n_victims", "n_unreachable", "ttff_s", "found_20min", "found_total",
          "fastsim_ttff_s", "fastsim_found_20min", "speed_factor", "effective_factor"]


def _spawn(cmd, env, log):
    return subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=open(log, "w"), stderr=subprocess.STDOUT,
                            start_new_session=True)


def _kill(p):
    if p and p.poll() is None:
        os.killpg(p.pid, signal.SIGTERM)
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)


async def one_run(seed, method, speed, t_max, logdir, n=3):
    import websockets

    env = {**os.environ, "PX4_SIM_SPEED_FACTOR": str(speed), "TRAAN_API": API,
           "TRAAN_PLANNER_MODE": MODE[method], "TRAAN_DB": str(logdir / f"{seed}_{method}.sqlite")}
    Path(env["TRAAN_DB"]).unlink(missing_ok=True)
    procs = []
    try:
        subprocess.run(["bash", "fleet/px4_sitl.sh", str(n)], cwd=ROOT, env=env, check=True,
                       stdout=open(logdir / "px4.log", "w"), stderr=subprocess.STDOUT)
        procs.append(_spawn([sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(PORT)], env,
                            logdir / f"api_{seed}_{method}.log"))
        async with httpx.AsyncClient(base_url=API, timeout=10) as api:
            for _ in range(60):
                try:
                    if (await api.get("/health")).status_code == 200:
                        break
                except httpx.HTTPError:
                    await asyncio.sleep(1)
            procs.append(_spawn([sys.executable, "-W", "ignore", "-m", "fleet.run", "--drones", str(n)], env,
                                logdir / f"fleet_{seed}_{method}.log"))

            scn = make_scenario(seed)
            victims, n_unreach = reachable_victims(scn)
            luck = np.random.default_rng([seed, 7]).random((len(scn.victims_xy), 4096))
            passes = np.zeros(len(scn.victims_xy), int)
            truth = SweepTracker(n)
            found, alt, t0, det_id = {}, {}, None, 0
            dist_m, last_xy, wall_flying = 0.0, {}, 0.0

            async with websockets.connect(API.replace("http", "ws") + "/ws", max_size=None) as ws:
                deadline = time.time() + 600                       # takeoff must finish within 10 min wall
                while True:
                    remaining = (deadline if t0 is None else t0 + t_max / speed) - time.time()
                    if remaining <= 0 or (t0 is not None and len(found) == len(victims)):
                        break
                    try:
                        e = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
                    except asyncio.TimeoutError:
                        break
                    if e.get("type") != "telemetry":
                        continue
                    i = int(e["drone"][1:]) - 1
                    alt[i] = e["alt"]
                    if t0 is None:
                        if len(alt) == n and min(alt.values()) >= 0.95 * SEARCH_ALT_M:
                            lat, lon = xy_to_latlon(*scn.alert_xy)
                            pings = [{"lat": float(a), "lon": float(b), "acc_m": acc}
                                     for x, y, acc in scn.pings for a, b in [xy_to_latlon(x, y)]]
                            await api.post("/commands/alert", json={"lat": float(lat), "lon": float(lon),
                                                                     "pings": pings, "by": "px4-check"})
                            t0 = time.time()
                            print(f"  seed {seed} {method}: all drones at 60 m, alert sent")
                        continue
                    xy = tuple(float(v) for v in latlon_to_xy(e["lat"], e["lon"]))
                    if i in last_xy:
                        step = math.dist(xy, last_xy[i][0])
                        if step > 0.5:
                            dist_m += step
                            wall_flying += e["ts"] - last_xy[i][1]
                    last_xy[i] = (xy, e["ts"])
                    newly = truth.move_to(i, xy)
                    t_sim = (time.time() - t0) * speed
                    for k, (r, c) in victims:
                        if k not in found and newly[r, c]:
                            hit = luck[k, passes[k]] < POD_TRUE
                            passes[k] += 1
                            if hit:
                                found[k] = t_sim
                                det_id += 1
                                vlat, vlon = xy_to_latlon(*scn.victims_xy[k])
                                await api.post("/events", json={
                                    "type": "detection", "ts": time.time(), "id": seed * 1000 + det_id,
                                    "drone": e["drone"], "lat": float(vlat), "lon": float(vlon), "conf": 0.9,
                                    "frame": "px4check/oracle", "status": "pending"})
                                await api.post("/commands/confirm", json={"id": seed * 1000 + det_id, "by": "px4-check"})
                                print(f"  seed {seed} {method}: found victim {k} at {t_sim:.0f} s "
                                      f"(cell {tuple(int(v) for v in latlon_to_cell(vlat, vlon))})")
            if t0 is None:
                raise RuntimeError("drones never reached search altitude; see logs in " + str(logdir))
    finally:
        for p in procs[::-1]:
            _kill(p)
        subprocess.run(["pkill", "-x", "px4"], check=False)
        await asyncio.sleep(2)

    times = sorted(found.values())
    effective = (dist_m / wall_flying / SPEED_MPS) if wall_flying > 0 else float("nan")
    fs = fastsim_run(scn, method)
    return {"seed": seed, "method": method, "n_victims": len(victims), "n_unreachable": n_unreach,
            "ttff_s": round(times[0], 1) if times else float("nan"),
            "found_20min": sum(t <= FIND_WINDOW_S for t in times), "found_total": len(times),
            "fastsim_ttff_s": fs.ttff_s, "fastsim_found_20min": fs.found_20min,
            "speed_factor": speed, "effective_factor": round(effective, 2)}


async def main(seeds, methods, speed, t_max):
    logdir = Path(os.environ.get("TRAAN_LOGDIR", "/tmp/traan_px4_check"))
    logdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in seeds:
        for method in methods:
            print(f"running seed {seed} / {method} at {speed}x ...")
            rows.append(await one_run(seed, method, speed, t_max, logdir))
            print("  ->", rows[-1])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {OUT}\n{'seed':>4} {'method':6} {'PX4 TTFF s':>10} {'fast-sim TTFF s':>15} "
          f"{'PX4 found<=20m':>14} {'fast-sim':>8} {'eff. speed':>10}")
    for r in rows:
        print(f"{r['seed']:>4} {r['method']:6} {r['ttff_s']:>10} {r['fastsim_ttff_s']:>15} "
              f"{r['found_20min']:>9}/{r['n_victims']:<4} {r['fastsim_found_20min']:>8} {r['effective_factor']:>9}x")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--methods", nargs="+", default=["bayes", "grid"], choices=list(MODE))
    ap.add_argument("--speed", type=float, default=4.0, help="PX4 SIH speed-up (lockstep)")
    ap.add_argument("--t-max", type=float, default=3600.0, help="simulated seconds per run")
    a = ap.parse_args()
    asyncio.run(main(a.seeds, a.methods, a.speed, a.t_max))
