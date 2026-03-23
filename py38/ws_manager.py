"""
WebSocket connection manager for the HRV Biofeedback Control Panel.
Manages two categories of WebSocket clients: the diagnost's browser panel and the Unity VR headset.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSManager:
    """Manages WebSocket connections for the control panel and Unity headset."""

    def __init__(self) -> None:
        self._panel: Optional[WebSocket] = None
        self._headset: Optional[WebSocket] = None

    @property
    def panel_connected(self) -> bool:
        return self._panel is not None

    @property
    def headset_connected(self) -> bool:
        return self._headset is not None

    async def connect_panel(self, ws: WebSocket) -> None:
        await ws.accept()
        self._panel = ws
        logger.info("Control panel connected")

    async def connect_headset(self, ws: WebSocket) -> None:
        await ws.accept()
        self._headset = ws
        logger.info("Unity headset connected")

    def disconnect_panel(self) -> None:
        self._panel = None
        logger.info("Control panel disconnected")

    def disconnect_headset(self) -> None:
        self._headset = None
        logger.info("Unity headset disconnected")

    async def send_to_panel(self, message: dict) -> None:
        if self._panel:
            try:
                await self._panel.send_text(json.dumps(message))
            except Exception as e:
                logger.error("Failed to send to panel: %s", e)
                self._panel = None

    async def send_to_headset(self, message: dict) -> None:
        if self._headset:
            try:
                await self._headset.send_text(json.dumps(message))
            except Exception as e:
                logger.error("Failed to send to headset: %s", e)
                self._headset = None

    async def broadcast(self, message: dict) -> None:
        await self.send_to_panel(message)
        await self.send_to_headset(message)
