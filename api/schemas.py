"""The four frozen event types. Change these only by PR with every module owner reviewing.
See CLAUDE.md for the field meanings. All coordinates on the wire are WGS84."""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ts: float


class Telemetry(_Event):
    type: Literal["telemetry"] = "telemetry"
    drone: str
    lat: float
    lon: float
    alt: float            # metres above home (AGL at launch point)
    battery: float = Field(ge=0.0, le=1.0)


class Detection(_Event):
    type: Literal["detection"] = "detection"
    id: int
    drone: str
    lat: float
    lon: float
    conf: float = Field(ge=0.0, le=1.0)
    frame: str            # HIT-UAV frame path, relative to the dataset root
    status: Literal["pending", "confirmed", "rejected"] = "pending"


class Confirm(_Event):
    type: Literal["confirm"] = "confirm"
    id: int               # detection id
    by: str


class MapUpdate(_Event):
    type: Literal["map_update"] = "map_update"
    version: int
    top_cells: list[tuple[int, int, float]]   # [row, col, p], p descending, row 0 = north


Event = Annotated[Union[Telemetry, Detection, Confirm, MapUpdate], Field(discriminator="type")]
