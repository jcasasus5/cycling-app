from __future__ import annotations

from app.models import AppSettings, RouteSegment


def get_segment_at_km(segments: list[RouteSegment], km: float) -> RouteSegment | None:
    if not segments:
        return None
    for segment in segments:
        if segment.start_km <= km < segment.end_km:
            return segment
    for segment in segments:
        if km <= segment.end_km:
            return segment
    return segments[-1]


def apply_trainer_grade_limit(grade_percent: float, settings: AppSettings) -> float:
    grade = grade_percent if settings.enable_negative_grades else max(0, grade_percent)
    return min(settings.max_trainer_grade_percent, grade)


def interpolate_altitude(segment: RouteSegment | None, km: float, fallback_altitude: float) -> float:
    if segment is None:
        return fallback_altitude
    span = max(0.001, segment.end_km - segment.start_km)
    ratio = min(1, max(0, (km - segment.start_km) / span))
    return segment.start_altitude_m + (segment.end_altitude_m - segment.start_altitude_m) * ratio


def calculate_averages(samples: list[dict]) -> dict:
    active = [sample for sample in samples if not sample.get("paused")]
    if not active:
        return {"avg_power_w": 0, "max_power_w": 0, "avg_cadence_rpm": 0, "avg_speed_kph": 0}
    return {
        "avg_power_w": round(sum(sample["power_w"] for sample in active) / len(active)),
        "max_power_w": round(max(sample["power_w"] for sample in active)),
        "avg_cadence_rpm": round(sum(sample["cadence_rpm"] for sample in active) / len(active)),
        "avg_speed_kph": round(sum(sample["speed_kph"] for sample in active) / len(active), 1),
    }
