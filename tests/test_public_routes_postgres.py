import os
from pathlib import Path
import subprocess

import pytest


def test_public_routes_rls_in_disposable_postgres():
    container = os.getenv("CYCLING_TEST_POSTGRES_CONTAINER")
    if not container:
        pytest.skip("Set CYCLING_TEST_POSTGRES_CONTAINER to a disposable migrated PostgreSQL container")
    sql = Path(__file__).with_name("sql").joinpath("public_routes.sql").read_text()
    result = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-X", "-U", "postgres", "-v", "ON_ERROR_STOP=1"],
        input=sql, text=True, capture_output=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stderr)
