from __future__ import annotations

import os
from typing import Any

import httpx

from app import strava
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


ACTIVITY_SELECT = (
    "id,route_id,route_name,started_at,ended_at,status,active_seconds,total_seconds,distance_km,"
    "avg_power_w,max_power_w,avg_cadence_rpm,avg_speed_kph,completed_elevation_m"
)
ROUTE_SELECT = (
    "id,user_id,is_public,name,distance_km,elevation_gain_m,start_altitude_m,"
    "end_altitude_m,avg_grade_percent,max_grade_percent,created_at,original_image_path"
)


def _activity_select() -> str:
    # TCX downloads and ordinary rides do not require the optional Strava migration.
    columns = ACTIVITY_SELECT
    if strava.configured():
        columns += ",strava_upload_id,strava_activity_id,strava_status,strava_error"
    return columns + ",routes(name)"


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


def _route(row: dict[str, Any], auth: AuthContext) -> Route:
    return Route(**row, is_owner=row["user_id"] == auth.user_id)


def _segment(row: dict[str, Any]) -> RouteSegment:
    return RouteSegment(**row)


def _activity(row: dict[str, Any]) -> Activity:
    route_name = row.get("route_name") or (row.get("routes") or {}).get("name") or "Ruta eliminada"
    return Activity(**{**row, "route_name": route_name})


def _all_rows(auth: AuthContext, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    while True:
        page = _request(auth, "GET", path, params={**params, "limit": "1000", "offset": str(len(rows))})
        # Supabase may cap pages below the requested limit. Only an empty page ends the list.
        if not page:
            return rows
        rows.extend(page)


def list_routes(auth: AuthContext) -> list[Route]:
    rows = _all_rows(
        auth,
        "routes",
        params={
            "select": ROUTE_SELECT,
            "or": f"(user_id.eq.{auth.user_id},is_public.eq.true)",
            "order": "created_at.desc,id.desc",
        },
    )
    return sorted((_route(row, auth) for row in rows), key=lambda route: not route.is_owner)


def get_route(auth: AuthContext, route_id: int) -> RouteWithSegments | None:
    rows = _request(
        auth,
        "GET",
        "routes",
        params={
            "id": f"eq.{route_id}",
            "select": ROUTE_SELECT,
        },
    )
    if not rows:
        return None
    segment_rows = _all_rows(
        auth,
        "route_segments",
        params={"route_id": f"eq.{route_id}", "select": "*", "order": "start_km.asc,id.asc"},
    )
    return RouteWithSegments(**_route(rows[0], auth).model_dump(), segments=[_segment(row) for row in segment_rows])


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
    _request(auth, "DELETE", "routes", params={"id": f"eq.{route_id}", "user_id": f"eq.{auth.user_id}"})


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
            "select": _activity_select(),
            "order": "started_at.desc",
        },
    )
    return [_activity(row) for row in rows]


def get_activity(auth: AuthContext, activity_id: int) -> ActivityDetail | None:
    rows = _request(
        auth,
        "GET",
        "activities",
        params={
            "id": f"eq.{activity_id}",
            "select": _activity_select(),
        },
    )
    if not rows:
        return None
    row = rows[0]
    activity = _activity(row)
    sample_rows = []
    while True:
        page = _request(
            auth,
            "GET",
            "activity_samples",
            params={
                "activity_id": f"eq.{activity_id}",
                "select": "*",
                "order": "elapsed_seconds.asc,id.asc",
                "limit": "1000",
                "offset": str(len(sample_rows)),
            },
        )
        # Keep going until empty: the project's row cap may be lower than our limit.
        if not page:
            break
        sample_rows.extend(page)
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


def update_activity_strava_status(
    auth: AuthContext,
    activity_id: int,
    *,
    upload_id: str = "",
    strava_activity_id: str = "",
    status: str,
    error: str = "",
) -> None:
    _request(
        auth,
        "PATCH",
        "activities",
        params={"id": f"eq.{activity_id}"},
        json={
            "strava_upload_id": upload_id,
            "strava_activity_id": strava_activity_id,
            "strava_status": status,
            "strava_error": error,
        },
        prefer="return=minimal",
    )


def get_strava_connection(auth: AuthContext) -> dict[str, object] | None:
    rows = _request(auth, "GET", "strava_connections", params={"select": "*"})
    return rows[0] if rows else None


def save_strava_connection(auth: AuthContext, connection: dict[str, object]) -> None:
    _request(
        auth,
        "POST",
        "strava_connections",
        json={"user_id": auth.user_id, **connection},
        prefer="resolution=merge-duplicates,return=minimal",
    )


def delete_strava_connection(auth: AuthContext) -> None:
    _request(auth, "DELETE", "strava_connections", params={"user_id": f"eq.{auth.user_id}"})


def get_settings(auth: AuthContext) -> AppSettings:
    rows = _request(auth, "GET", "user_settings", params={"select": "*"})
    if not rows:
        return AppSettings()
    row = rows[0]
    return AppSettings(
        openai_api_key="",
        openai_api_key_configured=bool(row.get("openai_api_key_encrypted")),
        enable_negative_grades=row["enable_negative_grades"],
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
        "enable_negative_grades": settings.enable_negative_grades,
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
