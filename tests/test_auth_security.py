import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.auth import local_mode, require_user
from app.secrets import decrypt_secret, encrypt_secret


def test_vercel_without_supabase_fails_closed(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)

    assert local_mode() is False
    with pytest.raises(HTTPException) as exc:
        require_user(None)
    assert exc.value.status_code == 503


def test_local_mode_does_not_require_login(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)

    assert require_user(None).user_id == "local-user"


def test_openai_key_is_encrypted_at_rest(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    encrypted = encrypt_secret("sk-private")

    assert encrypted != "sk-private"
    assert decrypt_secret(encrypted) == "sk-private"
