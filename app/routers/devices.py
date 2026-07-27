"""
Device (hardware) management endpoints.

A device must be registered by an authenticated user before it can connect
over the hardware websocket. Registration returns a `device_secret` which
the hardware must supply (alongside its `device_id`) to authenticate its
websocket connection. The secret is only ever returned at creation time and
on explicit regeneration - it is never included in normal GET responses.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_owned_device
from app.security import generate_device_secret, get_current_active_user

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.post("/", response_model=schemas.DeviceCreatedOut, status_code=status.HTTP_201_CREATED)
def register_device(
    device_in: schemas.DeviceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    device_id = device_in.device_id or f"dev-{uuid.uuid4().hex[:12]}"

    if db.query(models.Device).filter(models.Device.device_id == device_id).first():
        raise HTTPException(status_code=400, detail="A device with this device_id is already registered")

    device = models.Device(
        device_id=device_id,
        device_secret=generate_device_secret(),
        name=device_in.name,
        user_id=current_user.id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("/", response_model=list[schemas.DeviceOut])
def list_devices(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    return (
        db.query(models.Device)
        .filter(models.Device.user_id == current_user.id)
        .order_by(models.Device.created_at.desc())
        .all()
    )


@router.get("/{device_id}", response_model=schemas.DeviceOut)
def get_device(device: models.Device = Depends(get_owned_device)):
    return device


@router.patch("/{device_id}", response_model=schemas.DeviceOut)
def update_device(
    update: schemas.DeviceUpdate,
    device: models.Device = Depends(get_owned_device),
    db: Session = Depends(get_db),
):
    if update.name is not None:
        device.name = update.name
    if update.is_active is not None:
        device.is_active = update.is_active
    db.commit()
    db.refresh(device)
    return device


@router.post("/{device_id}/regenerate-secret", response_model=schemas.DeviceCreatedOut)
def regenerate_secret(
    device: models.Device = Depends(get_owned_device),
    db: Session = Depends(get_db),
):
    device.device_secret = generate_device_secret()
    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    device: models.Device = Depends(get_owned_device),
    db: Session = Depends(get_db),
):
    db.delete(device)
    db.commit()
    return None
