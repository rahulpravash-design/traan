import time

from fastapi.testclient import TestClient

from api.main import create_app


def client():
    return TestClient(create_app(":memory:"))


def test_health_and_world():
    c = client()
    assert c.get("/health").json()["ok"] is True
    w = c.get("/world").json()
    assert w["n_cells"] == 80 and w["cell_m"] == 25.0 and w["nofly"]["features"]


def test_ingest_validates_frozen_schema():
    c = client()
    ok = {"type": "telemetry", "ts": time.time(), "drone": "d1", "lat": 11.41, "lon": 76.7, "alt": 60, "battery": 0.8}
    assert c.post("/events", json=ok).status_code == 200
    assert c.post("/events", json={**ok, "extra": 1}).status_code == 422
    assert c.post("/events", json={**ok, "type": "nope"}).status_code == 422
    assert c.get("/events", params={"type": "telemetry"}).json()[0]["drone"] == "d1"


def test_ws_gets_snapshot_and_live_events():
    c = client()
    t = {"type": "telemetry", "ts": time.time(), "drone": "d2", "lat": 11.41, "lon": 76.7, "alt": 60, "battery": 0.5}
    c.post("/events", json=t)
    with c.websocket_connect("/ws") as ws:
        assert ws.receive_json()["drone"] == "d2"
        c.post("/events", json={**t, "drone": "d3"})
        assert ws.receive_json()["drone"] == "d3"


def test_alert_then_detection_confirm_flow():
    c = client()
    assert c.post("/commands/alert", json={"lat": 11.412, "lon": 76.701}).status_code == 200
    det = {"type": "detection", "ts": time.time(), "id": 17, "drone": "d2", "lat": 11.4121, "lon": 76.6988,
           "conf": 0.81, "frame": "test/0412.jpg", "status": "pending"}
    c.post("/events", json=det)
    r = c.post("/commands/confirm", json={"id": 17})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    assert c.post("/commands/confirm", json={"id": 17}).status_code == 409
    assert c.post("/commands/reject", json={"id": 99}).status_code == 404
    types = [e["type"] for e in c.get("/events").json()]
    assert types == ["map_update", "detection", "detection", "confirm", "map_update"]


def test_commands_need_a_named_human():
    assert client().post("/commands/alert", json={"lat": 11.41, "lon": 76.7, "by": ""}).status_code == 403
