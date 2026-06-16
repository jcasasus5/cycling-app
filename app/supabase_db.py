from __future__ import annotations

import os
from typing import Any

import httpx

from app.auth import AuthContext
from app.models import (
    Activity,
    ActivityCreate,
    ActivityDetail,
    ActivitySample,
    AppSettings,
    AppSettingsUpdate,
    Route,
    RouteCreate,
    RouteSegment,
    RouteWithSegments,
)
from app.secrets import decrypt_secret, encrypt_secret


def _headers(auth: AuthContext, *, prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"],
        "Authorization": f"Bearer {auth.access_token}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _request(
    auth: AuthContext,
    method: str,
    path: str,
    *,
    json: Any = None,
    params: dict[str, str] | None = None,
    prefer: str | None = None,
) -> Any:
    response = httpx.request(
        method,
        f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1/{path}",
        headers=_headers(auth, prefer=prefer),
        json=json,
        params=params,
        timeout=60,
    )
    if response.status_code >= 400:
        detail = response.json().get("message", "Error de base de datos.")
        raise RuntimeError(detail)
    if not response.content:
        return None
    return response.json()


def _route(row: dict[str, Any]) -> Route:
    return Route(**row)


def _segment(row: dict[str, Any]) -> RouteSegment:
    return RouteSegment(**row)


def _activity(row: dict[str, Any]) -> Activity:
    return Activity(**row)


def list_routes(auth: AuthContext) -> list[Route]:
    rows = _request(
        auth,
        "GET",
        "routes",
        params={
            "select": "id,name,distance_km,elevation_gain_m,start_altitude_m,end_altitude_m,avg_grade_percent,max_grade_percent,created_at,original_image_path",
            "order": "created_at.desc",
        },
    )
    return [_route(row) for row in rows]


def get_route(auth: AuthContext, route_id: int) -> RouteWithSegments | None:
    rows = _request(
        auth,
        "GET",
        "routes",
        params={
            "id": f"eq.{route_id}",
            "select": "id,name,distance_km,elevation_gain_m,start_altitude_m,end_altitude_m,avg_grade_percent,max_grade_percent,created_at,original_image_path",
        },
    )
    if not rows:
        return None
    segment_rows = _request(
        auth,
        "GET",
        "route_segments",
        params={"route_id": f"eq.{route_id}", "select": "*", "order": "start_km.asc"},
    )
    return RouteWithSegments(**rows[0], segments=[_segment(row) for row in segment_rows])


def create_route(auth: AuthContext, draft: RouteCreate) -> RouteWithSegments:
    result = _request(auth, "POST", "rpc/create_route", json={"draft": draft.model_dump()})
    route = get_route(auth, int(result))
    assert route is not None
    return route


def update_route(auth: AuthContext, route_id: int, draft: RouteCreate) -> RouteWithSegments | None:
    result = _request(
        auth,
        "POST",
        "rpc/update_route",
        json={"target_route_id": route_id, "draft": draft.model_dump()},
    )
    return get_route(auth, route_id) if result else None


def delete_route(auth: AuthContext, route_id: int) -> None:
    _request(auth, "DELETE", "routes", params={"id": f"eq.{route_id}"})


def duplicate_route(auth: AuthContext, route_id: int) -> RouteWithSegments | None:
    result = _request(auth, "POST", "rpc/duplicate_route", json={"target_route_id": route_id})
    if result is None:
        return None
    return get_route(auth, int(result))


def list_activities(auth: AuthContext) -> list[Activity]:
    rows = _request(
        auth,
        "GET",
        "activities",
        params={
            "select": "id,route_id,started_at,ended_at,status,active_seconds,total_seconds,distance_km,avg_power_w,max_power_w,avg_cadence_rpm,avg_speed_kph,completed_elevation_m,routes!inner(name)",
            "order": "started_at.desc",
        },
    )
    activities = []
    for row in rows:
        route_name = row["routes"]["name"]
        activities.append(_activity({**row, "route_name": route_name}))
    return activities


def get_activity(auth: AuthContext, activity_id: int) -> ActivityDetail | None:
    rows = _request(
        auth,
        "GET",
        "activities",
        params={
            "id": f"eq.{activity_id}",
            "select": "id,route_id,started_at,ended_at,status,active_seconds,total_seconds,distance_km,avg_power_w,max_power_w,avg_cadence_rpm,avg_speed_kph,completed_elevation_m,routes!inner(name)",
        },
    )
    if not rows:
        return None
    row = rows[0]
    activity = _activity({**row, "route_name": row["routes"]["name"]})
    sample_rows = _request(
        auth,
        "GET",
        "activity_samples",
        params={"activity_id": f"eq.{activity_id}", "select": "*", "order": "elapsed_seconds.asc"},
    )
    return ActivityDetail(activity=activity, samples=[ActivitySample(**sample) for sample in sample_rows])


def create_activity(auth: AuthContext, draft: ActivityCreate) -> Activity:
    result = _request(auth, "POST", "rpc/create_activity", json={"draft": draft.model_dump()})
    detail = get_activity(auth, int(result))
    assert detail is not None
    return detail.activity


def update_activity(auth: AuthContext, activity_id: int, draft: ActivityCreate) -> Activity | None:
    result = _request(
        auth,
        "POST",
        "rpc/update_activity",
        json={"target_activity_id": activity_id, "draft": draft.model_dump()},
    )
    detail = get_activity(auth, activity_id) if result else None
    return detail.activity if detail else None


def delete_activity(auth: AuthContext, activity_id: int) -> None:
    _request(auth, "DELETE", "activities", params={"id": f"eq.{activity_id}"})


def get_settings(auth: AuthContext) -> AppSettings:
    rows = _request(auth, "GET", "user_settings", params={"select": "*"})
    if not rows:
        return AppSettings()
    row = rows[0]
    return AppSettings(
        openai_api_key="",
        openai_api_key_configured=bool(row.get("openai_api_key_encrypted")),
        max_trainer_grade_percent=row["max_trainer_grade_percent"],
        enable_negative_grades=row["enable_negative_grades"],
        smooth_grade_changes=row["smooth_grade_changes"],
        rider_weight_kg=row["rider_weight_kg"],
        bike_weight_kg=row["bike_weight_kg"],
        ftp_w=row.get("ftp_w") or 0,
        ftp_updated_at=row.get("ftp_updated_at") or "",
        ftp_method=row.get("ftp_method") or "",
        ftp_test_history=row.get("ftp_test_history") or [],
    )


def get_openai_api_key(auth: AuthContext) -> str:
    rows = _request(
        auth,
        "GET",
        "user_settings",
        params={"select": "openai_api_key_encrypted"},
    )
    encrypted = rows[0].get("openai_api_key_encrypted") if rows else None
    return decrypt_secret(encrypted) if encrypted else ""


def update_settings(auth: AuthContext, settings: AppSettingsUpdate) -> AppSettings:
    existing = _request(
        auth,
        "GET",
        "user_settings",
        params={"select": "openai_api_key_encrypted"},
    )
    encrypted = existing[0].get("openai_api_key_encrypted") if existing else None
    if settings.clear_openai_api_key:
        encrypted = None
    elif settings.openai_api_key.strip():
        encrypted = encrypt_secret(settings.openai_api_key.strip())

    payload = {
        "user_id": auth.user_id,
        "openai_api_key_encrypted": encrypted,
        "max_trainer_grade_percent": settings.max_trainer_grade_percent,
        "enable_negative_grades": settings.enable_negative_grades,
        "smooth_grade_changes": settings.smooth_grade_changes,
        "rider_weight_kg": settings.rider_weight_kg,
        "bike_weight_kg": settings.bike_weight_kg,
        "ftp_w": settings.ftp_w,
        "ftp_updated_at": settings.ftp_updated_at or None,
        "ftp_method": settings.ftp_method,
        "ftp_test_history": settings.ftp_test_history,
    }
    _request(
        auth,
        "POST",
        "user_settings",
        json=payload,
        prefer="resolution=merge-duplicates,return=minimal",
    )
    return get_settings(auth)
