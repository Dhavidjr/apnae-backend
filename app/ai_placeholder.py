"""
PLACEHOLDER apnoea prediction/detection logic.

--------------------------------------------------------------------------
This module intentionally does NOT contain a real machine-learning model.
`run_apnea_prediction()` is a stand-in with simple, transparent heuristic
rules so the rest of the system (API contracts, storage, review history)
can be built and tested end-to-end right now.

To go live with real AI:
1. Replace the body of `run_apnea_prediction()` with a call to your trained
   model (e.g. load a serialized model at module import time, run inference
   over the `readings` list below).
2. Keep the return shape identical (or update `schemas.AIReviewOut` and the
   `ai_review` router together with it) so the rest of the API keeps working.
--------------------------------------------------------------------------
"""
import statistics
from typing import Any, Dict, List

from app.models import SensorReading

# Heuristic thresholds - illustrative only, NOT clinically validated.
SPO2_APNEA_THRESHOLD = 90.0          # SpO2 below this is considered a desaturation event
HEART_RATE_LOW_THRESHOLD = 45.0      # bradycardia-ish cutoff
HEART_RATE_HIGH_THRESHOLD = 140.0    # tachycardia-ish cutoff
HEART_BEAT_FLATNESS_STD_THRESHOLD = 0.02  # very low variance in accelerometer signal


def run_apnea_prediction(readings: List[SensorReading]) -> Dict[str, Any]:
    """
    Placeholder apnoea prediction over a list of SensorReading ORM objects,
    ordered chronologically (oldest first).

    Returns a dict matching the shape expected by `schemas.AIReviewOut.details`
    plus the top-level summary fields used to populate the AIReview record.
    """
    if not readings:
        return {
            "apnea_detected": False,
            "risk_score": 0.0,
            "confidence": 0.0,
            "summary": "No sensor data available in the requested range.",
            "model_version": "placeholder-v0",
            "details": {
                "flagged_events": [],
                "notes": "No readings to analyze.",
            },
        }

    spo2_values = [r.spo2 for r in readings]
    hr_values = [r.heart_rate for r in readings]
    beat_height_values = [r.heart_beat_height for r in readings]

    flagged_events = []

    for r in readings:
        reasons = []
        if r.spo2 < SPO2_APNEA_THRESHOLD:
            reasons.append("low_spo2")
        if r.heart_rate < HEART_RATE_LOW_THRESHOLD:
            reasons.append("bradycardia")
        if r.heart_rate > HEART_RATE_HIGH_THRESHOLD:
            reasons.append("tachycardia")
        if reasons:
            flagged_events.append(
                {
                    "reading_id": r.id,
                    "recorded_at": r.recorded_at.isoformat(),
                    "spo2": r.spo2,
                    "heart_rate": r.heart_rate,
                    "body_temperature": r.body_temperature,
                    "heart_beat_height": r.heart_beat_height,
                    "reasons": reasons,
                }
            )

    # Flatness in the accelerometer-derived "heart_beat_height" signal over a
    # long enough window can indicate a pause in respiratory-linked movement.
    beat_height_std = statistics.pstdev(beat_height_values) if len(beat_height_values) > 1 else 0.0
    flat_signal = beat_height_std < HEART_BEAT_FLATNESS_STD_THRESHOLD and len(readings) >= 10

    event_ratio = len(flagged_events) / len(readings)
    risk_score = min(1.0, event_ratio * 1.5 + (0.2 if flat_signal else 0.0))
    apnea_detected = risk_score >= 0.4 or flat_signal

    # Confidence is naive here: more samples -> more confidence in the heuristic.
    confidence = min(1.0, len(readings) / 500.0) if len(readings) < 500 else 1.0
    confidence = max(confidence, 0.1)

    summary_parts = [
        f"Analyzed {len(readings)} samples.",
        f"{len(flagged_events)} sample(s) flagged out of range "
        f"(SpO2<{SPO2_APNEA_THRESHOLD} or HR outside "
        f"[{HEART_RATE_LOW_THRESHOLD}, {HEART_RATE_HIGH_THRESHOLD}]).",
    ]
    if flat_signal:
        summary_parts.append(
            "Accelerometer-derived signal showed unusually low variability, "
            "which can be consistent with reduced respiratory movement."
        )
    summary_parts.append(
        "Apnoea risk flagged." if apnea_detected else "No significant apnoea risk detected."
    )

    return {
        "apnea_detected": apnea_detected,
        "risk_score": round(risk_score, 4),
        "confidence": round(confidence, 4),
        "summary": " ".join(summary_parts),
        "model_version": "placeholder-v0",
        "details": {
            "flagged_events": flagged_events,
            "stats": {
                "spo2_min": min(spo2_values),
                "spo2_avg": round(sum(spo2_values) / len(spo2_values), 2),
                "heart_rate_min": min(hr_values),
                "heart_rate_max": max(hr_values),
                "heart_rate_avg": round(sum(hr_values) / len(hr_values), 2),
                "heart_beat_height_std": round(beat_height_std, 5),
                "flat_signal_detected": flat_signal,
            },
            "thresholds_used": {
                "spo2_apnea_threshold": SPO2_APNEA_THRESHOLD,
                "heart_rate_low_threshold": HEART_RATE_LOW_THRESHOLD,
                "heart_rate_high_threshold": HEART_RATE_HIGH_THRESHOLD,
                "heart_beat_flatness_std_threshold": HEART_BEAT_FLATNESS_STD_THRESHOLD,
            },
            "disclaimer": "PLACEHOLDER heuristic output. Not a validated medical prediction.",
        },
    }
