"""One MAVSDK adapter per drone: connect, arm/takeoff/land, fly waypoints, push telemetry to the API.

Ports (CLAUDE.md): PX4 instance N sends MAVLink to UDP 14540+N; its mavsdk_server listens on gRPC 50051+N.
mavsdk-python starts that embedded server for us when given `port=`.

Altitudes: the planner speaks 60 m above home; MAVSDK goto_location wants AMSL, so we add home AMSL.
"""
from __future__ import annotations

import asyncio
import math
import os
import time

import httpx

from planner.sweep import SEARCH_ALT_M
from sim.fastsim import SPEED_MPS as CRUISE_MPS

API = os.environ.get("TRAAN_API", "http://localhost:8000")
ARRIVE_M = 5.0


def _dist_m(lat1, lon1, lat2, lon2):
    k = 111_320.0
    return math.hypot((lat2 - lat1) * k, (lon2 - lon1) * k * math.cos(math.radians(lat1)))


class DroneAdapter:
    def __init__(self, index: int, host: str = "0.0.0.0"):
        from mavsdk import System  # imported here so the rest of the repo runs without mavsdk installed

        self.index = index
        self.name = f"d{index + 1}"
        self.mavlink_url = f"udpin://{host}:{14540 + index}"
        self.system = System(port=50051 + index)
        self.lat = self.lon = self.rel_alt = self.home_amsl = None
        self.battery = 1.0

    async def connect(self):
        await self.system.connect(system_address=self.mavlink_url)
        async for s in self.system.core.connection_state():
            if s.is_connected:
                break
        async for h in self.system.telemetry.health():
            if h.is_global_position_ok and h.is_home_position_ok:
                break
        async for home in self.system.telemetry.home():
            self.home_amsl = home.absolute_altitude_m
            break
        asyncio.create_task(self._track_position())
        asyncio.create_task(self._track_battery())

    async def _track_position(self):
        async for p in self.system.telemetry.position():
            self.lat, self.lon, self.rel_alt = p.latitude_deg, p.longitude_deg, p.relative_altitude_m

    async def _track_battery(self):
        async for b in self.system.telemetry.battery():
            pct = b.remaining_percent
            self.battery = max(0.0, min(1.0, pct / 100.0 if pct > 1.0 else pct))  # MAVSDK v1 vs v2 units

    async def takeoff(self, alt_m=SEARCH_ALT_M):
        # goto_location flies at MPC_XY_CRUISE; match the planner's / benchmark's 8 m/s
        try:
            await self.system.param.set_param_float("MPC_XY_CRUISE", CRUISE_MPS)
        except Exception as e:  # older firmware / param missing: fly at its default, but say so
            print(f"[{self.name}] could not set MPC_XY_CRUISE: {e}")
        await self.system.action.set_takeoff_altitude(alt_m)
        await self.system.action.arm()
        await self.system.action.takeoff()
        while self.rel_alt is None or self.rel_alt < alt_m * 0.9:
            await asyncio.sleep(0.5)

    async def goto(self, lat, lon, alt_m=SEARCH_ALT_M):
        await self.system.action.goto_location(lat, lon, self.home_amsl + alt_m, float("nan"))
        while self.lat is None or _dist_m(self.lat, self.lon, lat, lon) > ARRIVE_M:
            await asyncio.sleep(0.25)

    async def fly(self, waypoints_latlon):
        for lat, lon in waypoints_latlon:
            await self.goto(lat, lon)

    async def land(self):
        await self.system.action.land()

    def telemetry_event(self):
        return {"type": "telemetry", "ts": time.time(), "drone": self.name, "lat": self.lat, "lon": self.lon,
                "alt": round(self.rel_alt or 0.0, 1), "battery": round(self.battery, 3)}

    async def stream_telemetry(self, hz=2.0):
        """Push telemetry to the API at 2 Hz until cancelled."""
        async with httpx.AsyncClient(base_url=API, timeout=2.0) as client:
            while True:
                if self.lat is not None:
                    try:
                        await client.post("/events", json=self.telemetry_event())
                    except httpx.HTTPError:
                        pass  # API restarting; next tick retries
                await asyncio.sleep(1.0 / hz)
