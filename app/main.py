from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app import db, strava, supabase_db
from app.auth import AuthContext, auth_enabled, local_mode, public_config, require_user
from app.models import (
    Activity,
    ActivityCreate,
    ActivityDetail,
    AppSettings,
    AppSettingsUpdate,
    ImportResult,
    Route,
    RouteCreate,
    RouteWithSegments,
    StravaAuthorization,
    StravaConnection,
    StravaOAuthCallback,
)
from app.openai_import import import_route_from_image
from app.secrets import decrypt_secret, encrypt_secret


app = FastAPI(title="Tacx Flux Climber", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    if local_mode():
        db.init_db()


@app.get("/api/config")
def get_public_config() -> dict[str, object]:
    return public_config()


@app.get("/api/routes", response_model=list[Route])
def list_routes(auth: AuthContext = Depends(require_user)) -> list[Route]:
    return supabase_db.list_routes(auth) if auth_enabled() else db.list_routes()


@app.post("/api/routes", response_model=RouteWithSegments)
def create_route(draft: RouteCreate, auth: AuthContext = Depends(require_user)) -> RouteWithSegments:
    return supabase_db.create_route(auth, draft) if auth_enabled() else db.create_route(draft)


@app.get("/api/routes/{route_id}", response_model=RouteWithSegments)
def get_route(route_id: int, auth: AuthContext = Depends(require_user)) -> RouteWithSegments:
    route = supabase_db.get_route(auth, route_id) if auth_enabled() else db.get_route(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Ruta no encontrada.")
    return route


@app.put("/api/routes/{route_id}", response_model=RouteWithSegments)
def update_route(
    route_id: int,
    draft: RouteCreate,
    auth: AuthContext = Depends(require_user),
) -> RouteWithSegments:
    route = supabase_db.update_route(auth, route_id, draft) if auth_enabled() else db.update_route(route_id, draft)
    if route is None:
        raise HTTPException(status_code=404, detail="Ruta no encontrada.")
    return route


@app.post("/api/routes/{route_id}/duplicate", response_model=RouteWithSegments)
def duplicate_route(route_id: int, auth: AuthContext = Depends(require_user)) -> RouteWithSegments:
    route = supabase_db.duplicate_route(auth, route_id) if auth_enabled() else db.duplicate_route(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Ruta no encontrada.")
    return route


@app.delete("/api/routes/{route_id}", status_code=204)
def delete_route(route_id: int, auth: AuthContext = Depends(require_user)) -> None:
    if auth_enabled():
        supabase_db.delete_route(auth, route_id)
    else:
        db.delete_route(route_id)


@app.get("/api/activities", response_model=list[Activity])
def list_activities(auth: AuthContext = Depends(require_user)) -> list[Activity]:
    return supabase_db.list_activities(auth) if auth_enabled() else db.list_activities()


@app.post("/api/activities", response_model=Activity)
def create_activity(draft: ActivityCreate, auth: AuthContext = Depends(require_user)) -> Activity:
    activity = supabase_db.create_activity(auth, draft) if auth_enabled() else db.create_activity(draft)
    return _upload_completed_activity_to_strava(auth, activity)


@app.put("/api/activities/{activity_id}", response_model=Activity)
def update_activity(
    activity_id: int,
    draft: ActivityCreate,
    auth: AuthContext = Depends(require_user),
) -> Activity:
    activity = (
        supabase_db.update_activity(auth, activity_id, draft)
        if auth_enabled()
        else db.update_activity(activity_id, draft)
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Actividad no encontrada.")
    return _upload_completed_activity_to_strava(auth, activity)


@app.get("/api/activities/{activity_id}", response_model=ActivityDetail)
def get_activity(activity_id: int, auth: AuthContext = Depends(require_user)) -> ActivityDetail:
    activity = supabase_db.get_activity(auth, activity_id) if auth_enabled() else db.get_activity(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Actividad no encontrada.")
    return _refresh_pending_strava_upload(auth, activity)


@app.delete("/api/activities/{activity_id}", status_code=204)
def delete_activity(activity_id: int, auth: AuthContext = Depends(require_user)) -> None:
    if auth_enabled():
        supabase_db.delete_activity(auth, activity_id)
    else:
        db.delete_activity(activity_id)


@app.get("/api/activities/{activity_id}/export.tcx", response_class=Response)
def download_activity_tcx(activity_id: int, auth: AuthContext = Depends(require_user)) -> Response:
    detail = supabase_db.get_activity(auth, activity_id) if auth_enabled() else db.get_activity(activity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Actividad no encontrada.")
    if not detail.samples:
        raise HTTPException(status_code=400, detail="Esta actividad no tiene datos registrados para exportar.")
    try:
        content = strava.build_tcx(detail)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="La fecha de inicio de la actividad no es válida.") from exc
    return Response(
        content=content,
        media_type="application/vnd.garmin.tcx+xml",
        headers={
            "Content-Disposition": f'attachment; filename="cycling-activity-{activity_id}.tcx"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/integrations/strava", response_model=StravaConnection)
def get_strava_connection(auth: AuthContext = Depends(require_user)) -> StravaConnection:
    connection = _get_strava_connection(auth)
    return _strava_connection_summary(connection)


@app.post("/api/integrations/strava/authorize", response_model=StravaAuthorization)
def authorize_strava(auth: AuthContext = Depends(require_user)) -> StravaAuthorization:
    try:
        authorization_url, oauth_state = strava.authorization_url(auth.user_id)
    except strava.StravaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StravaAuthorization(authorization_url=authorization_url, state=oauth_state)


@app.post("/api/integrations/strava/callback", response_model=StravaConnection)
def complete_strava_authorization(
    callback: StravaOAuthCallback,
    auth: AuthContext = Depends(require_user),
) -> StravaConnection:
    try:
        strava.verify_oauth_state(callback.state, auth.user_id)
        tokens, athlete = strava.exchange_authorization_code(callback.code)
        athlete_id = str(athlete.get("id") or "")
        if not athlete_id:
            raise strava.StravaError("Strava no ha devuelto el deportista autorizado.")
        now = datetime.now(timezone.utc).isoformat()
        connection = {
            "athlete_id": athlete_id,
            "athlete_name": strava.athlete_name(athlete),
            "access_token_encrypted": encrypt_secret(tokens.access_token),
            "refresh_token_encrypted": encrypt_secret(tokens.refresh_token),
            "expires_at": tokens.expires_at,
            "connected_at": now,
            "updated_at": now,
        }
        _save_strava_connection(auth, connection)
    except strava.StravaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _strava_connection_summary(connection)


@app.delete("/api/integrations/strava", status_code=204)
def disconnect_strava(auth: AuthContext = Depends(require_user)) -> None:
    connection = _get_strava_connection(auth)
    if not connection:
        return
    try:
        strava.revoke_token(decrypt_secret(str(connection["refresh_token_encrypted"])))
    except (strava.StravaError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _delete_strava_connection(auth)


@app.get("/api/settings", response_model=AppSettings)
def get_settings(auth: AuthContext = Depends(require_user)) -> AppSettings:
    if auth_enabled():
        return supabase_db.get_settings(auth)
    settings = db.get_settings()
    return settings.model_copy(
        update={
            "openai_api_key": "",
            "openai_api_key_configured": bool(settings.openai_api_key),
        }
    )


@app.put("/api/settings", response_model=AppSettings)
def update_settings(
    settings: AppSettingsUpdate,
    auth: AuthContext = Depends(require_user),
) -> AppSettings:
    if auth_enabled():
        return supabase_db.update_settings(auth, settings)
    updated = db.update_settings(settings)
    return updated.model_copy(
        update={
            "openai_api_key": "",
            "openai_api_key_configured": bool(updated.openai_api_key),
        }
    )


@app.post("/api/import/image", response_model=ImportResult)
async def import_image(
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_user),
) -> ImportResult:
    try:
        api_key = supabase_db.get_openai_api_key(auth) if auth_enabled() else db.get_settings().openai_api_key
        return await import_route_from_image(file, api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _upload_completed_activity_to_strava(auth: AuthContext, activity: Activity) -> Activity:
    if activity.status != "completed":
        return activity
    if activity.strava_activity_id or activity.strava_upload_id:
        return activity

    connection = _get_strava_connection(auth)
    if not connection:
        return activity
    try:
        strava.require_configuration()
        access_token = _valid_strava_access_token(auth, connection)
        detail = supabase_db.get_activity(auth, activity.id) if auth_enabled() else db.get_activity(activity.id)
        if detail is None:
            raise strava.StravaError("No se ha encontrado la actividad que se iba a subir.")
        result = strava.upload_activity(
            access_token,
            detail,
            external_id=f"cycling-app-{auth.user_id}-{activity.id}",
        )
        _update_activity_strava_status(
            auth,
            activity.id,
            upload_id=result.upload_id,
            strava_activity_id=result.activity_id,
            status=result.status,
            error=result.error,
        )
    except (strava.StravaError, RuntimeError) as exc:
        _update_activity_strava_status(
            auth,
            activity.id,
            status="error",
            error=str(exc)[:500],
        )

    detail = supabase_db.get_activity(auth, activity.id) if auth_enabled() else db.get_activity(activity.id)
    return detail.activity if detail else activity


def _valid_strava_access_token(auth: AuthContext, connection: dict[str, object]) -> str:
    access_token = decrypt_secret(str(connection["access_token_encrypted"]))
    if int(connection["expires_at"]) > int(time.time()) + 60:
        return access_token

    tokens = strava.refresh_tokens(decrypt_secret(str(connection["refresh_token_encrypted"])))
    updated = {
        **connection,
        "access_token_encrypted": encrypt_secret(tokens.access_token),
        "refresh_token_encrypted": encrypt_secret(tokens.refresh_token),
        "expires_at": tokens.expires_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    updated.pop("user_id", None)
    _save_strava_connection(auth, updated)
    return tokens.access_token


def _refresh_pending_strava_upload(auth: AuthContext, detail: ActivityDetail) -> ActivityDetail:
    activity = detail.activity
    if activity.strava_status != "pending" or not activity.strava_upload_id:
        return detail
    connection = _get_strava_connection(auth)
    if not connection:
        return detail
    try:
        access_token = _valid_strava_access_token(auth, connection)
        result = strava.get_upload_status(access_token, activity.strava_upload_id)
        if result.status == "pending":
            return detail
        _update_activity_strava_status(
            auth,
            activity.id,
            upload_id=result.upload_id,
            strava_activity_id=result.activity_id,
            status=result.status,
            error=result.error,
        )
    except (strava.StravaError, RuntimeError):
        return detail
    refreshed = supabase_db.get_activity(auth, activity.id) if auth_enabled() else db.get_activity(activity.id)
    return refreshed or detail


def _strava_connection_summary(connection: dict[str, object] | None) -> StravaConnection:
    return StravaConnection(
        configured=strava.configured(),
        connected=connection is not None,
        athlete_id=str(connection.get("athlete_id") or "") if connection else "",
        athlete_name=str(connection.get("athlete_name") or "") if connection else "",
        connected_at=str(connection.get("connected_at") or "") if connection else "",
    )


def _get_strava_connection(auth: AuthContext) -> dict[str, object] | None:
    if not strava.configured():
        return None
    return supabase_db.get_strava_connection(auth) if auth_enabled() else db.get_strava_connection(auth.user_id)


def _save_strava_connection(auth: AuthContext, connection: dict[str, object]) -> None:
    if auth_enabled():
        supabase_db.save_strava_connection(auth, connection)
    else:
        db.save_strava_connection(auth.user_id, connection)


def _delete_strava_connection(auth: AuthContext) -> None:
    if auth_enabled():
        supabase_db.delete_strava_connection(auth)
    else:
        db.delete_strava_connection(auth.user_id)


def _update_activity_strava_status(
    auth: AuthContext,
    activity_id: int,
    *,
    upload_id: str = "",
    strava_activity_id: str = "",
    status: str,
    error: str = "",
) -> None:
    if auth_enabled():
        supabase_db.update_activity_strava_status(
            auth,
            activity_id,
            upload_id=upload_id,
            strava_activity_id=strava_activity_id,
            status=status,
            error=error,
        )
    else:
        db.update_activity_strava_status(
            activity_id,
            upload_id=upload_id,
            strava_activity_id=strava_activity_id,
            status=status,
            error=error,
        )


static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")
