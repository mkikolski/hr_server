"""
Polar H10 BLE connection manager.
Async wrapper around polar_python for scanning, connecting, and streaming HR data.
"""

import asyncio
import logging
from bleak import BleakScanner
from polar_python import PolarDevice
from polar_python.models import HRData

logger = logging.getLogger(__name__)


class PolarManager:
    """Manages the BLE connection to a Polar H10 heart rate monitor."""

    def __init__(self):
        self._device: PolarDevice | None = None
        self._ble_device = None
        self._connected = False
        self._streaming = False
        self._hr_callback = None
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
                logger.error(f"BLE scan failed: {e}")
                return False

            if not self._ble_device:
                logger.warning("Polar H10 not found within timeout")
                return False

            logger.info(f"Found {self._ble_device.name}, connecting...")
            try:
                self._device = PolarDevice(self._ble_device)
                await self._device.connect()
                self._connected = True
                logger.info("Connected to Polar H10")
                return True
            except Exception as e:
                logger.error(f"Connection failed: {e}")
                self._device = None
                return False

    async def start_streaming(self, callback):
        """Start the HR data stream.

        Args:
            callback: async or sync function called with (heartrate: int, rr_intervals: list[float])
        """
        if not self._connected or not self._device:
            raise RuntimeError("Not connected to Polar H10")
        if self._streaming:
            logger.info("Already streaming")
            return

        self._hr_callback = callback

        def _hr_handler(data: HRData):
            if self._hr_callback:
                # The callback may be async — schedule it
                asyncio.get_event_loop().call_soon_threadsafe(
                    lambda: asyncio.ensure_future(
                        self._hr_callback(data.heartrate, data.rr_intervals)
                    )
                )

        await self._device.start_hr_stream(hr_callback=_hr_handler)
        self._streaming = True
        logger.info("HR streaming started")

    async def stop_streaming(self):
        """Stop the HR data stream."""
        if self._streaming and self._device:
            try:
                await self._device.stop_hr_stream()
            except Exception as e:
                logger.warning(f"Error stopping HR stream: {e}")
            self._streaming = False
            self._hr_callback = None
            logger.info("HR streaming stopped")

    async def disconnect(self):
        """Disconnect from the Polar device."""
        await self.stop_streaming()
        if self._device and self._connected:
            try:
                await self._device.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting: {e}")
            self._device = None
            self._connected = False
            logger.info("Disconnected from Polar H10")
