import os

os.environ["CYCLING_APP_DB"] = "data/test-activity-resume.db"

from app import db
from app.models import ActivityCreate, ActivitySampleBase, RouteCreate, RouteSegmentBase


def test_update_partial_activity_replaces_resume_state():
    db.init_db()
    route = db.create_route(
        RouteCreate(
            name="Test",
            distance_km=10,
            elevation_gain_m=500,
            start_altitude_m=700,
            end_altitude_m=1200,
            avg_grade_percent=5,
            max_grade_percent=8,
            segments=[
                RouteSegmentBase(start_km=0, end_km=10, grade_percent=5, start_altitude_m=700, end_altitude_m=1200)
            ],
        )
    )
    first = db.create_activity(
        ActivityCreate(
            route_id=route.id,
            started_at="2026-05-20T10:00:00Z",
            ended_at="2026-05-20T10:10:00Z",
            status="partial",
            active_seconds=600,
            total_seconds=620,
            distance_km=3.0,
            avg_power_w=200,
            max_power_w=260,
            avg_cadence_rpm=82,
            avg_speed_kph=18,
            completed_elevation_m=150,
            samples=[
                ActivitySampleBase(
                    timestamp_ms=1,
                    elapsed_seconds=600,
                    km=3.0,
                    speed_kph=18,
                    cadence_rpm=82,
                    power_w=200,
                    grade_percent=5,
                    altitude_m=850,
                    paused=False,
                )
            ],
        )
    )

    updated = db.update_activity(
        first.id,
        ActivityCreate(
            route_id=route.id,
            started_at="2026-05-20T10:00:00Z",
            ended_at="2026-05-20T10:20:00Z",
            status="completed",
            active_seconds=1200,
            total_seconds=1240,
            distance_km=10.0,
            avg_power_w=210,
            max_power_w=280,
            avg_cadence_rpm=84,
            avg_speed_kph=20,
            completed_elevation_m=500,
            samples=[
                ActivitySampleBase(
                    timestamp_ms=2,
                    elapsed_seconds=1200,
                    km=10.0,
                    speed_kph=20,
                    cadence_rpm=84,
                    power_w=210,
                    grade_percent=5,
                    altitude_m=1200,
                    paused=False,
                )
            ],
        ),
    )

    detail = db.get_activity(first.id)
    assert updated is not None
    assert updated.status == "completed"
    assert detail is not None
    assert detail.activity.distance_km == 10.0
    assert len(detail.samples) == 1
    assert detail.samples[0].km == 10.0


def test_delete_activity_removes_samples():
    route = db.create_route(
        RouteCreate(
            name="Delete Test",
            distance_km=5,
            elevation_gain_m=100,
            start_altitude_m=100,
            end_altitude_m=200,
            avg_grade_percent=2,
            max_grade_percent=4,
            segments=[
                RouteSegmentBase(start_km=0, end_km=5, grade_percent=2, start_altitude_m=100, end_altitude_m=200)
            ],
        )
    )
    activity = db.create_activity(
        ActivityCreate(
            route_id=route.id,
            started_at="2026-05-20T10:00:00Z",
            ended_at="2026-05-20T10:05:00Z",
            status="partial",
            active_seconds=300,
            total_seconds=300,
            distance_km=2,
            avg_power_w=180,
            max_power_w=220,
            avg_cadence_rpm=80,
            avg_speed_kph=20,
            completed_elevation_m=40,
            samples=[
                ActivitySampleBase(
                    timestamp_ms=1,
                    elapsed_seconds=300,
                    km=2,
                    speed_kph=20,
                    cadence_rpm=80,
                    power_w=180,
                    grade_percent=2,
                    altitude_m=140,
                    paused=False,
                )
            ],
        )
    )

    db.delete_activity(activity.id)

    assert db.get_activity(activity.id) is None
