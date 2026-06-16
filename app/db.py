from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

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


DB_PATH = Path(os.getenv("CYCLING_APP_DB", "data/cycling-app.db"))


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS routes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              distance_km REAL NOT NULL,
              elevation_gain_m REAL NOT NULL,
              start_altitude_m REAL NOT NULL,
              end_altitude_m REAL NOT NULL,
              avg_grade_percent REAL NOT NULL,
              max_grade_percent REAL NOT NULL,
              created_at TEXT NOT NULL,
              original_image_path TEXT
            );

            CREATE TABLE IF NOT EXISTS route_segments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
              start_km REAL NOT NULL,
              end_km REAL NOT NULL,
              grade_percent REAL NOT NULL,
              start_altitude_m REAL NOT NULL,
              end_altitude_m REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activities (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
              started_at TEXT NOT NULL,
              ended_at TEXT NOT NULL,
              status TEXT NOT NULL,
              active_seconds INTEGER NOT NULL,
              total_seconds INTEGER NOT NULL,
              distance_km REAL NOT NULL,
              avg_power_w INTEGER NOT NULL,
              max_power_w INTEGER NOT NULL,
              avg_cadence_rpm INTEGER NOT NULL,
              avg_speed_kph REAL NOT NULL,
              completed_elevation_m REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_samples (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
              timestamp_ms INTEGER NOT NULL,
              elapsed_seconds INTEGER NOT NULL,
              km REAL NOT NULL,
              speed_kph REAL NOT NULL,
              cadence_rpm INTEGER NOT NULL,
              power_w INTEGER NOT NULL,
              grade_percent REAL NOT NULL,
              altitude_m REAL NOT NULL,
              paused INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS imported_images (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              path TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_route(row: sqlite3.Row) -> Route:
    return Route(
        id=row["id"],
        name=row["name"],
        distance_km=row["distance_km"],
        elevation_gain_m=row["elevation_gain_m"],
        start_altitude_m=row["start_altitude_m"],
        end_altitude_m=row["end_altitude_m"],
        avg_grade_percent=row["avg_grade_percent"],
        max_grade_percent=row["max_grade_percent"],
        created_at=row["created_at"],
        original_image_path=row["original_image_path"],
    )


def row_to_segment(row: sqlite3.Row) -> RouteSegment:
    return RouteSegment(
        id=row["id"],
        route_id=row["route_id"],
        start_km=row["start_km"],
        end_km=row["end_km"],
        grade_percent=row["grade_percent"],
        start_altitude_m=row["start_altitude_m"],
        end_altitude_m=row["end_altitude_m"],
    )


def row_to_activity(row: sqlite3.Row) -> Activity:
    return Activity(
        id=row["id"],
        route_id=row["route_id"],
        route_name=row["route_name"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        status=row["status"],
        active_seconds=row["active_seconds"],
        total_seconds=row["total_seconds"],
        distance_km=row["distance_km"],
        avg_power_w=row["avg_power_w"],
        max_power_w=row["max_power_w"],
        avg_cadence_rpm=row["avg_cadence_rpm"],
        avg_speed_kph=row["avg_speed_kph"],
        completed_elevation_m=row["completed_elevation_m"],
    )


def row_to_sample(row: sqlite3.Row) -> ActivitySample:
    return ActivitySample(
        id=row["id"],
        activity_id=row["activity_id"],
        timestamp_ms=row["timestamp_ms"],
        elapsed_seconds=row["elapsed_seconds"],
        km=row["km"],
        speed_kph=row["speed_kph"],
        cadence_rpm=row["cadence_rpm"],
        power_w=row["power_w"],
        grade_percent=row["grade_percent"],
        altitude_m=row["altitude_m"],
        paused=bool(row["paused"]),
    )


def list_routes() -> list[Route]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM routes ORDER BY created_at DESC").fetchall()
        return [row_to_route(row) for row in rows]


def get_route(route_id: int) -> RouteWithSegments | None:
    with connect() as conn:
        route_row = conn.execute("SELECT * FROM routes WHERE id = ?", (route_id,)).fetchone()
        if route_row is None:
            return None
        segment_rows = conn.execute(
            "SELECT * FROM route_segments WHERE route_id = ? ORDER BY start_km ASC",
            (route_id,),
        ).fetchall()
        route = row_to_route(route_row)
        return RouteWithSegments(**route.model_dump(), segments=[row_to_segment(row) for row in segment_rows])


def create_route(draft: RouteCreate) -> RouteWithSegments:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO routes (
              name, distance_km, elevation_gain_m, start_altitude_m, end_altitude_m,
              avg_grade_percent, max_grade_percent, created_at, original_image_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft.name,
                draft.distance_km,
                draft.elevation_gain_m,
                draft.start_altitude_m,
                draft.end_altitude_m,
                draft.avg_grade_percent,
                draft.max_grade_percent,
                now_iso(),
                draft.original_image_path,
            ),
        )
        route_id = cur.lastrowid
        for segment in draft.segments:
            conn.execute(
                """
                INSERT INTO route_segments (
                  route_id, start_km, end_km, grade_percent, start_altitude_m, end_altitude_m
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    route_id,
                    segment.start_km,
                    segment.end_km,
                    segment.grade_percent,
                    segment.start_altitude_m,
                    segment.end_altitude_m,
                ),
            )
    route = get_route(route_id)
    assert route is not None
    return route


def update_route(route_id: int, draft: RouteCreate) -> RouteWithSegments | None:
    if get_route(route_id) is None:
        return None
    with connect() as conn:
        conn.execute(
            """
            UPDATE routes SET
              name = ?, distance_km = ?, elevation_gain_m = ?, start_altitude_m = ?, end_altitude_m = ?,
              avg_grade_percent = ?, max_grade_percent = ?, original_image_path = ?
            WHERE id = ?
            """,
            (
                draft.name,
                draft.distance_km,
                draft.elevation_gain_m,
                draft.start_altitude_m,
                draft.end_altitude_m,
                draft.avg_grade_percent,
                draft.max_grade_percent,
                draft.original_image_path,
                route_id,
            ),
        )
        conn.execute("DELETE FROM route_segments WHERE route_id = ?", (route_id,))
        for segment in draft.segments:
            conn.execute(
                """
                INSERT INTO route_segments (
                  route_id, start_km, end_km, grade_percent, start_altitude_m, end_altitude_m
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    route_id,
                    segment.start_km,
                    segment.end_km,
                    segment.grade_percent,
                    segment.start_altitude_m,
                    segment.end_altitude_m,
                ),
            )
    return get_route(route_id)


def delete_route(route_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM routes WHERE id = ?", (route_id,))


def duplicate_route(route_id: int) -> RouteWithSegments | None:
    route = get_route(route_id)
    if route is None:
        return None
    draft = RouteCreate(
        name=f"{route.name} copia",
        distance_km=route.distance_km,
        elevation_gain_m=route.elevation_gain_m,
        start_altitude_m=route.start_altitude_m,
        end_altitude_m=route.end_altitude_m,
        avg_grade_percent=route.avg_grade_percent,
        max_grade_percent=route.max_grade_percent,
        original_image_path=route.original_image_path,
        segments=[segment.model_dump(exclude={"id", "route_id"}) for segment in route.segments],
    )
    return create_route(draft)


def get_settings() -> AppSettings:
    settings = AppSettings(openai_api_key=os.getenv("OPENAI_API_KEY", ""))
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    data = settings.model_dump()
    for row in rows:
        key = row["key"]
        if key not in data:
            continue
        default = data[key]
        if isinstance(default, bool):
            data[key] = row["value"].strip().lower() in {"true", "1", "yes", "on"}
        elif isinstance(default, (int, float)):
            data[key] = float(row["value"])
        elif isinstance(default, (dict, list)):
            try:
                data[key] = json.loads(row["value"])
            except json.JSONDecodeError:
                data[key] = default
        else:
            data[key] = row["value"]
    data["openai_api_key_configured"] = bool(data["openai_api_key"])
    return AppSettings(**data)


def update_settings(settings: AppSettingsUpdate | AppSettings) -> AppSettings:
    current = get_settings()
    api_key = current.openai_api_key
    if getattr(settings, "clear_openai_api_key", False):
        api_key = ""
    elif settings.openai_api_key.strip():
        api_key = settings.openai_api_key.strip()
    values = {
        **settings.model_dump(exclude={"clear_openai_api_key", "openai_api_key_configured"}),
        "openai_api_key": api_key,
    }
    with connect() as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, serialize_setting_value(value)),
            )
    return get_settings()


def serialize_setting_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def save_imported_image(path: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO imported_images (path, created_at) VALUES (?, ?)", (path, now_iso()))


def list_activities() -> list[Activity]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT activities.*, routes.name AS route_name
            FROM activities
            JOIN routes ON routes.id = activities.route_id
            ORDER BY started_at DESC
            """
        ).fetchall()
    return [row_to_activity(row) for row in rows]


def get_activity(activity_id: int) -> ActivityDetail | None:
    with connect() as conn:
        activity_row = conn.execute(
            """
            SELECT activities.*, routes.name AS route_name
            FROM activities
            JOIN routes ON routes.id = activities.route_id
            WHERE activities.id = ?
            """,
            (activity_id,),
        ).fetchone()
        if activity_row is None:
            return None
        sample_rows = conn.execute(
            "SELECT * FROM activity_samples WHERE activity_id = ? ORDER BY elapsed_seconds ASC",
            (activity_id,),
        ).fetchall()
    return ActivityDetail(activity=row_to_activity(activity_row), samples=[row_to_sample(row) for row in sample_rows])


def delete_activity(activity_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))


def create_activity(draft: ActivityCreate) -> Activity:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO activities (
              route_id, started_at, ended_at, status, active_seconds, total_seconds, distance_km,
              avg_power_w, max_power_w, avg_cadence_rpm, avg_speed_kph, completed_elevation_m
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft.route_id,
                draft.started_at,
                draft.ended_at,
                draft.status,
                draft.active_seconds,
                draft.total_seconds,
                draft.distance_km,
                draft.avg_power_w,
                draft.max_power_w,
                draft.avg_cadence_rpm,
                draft.avg_speed_kph,
                draft.completed_elevation_m,
            ),
        )
        activity_id = cur.lastrowid
        for sample in draft.samples:
            conn.execute(
                """
                INSERT INTO activity_samples (
                  activity_id, timestamp_ms, elapsed_seconds, km, speed_kph, cadence_rpm,
                  power_w, grade_percent, altitude_m, paused
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activity_id,
                    sample.timestamp_ms,
                    sample.elapsed_seconds,
                    sample.km,
                    sample.speed_kph,
                    sample.cadence_rpm,
                    sample.power_w,
                    sample.grade_percent,
                    sample.altitude_m,
                    int(sample.paused),
                ),
            )
    activity = get_activity(activity_id)
    assert activity is not None
    return activity.activity


def update_activity(activity_id: int, draft: ActivityCreate) -> Activity | None:
    if get_activity(activity_id) is None:
        return None
    with connect() as conn:
        conn.execute(
            """
            UPDATE activities SET
              route_id = ?, started_at = ?, ended_at = ?, status = ?, active_seconds = ?,
              total_seconds = ?, distance_km = ?, avg_power_w = ?, max_power_w = ?,
              avg_cadence_rpm = ?, avg_speed_kph = ?, completed_elevation_m = ?
            WHERE id = ?
            """,
            (
                draft.route_id,
                draft.started_at,
                draft.ended_at,
                draft.status,
                draft.active_seconds,
                draft.total_seconds,
                draft.distance_km,
                draft.avg_power_w,
                draft.max_power_w,
                draft.avg_cadence_rpm,
                draft.avg_speed_kph,
                draft.completed_elevation_m,
                activity_id,
            ),
        )
        conn.execute("DELETE FROM activity_samples WHERE activity_id = ?", (activity_id,))
        for sample in draft.samples:
            conn.execute(
                """
                INSERT INTO activity_samples (
                  activity_id, timestamp_ms, elapsed_seconds, km, speed_kph, cadence_rpm,
                  power_w, grade_percent, altitude_m, paused
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activity_id,
                    sample.timestamp_ms,
                    sample.elapsed_seconds,
                    sample.km,
                    sample.speed_kph,
                    sample.cadence_rpm,
                    sample.power_w,
                    sample.grade_percent,
                    sample.altitude_m,
                    int(sample.paused),
                ),
            )
    activity = get_activity(activity_id)
    return activity.activity if activity else None
