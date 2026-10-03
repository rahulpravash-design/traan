# CLAUDE.md — TRAAN interface contracts (frozen Day 1)

These contracts let six people build in parallel. **Do not change them without a PR reviewed
by every module owner it touches.** Claude Code: treat everything below as hard rules.

## 1. Event types (exactly four)

Defined in `api/schemas.py` (pydantic, `extra="forbid"`). Every module emits and consumes only these.

```json
{"type":"telemetry","ts":1760000000.1,"drone":"d1","lat":11.4102,"lon":76.6950,"alt":60,"battery":0.82}
{"type":"detection","ts":1760000042.7,"id":17,"drone":"d2","lat":11.4121,"lon":76.6988,"conf":0.81,"frame":"test/0412.jpg","status":"pending"}
{"type":"confirm","ts":1760000050.3,"id":17,"by":"operator"}
{"type":"map_update","ts":1760000051.0,"version":42,"top_cells":[[31,44,0.012],[30,44,0.011]]}
```

| Field | Meaning |
|---|---|
| `ts` | Unix seconds, float |
| `drone` | `d1`, `d2`, `d3` (PX4 instance N ↔ `d{N+1}`) |
| `alt` | metres above the launch point |
| `battery` | 0.0–1.0 |
| `detection.status` | `pending` → `confirmed` or `rejected`. A status change is re-emitted as a new `detection` event with the same `id` |
| `detection.frame` | HIT-UAV frame path relative to the dataset's `images/` dir (`mock/...` from the mock feed) |
| `map_update.top_cells` | `[row, col, p]`, sorted by `p` descending, at most 500 entries; `version` only increases |

Transport: producers `POST /events` to the API; consumers subscribe to `ws://<api>:8000/ws`
(a new socket first receives a snapshot: latest map, last telemetry per drone, the latest state of
every detection, and only then live events, in order).

## 1b. Live-loop REST (not events)

| Call | Who | What |
|---|---|---|
| `POST /commands/alert {lat, lon, pings?: [{lat, lon, acc_m}], by}` | dashboard / reporter | New search area: planner builds the prior, a `map_update` goes out |
| `POST /commands/confirm {id, by}` · `POST /commands/reject {id, by}` | dashboard | Operator decision on a pending detection |
| `POST /planner/next {drone, lat, lon}` → `{waypoints: [[lat, lon], ...], target, version}` | fleet (mock or PX4) | Next leg for that drone; `409` until an alert exists |
| `GET /world` | dashboard | Grid corners, home, no-fly zones (GeoJSON) |

There is exactly **one live `Planner`, inside the API process**. Telemetry at or above 48 m (0.8 × search
altitude) counts as searching: the swept strip since that drone's last report is a pass, and a
`map_update` follows at most once per second. Fleets never run their own planner.

## 2. Coordinates

- **On the wire: WGS84 lat/lon** (EPSG:4326). Always.
- **Inside: UTM zone 43N metres** (EPSG:32643). Local metres `x` east / `y` north from the grid's SW corner.
- All conversions live in `sim/world.py`. Never write your own lat/lon ↔ metres maths.

## 3. Grid

- 80 × 80 cells, 25 m each, a 2 × 2 km square centred on Ooty (11.41° N, 76.70° E).
- Cell `(row, col)`: **row 0 = northern edge, col 0 = western edge** (image convention).
- Drones launch from `HOME_XY` = middle of the southern edge.

## 4. Ownership rules

- **Nothing outside `planner/` reads or writes the probability grid.** Others call `planner.service.Planner`
  methods or read `map_update` events.
- **Every operator command goes through `api/commands.py::authorize_command`** — the single
  signed, human-confirmed path. Today it requires a named human and writes an audit line; module 9
  adds JWT roles + signatures there. Never add a command endpoint that skips it.
- Drones are commanded only by `fleet/` (MAVSDK). The planner returns waypoints; it never calls MAVSDK.
- The detector is used only through `perception/detector.py::Detector` (keeps AGPL Ultralytics swappable).

## 5. Ports

| Service | Port |
|---|---|
| PX4 SITL instance N → MAVLink | UDP 14540+N |
| mavsdk_server for drone N | gRPC 50051+N |
| api | 8000 |
| perception | 8001 |
| dashboard | 5173 |

## 6. Benchmark rules

- True victim positions come from a different model (debris runout + buildings, `sim/scenario.py`)
  than the planner's prior (`planner/prior.py`). The planner only sees `Scenario.observable()`.
- Phone pings: 50–300 m error, 30% missing. Same seeds for both methods; 100 runs each;
  plus a wrong-prior set shifted 400 m.
- Fast sim: 8 m/s, 60 m altitude, 50 m sensor strip, true POD 0.8 per pass. Each victim has a pre-drawn
  sequence of detection coin flips shared by every method (common random numbers).
- Victims inside a no-fly zone are unreachable for every method: report them (`n_unreachable`), don't score them.
- Report median time-to-first-find with IQR and % of victims found within 20 min. Publish the CSV.
  If Bayes does not win, say so.

## 7. Honesty rules for the demo

- Frames are "thermal frame replay (HIT-UAV)", never "live camera".
- Drones are "PX4 SITL", never "real drones".
- `perception.detector.LabelOracleDetector` reads ground-truth labels; it is for plumbing tests only
  and must never be reported as model performance.

## 8. Dev commands

```bash
pip install -r requirements.txt && pytest          # all Python tests
python -m bench.run --runs 100 && python -m bench.plot bench/results/fastsim_100.csv
uvicorn api.main:app --port 8000                   # API
python -m fleet.mock_feed --seed 1 --speedup 5     # fake fleet flying the API planner (no PX4)
python -m fleet.run --drones 3                     # same loop on PX4 SITL
cd dashboard && npm install && npm run dev          # dashboard
```
