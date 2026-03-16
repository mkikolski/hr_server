"""
Diagnosis workflow state machine for the HRV Biofeedback Control Panel.
Governs the full lifecycle of a biofeedback session from connection to completion.
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum

from hrv_analysis import (
    compute_baseline_hr,
    compute_hrv_amplitude,
    compute_resonant_frequency,
    compute_rmssd,
    compute_sdnn,
)
from data_store import DataStore
from ws_manager import WSManager
from polar_manager import PolarManager

logger = logging.getLogger(__name__)


class SessionState(str, Enum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    READY = "READY"
    CALIBRATION_TUTORIAL = "CALIBRATION_TUTORIAL"
    HR_BASELINE = "HR_BASELINE"
    BASELINE_COMPLETE = "BASELINE_COMPLETE"
    HRV_TUTORIAL = "HRV_TUTORIAL"
    HRV_CALIBRATION = "HRV_CALIBRATION"
    CALIBRATION_COMPLETE = "CALIBRATION_COMPLETE"
    THERAPY = "THERAPY"
    COMPLETE = "COMPLETE"


# Paced breathing rates to test (breaths per minute)
BREATHING_RATES = [7.0, 6.5, 6.0, 5.5, 5.0]
SEGMENT_DURATION = 12  # seconds per breathing rate
BASELINE_DURATION = 90  # seconds for HR baseline


class SessionManager:
    """Manages the diagnosis workflow state machine."""

    def __init__(self, ws: WSManager, polar: PolarManager):
        self._ws = ws
        self._polar = polar
        self._data = DataStore()
        self._state = SessionState.IDLE
        self._timer_task: asyncio.Task | None = None
        self._elapsed = 0
        self._total_duration = 0

        # Baseline collection
        self._baseline_hr_values: list[int] = []

        # HRV calibration
        self._current_segment_index = 0
        self._segment_rr: list[float] = []
        self._hrv_segments: dict[float, list[float]] = {}

        # Results
        self._baseline_mean: float | None = None
        self._resonant_frequency: float | None = None
        self._hrv_amplitudes: dict[float, float] = {}

        # All RR intervals collected during session (for live metrics)
        self._all_rr: list[float] = []

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def baseline_mean(self) -> float | None:
        return self._baseline_mean

    @property
    def resonant_frequency(self) -> float | None:
        return self._resonant_frequency

    async def _set_state(self, new_state: SessionState):
        """Transition to a new state and notify clients."""
        old_state = self._state
        self._state = new_state
        self._data.log_state_change(new_state.value)
        logger.info(f"State: {old_state.value} → {new_state.value}")
        await self._ws.send_to_panel({
            "type": "state",
            "state": new_state.value,
            "elapsed": 0,
            "total": 0,
        })

    async def _on_hr_data(self, heartrate: int, rr_intervals: list[float]):
        """Callback invoked by PolarManager on every HR data packet."""
        timestamp = datetime.now().isoformat()

        # Always log
        self._data.log_hr(heartrate, rr_intervals)
        self._all_rr.extend(rr_intervals)

        # Send to panel for live display
        rmssd = compute_rmssd(self._all_rr[-60:]) if len(self._all_rr) >= 2 else 0.0
        sdnn = compute_sdnn(self._all_rr[-60:]) if len(self._all_rr) >= 2 else 0.0

        await self._ws.send_to_panel({
            "type": "hr_update",
            "heartrate": heartrate,
            "rr_intervals": rr_intervals,
            "rmssd": round(rmssd, 1),
            "sdnn": round(sdnn, 1),
            "timestamp": timestamp,
        })

        # State-specific collection
        if self._state == SessionState.HR_BASELINE:
            self._baseline_hr_values.append(heartrate)
            self._data.add_baseline_hr(heartrate)

        elif self._state == SessionState.HRV_CALIBRATION:
            self._segment_rr.extend(rr_intervals)

        elif self._state == SessionState.THERAPY:
            self._data.log_therapy_data(heartrate, rr_intervals)
            # Stream raw data to headset during therapy
            await self._ws.send_to_headset({
                "type": "hr_data",
                "heartrate": heartrate,
                "rr_intervals": rr_intervals,
                "timestamp": timestamp,
            })

    async def handle_action(self, action: str):
        """Handle a diagnost action from the control panel."""
        logger.info(f"Action received: {action} (state: {self._state.value})")

        if action == "connect_devices":
            await self._do_connect()
        elif action == "next_step":
            await self._advance()
        elif action == "skip_tutorial":
            await self._skip_tutorial()
        elif action == "stop_session":
            await self._stop_session()

    async def _do_connect(self):
        """Initiate connections to Polar H10 and notify the headset."""
        if self._state != SessionState.IDLE:
            return

        await self._set_state(SessionState.CONNECTING)
        self._data.start_session()

        # Connect to Polar H10
        polar_ok = await self._polar.scan_and_connect()
        if not polar_ok:
            await self._ws.send_to_panel({
                "type": "error",
                "message": "Polar H10 not found. Ensure the sensor is awake and nearby.",
            })
            await self._set_state(SessionState.IDLE)
            return

        # Start HR streaming
        await self._polar.start_streaming(self._on_hr_data)

        # Notify headset to connect
        await self._ws.send_to_headset({
            "type": "command",
            "action": "connect_headset",
        })

        # Send connection status
        await self._ws.send_to_panel({
            "type": "connection_status",
            "polar": True,
            "headset": self._ws.headset_connected,
        })

        await self._set_state(SessionState.READY)

    async def _advance(self):
        """Advance to the next step in the diagnosis workflow."""
        transitions = {
            SessionState.READY: self._start_calibration_tutorial,
            SessionState.CALIBRATION_TUTORIAL: self._start_hr_baseline,
            SessionState.BASELINE_COMPLETE: self._start_hrv_tutorial,
            SessionState.HRV_TUTORIAL: self._start_hrv_calibration,
            SessionState.CALIBRATION_COMPLETE: self._start_therapy,
        }

        handler = transitions.get(self._state)
        if handler:
            await handler()

    async def _skip_tutorial(self):
        """Skip the current tutorial phase."""
        if self._state == SessionState.CALIBRATION_TUTORIAL:
            await self._ws.send_to_headset({
                "type": "command",
                "action": "skip_tutorial",
            })
            await self._start_hr_baseline()
        elif self._state == SessionState.HRV_TUTORIAL:
            await self._ws.send_to_headset({
                "type": "command",
                "action": "skip_tutorial",
            })
            await self._start_hrv_calibration()

    # ── Phase Starters ──────────────────────────────────────────────

    async def _start_calibration_tutorial(self):
        await self._set_state(SessionState.CALIBRATION_TUTORIAL)
        await self._ws.send_to_headset({
            "type": "command",
            "action": "play_calibration_tutorial",
        })

    async def _start_hr_baseline(self):
        self._baseline_hr_values = []
        await self._set_state(SessionState.HR_BASELINE)
        await self._ws.send_to_headset({
            "type": "command",
            "action": "start_hr_baseline",
        })
        await self._start_timer(BASELINE_DURATION, self._on_baseline_complete)

    async def _on_baseline_complete(self):
        """Called when the 90-second baseline period ends."""
        self._baseline_mean = compute_baseline_hr(self._baseline_hr_values)
        self._data.set_baseline_result(self._baseline_mean)

        await self._ws.send_to_panel({
            "type": "baseline_result",
            "mean_hr": round(self._baseline_mean, 1),
            "sample_count": len(self._baseline_hr_values),
        })
        await self._ws.send_to_headset({
            "type": "baseline_result",
            "mean_hr": round(self._baseline_mean, 1),
        })
        await self._set_state(SessionState.BASELINE_COMPLETE)

    async def _start_hrv_tutorial(self):
        await self._set_state(SessionState.HRV_TUTORIAL)
        await self._ws.send_to_headset({
            "type": "command",
            "action": "play_hrv_tutorial",
        })

    async def _start_hrv_calibration(self):
        self._current_segment_index = 0
        self._hrv_segments = {}
        await self._set_state(SessionState.HRV_CALIBRATION)
        await self._run_hrv_segments()

    async def _run_hrv_segments(self):
        """Run through all 5 paced breathing segments sequentially."""
        for i, rate in enumerate(BREATHING_RATES):
            self._current_segment_index = i
            self._segment_rr = []

            # Tell headset to display this breathing rate
            await self._ws.send_to_headset({
                "type": "command",
                "action": "start_hrv_calibration",
                "breathing_rate": rate,
                "segment": i + 1,
                "total_segments": len(BREATHING_RATES),
            })

            # Update panel timer
            total_remaining = (len(BREATHING_RATES) - i) * SEGMENT_DURATION
            await self._ws.send_to_panel({
                "type": "hrv_segment",
                "breathing_rate": rate,
                "segment": i + 1,
                "total_segments": len(BREATHING_RATES),
            })

            # Wait for segment duration with countdown
            await self._run_countdown(SEGMENT_DURATION,
                                      total_elapsed_offset=i * SEGMENT_DURATION,
                                      total_duration=len(BREATHING_RATES) * SEGMENT_DURATION)

            # Store segment data
            self._hrv_segments[rate] = list(self._segment_rr)
            self._data.set_hrv_segment(rate, list(self._segment_rr))

        # All segments complete — compute resonant frequency
        await self._on_hrv_complete()

    async def _on_hrv_complete(self):
        """Called when all HRV calibration segments are complete."""
        self._resonant_frequency, self._hrv_amplitudes = compute_resonant_frequency(
            self._hrv_segments
        )
        self._data.set_resonant_frequency(self._resonant_frequency, self._hrv_amplitudes)

        await self._ws.send_to_panel({
            "type": "resonant_result",
            "frequency": self._resonant_frequency,
            "amplitudes": {str(k): round(v, 2) for k, v in self._hrv_amplitudes.items()},
        })
        await self._ws.send_to_headset({
            "type": "resonant_result",
            "frequency": self._resonant_frequency,
        })
        await self._set_state(SessionState.CALIBRATION_COMPLETE)

    async def _start_therapy(self):
        await self._set_state(SessionState.THERAPY)
        await self._ws.send_to_headset({
            "type": "command",
            "action": "start_therapy",
            "resonant_frequency": self._resonant_frequency,
            "baseline_hr": round(self._baseline_mean, 1) if self._baseline_mean else 0,
        })
        # Therapy runs indefinitely until diagnost stops it
        # Start an open-ended timer for display purposes
        self._elapsed = 0
        self._total_duration = 0  # 0 = no limit
        self._timer_task = asyncio.create_task(self._therapy_timer())

    async def _therapy_timer(self):
        """Open-ended timer that counts up during therapy."""
        try:
            while self._state == SessionState.THERAPY:
                await asyncio.sleep(1)
                self._elapsed += 1
                await self._ws.send_to_panel({
                    "type": "state",
                    "state": SessionState.THERAPY.value,
                    "elapsed": self._elapsed,
                    "total": 0,
                })
        except asyncio.CancelledError:
            pass

    async def _stop_session(self):
        """Stop the current session, save data, and reset."""
        # Cancel any running timer
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            self._timer_task = None

        # Stop streaming
        await self._polar.stop_streaming()

        # Tell headset
        await self._ws.send_to_headset({
            "type": "command",
            "action": "session_complete",
        })

        # Save data
        filepath = self._data.save()
        save_msg = str(filepath) if filepath else "Failed to save"

        await self._set_state(SessionState.COMPLETE)
        await self._ws.send_to_panel({
            "type": "session_complete",
            "file": save_msg,
        })

        # Reset for next session
        self._reset()

    def _reset(self):
        """Reset all internal state for a new session."""
        self._baseline_hr_values = []
        self._baseline_mean = None
        self._hrv_segments = {}
        self._segment_rr = []
        self._resonant_frequency = None
        self._hrv_amplitudes = {}
        self._all_rr = []
        self._elapsed = 0
        self._total_duration = 0
        self._data = DataStore()

    # ── Timer Utilities ─────────────────────────────────────────────

    async def _start_timer(self, duration: int, on_complete):
        """Start a countdown timer and call on_complete when finished."""
        self._elapsed = 0
        self._total_duration = duration

        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

        self._timer_task = asyncio.create_task(
            self._run_timer(duration, on_complete)
        )

    async def _run_timer(self, duration: int, on_complete):
        """Run a countdown, sending elapsed/total updates each second."""
        try:
            for second in range(1, duration + 1):
                await asyncio.sleep(1)
                self._elapsed = second
                await self._ws.send_to_panel({
                    "type": "state",
                    "state": self._state.value,
                    "elapsed": second,
                    "total": duration,
                })
            await on_complete()
        except asyncio.CancelledError:
            logger.info("Timer cancelled")

    async def _run_countdown(self, duration: int, total_elapsed_offset: int = 0,
                              total_duration: int = 0):
        """Run a blocking countdown for a segment within HRV calibration."""
        for second in range(1, duration + 1):
            await asyncio.sleep(1)
            elapsed = total_elapsed_offset + second
            await self._ws.send_to_panel({
                "type": "state",
                "state": self._state.value,
                "elapsed": elapsed,
                "total": total_duration,
            })

    async def handle_headset_message(self, message: dict):
        """Handle a message from the Unity headset."""
        msg_type = message.get("type")
        action = message.get("action")

        if msg_type == "status" and action == "headset_ready":
            await self._ws.send_to_panel({
                "type": "connection_status",
                "polar": self._polar.connected,
                "headset": True,
            })
        elif msg_type == "status" and action == "tutorial_complete":
            # Auto-advance when headset signals tutorial is done
            if self._state in (SessionState.CALIBRATION_TUTORIAL, SessionState.HRV_TUTORIAL):
                logger.info(f"Headset reported {self._state.value} is complete. Auto-advancing.")
                await self._advance()
