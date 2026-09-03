import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes_videos import router as videos_router
from app.db import init_db

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Conveyor Bag Counter",
    description="Upload conveyor footage, count bags with an MMDetection-based "
                 "pipeline, and monitor counting anomalies.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(videos_router, prefix="/api")

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
