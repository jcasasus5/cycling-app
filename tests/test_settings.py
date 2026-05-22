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
                smooth_grade_changes=True,
                rider_weight_kg=66.5,
                bike_weight_kg=8.7,
            )
        )

        settings = db.get_settings()

        assert settings.max_trainer_grade_percent == 12.5
        assert settings.enable_negative_grades is True
        assert settings.smooth_grade_changes is True
        assert settings.rider_weight_kg == 66.5
        assert settings.bike_weight_kg == 8.7
    finally:
        db.DB_PATH = original_db_path


def test_get_settings_reads_legacy_capitalized_booleans(tmp_path):
    original_db_path = db.DB_PATH
    try:
        db.DB_PATH = tmp_path / "settings.db"
        db.init_db()

        with db.connect() as conn:
            conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", ("enable_negative_grades", "True"))
            conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", ("smooth_grade_changes", "False"))

        settings = db.get_settings()

        assert settings.enable_negative_grades is True
        assert settings.smooth_grade_changes is False
    finally:
        db.DB_PATH = original_db_path
