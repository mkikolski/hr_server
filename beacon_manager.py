"""
UDP Beacon Manager for headset discovery.
Broadcasts the server's WebSocket URL so that headsets on the local network
can auto-discover this server and connect as WebSocket clients.
"""

import asyncio
import json
import logging
import socket

logger = logging.getLogger(__name__)

BEACON_PORT = 15000
BEACON_INTERVAL = 1.0  # seconds between broadcasts


def _get_local_ip() -> str:
    """Detect the local IP address used for LAN communication."""
    try:
        # Connect to an external address to determine the outbound interface.
        # No data is actually sent.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())


class BeaconManager:
    """Broadcasts a UDP beacon so headsets can discover this server."""

    def __init__(self, ws_port: int = 8000):
        self._ws_port = ws_port
        self._running = False
        self._task: asyncio.Task | None = None
        self._sock: socket.socket | None = None

    @property
    def running(self) -> bool:
        return self._running

    def _build_payload(self) -> bytes:
        """Build the JSON beacon payload with the current server IP."""
        local_ip = _get_local_ip()
        payload = {
            "service": "hrv-biofeedback",
            "ws_url": f"ws://{local_ip}:{self._ws_port}/ws/headset",
        }
        return json.dumps(payload).encode("utf-8")

    async def start(self):
        if self._running:
            logger.info("Beacon already running")
            return

        # 1. Grab the correct local IP first
        local_ip = _get_local_ip()

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.setblocking(False)

        # 2. Bind the socket to the specific interface before broadcasting
        self._sock.bind((local_ip, 0))

        self._running = True
        self._task = asyncio.create_task(self._broadcast_loop())
        logger.info(f"UDP beacon started on port {BEACON_PORT} via interface {local_ip}")

    async def stop(self):
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

    async def _broadcast_loop(self):
        """Send beacon packets at a fixed interval."""
        try:
            while self._running:
                try:
                    payload = self._build_payload()
                    self._sock.sendto(payload, ("255.255.255.255", BEACON_PORT))
                except Exception as e:
                    logger.warning(f"Beacon send failed: {e}")
                await asyncio.sleep(BEACON_INTERVAL)
        except asyncio.CancelledError:
            pass
