"""
Polar H10 BLE connection manager.
Uses bleak directly to scan, connect, and stream HR data (no polar_python dependency).
Compatible with Python 3.8+.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import Callable, List, Optional

from bleak import BleakClient, BleakScanner

logger = logging.getLogger(__name__)

# Standard Bluetooth Heart Rate Measurement characteristic UUID
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


def _parse_hr_measurement(data: bytearray):
    """Parse a standard BLE Heart Rate Measurement characteristic value.

    Returns:
        (heartrate, rr_intervals) tuple.
    """
    flags = data[0]
    hr_format_16bit = flags & 0x01
    rr_present = (flags >> 4) & 0x01

    offset = 1
    if hr_format_16bit:
        heartrate = struct.unpack_from("<H", data, offset)[0]
        offset += 2
    else:
        heartrate = data[offset]
        offset += 1

    # Skip energy expended if present
    if (flags >> 3) & 0x01:
        offset += 2

    rr_intervals: List[float] = []
    if rr_present:
        while offset + 1 < len(data):
            rr_raw = struct.unpack_from("<H", data, offset)[0]
            # RR values are in 1/1024 seconds — convert to milliseconds
            rr_intervals.append(rr_raw / 1024.0 * 1000.0)
            offset += 2

    return heartrate, rr_intervals


class PolarManager:
    """Manages the BLE connection to a Polar H10 heart rate monitor.

    Uses bleak directly (no polar_python) for Python 3.8 compatibility.
    """

    def __init__(self) -> None:
        self._client: Optional[BleakClient] = None
        self._ble_device = None
        self._connected = False
        self._streaming = False
        self._hr_callback: Optional[Callable] = None
        self._connect_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def streaming(self) -> bool:
        return self._streaming

    async def scan_and_connect(self, timeout: float = 10.0) -> bool:
        """Scan for a Polar H10 and connect to it.

        Returns:
            True if connection was successful, False otherwise.
        """
        async with self._connect_lock:
            if self._connected:
                logger.info("Already connected to Polar H10")
                return True

            logger.info("Scanning for Polar H10...")
            try:
                self._ble_device = await BleakScanner.find_device_by_filter(
                    lambda bd, ad: bd.name and "Polar H10" in bd.name,
                    timeout=timeout,
                )
            except Exception as e:
                logger.error("BLE scan failed: %s", e)
                return False

            if not self._ble_device:
                logger.warning("Polar H10 not found within timeout")
                return False

            logger.info("Found %s, connecting...", self._ble_device.name)
            try:
                self._client = BleakClient(self._ble_device)
                await self._client.connect()
                self._connected = True
                logger.info("Connected to Polar H10")
                return True
            except Exception as e:
                logger.error("Connection failed: %s", e)
                self._client = None
                return False

    async def start_streaming(self, callback: Callable) -> None:
        """Start the HR data stream.

        Args:
            callback: async or sync function called with (heartrate: int, rr_intervals: list)
        """
        if not self._connected or not self._client:
            raise RuntimeError("Not connected to Polar H10")
        if self._streaming:
            logger.info("Already streaming")
            return

        self._hr_callback = callback

        def _hr_notification_handler(sender, data: bytearray) -> None:
            heartrate, rr_intervals = _parse_hr_measurement(data)
            if self._hr_callback:
                asyncio.get_event_loop().call_soon_threadsafe(
                    lambda: asyncio.ensure_future(
                        self._hr_callback(heartrate, rr_intervals)
                    )
                )

        await self._client.start_notify(HR_MEASUREMENT_UUID, _hr_notification_handler)
        self._streaming = True
        logger.info("HR streaming started")

    async def stop_streaming(self) -> None:
        """Stop the HR data stream."""
        if self._streaming and self._client:
            try:
                await self._client.stop_notify(HR_MEASUREMENT_UUID)
            except Exception as e:
                logger.warning("Error stopping HR stream: %s", e)
            self._streaming = False
            self._hr_callback = None
            logger.info("HR streaming stopped")

    async def disconnect(self) -> None:
        """Disconnect from the Polar device."""
        await self.stop_streaming()
        if self._client and self._connected:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.warning("Error disconnecting: %s", e)
            self._client = None
            self._connected = False
            logger.info("Disconnected from Polar H10")
