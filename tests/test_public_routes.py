import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, main, supabase_db
from app.auth import AuthContext
from app.models import RouteCreate


@pytest.fixture
def route_draft():
    return {
        "name": "Puerto compartido", "distance_km": 1, "elevation_gain_m": 50,
        "start_altitude_m": 100, "end_altitude_m": 150,
        "avg_grade_percent": 5, "max_grade_percent": 5,
        "segments": [{"start_km": 0, "end_km": 1, "grade_percent": 5,
                      "start_altitude_m": 100, "end_altitude_m": 150}],
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "VERCEL", "STRAVA_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "routes.db")
    with TestClient(main.app) as client:
        yield client


def test_routes_are_private_by_default_and_copies_are_independent(client, route_draft):
    route = client.post("/api/routes", json=route_draft).json()
    assert route["is_public"] is False
    assert route["is_owner"] is True
    route_draft["is_public"] = True
    public = client.put(f"/api/routes/{route['id']}", json=route_draft).json()
    assert public["is_public"] is True
    assert client.get("/api/routes").json()[0]["is_public"] is True
    copy = client.post(f"/api/routes/{route['id']}/duplicate").json()
    assert copy["id"] != route["id"]
    assert copy["is_public"] is False
    assert copy["is_owner"] is True
    assert copy["segments"][0]["id"] != route["segments"][0]["id"]
    route_draft.update(name="Mi copia editada", is_public=False)
    assert client.put(f"/api/routes/{copy['id']}", json=route_draft).status_code == 200
    assert client.get(f"/api/routes/{route['id']}").json()["name"] == "Puerto compartido"
    assert client.delete(f"/api/routes/{copy['id']}").status_code == 204
    assert client.get(f"/api/routes/{route['id']}").status_code == 200
    assert client.put(f"/api/routes/{route['id']}", json=route_draft).json()["is_public"] is False


@pytest.mark.parametrize("method", ["put", "delete"])
def test_api_rejects_public_route_writes_by_another_user(client, route_draft, monkeypatch, method):
    route = db.create_route(RouteCreate(**route_draft, is_public=True))
    monkeypatch.setattr(main, "auth_enabled", lambda: True)
    monkeypatch.setattr(supabase_db, "get_route", lambda *_: route.model_copy(update={"is_owner": False}))

    def forbidden_write(*_):
        pytest.fail("A non-owner must not reach a write operation")

    monkeypatch.setattr(supabase_db, "update_route", forbidden_write)
    monkeypatch.setattr(supabase_db, "delete_route", forbidden_write)
    response = client.request(method, f"/api/routes/{route.id}", json=route_draft)
    assert response.status_code == 403
    monkeypatch.setattr(supabase_db, "get_route", lambda *_: None)
    assert client.request(method, f"/api/routes/{route.id}", json=route_draft).status_code == 404


@pytest.mark.parametrize("server_cap", [1, 2])
def test_supabase_lists_all_routes_with_ownership_and_own_first(client, route_draft, monkeypatch, server_cap):
    template = db.create_route(RouteCreate(**route_draft)).model_dump(exclude={"segments", "is_owner"})
    rows = [
        {**template, "id": 3, "user_id": "other", "is_public": True},
        {**template, "id": 2, "user_id": "owner", "is_public": False},
        {**template, "id": 1, "user_id": "owner", "is_public": True},
    ]
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "test-key")
    offsets = []

    def rest(method, url, *, headers, params, **_):
        assert method == "GET" and url.endswith("/routes")
        assert headers["Authorization"] == "Bearer user-token"
        assert params["or"] == "(user_id.eq.owner,is_public.eq.true)"
        assert params["order"] == "created_at.desc,id.desc"
        offset = int(params["offset"])
        offsets.append(offset)
        return httpx.Response(200, json=rows[offset:offset + server_cap])

    monkeypatch.setattr(httpx, "request", rest)
    result = supabase_db.list_routes(AuthContext("owner", "user-token"))
    assert [route.id for route in result] == [2, 1, 3]
    assert [route.is_owner for route in result] == [True, True, False]
    assert "user_id" not in result[0].model_dump()
    assert offsets[-1] == len(rows)


@pytest.mark.parametrize("is_public", [False, True])
@pytest.mark.parametrize("status", ["partial", "completed"])
def test_deleting_any_route_preserves_activity_samples_and_export(client, route_draft, is_public, status):
    route = client.post("/api/routes", json={**route_draft, "is_public": is_public}).json()
    activity = client.post("/api/activities", json={
        "route_id": route["id"], "started_at": "2026-08-31T10:00:00Z", "ended_at": "2026-08-31T10:01:00Z",
        "status": status, "active_seconds": 60, "total_seconds": 60, "distance_km": 0.5,
        "avg_power_w": 200, "max_power_w": 220, "avg_cadence_rpm": 85, "avg_speed_kph": 30,
        "completed_elevation_m": 25,
        "samples": [{"timestamp_ms": 1788170460000, "elapsed_seconds": 60, "km": 0.5,
                     "speed_kph": 30, "cadence_rpm": 85, "power_w": 200, "grade_percent": 5,
                     "altitude_m": 125, "paused": False}],
    }).json()
    path = f"/api/activities/{activity['id']}"
    before = client.get(path).json()
    tcx_before = client.get(path + "/export.tcx").content
    assert client.put(f"/api/routes/{route['id']}", json={
        **route_draft, "name": "Ruta renombrada", "is_public": is_public,
    }).status_code == 200
    assert client.get(path).json()["activity"]["route_name"] == route_draft["name"]
    assert client.delete(f"/api/routes/{route['id']}").status_code == 204
    after = client.get(path).json()
    assert after["samples"] == before["samples"]
    assert after["activity"] == {**before["activity"], "route_id": None}
    assert client.get("/api/activities").json() == [after["activity"]]
    assert client.get(path + "/export.tcx").content == tcx_before
    db.init_db()
    assert client.get(path).json() == after
    # Only explicitly deleting the activity removes its samples.
    assert client.delete(path).status_code == 204
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM activity_samples").fetchone()[0] == 0


def test_legacy_sqlite_migration_keeps_history_and_defaults_routes_to_private(client, route_draft):
    # Reproduce the old SQLite schema without reading or changing real user data.
    with db.connect() as conn:
        conn.execute("DROP TABLE activities")
        conn.execute("""CREATE TABLE activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
            started_at TEXT NOT NULL, ended_at TEXT NOT NULL, status TEXT NOT NULL,
            active_seconds INTEGER NOT NULL, total_seconds INTEGER NOT NULL, distance_km REAL NOT NULL,
            avg_power_w INTEGER NOT NULL, max_power_w INTEGER NOT NULL, avg_cadence_rpm INTEGER NOT NULL,
            avg_speed_kph REAL NOT NULL, completed_elevation_m REAL NOT NULL
        )""")
        conn.execute("ALTER TABLE routes DROP COLUMN is_public")
        conn.execute("""INSERT INTO routes VALUES (1, 'Ruta antigua', 1, 50, 100, 150, 5, 5, '2026-01-01', NULL)""")
        conn.execute("""INSERT INTO activities VALUES (1, 1, '2026-01-01', '2026-01-01', 'partial', 60, 60, 0.5, 200, 200, 85, 30, 25)""")
        conn.execute("""INSERT INTO activity_samples VALUES (1, 1, 1, 60, 0.5, 30, 85, 200, 5, 125, 0)""")
    db.init_db()
    db.init_db()
    assert db.get_route(1).is_public is False
    before = db.get_activity(1)
    assert before.activity.route_name == "Ruta antigua"
    assert len(before.samples) == 1
    db.delete_route(1)
    after = db.get_activity(1)
    assert after.activity.route_id is None
    assert after.samples == before.samples
    assert after.activity.route_name == before.activity.route_name
    with db.connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("route_id", [None, 1])
def test_cloud_activity_remains_readable_without_visible_route(monkeypatch, route_id):
    row = {
        "id": 1, "route_id": route_id, "route_name": "Nombre conservado", "routes": None,
        "started_at": "2026-08-31T10:00:00Z", "ended_at": "2026-08-31T10:01:00Z", "status": "partial",
        "active_seconds": 60, "total_seconds": 60, "distance_km": 0.5, "avg_power_w": 200,
        "max_power_w": 200, "avg_cadence_rpm": 85, "avg_speed_kph": 30, "completed_elevation_m": 25,
    }

    def rest(auth, method, path, *, params):
        if path == "activity_samples":
            return []
        assert "!inner" not in params["select"]
        return [row]

    monkeypatch.setattr(supabase_db, "_request", rest)
    auth = AuthContext("owner", "token")
    assert supabase_db.get_activity(auth, 1).activity.route_name == "Nombre conservado"
    assert supabase_db.list_activities(auth)[0].route_id == route_id
