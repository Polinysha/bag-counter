import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_videos import router as videos_router
from app.config import settings
from app.db import init_db
from app.health import check_db, check_redis

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if not settings.api_key:
        log.warning(
            "BC_API_KEY is not set - /api/v1/* is running WITHOUT authentication. "
            "Set BC_API_KEY (see .env.example) before exposing this beyond a trusted network."
        )
    yield


app = FastAPI(
    title="Conveyor Bag Counter",
    description="Upload conveyor footage, count bags with an MMDetection-based "
    "pipeline, and monitor counting anomalies. "
    "See docs/API_CONTRACTS.md in the repository for the full contract.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["meta"])
def health() -> JSONResponse:
    """
    Liveness/readiness probe. Deliberately outside /api/v1: a health
    check is infrastructure, not part of the versioned business API.

    Actually checks the two things this service can't function without
    (SQLite file + Redis) rather than always returning "ok" - an
    orchestrator routing traffic based on this needs to know when the
    process is up but its dependencies aren't.
    """
    checks = {"db": check_db(), "redis": check_redis()}
    healthy = all(checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )


app.include_router(videos_router, prefix=API_V1_PREFIX)

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
