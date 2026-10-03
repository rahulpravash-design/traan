"""Perception service (port 8001): frame replay -> detector -> `detection` event on the API.

    uvicorn perception.service:app --port 8001

POST /observe {"drone": "d2", "lat": .., "lon": .., "step": 412, "victim_in_view": true}
The caller (fleet/sim integration) decides `victim_in_view` from the scenario's ground truth;
this service never sees victim positions.
"""
from __future__ import annotations

import itertools
import json
import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.schemas import Detection
from perception.detector import load_detector
from perception.replay import FrameReplay

API = os.environ.get("TRAAN_API", "http://localhost:8000")
def _default_conf_min():
    """The threshold perception/operating_point.py picked from the test split (frame recall = the
    benchmark's POD), unless TRAAN_CONF_MIN overrides it."""
    try:
        return float(json.loads(Path("perception/metrics.json").read_text())["operating_point"]["conf_min"])
    except (OSError, KeyError, ValueError):
        return 0.6


CONF_MIN = float(os.environ.get("TRAAN_CONF_MIN", _default_conf_min()))

app = FastAPI(title="TRAAN perception", version="0.1.0")
_state = {}
_ids = itertools.count(int(time.time() * 1000) % 2_000_000_000)  # unique across restarts


def _replay():
    if "replay" not in _state:
        _state["replay"] = FrameReplay(root=os.environ.get("TRAAN_REPLAY_ROOT", "data/hituav_person"),
                                       seed=int(os.environ.get("TRAAN_SEED", "0")))
        _state["detector"] = load_detector()
    return _state["replay"], _state["detector"]


class Observation(BaseModel):
    drone: str
    lat: float
    lon: float
    step: int
    victim_in_view: bool


@app.get("/health")
def health():
    try:
        _, det = _replay()
        return {"ok": True, "detector": det.name, "conf_min": CONF_MIN}
    except FileNotFoundError:
        return {"ok": False, "error": "replay index missing — run perception.prepare_hituav"}


@app.post("/observe")
def observe(obs: Observation):
    replay, det = _replay()
    frame = replay.pick(obs.drone, obs.step, obs.victim_in_view)
    boxes = det.detect(str(replay.path(frame)))
    best = max(boxes, key=lambda b: b.conf, default=None)
    out = {"frame": frame, "detector": det.name, "boxes": [b.__dict__ for b in boxes], "event": None}
    if best and best.conf >= CONF_MIN:
        ev = Detection(ts=time.time(), id=next(_ids), drone=obs.drone, lat=obs.lat, lon=obs.lon,
                       conf=round(best.conf, 3), frame=frame).model_dump()
        try:
            httpx.post(f"{API}/events", json=ev, timeout=2.0)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"API unreachable: {e}")
        out["event"] = ev
    return out


@app.get("/frames/{split}/{name}")
def frame(split: str, name: str):
    replay, _ = _replay()
    p = replay.path(f"{split}/{name}")
    if not p.exists() or ".." in name:
        raise HTTPException(404)
    return FileResponse(p)


_annotated: dict[str, bytes] = {}


@app.get("/annotated/{split}/{name}")
def annotated(split: str, name: str):
    """The frame with the detector's boxes (conf >= CONF_MIN) drawn on, for the dashboard card."""
    import io

    from fastapi.responses import Response
    from PIL import Image, ImageDraw

    key = f"{split}/{name}"
    if key not in _annotated:
        replay, det = _replay()
        p = replay.path(key)
        if not p.exists() or ".." in name:
            raise HTTPException(404)
        img = Image.open(p).convert("RGB")
        draw = ImageDraw.Draw(img)
        for b in det.detect(str(p)):
            if b.conf < CONF_MIN:
                continue
            x0, y0, x1, y1 = b.xyxy
            if max(b.xyxy) <= 1.0:                       # label oracle: normalised coordinates
                x0, x1, y0, y1 = x0 * img.width, x1 * img.width, y0 * img.height, y1 * img.height
            draw.rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2], outline=(255, 196, 0), width=3)
            draw.text((x0, max(0, y0 - 14)), f"person {b.conf:.2f}", fill=(255, 196, 0))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        _annotated[key] = buf.getvalue()
    return Response(_annotated[key], media_type="image/jpeg")
