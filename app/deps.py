"""
Shared dependencies used across routers.
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.security import get_current_active_user


def get_owned_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> models.Device:
    """Fetch a device by its public device_id string and ensure the current
    authenticated user owns it. Raises 404 otherwise (never reveals whether
    the device exists to non-owners)."""
    device = db.query(models.Device).filter(models.Device.device_id == device_id).first()
    if device is None or device.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device
