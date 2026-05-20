from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.models import Activity, ActivityCreate, ActivityDetail, AppSettings, ImportResult, Route, RouteCreate, RouteWithSegments
from app.openai_import import import_route_from_image


app = FastAPI(title="Tacx Flux Climber", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    db.init_db()


@app.get("/api/routes", response_model=list[Route])
def list_routes() -> list[Route]:
    return db.list_routes()


@app.post("/api/routes", response_model=RouteWithSegments)
def create_route(draft: RouteCreate) -> RouteWithSegments:
    return db.create_route(draft)


@app.get("/api/routes/{route_id}", response_model=RouteWithSegments)
def get_route(route_id: int) -> RouteWithSegments:
    route = db.get_route(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Ruta no encontrada.")
    return route


@app.put("/api/routes/{route_id}", response_model=RouteWithSegments)
def update_route(route_id: int, draft: RouteCreate) -> RouteWithSegments:
    route = db.update_route(route_id, draft)
    if route is None:
        raise HTTPException(status_code=404, detail="Ruta no encontrada.")
    return route


@app.post("/api/routes/{route_id}/duplicate", response_model=RouteWithSegments)
def duplicate_route(route_id: int) -> RouteWithSegments:
    route = db.duplicate_route(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Ruta no encontrada.")
    return route


@app.delete("/api/routes/{route_id}", status_code=204)
def delete_route(route_id: int) -> None:
    db.delete_route(route_id)


@app.get("/api/activities", response_model=list[Activity])
def list_activities() -> list[Activity]:
    return db.list_activities()


@app.post("/api/activities", response_model=Activity)
def create_activity(draft: ActivityCreate) -> Activity:
    return db.create_activity(draft)


@app.put("/api/activities/{activity_id}", response_model=Activity)
def update_activity(activity_id: int, draft: ActivityCreate) -> Activity:
    activity = db.update_activity(activity_id, draft)
    if activity is None:
        raise HTTPException(status_code=404, detail="Actividad no encontrada.")
    return activity


@app.get("/api/activities/{activity_id}", response_model=ActivityDetail)
def get_activity(activity_id: int) -> ActivityDetail:
    activity = db.get_activity(activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Actividad no encontrada.")
    return activity


@app.delete("/api/activities/{activity_id}", status_code=204)
def delete_activity(activity_id: int) -> None:
    db.delete_activity(activity_id)


@app.get("/api/settings", response_model=AppSettings)
def get_settings() -> AppSettings:
    return db.get_settings()


@app.put("/api/settings", response_model=AppSettings)
def update_settings(settings: AppSettings) -> AppSettings:
    return db.update_settings(settings)


@app.post("/api/import/image", response_model=ImportResult)
async def import_image(file: UploadFile = File(...)) -> ImportResult:
    try:
        return await import_route_from_image(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")
