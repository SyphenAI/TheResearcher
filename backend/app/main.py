from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.routers import auth, health, projects, research, secrets, settings, workspace
from app.services.migrate import ensure_schema
from app.services.startup import ensure_seed_data, log_startup, run_self_check

logger = logging.getLogger("theresearcher")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    from app.services.storage_paths import storage_root

    storage_root()  # storage/projects, storage/archive, storage/tmp

    ensure_schema(engine)
    checks = run_self_check()
    logger.info("Startup self-check: %s", checks)

    db = SessionLocal()
    try:
        ensure_seed_data(db)
        log_startup(db, checks)
    finally:
        db.close()

    yield


app = FastAPI(
    title="TheResearcher",
    description=(
        "Local research agent for Gartner-style SecOps analysis: "
        "Offensive Security, Exposure Management, Vulnerability Management."
    ),
    version="0.2.0-preprod",
    lifespan=lifespan,
)

settings = get_settings()
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(research.router)
app.include_router(secrets.router)
app.include_router(settings.router)
app.include_router(workspace.router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"detail": "Frontend not built"}
else:

    @app.get("/")
    async def root():
        return {
            "app": "TheResearcher",
            "message": "API is running. Frontend static build not found yet.",
            "health": "/api/health",
            "docs": "/docs",
        }
