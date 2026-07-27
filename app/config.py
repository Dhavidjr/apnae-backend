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


settings = Settings()
