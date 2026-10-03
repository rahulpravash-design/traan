"""TRAAN API: event bus (WebSocket), event ingest (REST), SQLite event store, operator commands,
and the one live Planner instance.

    uvicorn api.main:app --reload --port 8000

Live loop: fleet POSTs `telemetry` -> the planner counts the sweep as a pass (negative information)
-> a `map_update` goes out at most once a second. When a drone finishes a leg the fleet calls
POST /planner/next and flies the waypoints it gets back.
"""
from __future__ import annotations

import asyncio
import os
import time

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.commands import authorize_command
from api.schemas import Confirm, Event, MapUpdate
from api.store import EventStore
from planner.nofly import DEFAULT_ZONES
from planner.service import Planner
from planner.sweep import SEARCH_ALT_M
from sim.osm import load_buildings
from sim.terrain import load_dem
from sim.world import (CELL_M, CENTER_LAT, CENTER_LON, HOME_XY, N_CELLS, SIZE_M, corners_latlon, latlon_to_cell,
                       latlon_to_xy, xy_to_latlon)

MAP_UPDATE_MIN_S = 1.0          # throttle for telemetry-driven map updates
SEARCHING_ALT_M = 0.8 * SEARCH_ALT_M  # below this the drone is climbing/landing, not searching
CLIENT_QUEUE = 2000             # events buffered per dashboard before it is dropped as too slow


class Ping(BaseModel):
    lat: float
    lon: float
    acc_m: float = Field(gt=0)


class AlertCmd(BaseModel):
    lat: float
    lon: float
    pings: list[Ping] = []      # phone pings from the telco, if any
    by: str = "operator"


class DecisionCmd(BaseModel):
    id: int
    by: str = "operator"


class NextLegReq(BaseModel):
    drone: str
    lat: float
    lon: float


class Bus:
    """Fan-out with one queue per client: a slow dashboard can't stall ingest, and each client
    gets its snapshot strictly before any live event."""

    def __init__(self):
        self.clients: dict[WebSocket, asyncio.Queue] = {}

    def subscribe(self, ws):
        q = asyncio.Queue(CLIENT_QUEUE)
        self.clients[ws] = q
        return q

    def unsubscribe(self, ws):
        self.clients.pop(ws, None)

    def broadcast(self, event: dict):
        for ws, q in list(self.clients.items()):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                self.unsubscribe(ws)  # it reconnects and gets a fresh snapshot


def _basemap_png(dem, px=800) -> bytes:
    import io

    from PIL import Image, ImageDraw

    from sim.osm import building_rings

    # hillshade from the DEM upsampled first, so 25 m cells don't show as blocks
    fine = np.asarray(Image.fromarray(dem.astype(np.float32)).resize((px, px), Image.BICUBIC), float)
    cell = SIZE_M / px
    gy, gx = np.gradient(fine, cell)                   # row 0 = north
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gy, -gx)
    az, alt = np.radians(315.0), np.radians(45.0)      # light from the north-west
    shade = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
    tone = 0.62 + 0.36 * shade
    rgb = np.stack([tone * 0.97, tone * 0.98, tone * 0.93], axis=-1)
    img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    for lats, lons in building_rings():                # real footprints (OSM or Open Buildings)
        x, y = latlon_to_xy(np.asarray(lats), np.asarray(lons))
        pts = list(zip((np.asarray(x) / SIZE_M * px).tolist(), ((SIZE_M - np.asarray(y)) / SIZE_M * px).tolist()))
        if len(pts) >= 3:
            draw.polygon(pts, fill=(176, 168, 158), outline=(150, 142, 132))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def drone_index(name: str, n: int):
    try:
        i = int(name.lstrip("d")) - 1
    except ValueError:
        return None
    return i if 0 <= i < n else None


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="TRAAN API", version="0.2.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    store = EventStore(db_path or os.environ.get("TRAAN_DB", "traan.sqlite"))
    bus = Bus()
    planner = Planner(n_drones=int(os.environ.get("TRAAN_DRONES", "3")),
                      mode=os.environ.get("TRAAN_PLANNER_MODE", "path"))   # "grid" only for the PX4 cross-check
    dem = load_dem()
    buildings = load_buildings()    # OSM footprints if data/osm.json exists, else None
    last_map = {"t": 0.0, "version": -1}
    basemap_cache: dict[str, bytes] = {}
    app.state.store, app.state.bus, app.state.planner = store, bus, planner

    # Everything that touches the planner or the bus runs on the event loop (async handlers),
    # never in FastAPI's threadpool: neither is thread-safe, and planner calls take milliseconds.
    def publish(event: dict) -> int:
        seq = store.append(event)
        bus.broadcast(event)
        return seq

    def publish_map(force=False):
        if not planner.ready or planner.version == last_map["version"]:
            return
        now = time.monotonic()
        if force or now - last_map["t"] >= MAP_UPDATE_MIN_S:
            publish(MapUpdate(**planner.map_update()).model_dump())
            last_map.update(t=now, version=planner.version)

    @app.get("/health")
    def health():
        return {"ok": True, "ts": time.time(), "ws_clients": len(bus.clients),
                "planner": {"ready": planner.ready, "version": planner.version, "mode": planner.mode}}

    @app.get("/world")
    def world():
        home_lat, home_lon = xy_to_latlon(*HOME_XY)
        return {"center": [CENTER_LAT, CENTER_LON], "cell_m": CELL_M, "n_cells": N_CELLS,
                "corners": corners_latlon(), "home": [float(home_lat), float(home_lon)],
                "nofly": {"type": "FeatureCollection", "features": [z.to_geojson() for z in DEFAULT_ZONES]}}

    @app.get("/world/basemap.png")
    def basemap():
        """Offline basemap for the dashboard: hillshade of the grid's DEM, building cells shaded.
        Works with no internet (venue Wi-Fi), drawn under the heatmap at the grid corners."""
        if "png" not in basemap_cache:
            basemap_cache["png"] = _basemap_png(dem)
        return Response(basemap_cache["png"], media_type="image/png",
                        headers={"Cache-Control": "max-age=3600"})

    @app.post("/events")
    async def ingest(event: Event):
        e = event.model_dump()
        seq = publish(e)
        if e["type"] == "telemetry":
            i = drone_index(e["drone"], planner.n)
            if i is not None:
                x, y = latlon_to_xy(e["lat"], e["lon"])
                planner.on_position(i, (float(x), float(y)), searching=e["alt"] >= SEARCHING_ALT_M)
                publish_map()
        return {"seq": seq}

    @app.get("/events")
    def events(type: str | None = None, after: int = 0, limit: int = 1000):
        return store.query(type, after, min(limit, 5000))

    @app.post("/planner/next")
    async def next_leg(req: NextLegReq):
        """The fleet asks for drone `req.drone`'s next leg. Waypoints are WGS84 [lat, lon]."""
        i = drone_index(req.drone, planner.n)
        if i is None:
            raise HTTPException(404, f"unknown drone {req.drone}")
        if not planner.ready:
            raise HTTPException(409, "no search area yet: waiting for an alert pin")
        x, y = latlon_to_xy(req.lat, req.lon)
        wps = planner.next_route(i, (float(x), float(y)))
        return {"drone": req.drone, "version": planner.version, "target": list(planner.targets[i]),
                "waypoints": [[float(v) for v in xy_to_latlon(*w)] for w in wps]}

    # --- operator commands: the one path every command takes (see api/commands.py) ---
    @app.post("/commands/alert")
    async def alert(cmd: AlertCmd):
        authorize_command("alert", cmd.model_dump())
        x, y = latlon_to_xy(cmd.lat, cmd.lon)
        pings = []
        for p in cmd.pings:
            px, py = latlon_to_xy(p.lat, p.lon)
            pings.append((float(px), float(py), p.acc_m))
        planner.set_prior({"alert_xy": (float(x), float(y)), "pings": pings, "dem": dem, "buildings": buildings})
        publish_map(force=True)
        return {"version": planner.version}

    def _decide(cmd: DecisionCmd, status: str):
        authorize_command(status, cmd.model_dump())
        det = store.latest_detection(cmd.id)
        if det is None:
            raise HTTPException(404, f"no detection {cmd.id}")
        if det["status"] != "pending":
            raise HTTPException(409, f"detection {cmd.id} is already {det['status']}")
        det = {**det, "status": status, "ts": time.time()}
        publish(det)
        if status == "confirmed":
            publish(Confirm(ts=time.time(), id=cmd.id, by=cmd.by).model_dump())
            if planner.ready:
                r, c = latlon_to_cell(det["lat"], det["lon"])
                planner.confirm(int(r), int(c))
                publish_map(force=True)
        return det

    @app.post("/commands/confirm")
    async def confirm(cmd: DecisionCmd):
        return _decide(cmd, "confirmed")

    @app.post("/commands/reject")
    async def reject(cmd: DecisionCmd):
        return _decide(cmd, "rejected")

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        snapshot = store.snapshot()   # no await between these two lines: nothing can slip in between
        q = bus.subscribe(websocket)

        async def drain_incoming():
            while True:
                await websocket.receive_text()  # dashboard sends nothing yet; this notices disconnects

        reader = asyncio.create_task(drain_incoming())
        try:
            for e in snapshot:
                await websocket.send_json(e)
            while not reader.done():
                get = asyncio.create_task(q.get())
                done, _ = await asyncio.wait({get, reader}, return_when=asyncio.FIRST_COMPLETED)
                if get in done:
                    await websocket.send_json(get.result())
                else:
                    get.cancel()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            reader.cancel()
            bus.unsubscribe(websocket)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
