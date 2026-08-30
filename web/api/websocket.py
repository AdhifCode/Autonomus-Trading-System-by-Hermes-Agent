"""WebSocket Connection Manager for Trader Control Center.

Broadcasts live log entries, market ticks, risk alerts, and execution events
to connected dashboard clients.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """Manages active WebSocket client connections."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast JSON message to all active WebSocket clients."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Error broadcasting to WebSocket client: {e}")
                self.disconnect(connection)


ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint streaming live logs, status ticks, and notifications."""
    await ws_manager.connect(websocket)
    try:
        # Send initial connection status
        await websocket.send_json({
            "type": "SYSTEM_LOG",
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "INFO",
            "message": "Connected to Hermes Trader Control Center WebSocket stream.",
        })

        # Main message loop
        while True:
            # Client can send ping or commands
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({
                    "type": "PONG",
                    "timestamp": datetime.now(UTC).isoformat(),
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket exception: {e}")
        ws_manager.disconnect(websocket)
