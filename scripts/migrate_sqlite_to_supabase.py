from __future__ import annotations

import argparse
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

import httpx

from app.secrets import encrypt_secret


TABLE_ORDER = (
    "routes",
    "route_segments",
    "activities",
    "activity_samples",
    "imported_images",
)


def chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def read_rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = [dict(row) for row in connection.execute(f"select * from {table} order by id")]
    if table == "activity_samples":
        for row in rows:
            row["paused"] = bool(row["paused"])
    return rows


def read_settings(connection: sqlite3.Connection) -> dict[str, Any]:
    stored = {
        row["key"]: row["value"]
        for row in connection.execute("select key, value from app_settings")
    }

    def as_bool(key: str, default: bool) -> bool:
        return stored.get(key, str(default)).strip().lower() in {"true", "1", "yes", "on"}

    api_key = stored.get("openai_api_key", "").strip()
    return {
        "openai_api_key_encrypted": encrypt_secret(api_key) if api_key else None,
        "max_trainer_grade_percent": float(stored.get("max_trainer_grade_percent", 16)),
        "enable_negative_grades": as_bool("enable_negative_grades", True),
        "smooth_grade_changes": as_bool("smooth_grade_changes", True),
        "rider_weight_kg": float(stored.get("rider_weight_kg", 75)),
        "bike_weight_kg": float(stored.get("bike_weight_kg", 9)),
    }


def call_import(
    *,
    supabase_url: str,
    publishable_key: str,
    migration_token: str,
    user_id: str,
    entity: str,
    rows: list[dict[str, Any]],
) -> None:
    response = None
    for attempt in range(5):
        try:
            response = httpx.post(
                f"{supabase_url.rstrip('/')}/rest/v1/rpc/import_legacy_rows",
                headers={
                    "apikey": publishable_key,
                    "Content-Type": "application/json",
                },
                json={
                    "import_token": migration_token,
                    "target_user_id": user_id,
                    "entity": entity,
                    "rows": rows,
                },
                timeout=120,
            )
            break
        except httpx.TransportError:
            if attempt == 4:
                raise
            time.sleep(2**attempt)
    assert response is not None
    if response.status_code >= 400:
        raise RuntimeError(f"Migration failed for {entity}: {response.text}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/cycling-app.db")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    supabase_url = os.environ["SUPABASE_URL"]
    publishable_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    migration_token = os.environ["MIGRATION_TOKEN"]

    connection = sqlite3.connect(Path(args.database))
    connection.row_factory = sqlite3.Row
    try:
        for table in TABLE_ORDER:
            rows = read_rows(connection, table)
            for batch in chunks(rows, args.batch_size):
                call_import(
                    supabase_url=supabase_url,
                    publishable_key=publishable_key,
                    migration_token=migration_token,
                    user_id=args.user_id,
                    entity=table,
                    rows=batch,
                )
            print(f"{table}: {len(rows)}")

        call_import(
            supabase_url=supabase_url,
            publishable_key=publishable_key,
            migration_token=migration_token,
            user_id=args.user_id,
            entity="user_settings",
            rows=[read_settings(connection)],
        )
        call_import(
            supabase_url=supabase_url,
            publishable_key=publishable_key,
            migration_token=migration_token,
            user_id=args.user_id,
            entity="finish",
            rows=[],
        )
        print("user_settings: 1")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
