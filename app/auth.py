from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from fastapi import Header, HTTPException


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    access_token: str
    email: str = ""


def auth_enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_PUBLISHABLE_KEY"))


def local_mode() -> bool:
    return not auth_enabled() and not os.getenv("VERCEL")


def public_config() -> dict[str, object]:
    return {
        "auth_enabled": auth_enabled(),
        "config_error": bool(os.getenv("VERCEL") and not auth_enabled()),
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_publishable_key": os.getenv("SUPABASE_PUBLISHABLE_KEY", ""),
    }


def require_user(authorization: str | None = Header(default=None)) -> AuthContext:
    if local_mode():
        return AuthContext(user_id="local-user", access_token="", email="local@localhost")
    if not auth_enabled():
        raise HTTPException(status_code=503, detail="La autenticación no está configurada.")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")

    access_token = authorization.removeprefix("Bearer ").strip()
    headers = {
        "apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"],
        "Authorization": f"Bearer {access_token}",
    }
    try:
        response = httpx.get(
            f"{os.environ['SUPABASE_URL'].rstrip('/')}/auth/v1/user",
            headers=headers,
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="No se ha podido validar la sesión.") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="La sesión ha caducado. Inicia sesión de nuevo.")

    user = response.json()
    return AuthContext(
        user_id=user["id"],
        access_token=access_token,
        email=user.get("email", ""),
    )
