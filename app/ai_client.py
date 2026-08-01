"""
Client for the external Apnoea AI prediction service (deployed separately,
e.g. on Render at https://apnea-monitoring.onrender.com).

Responsibilities:
  - Waking the service up via GET /health before the real call, since a
    Render free-tier instance sleeps after inactivity and can take 30-60s
    to cold-start on the first request.
  - Mapping our internal `SensorReading` ORM rows into the payload shape
    the AI service expects.
  - Calling the analysis endpoint and returning its raw JSON response.

This module does NOT decide what happens on failure - that's handled by the
caller (see app/routers/ai_review.py), which can fall back to the local
heuristic in app/ai_placeholder.py depending on
settings.AI_FALLBACK_TO_LOCAL_ON_ERROR.
"""
import asyncio
import datetime
from typing import Any, Dict, List

import httpx

from app.config import settings
from app.models import SensorReading


class AIServiceError(Exception):
    """Raised when the external AI service can't be reached or returns an error."""


def _iso_z(dt: datetime.datetime) -> str:
    """Format a datetime (naive or aware) as a 'Z'-suffixed ISO8601 string,
    matching the format used in the AI service's example payloads."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="milliseconds") + "Z"


def parse_ai_datetime(value: Any) -> "datetime.datetime | None":
    """Parses the datetime strings returned by the AI service
    (e.g. '2026-08-01T14:32:53.347000Z') into naive UTC datetimes for storage."""
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value
    try:
        s = str(value)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _derive_activity_percent(heart_beat_height: float) -> float:
    """
    PLACEHOLDER mapping: our hardware has no dedicated activity/motion sensor
    channel, only `heart_beat_height` (an MPU6050-derived accelerometer
    amplitude). The external AI model expects an `activity_percent` (0-100)
    feature. Until real activity/actigraphy data is available, this linearly
    rescales heart_beat_height into 0-100 using ACTIVITY_HEIGHT_MIN/MAX as a
    rough calibration range.

    >>> Recalibrate ACTIVITY_HEIGHT_MIN/MAX (in .env) against real device
    >>> output, or replace this function if you add a dedicated activity metric.
    """
    lo, hi = settings.ACTIVITY_HEIGHT_MIN, settings.ACTIVITY_HEIGHT_MAX
    if hi <= lo:
        return 0.0
    pct = (heart_beat_height - lo) / (hi - lo) * 100.0
    return max(0.0, min(100.0, pct))


def _reading_to_payload(r: SensorReading) -> Dict[str, Any]:
    return {
        "id": r.id,
        "body_temperature": r.body_temperature,
        "heart_rate": r.heart_rate,
        "spo2": r.spo2,
        "activity_percent": round(_derive_activity_percent(r.heart_beat_height), 2),
        "heart_beat_height": r.heart_beat_height,
        "recorded_at": _iso_z(r.recorded_at),
    }


async def wake_up_ai_service(client: httpx.AsyncClient) -> bool:
    """
    Pings the AI service's health endpoint, retrying with a delay between
    attempts since a sleeping Render free-tier instance can take up to ~50s
    to cold-start. Returns True as soon as it gets any non-5xx response.
    """
    url = f"{settings.AI_SERVICE_BASE_URL}{settings.AI_SERVICE_HEALTH_PATH}"
    last_error: Exception | None = None

    for attempt in range(1, settings.AI_SERVICE_WAKEUP_MAX_RETRIES + 1):
        try:
            resp = await client.get(url, timeout=settings.AI_SERVICE_TIMEOUT_SECONDS)
            if resp.status_code < 500:
                return True
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            last_error = e

        if attempt < settings.AI_SERVICE_WAKEUP_MAX_RETRIES:
            await asyncio.sleep(settings.AI_SERVICE_WAKEUP_RETRY_DELAY_SECONDS)

    return False


async def call_ai_service(device_id: str, readings: List[SensorReading]) -> Dict[str, Any]:
    """
    Wakes the AI service (if asleep) then POSTs the readings for analysis.
    Returns the parsed JSON response exactly as the AI service returns it
    (see AI_API.md-style shape: id, device_id, created_at, range_start,
    range_end, samples_analyzed, apnea_detected, risk_score, confidence,
    summary, model_version, details).

    Raises AIServiceError on any failure (unreachable, timeout, non-2xx,
    invalid JSON) - callers decide whether to fall back or bubble up.
    """
    payload = {
        "device_id": device_id,
        "readings": [_reading_to_payload(r) for r in readings],
    }

    async with httpx.AsyncClient() as client:
        awake = await wake_up_ai_service(client)
        if not awake:
            raise AIServiceError(
                "AI service did not respond to its health check after "
                f"{settings.AI_SERVICE_WAKEUP_MAX_RETRIES} attempts "
                "(it may be cold-starting or down)."
            )

        url = f"{settings.AI_SERVICE_BASE_URL}{settings.AI_SERVICE_ANALYZE_PATH}"
        try:
            resp = await client.post(url, json=payload, timeout=settings.AI_SERVICE_TIMEOUT_SECONDS)
        except httpx.HTTPError as e:
            raise AIServiceError(f"Failed to reach AI service at {url}: {e}") from e

        if resp.status_code >= 400:
            raise AIServiceError(
                f"AI service returned HTTP {resp.status_code}: {resp.text[:500]}"
            )

        try:
            return resp.json()
        except ValueError as e:
            raise AIServiceError(f"AI service returned invalid JSON: {e}") from e
