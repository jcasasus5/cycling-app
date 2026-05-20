import pytest

from app.models import RouteCreate, RouteSegmentBase
from app.openai_import import validate_extracted_route


def test_rejects_extracted_route_without_meaningful_profile_data():
    draft = RouteCreate(
        name="Ruta inventada",
        distance_km=1,
        elevation_gain_m=0,
        start_altitude_m=0,
        end_altitude_m=0,
        avg_grade_percent=0,
        max_grade_percent=0,
        segments=[
            RouteSegmentBase(start_km=0, end_km=1, grade_percent=0, start_altitude_m=0, end_altitude_m=0)
        ],
    )

    with pytest.raises(ValueError, match="no contiene todos los datos necesarios"):
        validate_extracted_route(draft)


def test_accepts_extracted_route_with_valid_segments_and_altitude_change():
    draft = RouteCreate(
        name="Puerto válido",
        distance_km=5,
        elevation_gain_m=250,
        start_altitude_m=700,
        end_altitude_m=950,
        avg_grade_percent=5,
        max_grade_percent=8,
        segments=[
            RouteSegmentBase(start_km=0, end_km=5, grade_percent=5, start_altitude_m=700, end_altitude_m=950)
        ],
    )

    validate_extracted_route(draft)
