"""
Central configuration for the Apnoea Monitoring Backend.

All values can be overridden via environment variables or a `.env` file
placed at the project root (see `.env.example`).
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- General ---
    PROJECT_NAME: str = "Apnoea Prediction & Detection Backend"
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./apnoea.db")

    # --- Security / JWT ---
    SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    # --- CORS ---
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")

    # --- Data limits ---
    MAX_QUERY_LIMIT: int = int(os.getenv("MAX_QUERY_LIMIT", "5000"))
    DEFAULT_QUERY_LIMIT: int = int(os.getenv("DEFAULT_QUERY_LIMIT", "200"))

    # --- Sensor validation bounds (used to reject obviously bad hardware data) ---
    HEART_RATE_MIN: float = 0.0
    HEART_RATE_MAX: float = 300.0
    SPO2_MIN: float = 0.0
    SPO2_MAX: float = 100.0
    BODY_TEMP_MIN: float = 20.0
    BODY_TEMP_MAX: float = 45.0

    # --- External AI prediction service (deployed separately, e.g. on Render) ---
    AI_SERVICE_BASE_URL: str = os.getenv(
        "AI_SERVICE_BASE_URL", "https://apnea-monitoring.onrender.com"
    )
    # All three of /api/v1/analyses, /predict, /analyze on that service return
    # the identical response shape - /api/v1/analyses is used by default as
    # the most REST-conventional path. Override via env if you prefer another.
    AI_SERVICE_ANALYZE_PATH: str = os.getenv("AI_SERVICE_ANALYZE_PATH", "/api/v1/analyses")
    AI_SERVICE_HEALTH_PATH: str = os.getenv("AI_SERVICE_HEALTH_PATH", "/health")
    AI_SERVICE_TIMEOUT_SECONDS: float = float(os.getenv("AI_SERVICE_TIMEOUT_SECONDS", "60"))
    # Render free-tier instances sleep after inactivity and can take 30-60s to
    # cold-start; we ping /health first and retry with backoff before the
    # real analysis request.
    AI_SERVICE_WAKEUP_MAX_RETRIES: int = int(os.getenv("AI_SERVICE_WAKEUP_MAX_RETRIES", "7"))
    AI_SERVICE_WAKEUP_RETRY_DELAY_SECONDS: float = float(
        os.getenv("AI_SERVICE_WAKEUP_RETRY_DELAY_SECONDS", "8")
    )
    # If the remote AI service is unreachable after all retries, fall back to
    # the local heuristic (app/ai_placeholder.py) instead of failing the
    # request outright. Set to "false" to make the endpoint hard-fail (502)
    # when the remote service is down.
    AI_FALLBACK_TO_LOCAL_ON_ERROR: bool = os.getenv("AI_FALLBACK_TO_LOCAL_ON_ERROR", "true").lower() == "true"

    # --- activity_percent derivation (see app/ai_client.py) ---
    # Our hardware has no dedicated activity/motion sensor - only
    # `heart_beat_height` (MPU6050 accelerometer amplitude). These bounds are
    # used to linearly rescale heart_beat_height into the 0-100
    # `activity_percent` feature the remote AI model expects. Recalibrate
    # against real device output.
    ACTIVITY_HEIGHT_MIN: float = float(os.getenv("ACTIVITY_HEIGHT_MIN", "0.0"))
    ACTIVITY_HEIGHT_MAX: float = float(os.getenv("ACTIVITY_HEIGHT_MAX", "1.0"))


settings = Settings()
