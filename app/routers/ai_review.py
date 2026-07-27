"""
AI review endpoints.

POST /{device_id}/review   -> runs the (placeholder) apnoea prediction over a
                               range of stored sensor data and persists the result.
GET  /{device_id}/reviews  -> lists past review results for a device.
GET  /reviews/{review_id}  -> fetch a single review result by its ID.

NOTE: `run_apnea_prediction` in app/ai_placeholder.py is a stand-in heuristic.
Swap it for a real trained model without touching this router - just keep the
returned dict shape the same (see docstring there).
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.ai_placeholder import run_apnea_prediction
from app.config import settings
from app.database import get_db
from app.deps import get_owned_device
from app.security import get_current_active_user

router = APIRouter(prefix="/ai", tags=["AI Review"])


@router.post("/{device_id}/review", response_model=schemas.AIReviewOut, status_code=201)
def request_ai_review(
    request: schemas.AIReviewRequest = schemas.AIReviewRequest(),
    device: models.Device = Depends(get_owned_device),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Triggers an apnoea prediction run over stored data for this device.

    If `start`/`end` are omitted, defaults to the last 24 hours of data.
    The call is synchronous (the placeholder function is cheap); if a real
    model needs longer inference time, swap this for a background task /
    job queue and have the client poll GET /ai/reviews/{review_id}.
    """
    end = request.end or datetime.datetime.utcnow()
    start = request.start or (end - datetime.timedelta(hours=24))

    if start >= end:
        raise HTTPException(status_code=400, detail="'start' must be before 'end'")

    q = (
        db.query(models.SensorReading)
        .filter(models.SensorReading.device_id == device.id)
        .filter(models.SensorReading.recorded_at >= start)
        .filter(models.SensorReading.recorded_at <= end)
        .order_by(models.SensorReading.recorded_at.asc())
    )

    if request.limit_samples:
        # take the most recent N samples within the range
        total = q.count()
        offset = max(0, total - request.limit_samples)
        readings = q.offset(offset).all()
    else:
        readings = q.limit(settings.MAX_QUERY_LIMIT).all()

    result = run_apnea_prediction(readings)

    review = models.AIReview(
        user_id=current_user.id,
        device_id=device.id,
        range_start=start,
        range_end=end,
        samples_analyzed=len(readings),
        apnea_detected=result["apnea_detected"],
        risk_score=result["risk_score"],
        confidence=result["confidence"],
        summary=result["summary"],
        model_version=result["model_version"],
        details=result["details"],
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    return _to_review_out(review, device.device_id)


@router.get("/{device_id}/reviews", response_model=list[schemas.AIReviewOut])
def list_ai_reviews(
    device: models.Device = Depends(get_owned_device),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    reviews = (
        db.query(models.AIReview)
        .filter(models.AIReview.device_id == device.id)
        .order_by(models.AIReview.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_review_out(r, device.device_id) for r in reviews]


@router.get("/reviews/{review_id}", response_model=schemas.AIReviewOut)
def get_ai_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    review = db.query(models.AIReview).filter(models.AIReview.id == review_id).first()
    if review is None or review.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Review not found")
    device = db.query(models.Device).filter(models.Device.id == review.device_id).first()
    return _to_review_out(review, device.device_id if device else "unknown")


def _to_review_out(review: models.AIReview, device_id_str: str) -> schemas.AIReviewOut:
    return schemas.AIReviewOut(
        id=review.id,
        device_id=device_id_str,
        created_at=review.created_at,
        range_start=review.range_start,
        range_end=review.range_end,
        samples_analyzed=review.samples_analyzed,
        apnea_detected=review.apnea_detected,
        risk_score=review.risk_score,
        confidence=review.confidence,
        summary=review.summary,
        model_version=review.model_version,
        details=review.details,
    )
