from app.models import AppSettings, RouteSegment
from app.route_math import apply_trainer_grade_limit, calculate_averages, get_segment_at_km, interpolate_altitude


segments = [
    RouteSegment(id=1, route_id=1, start_km=0, end_km=2, grade_percent=5, start_altitude_m=700, end_altitude_m=800),
    RouteSegment(id=2, route_id=1, start_km=2, end_km=4, grade_percent=10, start_altitude_m=800, end_altitude_m=1000),
]


def test_get_segment_at_km():
    assert get_segment_at_km(segments, 1).id == 1
    assert get_segment_at_km(segments, 2.5).id == 2


def test_apply_trainer_grade_limit():
    settings = AppSettings(max_trainer_grade_percent=8)
    assert apply_trainer_grade_limit(12, settings) == 8
    assert apply_trainer_grade_limit(6, settings) == 6


def test_disable_negative_grades():
    settings = AppSettings(enable_negative_grades=False)
    assert apply_trainer_grade_limit(-4, settings) == 0


def test_interpolate_altitude():
    assert interpolate_altitude(segments[0], 1, 0) == 750


def test_calculate_averages():
    assert calculate_averages(
        [
            {"speed_kph": 20, "cadence_rpm": 80, "power_w": 200, "paused": False},
            {"speed_kph": 30, "cadence_rpm": 90, "power_w": 300, "paused": False},
            {"speed_kph": 0, "cadence_rpm": 0, "power_w": 0, "paused": True},
        ]
    ) == {"avg_power_w": 250, "max_power_w": 300, "avg_cadence_rpm": 85, "avg_speed_kph": 25}
