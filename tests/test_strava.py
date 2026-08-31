from __future__ import annotations

from xml.etree import ElementTree as ET

import httpx
import pytest
from cryptography.fernet import Fernet

from app import db, main, strava, supabase_db
from app.auth import AuthContext
from app.models import ActivityCreate, ActivityDetail, ActivitySample, RouteCreate, RouteSegmentBase
from app.secrets import encrypt_secret


@pytest.fixture
def strava_environment(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("STRAVA_CLIENT_ID", "12345")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("STRAVA_REDIRECT_URI", "http://127.0.0.1:8001/")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)


def sample_draft(*, status: str = "completed") -> ActivityCreate:
    return ActivityCreate(
        route_id=1,
        started_at="2026-08-29T10:00:00Z",
        ended_at="2026-08-29T10:00:02Z",
        status=status,
        active_seconds=2,
        total_seconds=2,
        distance_km=0.02,
        avg_power_w=210,
        max_power_w=240,
        avg_cadence_rpm=86,
        avg_speed_kph=36,
        completed_elevation_m=2,
        samples=[
            {
                "timestamp_ms": 1787997600000,
                "elapsed_seconds": 0,
                "km": 0,
                "speed_kph": 32,
                "cadence_rpm": 82,
                "power_w": 180,
                "grade_percent": 5,
                "altitude_m": 700,
                "paused": False,
            },
            {
                "timestamp_ms": 1787997601000,
                "elapsed_seconds": 1,
                "km": 0.02,
                "speed_kph": 40,
                "cadence_rpm": 90,
                "power_w": 240,
                "grade_percent": 5,
                "altitude_m": 702,
                "paused": False,
            },
        ],
    )


def activity_detail() -> ActivityDetail:
    draft = sample_draft()
    return ActivityDetail(
        activity={
            "id": 7,
            "route_id": 1,
            "route_name": "Puerto de prueba",
            **draft.model_dump(exclude={"samples"}),
        },
        samples=[
            ActivitySample(id=index, activity_id=7, **sample.model_dump())
            for index, sample in enumerate(draft.samples, start=1)
        ],
    )


def test_oauth_state_is_signed_bound_to_user_and_expires(strava_environment):
    state = strava.create_oauth_state("user-a", now=1_000, nonce="fixed")

    strava.verify_oauth_state(state, "user-a", now=1_300)

    with pytest.raises(strava.StravaError, match="otro usuario"):
        strava.verify_oauth_state(state, "user-b", now=1_300)
    with pytest.raises(strava.StravaError, match="caducado"):
        strava.verify_oauth_state(state, "user-a", now=2_000)
    with pytest.raises(strava.StravaError, match="no es válido"):
        strava.verify_oauth_state(f"{state}tampered", "user-a", now=1_300)


def test_oauth_rejects_connection_without_activity_write_scope(monkeypatch, strava_environment):
    monkeypatch.setattr(
        strava.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": 4_102_444_800,
                "scope": "read",
                "athlete": {"id": 77},
            },
        ),
    )

    with pytest.raises(strava.StravaError, match="permiso"):
        strava.exchange_authorization_code("code")


def test_build_tcx_contains_trainer_streams():
    root = ET.fromstring(strava.build_tcx(activity_detail()))
    tcx = {"tcx": strava.TCX_NAMESPACE, "ns3": strava.ACTIVITY_EXTENSION_NAMESPACE}

    activity = root.find("tcx:Activities/tcx:Activity", tcx)
    points = root.findall(".//tcx:Trackpoint", tcx)

    assert activity is not None
    assert activity.attrib["Sport"] == "Biking"
    assert len(points) == 2
    assert points[1].findtext("tcx:DistanceMeters", namespaces=tcx) == "20.0"
    assert points[1].findtext("tcx:Cadence", namespaces=tcx) == "90"
    assert points[1].findtext("tcx:Extensions/ns3:TPX/ns3:Watts", namespaces=tcx) == "240"
    assert points[1].findtext("tcx:Extensions/ns3:TPX/ns3:Speed", namespaces=tcx) == "11.111"


def test_upload_marks_activity_as_virtual_trainer_ride(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return httpx.Response(201, json={"id": 91, "id_str": "91", "activity_id": None, "error": None})

    def fake_get(url, **kwargs):
        return httpx.Response(200, json={"id_str": "91", "activity_id": 1234567890123, "error": None})

    monkeypatch.setattr(strava.httpx, "post", fake_post)
    monkeypatch.setattr(strava.httpx, "get", fake_get)

    result = strava.upload_activity("access-token", activity_detail(), "cycling-app-user-7", sleeper=lambda _: None)

    assert result == strava.StravaUploadResult(upload_id="91", activity_id="1234567890123", status="ready")
    assert captured["data"]["sport_type"] == "VirtualRide"
    assert captured["data"]["trainer"] == "1"
    assert captured["data"]["external_id"] == "cycling-app-user-7"
    assert b"<ae:Watts>240</ae:Watts>" in captured["files"]["file"][1]


def test_completed_activity_is_uploaded_once_when_strava_is_connected(tmp_path, monkeypatch, strava_environment):
    original_db_path = db.DB_PATH
    db.DB_PATH = tmp_path / "strava.db"
    try:
        db.init_db()
        route = db.create_route(
            RouteCreate(
                name="Puerto de prueba",
                distance_km=1,
                elevation_gain_m=100,
                start_altitude_m=700,
                end_altitude_m=800,
                avg_grade_percent=10,
                max_grade_percent=10,
                segments=[
                    RouteSegmentBase(
                        start_km=0,
                        end_km=1,
                        grade_percent=10,
                        start_altitude_m=700,
                        end_altitude_m=800,
                    )
                ],
            )
        )
        connection = {
            "athlete_id": "77",
            "athlete_name": "Test Rider",
            "access_token_encrypted": encrypt_secret("access-token"),
            "refresh_token_encrypted": encrypt_secret("refresh-token"),
            "expires_at": 4_102_444_800,
            "connected_at": "2026-08-29T09:00:00Z",
        }
        db.save_strava_connection("local-user", connection)
        calls = []

        def fake_upload(access_token, detail, external_id):
            calls.append((access_token, detail, external_id))
            return strava.StravaUploadResult(upload_id="91", activity_id="123", status="ready")

        monkeypatch.setattr(strava, "upload_activity", fake_upload)
        auth = AuthContext(user_id="local-user", access_token="")
        draft = sample_draft().model_copy(update={"route_id": route.id})

        partial = main.create_activity(draft.model_copy(update={"status": "partial"}), auth)
        assert partial.strava_status == ""
        assert calls == []

        activity = main.create_activity(draft, auth)
        repeated = main.update_activity(activity.id, draft, auth)

        assert activity.strava_status == "ready"
        assert activity.strava_activity_id == "123"
        assert repeated.strava_activity_id == "123"
        assert len(calls) == 1
        assert calls[0][0] == "access-token"
        assert calls[0][1].activity.route_name == "Puerto de prueba"
    finally:
        db.DB_PATH = original_db_path


@pytest.mark.parametrize("missing_variable", [
    "STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REDIRECT_URI", "APP_ENCRYPTION_KEY",
])
def test_cloud_activities_work_without_optional_strava_schema(
    monkeypatch, strava_environment, missing_variable,
):
    monkeypatch.delenv(missing_variable)
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "publishable-test")
    detail = activity_detail()
    row = detail.activity.model_dump(exclude={
        "route_name", "strava_upload_id", "strava_activity_id", "strava_status", "strava_error",
    })
    row["routes"] = {"name": detail.activity.route_name}
    auth = AuthContext(user_id="owner", access_token="user-token")

    def fake_request(request_auth, method, path, *, params=None, json=None):
        assert request_auth == auth
        if method == "GET" and path == "activities":
            assert "strava_" not in params["select"]
            return [row]
        if method == "GET" and path == "activity_samples":
            return [sample.model_dump() for sample in detail.samples] if params["offset"] == "0" else []
        if method == "POST" and path in {"rpc/create_activity", "rpc/update_activity"}:
            return detail.activity.id
        pytest.fail(f"Unexpected database access without Strava configured: {method} {path}")

    monkeypatch.setattr(supabase_db, "_request", fake_request)
    summary = main.get_strava_connection(auth)
    assert not summary.configured
    assert not summary.connected
    assert main.disconnect_strava(auth) is None
    assert main.list_activities(auth) == [detail.activity]
    assert main.get_activity(detail.activity.id, auth) == detail
    assert main.create_activity(sample_draft(), auth) == detail.activity
    assert main.update_activity(detail.activity.id, sample_draft(), auth) == detail.activity


def test_cloud_activity_reads_include_strava_status_when_configured(monkeypatch, strava_environment):
    detail = activity_detail()
    row = detail.activity.model_dump(exclude={"route_name"})
    row.update(strava_activity_id="123", strava_status="ready", routes={"name": detail.activity.route_name})

    def fake_request(auth, method, path, *, params):
        if path == "activity_samples":
            return []
        assert path == "activities"
        assert "strava_upload_id,strava_activity_id,strava_status,strava_error" in params["select"]
        return [row]

    monkeypatch.setattr(supabase_db, "_request", fake_request)
    auth = AuthContext(user_id="owner", access_token="user-token")
    assert supabase_db.list_activities(auth)[0].strava_activity_id == "123"
    assert supabase_db.get_activity(auth, detail.activity.id).activity.strava_status == "ready"
