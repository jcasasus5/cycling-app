from __future__ import annotations

from xml.etree import ElementTree as ET

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, main, strava
from app.models import ActivityCreate, RouteCreate, RouteSegmentBase


@pytest.fixture
def export_client(tmp_path, monkeypatch):
    for name in (
        "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "VERCEL",
        "STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REDIRECT_URI", "APP_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "export.db")

    def unexpected_strava_call(*args, **kwargs):
        pytest.fail("La descarga no debe consultar la conexion ni subir datos a Strava")

    monkeypatch.setattr(main, "_get_strava_connection", unexpected_strava_call)
    monkeypatch.setattr(main, "_refresh_pending_strava_upload", unexpected_strava_call)
    monkeypatch.setattr(strava, "upload_activity", unexpected_strava_call)
    with TestClient(main.app) as client:
        yield client


@pytest.fixture
def saved_activity(export_client):
    route = db.create_route(RouteCreate(
        name="Puerto de prueba", distance_km=1, elevation_gain_m=50,
        start_altitude_m=100, end_altitude_m=150, avg_grade_percent=5, max_grade_percent=5,
        segments=[RouteSegmentBase(
            start_km=0, end_km=1, grade_percent=5, start_altitude_m=100, end_altitude_m=150,
        )],
    ))
    draft = ActivityCreate(
        route_id=route.id, started_at="2026-08-31T10:00:00Z", ended_at="2026-08-31T10:01:00Z",
        status="completed", active_seconds=60, total_seconds=60, distance_km=0.5,
        avg_power_w=210, max_power_w=240, avg_cadence_rpm=85, avg_speed_kph=30,
        completed_elevation_m=25,
        samples=[{
            "timestamp_ms": 1788170460000, "elapsed_seconds": 60, "km": 0.5,
            "speed_kph": 30, "cadence_rpm": 85, "power_w": 210,
            "grade_percent": 5, "altitude_m": 125, "paused": False,
        }],
    )
    return db.create_activity(draft), draft


@pytest.mark.parametrize("status", ["completed", "partial"])
def test_download_tcx_without_strava_credentials(export_client, saved_activity, status):
    activity, draft = saved_activity
    db.update_activity(activity.id, draft.model_copy(update={"status": status}))
    db.update_activity_strava_status(activity.id, upload_id="91", status="pending")
    before = db.get_activity(activity.id)

    response = export_client.get(f"/api/activities/{activity.id}/export.tcx")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.garmin.tcx+xml"
    assert response.headers["content-disposition"] == f'attachment; filename="cycling-activity-{activity.id}.tcx"'
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert not strava.configured()
    namespaces = {"tcx": strava.TCX_NAMESPACE, "ae": strava.ACTIVITY_EXTENSION_NAMESPACE}
    root = ET.fromstring(response.content)
    assert root.find("tcx:Activities/tcx:Activity", namespaces).attrib["Sport"] == "Biking"
    point = root.find(".//tcx:Trackpoint", namespaces)
    assert point.findtext("tcx:Time", namespaces=namespaces) == "2026-08-31T10:01:00.000Z"
    assert point.findtext("tcx:DistanceMeters", namespaces=namespaces) == "500.0"
    assert point.findtext("tcx:AltitudeMeters", namespaces=namespaces) == "125.0"
    assert point.findtext("tcx:Cadence", namespaces=namespaces) == "85"
    assert point.findtext("tcx:Extensions/ae:TPX/ae:Watts", namespaces=namespaces) == "210"
    assert point.findtext("tcx:Extensions/ae:TPX/ae:Speed", namespaces=namespaces) == "8.333"
    assert db.get_activity(activity.id) == before


def test_download_missing_activity_returns_404(export_client):
    assert export_client.get("/api/activities/999/export.tcx").status_code == 404


def test_download_activity_without_samples_returns_clear_error(export_client, saved_activity):
    activity, draft = saved_activity
    db.update_activity(activity.id, draft.model_copy(update={"samples": []}))
    response = export_client.get(f"/api/activities/{activity.id}/export.tcx")
    assert response.status_code == 400
    assert "no tiene datos" in response.json()["detail"]


def test_download_activity_with_invalid_date_returns_clear_error(export_client, saved_activity):
    activity, draft = saved_activity
    db.update_activity(activity.id, draft.model_copy(update={"started_at": "invalid"}))
    response = export_client.get(f"/api/activities/{activity.id}/export.tcx")
    assert response.status_code == 422
    assert "fecha de inicio" in response.json()["detail"]


def test_download_requires_cloud_authentication(export_client, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "publishable-test")
    assert export_client.get("/api/activities/1/export.tcx").status_code == 401


def test_download_fails_closed_without_production_auth(export_client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    assert export_client.get("/api/activities/1/export.tcx").status_code == 503


@pytest.mark.parametrize("sample_count, server_cap", [(1, 1000), (2000, 1000), (1201, 500)])
def test_download_forwards_user_token_and_respects_rls_result(
    export_client, saved_activity, monkeypatch, sample_count, server_cap,
):
    activity, _ = saved_activity
    detail = db.get_activity(activity.id)
    sample_rows = [
        detail.samples[0].model_copy(update={"id": index + 1, "elapsed_seconds": index}).model_dump()
        for index in range(sample_count)
    ]
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "publishable-test")
    requests = []

    def fake_auth(url, *, headers, **kwargs):
        assert url.endswith("/auth/v1/user")
        token = headers["Authorization"].removeprefix("Bearer ")
        return httpx.Response(200, json={"id": token})

    def fake_rest(method, url, *, headers, params, **kwargs):
        assert method == "GET"
        assert headers["apikey"] == "publishable-test"
        requests.append((url, headers["Authorization"], params))
        if headers["Authorization"] != "Bearer owner":
            return httpx.Response(200, json=[])
        if url.endswith("/activities"):
            assert params["id"] == f"eq.{activity.id}"
            assert "strava_" not in params["select"]
            row = detail.activity.model_dump(exclude={
                "route_name", "strava_upload_id", "strava_activity_id", "strava_status", "strava_error",
            })
            return httpx.Response(200, json=[{**row, "routes": {"name": activity.route_name}}])
        assert url.endswith("/activity_samples")
        assert params["activity_id"] == f"eq.{activity.id}"
        assert params["order"] == "elapsed_seconds.asc,id.asc"
        offset = int(params["offset"])
        limit = min(int(params["limit"]), server_cap)
        return httpx.Response(200, json=sample_rows[offset:offset + limit])

    monkeypatch.setattr(httpx, "get", fake_auth)
    monkeypatch.setattr(httpx, "request", fake_rest)
    path = f"/api/activities/{activity.id}/export.tcx"
    response = export_client.get(path, headers={"Authorization": "Bearer owner"})
    assert response.status_code == 200
    points = ET.fromstring(response.content).findall(f".//{{{strava.TCX_NAMESPACE}}}Trackpoint")
    assert len(points) == sample_count
    assert export_client.get(path, headers={"Authorization": "Bearer other-user"}).status_code == 404
    assert all(token == "Bearer owner" for _, token, _ in requests[:-1])
    assert requests[-1][1] == "Bearer other-user"
    offsets = [int(params["offset"]) for url, _, params in requests if url.endswith("/activity_samples")]
    assert offsets == [*range(0, sample_count, server_cap), sample_count]
