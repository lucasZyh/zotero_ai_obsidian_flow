from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import (
    PROJECT_ROOT,
    STATE_FILE_PATH,
    get_effective_paths,
    delete_provider,
    get_env_value,
    get_mineru_ui_settings,
    get_provider_payload,
    list_template_files,
    load_collection_names,
    load_papers_for_collection,
    persist_mineru_ui_settings,
    persist_paths,
    set_env_value,
    upsert_provider,
)
from backend.job_runner import job_runner
from backend.provider_test import test_provider_connection
from backend.schemas import JobStartRequest, MineruSettings, PathSettings, ProviderConnectionTest, ProviderUpsert
from pipeline import copy_db_to_temp
from services.dashboard_stats import compute_zotero_dashboard_stats


app = FastAPI(title="Zotero AI Obsidian Flow API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/app/bootstrap")
def get_bootstrap() -> dict:
    paths = get_effective_paths()
    mineru = get_mineru_ui_settings()
    return {
        "paths": paths,
        "templates": list_template_files(paths["template_dir_path"]),
        "providers": get_provider_payload(paths["provider_config_path"])["providers"],
        "job": job_runner.status(),
        "defaults": {
            "pdf_parser": "auto",
            "mineru_model_version": mineru["model_version"],
            "mineru_language": mineru["language"],
            "scan_mode": "collection_paper",
            "limit": 1,
            "since_days": 0,
        },
    }


@app.get("/api/dashboard")
def get_dashboard() -> dict:
    paths = get_effective_paths()
    return compute_zotero_dashboard_stats(paths["zotero_db_path"], STATE_FILE_PATH, copy_db_to_temp)


@app.get("/api/collections")
def get_collections() -> dict:
    paths = get_effective_paths()
    return {"collections": load_collection_names(paths["zotero_db_path"])}


@app.get("/api/collections/{name:path}/papers")
def get_collection_papers(name: str, sinceDays: int = Query(0, ge=0)) -> dict:
    paths = get_effective_paths()
    return {"papers": load_papers_for_collection(paths["zotero_db_path"], name, int(sinceDays))}


@app.post("/api/jobs")
def start_job(payload: JobStartRequest) -> dict:
    try:
        return job_runner.start(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/jobs/current")
def get_current_job() -> dict:
    return job_runner.status()


@app.get("/api/jobs/current/log")
def get_current_job_log(tail: int = Query(30000, ge=0, le=500000)) -> dict:
    return job_runner.log(tail)


@app.post("/api/jobs/current/stop")
def stop_current_job() -> dict:
    return job_runner.stop()


@app.get("/api/settings/paths")
def get_path_settings() -> dict:
    return get_effective_paths()


@app.put("/api/settings/paths")
def put_path_settings(payload: PathSettings) -> dict:
    return persist_paths(payload.dict(exclude_none=True))


@app.get("/api/settings/providers")
def get_provider_settings() -> dict:
    paths = get_effective_paths()
    return get_provider_payload(paths["provider_config_path"])


@app.put("/api/settings/providers")
def put_provider_settings(payload: ProviderUpsert) -> dict:
    paths = get_effective_paths()
    try:
        provider = upsert_provider(paths["provider_config_path"], payload.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"provider": provider, **get_provider_payload(paths["provider_config_path"])}


@app.post("/api/settings/providers/test")
def test_provider_settings(payload: ProviderConnectionTest) -> dict:
    return test_provider_connection(payload.dict())


@app.delete("/api/settings/providers/{name:path}")
def delete_provider_settings(name: str) -> dict:
    paths = get_effective_paths()
    try:
        delete_provider(paths["provider_config_path"], name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_provider_payload(paths["provider_config_path"])


@app.get("/api/settings/mineru")
def get_mineru_settings() -> dict:
    token = get_env_value("MINERU_API_TOKEN")
    return {
        "env_var": "MINERU_API_TOKEN",
        "token": token,
        "has_token": bool(token),
        **get_mineru_ui_settings(),
    }


@app.put("/api/settings/mineru")
def put_mineru_settings(payload: MineruSettings) -> dict:
    if payload.token is not None:
        set_env_value("MINERU_API_TOKEN", payload.token)
    persist_mineru_ui_settings(payload.dict(exclude_none=True))
    return get_mineru_settings()


dist_dir = PROJECT_ROOT / "frontend" / "dist"
if dist_dir.exists():
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @app.get("/{path:path}")
    def serve_frontend(path: str) -> FileResponse:
        target = dist_dir / path
        if path and target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(dist_dir / "index.html")
