"""
Websocket endpoints.

1) ws://.../ws/device/{device_id}?secret=<device_secret>
   Used by the HARDWARE unit. It must supply the device_id (path) and its
   device_secret (query param) as generated at registration time. Once
   connected, it sends one JSON message per sample:

       {
         "body_temperature": 36.8,
         "heart_rate": 72,
         "spo2": 97,
         "heart_beat_height": 0.42,
         "timestamp": "2026-07-23T10:00:00Z"   // optional, server time used if omitted
       }

   Each valid message is persisted to the database and immediately
   rebroadcast to any frontend clients subscribed via the stream endpoint
   below. Invalid messages get an {"type": "error", ...} reply and do not
   close the connection.

2) ws://.../ws/stream/{device_id}?token=<jwt access token>
   Used by the FRONTEND to receive a live feed of readings as they arrive
   for a device owned by the authenticated user. The server pushes messages
   shaped like:

       {"type": "reading", "device_id": "dev-abc123", "data": {...SensorReadingOut...}}

   The client does not need to send anything after connecting; the
   connection is kept open until the client disconnects. A lightweight
   ping/pong keepalive is handled automatically.
"""
import datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import SessionLocal, get_db
from app.security import get_user_from_token_str
from app.websocket_manager import manager

router = APIRouter(tags=["WebSockets"])


@router.websocket("/ws/device/{device_id}")
async def device_websocket(
    websocket: WebSocket,
    device_id: str,
    secret: str = Query(..., description="The device_secret issued at registration"),
):
    # Validate device + secret BEFORE accepting, using a short-lived session.
    db: Session = SessionLocal()
    try:
        device = db.query(models.Device).filter(models.Device.device_id == device_id).first()
        if device is None or device.device_secret != secret:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid device_id or secret")
            return
        if not device.is_active:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Device is disabled")
            return
        device_pk = device.id
    finally:
        db.close()

    await manager.connect_device(device_id, websocket)

    try:
        while True:
            raw = await websocket.receive_json()
            db = SessionLocal()
            try:
                try:
                    payload = schemas.SensorDataIn(**raw)
                except ValidationError as e:
                    safe_errors = [
                        {
                            "loc": [str(part) for part in err.get("loc", [])],
                            "msg": err.get("msg"),
                            "type": err.get("type"),
                        }
                        for err in e.errors()
                    ]
                    await websocket.send_json({"type": "error", "detail": safe_errors})
                    continue
                except (TypeError, ValueError) as e:
                    await websocket.send_json({"type": "error", "detail": str(e)})
                    continue

                reading = models.SensorReading(
                    device_id=device_pk,
                    body_temperature=payload.body_temperature,
                    heart_rate=payload.heart_rate,
                    spo2=payload.spo2,
                    heart_beat_height=payload.heart_beat_height,
                    recorded_at=payload.timestamp or datetime.datetime.utcnow(),
                )
                db.add(reading)

                device_row = db.query(models.Device).filter(models.Device.id == device_pk).first()
                if device_row is not None:
                    device_row.last_seen_at = datetime.datetime.utcnow()

                db.commit()
                db.refresh(reading)

                reading_out = schemas.SensorReadingOut.model_validate(reading)
                await websocket.send_json({"type": "ack", "reading_id": reading.id})

                message = schemas.WSReadingMessage(device_id=device_id, data=reading_out)
                await manager.broadcast_to_viewers(device_id, message.model_dump(mode="json"))
            finally:
                db.close()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_device(device_id, websocket)


@router.websocket("/ws/stream/{device_id}")
async def stream_websocket(
    websocket: WebSocket,
    device_id: str,
    token: str = Query(..., description="JWT access token obtained from /auth/login"),
):
    db: Session = SessionLocal()
    try:
        user = get_user_from_token_str(token, db)
        if user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
            return

        device = db.query(models.Device).filter(models.Device.device_id == device_id).first()
        if device is None or device.user_id != user.id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Device not found or not owned by user")
            return
    finally:
        db.close()

    await manager.connect_viewer(device_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "device_id": device_id})
        while True:
            # We don't require the client to send anything, but reading here
            # lets us detect disconnects promptly and supports optional
            # client-side pings without erroring out.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_viewer(device_id, websocket)
