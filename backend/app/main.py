import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes_videos import router as videos_router
from app.db import init_db

logging.basicConfig(level=logging.INFO)

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
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
def health() -> dict:
    """Liveness/readiness probe. Deliberately outside /api/v1: a health
    check is infrastructure, not part of the versioned business API."""
    return {"status": "ok"}


app.include_router(videos_router, prefix=API_V1_PREFIX)

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
