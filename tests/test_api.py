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


def _telemetry(drone, lat, lon, alt=60.0):
    return {"type": "telemetry", "ts": time.time(), "drone": drone, "lat": lat, "lon": lon, "alt": alt, "battery": 0.9}


def test_planner_next_needs_an_alert_then_returns_safe_waypoints():
    from planner.nofly import DEFAULT_ZONES
    from sim.world import latlon_to_xy
    c = client()
    assert c.post("/planner/next", json={"drone": "d1", "lat": 11.401, "lon": 76.70}).status_code == 409
    c.post("/commands/alert", json={"lat": 11.412, "lon": 76.701,
                                    "pings": [{"lat": 11.413, "lon": 76.702, "acc_m": 120}]})
    r = c.post("/planner/next", json={"drone": "d1", "lat": 11.401, "lon": 76.70})
    assert r.status_code == 200
    wps = r.json()["waypoints"]
    assert wps and all(not any(z.contains(*latlon_to_xy(a, b)) for z in DEFAULT_ZONES) for a, b in wps)
    assert c.post("/planner/next", json={"drone": "d9", "lat": 11.4, "lon": 76.7}).status_code == 404


def test_searching_telemetry_updates_the_map_and_climbing_does_not():
    c = client()
    c.post("/commands/alert", json={"lat": 11.41, "lon": 76.70})
    v0 = c.get("/health").json()["planner"]["version"]
    c.post("/events", json=_telemetry("d1", 11.4100, 76.7000, alt=20))      # climbing: no search
    c.post("/events", json=_telemetry("d1", 11.4105, 76.7000, alt=20))
    assert c.get("/health").json()["planner"]["version"] == v0
    c.post("/events", json=_telemetry("d1", 11.4100, 76.7000))
    c.post("/events", json=_telemetry("d1", 11.4110, 76.7000))              # ~110 m at 60 m: a pass
    assert c.get("/health").json()["planner"]["version"] > v0


def test_ws_snapshot_is_current_after_many_events():
    c = client()
    for k in range(300):
        c.post("/events", json=_telemetry("d1", 11.40 + k * 1e-5, 76.70))
    c.post("/events", json=_telemetry("d2", 11.41, 76.71))
    with c.websocket_connect("/ws") as ws:
        got = [ws.receive_json(), ws.receive_json()]
    by_drone = {e["drone"]: e for e in got}
    assert abs(by_drone["d1"]["lat"] - (11.40 + 299e-5)) < 1e-9 and "d2" in by_drone


def test_offline_basemap_is_a_png():
    r = client().get("/world/basemap.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:4] == b"\x89PNG"
