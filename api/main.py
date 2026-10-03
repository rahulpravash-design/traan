"""TRAAN API: event bus (WebSocket), event ingest (REST), SQLite event store, operator commands.

    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import os
import time

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.commands import authorize_command
from api.schemas import Confirm, Event, MapUpdate
from api.store import EventStore
from planner.nofly import DEFAULT_ZONES
from planner.service import Planner
from sim.world import (CELL_M, CENTER_LAT, CENTER_LON, HOME_XY, N_CELLS, corners_latlon, latlon_to_cell,
                       latlon_to_xy, xy_to_latlon)

class AlertCmd(BaseModel):
    lat: float
    lon: float
    by: str = "operator"


class DecisionCmd(BaseModel):
    id: int
    by: str = "operator"


class Bus:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, event: dict):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="TRAAN API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    store = EventStore(db_path or os.environ.get("TRAAN_DB", "traan.sqlite"))
    bus = Bus()
    planner = Planner(n_drones=int(os.environ.get("TRAAN_DRONES", "3")))
    app.state.store, app.state.bus, app.state.planner = store, bus, planner

    async def publish(event: dict) -> int:
        seq = store.append(event)
        await bus.broadcast(event)
        return seq

    @app.get("/health")
    def health():
        return {"ok": True, "ts": time.time(), "ws_clients": len(bus.clients)}

    @app.get("/world")
    def world():
        home_lat, home_lon = xy_to_latlon(*HOME_XY)
        return {"center": [CENTER_LAT, CENTER_LON], "cell_m": CELL_M, "n_cells": N_CELLS,
                "corners": corners_latlon(), "home": [float(home_lat), float(home_lon)],
                "nofly": {"type": "FeatureCollection", "features": [z.to_geojson() for z in DEFAULT_ZONES]}}

    @app.post("/events")
    async def ingest(event: Event):
        return {"seq": await publish(event.model_dump())}

    @app.get("/events")
    def events(type: str | None = None, after: int = 0, limit: int = 1000):
        return store.query(type, after, min(limit, 5000))

    # --- operator commands: the one path every command takes (see api/commands.py) ---
    @app.post("/commands/alert")
    async def alert(cmd: AlertCmd):
        authorize_command("alert", cmd.model_dump())
        x, y = latlon_to_xy(cmd.lat, cmd.lon)
        planner.set_prior({"alert_xy": (float(x), float(y)), "pings": [], "dem": None, "buildings": None})
        mu = MapUpdate(**planner.map_update()).model_dump()
        await publish(mu)
        return {"version": mu["version"]}

    async def _decide(cmd: DecisionCmd, status: str):
        authorize_command(status, cmd.model_dump())
        det = store.latest_detection(cmd.id)
        if det is None:
            raise HTTPException(404, f"no detection {cmd.id}")
        if det["status"] != "pending":
            raise HTTPException(409, f"detection {cmd.id} is already {det['status']}")
        det = {**det, "status": status, "ts": time.time()}
        await publish(det)
        if status == "confirmed":
            await publish(Confirm(ts=time.time(), id=cmd.id, by=cmd.by).model_dump())
            if planner.P is not None:
                r, c = latlon_to_cell(det["lat"], det["lon"])
                planner.confirm(int(r), int(c))
                await publish(MapUpdate(**planner.map_update()).model_dump())
        return det

    @app.post("/commands/confirm")
    async def confirm(cmd: DecisionCmd):
        return await _decide(cmd, "confirmed")

    @app.post("/commands/reject")
    async def reject(cmd: DecisionCmd):
        return await _decide(cmd, "rejected")

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        # replay enough state for a fresh dashboard: latest map, last telemetry per drone, detections
        snapshot = {}
        for e in store.query(None, 0, 100000)[-5000:]:
            key = e["type"] + ":" + str(e.get("drone") if e["type"] == "telemetry" else e.get("id", ""))
            snapshot[key] = e
        for e in sorted(snapshot.values(), key=lambda e: e["seq"]):
            e.pop("seq", None)
            await websocket.send_json(e)
        bus.clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()  # dashboard sends nothing yet; keeps the socket alive
        except WebSocketDisconnect:
            pass
        finally:
            bus.clients.discard(websocket)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
