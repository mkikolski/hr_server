"""
UDP Beacon Manager for headset discovery.
Broadcasts the server's WebSocket URL so that headsets on the local network
can auto-discover this server and connect as WebSocket clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Optional

logger = logging.getLogger(__name__)

BEACON_PORT = 15000
BEACON_INTERVAL = 1.0  # seconds between broadcasts


def _get_local_ip() -> str:
    """Detect the local IP address used for LAN communication."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())


class BeaconManager:
    """Broadcasts a UDP beacon so headsets can discover this server."""

    def __init__(self, ws_port: int = 8000) -> None:
        self._ws_port = ws_port
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._sock: Optional[socket.socket] = None

    @property
    def running(self) -> bool:
        return self._running

    def _build_payload(self) -> bytes:
        """Build the JSON beacon payload with the current server IP."""
        local_ip = _get_local_ip()
        payload = {
            "service": "hrv-biofeedback",
            "ws_url": "ws://{}:{}/ws/headset".format(local_ip, self._ws_port),
        }
        return json.dumps(payload).encode("utf-8")

    async def start(self) -> None:
        """Start broadcasting the UDP beacon."""
        if self._running:
            logger.info("Beacon already running")
            return

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.setblocking(False)

        self._running = True
        self._task = asyncio.create_task(self._broadcast_loop())
        logger.info("UDP beacon started on port %d", BEACON_PORT)

    async def stop(self) -> None:
        """Stop the beacon broadcast."""
        if not self._running:
            return

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._sock:
            self._sock.close()
            self._sock = None

        logger.info("UDP beacon stopped")

    async def _broadcast_loop(self) -> None:
        """Send beacon packets at a fixed interval."""
        try:
            while self._running:
                try:
                    payload = self._build_payload()
                    self._sock.sendto(payload, ("255.255.255.255", BEACON_PORT))
                except Exception as e:
                    logger.warning("Beacon send failed: %s", e)
                await asyncio.sleep(BEACON_INTERVAL)
        except asyncio.CancelledError:
            pass
