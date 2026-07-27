"""
Endpoints for retrieving stored sensor data for a device the current user owns.

Three retrieval styles, as requested:
  - /raw    -> plain list of raw rows (all stored fields)
  - /json   -> structured JSON envelope with query metadata + readings
  - /graph  -> rendered PNG plot (matplotlib) of one metric or all metrics
Plus:
  - /latest -> most recent single reading
  - /export -> download as .json or .csv file
"""
import csv
import datetime
import io
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_owned_device
from app.config import settings
from app.utils.plotting import plot_readings

router = APIRouter(prefix="/data", tags=["Sensor Data"])


def _query_readings(
    db: Session,
    device: models.Device,
    start: Optional[datetime.datetime],
    end: Optional[datetime.datetime],
    limit: int,
    offset: int,
    order: str,
):
    q = db.query(models.SensorReading).filter(models.SensorReading.device_id == device.id)
    if start is not None:
        q = q.filter(models.SensorReading.recorded_at >= start)
    if end is not None:
        q = q.filter(models.SensorReading.recorded_at <= end)

    if order == "desc":
        q = q.order_by(models.SensorReading.recorded_at.desc())
    else:
        q = q.order_by(models.SensorReading.recorded_at.asc())

    return q.offset(offset).limit(limit).all()


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, settings.MAX_QUERY_LIMIT))


@router.get("/{device_id}/raw")
def get_raw_readings(
    device: models.Device = Depends(get_owned_device),
    db: Session = Depends(get_db),
    start: Optional[datetime.datetime] = Query(None, description="ISO 8601 start time (inclusive)"),
    end: Optional[datetime.datetime] = Query(None, description="ISO 8601 end time (inclusive)"),
    limit: int = Query(settings.DEFAULT_QUERY_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    order: Literal["asc", "desc"] = Query("asc"),
):
    """Returns the raw stored rows exactly as persisted, with no extra envelope."""
    limit = _clamp_limit(limit)
    readings = _query_readings(db, device, start, end, limit, offset, order)
    return [
        {
            "id": r.id,
            "device_id": device.device_id,
            "body_temperature": r.body_temperature,
            "heart_rate": r.heart_rate,
            "spo2": r.spo2,
            "heart_beat_height": r.heart_beat_height,
            "recorded_at": r.recorded_at.isoformat(),
        }
        for r in readings
    ]


@router.get("/{device_id}/json", response_model=schemas.ReadingsJSONResponse)
def get_json_readings(
    device: models.Device = Depends(get_owned_device),
    db: Session = Depends(get_db),
    start: Optional[datetime.datetime] = Query(None),
    end: Optional[datetime.datetime] = Query(None),
    limit: int = Query(settings.DEFAULT_QUERY_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    order: Literal["asc", "desc"] = Query("asc"),
):
    """Returns a structured JSON envelope including query metadata - convenient
    for frontend consumption/charting libraries."""
    limit = _clamp_limit(limit)
    readings = _query_readings(db, device, start, end, limit, offset, order)
    return schemas.ReadingsJSONResponse(
        device_id=device.device_id,
        count=len(readings),
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        order=order,
        readings=readings,
    )


@router.get("/{device_id}/latest", response_model=schemas.SensorReadingOut)
def get_latest_reading(
    device: models.Device = Depends(get_owned_device),
    db: Session = Depends(get_db),
):
    reading = (
        db.query(models.SensorReading)
        .filter(models.SensorReading.device_id == device.id)
        .order_by(models.SensorReading.recorded_at.desc())
        .first()
    )
    if reading is None:
        raise HTTPException(status_code=404, detail="No readings found for this device yet")
    return reading


@router.get("/{device_id}/graph")
def get_graph(
    device: models.Device = Depends(get_owned_device),
    db: Session = Depends(get_db),
    metric: Literal["body_temperature", "heart_rate", "spo2", "heart_beat_height", "all"] = Query("all"),
    start: Optional[datetime.datetime] = Query(None),
    end: Optional[datetime.datetime] = Query(None),
    limit: int = Query(settings.DEFAULT_QUERY_LIMIT, ge=1),
    order: Literal["asc", "desc"] = Query("asc"),
):
    """Renders a PNG plot of the requested metric(s) over time."""
    limit = _clamp_limit(limit)
    readings = _query_readings(db, device, start, end, limit, 0, order)
    # Plot always in chronological order regardless of requested 'order'
    readings_sorted = sorted(readings, key=lambda r: r.recorded_at)
    buf = plot_readings(readings_sorted, metric, device_label=device.name or device.device_id)
    return StreamingResponse(buf, media_type="image/png")


@router.get("/{device_id}/export")
def export_readings(
    device: models.Device = Depends(get_owned_device),
    db: Session = Depends(get_db),
    format: Literal["json", "csv"] = Query("json"),
    start: Optional[datetime.datetime] = Query(None),
    end: Optional[datetime.datetime] = Query(None),
    order: Literal["asc", "desc"] = Query("asc"),
):
    """Streams all matching readings (up to MAX_QUERY_LIMIT) as a downloadable file."""
    readings = _query_readings(db, device, start, end, settings.MAX_QUERY_LIMIT, 0, order)

    if format == "json":
        import json

        payload = json.dumps(
            [
                {
                    "id": r.id,
                    "body_temperature": r.body_temperature,
                    "heart_rate": r.heart_rate,
                    "spo2": r.spo2,
                    "heart_beat_height": r.heart_beat_height,
                    "recorded_at": r.recorded_at.isoformat(),
                }
                for r in readings
            ],
            indent=2,
        )
        buf = io.BytesIO(payload.encode("utf-8"))
        return StreamingResponse(
            buf,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{device.device_id}_readings.json"'},
        )

    # CSV
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "body_temperature", "heart_rate", "spo2", "heart_beat_height", "recorded_at"])
    for r in readings:
        writer.writerow(
            [r.id, r.body_temperature, r.heart_rate, r.spo2, r.heart_beat_height, r.recorded_at.isoformat()]
        )
    byte_buf = io.BytesIO(buf.getvalue().encode("utf-8"))
    return StreamingResponse(
        byte_buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{device.device_id}_readings.csv"'},
    )
