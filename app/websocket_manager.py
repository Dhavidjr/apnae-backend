"""
In-memory connection manager for websockets.

Two kinds of connections are tracked, keyed by the public `device_id` string:

- device connections: the hardware unit itself (at most one active connection
  per device; a new connection replaces the old one).
- viewer connections: frontend clients subscribed to live data for a device.

When the hardware sends a new reading, it is persisted to the DB and then
broadcast to every viewer currently subscribed to that device_id.
"""
import asyncio
from typing import Dict, List

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.device_connections: Dict[str, WebSocket] = {}
        self.viewer_connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------- device
    async def connect_device(self, device_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            existing = self.device_connections.get(device_id)
            self.device_connections[device_id] = websocket
        if existing is not None and existing is not websocket:
            try:
                await existing.close(code=4000, reason="Replaced by new connection")
            except Exception:
                pass

    async def disconnect_device(self, device_id: str, websocket: WebSocket):
        async with self._lock:
            if self.device_connections.get(device_id) is websocket:
                del self.device_connections[device_id]

    def is_device_connected(self, device_id: str) -> bool:
        return device_id in self.device_connections

    # ---------------------------------------------------------------- viewer
    async def connect_viewer(self, device_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.viewer_connections.setdefault(device_id, []).append(websocket)

    async def disconnect_viewer(self, device_id: str, websocket: WebSocket):
        async with self._lock:
            conns = self.viewer_connections.get(device_id)
            if conns and websocket in conns:
                conns.remove(websocket)
            if conns is not None and len(conns) == 0:
                self.viewer_connections.pop(device_id, None)

    async def broadcast_to_viewers(self, device_id: str, message: dict):
        conns = list(self.viewer_connections.get(device_id, []))
        dead = []
        for conn in conns:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        if dead:
            async with self._lock:
                for conn in dead:
                    if conn in self.viewer_connections.get(device_id, []):
                        self.viewer_connections[device_id].remove(conn)


manager = ConnectionManager()
