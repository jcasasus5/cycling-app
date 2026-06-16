from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ActivityStatus = Literal["completed", "partial"]


class RouteSegmentBase(BaseModel):
    start_km: float = Field(ge=0)
    end_km: float = Field(gt=0)
    grade_percent: float
    start_altitude_m: float
    end_altitude_m: float


class RouteSegment(RouteSegmentBase):
    id: int
    route_id: int


class RouteBase(BaseModel):
    name: str = Field(min_length=1)
    distance_km: float = Field(gt=0)
    elevation_gain_m: float = Field(ge=0)
    start_altitude_m: float
    end_altitude_m: float
    avg_grade_percent: float
    max_grade_percent: float
    original_image_path: str | None = None


class RouteCreate(RouteBase):
    segments: list[RouteSegmentBase] = Field(min_length=1)


class Route(RouteBase):
    id: int
    created_at: str


class RouteWithSegments(Route):
    segments: list[RouteSegment]


class ActivitySampleBase(BaseModel):
    timestamp_ms: int
    elapsed_seconds: int
    km: float
    speed_kph: float
    cadence_rpm: int
    power_w: int
    grade_percent: float
    altitude_m: float
    paused: bool


class ActivitySample(ActivitySampleBase):
    id: int
    activity_id: int


class ActivityCreate(BaseModel):
    route_id: int
    started_at: str
    ended_at: str
    status: ActivityStatus
    active_seconds: int
    total_seconds: int
    distance_km: float
    avg_power_w: int
    max_power_w: int
    avg_cadence_rpm: int
    avg_speed_kph: float
    completed_elevation_m: float
    samples: list[ActivitySampleBase]


class Activity(BaseModel):
    id: int
    route_id: int
    route_name: str
    started_at: str
    ended_at: str
    status: ActivityStatus
    active_seconds: int
    total_seconds: int
    distance_km: float
    avg_power_w: int
    max_power_w: int
    avg_cadence_rpm: int
    avg_speed_kph: float
    completed_elevation_m: float


class ActivityDetail(BaseModel):
    activity: Activity
    samples: list[ActivitySample]


class AppSettings(BaseModel):
    openai_api_key: str = ""
    openai_api_key_configured: bool = False
    max_trainer_grade_percent: float = 16
    enable_negative_grades: bool = True
    smooth_grade_changes: bool = True
    rider_weight_kg: float = 75
    bike_weight_kg: float = 9
    ftp_w: int = Field(default=0, ge=0)
    ftp_updated_at: str = ""
    ftp_method: str = ""
    ftp_test_history: list[dict[str, Any]] = Field(default_factory=list)


class AppSettingsUpdate(BaseModel):
    openai_api_key: str = ""
    clear_openai_api_key: bool = False
    max_trainer_grade_percent: float = 16
    enable_negative_grades: bool = True
    smooth_grade_changes: bool = True
    rider_weight_kg: float = 75
    bike_weight_kg: float = 9
    ftp_w: int = Field(default=0, ge=0)
    ftp_updated_at: str = ""
    ftp_method: str = ""
    ftp_test_history: list[dict[str, Any]] = Field(default_factory=list)


class ImportResult(BaseModel):
    draft: RouteCreate
    image_path: str
