# TRAAN: 14-day plan to 50%

6 members, ~4 focused hours each per day, Sun 4 Oct – Sat 17 Oct, simulation only.
Stretch days if college needs it, but keep the order and the daily checks.

## Day by day

| Day | Date | Build | ✅ Check (pass / fail) |
|---|---|---|---|
| 1 | Sun 4 Oct | Repo, Docker, CLAUDE.md contracts, roles. A: one PX4 SITL drone | Everyone runs `docker compose up`; `python -m fleet.smoke_test` arms, takes off, lands |
| 2 | Mon 5 | A: 3 drones, origin at Nilgiris. B: API skeleton. C: grid + prior from slope, buildings, pings. D: HIT-UAV person subset, **start training**. E: MapLibre on the mock feed. F: SRTM + OSM | 3 drones in QGroundControl; prior heatmap PNG |
| 3 | Tue 6 | A: 3 drones fly waypoint missions at once. B: telemetry → WS at 2 Hz. C: Bayes update + grid-sweep baseline in fast sim. D: **mAP50 on test split**. E: live drone markers. F: victim generator | mAP recorded; baseline runs end to end in fast sim |
| 4 | Wed 7 | C: greedy allocation + fixed no-fly zone, first 10 benchmark runs. A+B: planner → MAVSDK waypoint streaming. D: inference endpoint + replay mapper. E: heatmap layer | **Planner commands the SITL drones** |
| 5 | Thu 8 | **Integration #1:** alert pin → prior → 3 drones fly planner waypoints → heatmap updates | Search runs live with no manual steering |
| 6 | Fri 9 | D+B: detection in the loop. E: detection queue + confirm. C: 100-run benchmark + wrong-prior test | Detections reach the dashboard |
| 7 | Sat 10 | **Integration #2:** full Find loop | 1 scenario, ≥1 confirmed find; only manual input is "confirm" |
| 8 | Sun 11 | Buffer, bug bash, rough screen recording | Nothing on the critical path open |
| 9 | Mon 12 | Hardening: reconnects, scenario reset, fixed seeds. C: charts. D: P/R table. E: timer + coverage % | Find loop 3× in a row without restart |
| 10 | Tue 13 | 3 full scenarios in PX4 SITL, Bayes vs grid, cross-check fast sim | PX4 agrees in direction with fast sim |
| 11 | Wed 14 | README, `bench/results/*.csv`, tag `v0.5` | Fresh clone runs from README alone |
| 12 | Thu 15 | Record demo video; update deck | Video ≤ 2:30, uploaded |
| 13 | Fri 16 | Judge Q&A dry run incl. "add a no-fly zone now" | Each answer backed by something on screen |
| 14 | Sat 17 | Freeze, repo public, fill deck placeholders | Links work; no «…» left in deck |

## What already exists after Day 1 scaffold

| Owner | Ready to extend | First real task |
|---|---|---|
| A | `fleet/px4_sitl.sh`, `docker/px4.Dockerfile` | Build PX4, verify home position lands at Ooty (SIH may ignore `PX4_HOME_*`) |
| B | `api/` (bus, store, commands, live planner), `fleet/adapter.py`, `fleet/run.py` | Run `fleet.smoke_test`, then `fleet.run --drones 3`, against SITL |
| C | `planner/`, `sim/`, `bench/` | Remaining wrong-prior tail (5/99 no-find vs 1/99 grid): try a coverage floor or prior-trust decay; tune `ALERT_SIGMA_M` |
| D | `perception/` | `data/fetch.sh hituav` → `prepare_hituav` → `train` → `metrics.json` |
| E | `dashboard/` | Coverage %, mission timer, frame image in detection card |
| F | `data/fetch.sh`, README, this plan | Use `data/osm.json` buildings in `sim/scenario.py` instead of synthetic hamlets |

## Demo video (2:30)

| Time | Shot |
|---|---|
| 0:00–0:15 | Problem: 134.5 min, 2.2× the golden hour; Wayanad search done by hand |
| 0:15–0:35 | Drop alert pin on the Nilgiris map; prior heatmap appears |
| 0:35–1:10 | 3 PX4 drones launch; cleared cells fade; zoom into one replan |
| 1:10–1:40 | Detection with thermal frame + box; operator confirms; marker turns green |
| 1:40–2:10 | Benchmark chart incl. wrong-prior result |
| 2:10–2:30 | "50% complete: 6 of 9 modules. Next: comms-loss handling, ground robot, signed commands." |

## Judge Q&A, with what to show

| Question | Show |
|---|---|
| Why Bayesian search? | Benchmark chart + CSV |
| What if the prior is wrong? | 400 m wrong-prior row, including the no-find tail and what we're doing about it |
| Are these real drones? | "PX4 SITL simulation for this prototype" |
| Is the thermal camera live? | "HIT-UAV thermal frame replay; live camera is the next phase" |
| What if comms drop? | "Store-and-forward + relay drone are planned, deliberately outside the 50% build" |

## Risks and fallbacks

| Risk | Fallback |
|---|---|
| Gazebo too heavy for 8 GB laptops | SIH headless (`px4_sitl.sh` already uses it); dashboard is the visual |
| MAVSDK port clashes | One mavsdk_server per drone on 50051+N; PX4 `-i N` → UDP 14540+N (built into `fleet/adapter.py`) |
| YOLO weak on small thermal targets | `yolov8s.pt`, person class only, free cloud GPU |
| Bayes doesn't beat grid sweep | Check prior and POD settings; report honestly |
| Integration slips | Contracts + mock feed mean nobody waits on anyone |
| Team split across other PSs | One owner per module; daily checks surface slippage within 24 h |

## When you hit 50%, update the deck

- Slide 3: "≈50% of the prototype is complete: 6 of 9 modules working; Find loop live in PX4 simulation", plus GitHub + demo links.
- Slide 5 KPI: replace "≥30%" with the **measured** median; drop its TARGET tag. Keep the tag on "0 Lost".
