"""Replay mapper + perception plumbing. Uses a tiny fake HIT-UAV layout and the label-oracle
detector, so it tests wiring only — never model quality."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sim.replay_mapper import ReplayMapper
from sim.scenario import make_scenario
from sim.world import xy_to_latlon


@pytest.fixture
def fake_hituav(tmp_path):
    for split in ("test",):
        (tmp_path / "images" / split).mkdir(parents=True)
        (tmp_path / "labels" / split).mkdir(parents=True)
    person, empty = [], []
    for k in range(3):
        (tmp_path / "images/test" / f"p{k}.jpg").write_bytes(b"\xff\xd8fake")
        (tmp_path / "labels/test" / f"p{k}.txt").write_text("0 0.5 0.5 0.05 0.1\n")
        person.append(f"test/p{k}.jpg")
        (tmp_path / "images/test" / f"e{k}.jpg").write_bytes(b"\xff\xd8fake")
        (tmp_path / "labels/test" / f"e{k}.txt").write_text("")
        empty.append(f"test/e{k}.jpg")
    (tmp_path / "replay_index.json").write_text(json.dumps({"person": person, "empty": empty}))
    return tmp_path


def _tel(drone, x, y, ts, alt=60.0):
    lat, lon = xy_to_latlon(x, y)
    return {"type": "telemetry", "ts": ts, "drone": drone, "lat": float(lat), "lon": float(lon), "alt": alt, "battery": 1.0}


def _scenario_with_reachable_victim():
    for seed in range(50):
        m = ReplayMapper(make_scenario(seed), empty_every_s=1e9)
        if m.victims:
            return m
    raise AssertionError("no scenario with a reachable victim")


def test_victim_frame_when_footprint_crosses_victim():
    m = _scenario_with_reachable_victim()
    k, _ = m.victims[0]
    vx, vy = m.scn.victims_xy[k]
    first = m.on_telemetry(_tel("d1", vx - 150, vy, 0.0))             # first fix: victim not in view yet
    assert not any(o.victim_in_view for o in first)
    obs = m.on_telemetry(_tel("d1", vx + 150, vy, 1.0))              # flew right over the victim
    assert any(o.victim_in_view for o in obs)
    o = next(o for o in obs if o.victim_in_view)
    lat, lon = xy_to_latlon(vx, vy)
    assert abs(o.lat - lat) < 1e-3 and abs(o.lon - lon) < 1e-3       # simulated geolocation, ~8 m error
    assert not any(o.victim_in_view for o in m.on_telemetry(_tel("d1", vx + 150, vy, 2.0)))  # same pass


def test_climbing_drone_sees_nothing_and_empty_frames_are_throttled():
    m = ReplayMapper(make_scenario(1), empty_every_s=4.0)
    k_xy = m.scn.victims_xy[m.victims[0][0]] if m.victims else np.array([1000.0, 1000.0])
    assert m.on_telemetry(_tel("d2", *k_xy, 0.0, alt=10)) == []      # climbing right over a victim
    far = (1950.0, 50.0)
    frames = [m.on_telemetry(_tel("d2", far[0], far[1] + 5 * t, float(t + 1))) for t in range(9)]
    empties = [o for f in frames for o in f if not o.victim_in_view]
    assert len(empties) == 3 and not any(o.victim_in_view for f in frames for o in f)  # t = 1, 5, 9 s


def test_perception_service_turns_person_frames_into_detections(fake_hituav, monkeypatch):
    monkeypatch.setenv("TRAAN_REPLAY_ROOT", str(fake_hituav))
    monkeypatch.setenv("TRAAN_DETECTOR", "label-oracle")
    import perception.service as svc
    svc._state.clear()
    posted = []
    monkeypatch.setattr(svc.httpx, "post", lambda url, json, timeout: posted.append(json))
    c = TestClient(svc.app)
    h = c.get("/health").json()
    assert h["ok"] and h["detector"] == "label-oracle" and 0 < h["conf_min"] < 1

    body = {"drone": "d2", "lat": 11.41, "lon": 76.70, "step": 1, "victim_in_view": True}
    r = c.post("/observe", json=body).json()
    assert r["event"]["type"] == "detection" and r["event"]["status"] == "pending"
    assert r["event"]["frame"].startswith("test/p") and posted == [r["event"]]

    r = c.post("/observe", json={**body, "step": 2, "victim_in_view": False}).json()
    assert r["event"] is None and len(posted) == 1
    assert c.get(f"/frames/{r['frame']}").status_code == 200


def test_replay_is_deterministic(fake_hituav):
    from perception.replay import FrameReplay
    a, b = FrameReplay(fake_hituav, seed=3), FrameReplay(fake_hituav, seed=3)
    assert [a.pick("d1", s, True) for s in range(10)] == [b.pick("d1", s, True) for s in range(10)]


def test_annotated_frame_draws_boxes(fake_hituav, monkeypatch):
    monkeypatch.setenv("TRAAN_REPLAY_ROOT", str(fake_hituav))
    monkeypatch.setenv("TRAAN_DETECTOR", "label-oracle")
    from PIL import Image
    import perception.service as svc
    svc._state.clear()
    svc._annotated.clear()
    Image.new("RGB", (640, 512), (40, 40, 40)).save(fake_hituav / "images/test/p0.jpg")
    r = TestClient(svc.app).get("/annotated/test/p0.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    import io
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    assert any(px[0] > 200 and px[1] > 150 and px[2] < 80 for px in img.getdata())   # a yellow box was drawn
