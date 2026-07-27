"""
Apnoea Prediction & Detection Backend - FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import ai_review, auth_router, data, devices, ws

# Create all tables if they do not already exist.
# For production, consider using Alembic migrations instead.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Backend for an apnoea prediction and detection system. Hardware units "
        "stream body_temperature, heart_rate, spo2, and heart_beat_height "
        "(accelerometer) readings over a websocket; users can query stored data "
        "as raw rows, structured JSON, or rendered graphs, and request an AI "
        "review that predicts apnoea risk from the stored data."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = settings.API_V1_PREFIX

app.include_router(auth_router.router, prefix=API_PREFIX)
app.include_router(devices.router, prefix=API_PREFIX)
app.include_router(data.router, prefix=API_PREFIX)
app.include_router(ai_review.router, prefix=API_PREFIX)
# Websocket routes are mounted without the versioned prefix removed - kept under
# the same prefix for consistency with the rest of the API.
app.include_router(ws.router, prefix=API_PREFIX)


@app.get("/", tags=["Health"])
def root():
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "docs": "/docs",
    }


@app.get(f"{API_PREFIX}/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}
