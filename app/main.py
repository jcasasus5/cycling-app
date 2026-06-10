from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import db, supabase_db
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
)
from app.openai_import import import_route_from_image


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
    return supabase_db.create_activity(auth, draft) if auth_enabled() else db.create_activity(draft)


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
    return activity


@app.get("/api/activities/{activity_id}", response_model=ActivityDetail)
def get_activity(activity_id: int, auth: AuthContext = Depends(require_user)) -> ActivityDetail:
    activity = supabase_db.get_activity(auth, activity_id) if auth_enabled() else db.get_activity(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Actividad no encontrada.")
    return activity


@app.delete("/api/activities/{activity_id}", status_code=204)
def delete_activity(activity_id: int, auth: AuthContext = Depends(require_user)) -> None:
    if auth_enabled():
        supabase_db.delete_activity(auth, activity_id)
    else:
        db.delete_activity(activity_id)


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


static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")
