import pytest
from pydantic import ValidationError

from app import db
from app.models import AppSettings


def test_update_settings_persists_booleans_and_numbers(tmp_path):
    original_db_path = db.DB_PATH
    try:
        db.DB_PATH = tmp_path / "settings.db"
        db.init_db()

        db.update_settings(
            AppSettings(
                openai_api_key="test-key",
                max_trainer_grade_percent=12.5,
                enable_negative_grades=True,
                rider_weight_kg=66.5,
                bike_weight_kg=8.7,
                ftp_w=238,
                ftp_updated_at="2026-06-17T10:00:00Z",
                ftp_method="ramp",
                ftp_test_history=[{"method": "ramp", "ftp_w": 238}],
            )
        )

        settings = db.get_settings()

        assert settings.max_trainer_grade_percent == 12.5
        assert settings.enable_negative_grades is True
        assert settings.rider_weight_kg == 66.5
        assert settings.bike_weight_kg == 8.7
        assert settings.ftp_w == 238
        assert settings.ftp_updated_at == "2026-06-17T10:00:00Z"
        assert settings.ftp_method == "ramp"
        assert settings.ftp_test_history == [{"method": "ramp", "ftp_w": 238}]
    finally:
        db.DB_PATH = original_db_path


def test_get_settings_reads_legacy_capitalized_boolean(tmp_path):
    original_db_path = db.DB_PATH
    try:
        db.DB_PATH = tmp_path / "settings.db"
        db.init_db()

        with db.connect() as conn:
            conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", ("enable_negative_grades", "True"))

        settings = db.get_settings()

        assert settings.enable_negative_grades is True
    finally:
        db.DB_PATH = original_db_path


def test_manual_grade_limit_is_not_tied_to_one_trainer_model():
    assert AppSettings(max_trainer_grade_percent=0).max_trainer_grade_percent == 0
    assert AppSettings(max_trainer_grade_percent=25).max_trainer_grade_percent == 25

    with pytest.raises(ValidationError):
        AppSettings(max_trainer_grade_percent=101)
