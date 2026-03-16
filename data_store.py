"""
Session data persistence for the HRV Biofeedback Control Panel.
Saves session data as timestamped JSON files.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path(__file__).parent / "sessions"


class DataStore:
    """Handles saving session data to timestamped JSON files."""

    def __init__(self):
        self._session_start: datetime | None = None
        self._hr_log: list[dict] = []
        self._rr_log: list[dict] = []
        self._baseline_hr_values: list[int] = []
        self._baseline_mean: float | None = None
        self._hrv_segments: dict[float, list[float]] = {}
        self._resonant_frequency: float | None = None
        self._therapy_data: list[dict] = []
        self._events: list[dict] = []

    def start_session(self):
        """Initialize a new session."""
        self._session_start = datetime.now()
        self._hr_log = []
        self._rr_log = []
        self._baseline_hr_values = []
        self._baseline_mean = None
        self._hrv_segments = {}
        self._resonant_frequency = None
        self._therapy_data = []
        self._events = []
        self._log_event("session_started")

    def log_hr(self, heartrate: int, rr_intervals: list[float]):
        """Log an HR data point with timestamp."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "heartrate": heartrate,
            "rr_intervals": rr_intervals,
        }
        self._hr_log.append(entry)

    def add_baseline_hr(self, heartrate: int):
        """Add an HR value to the baseline collection."""
        self._baseline_hr_values.append(heartrate)

    def set_baseline_result(self, mean_hr: float):
        """Store the calculated baseline mean HR."""
        self._baseline_mean = mean_hr
        self._log_event("baseline_complete", {"mean_hr": mean_hr})

    def set_hrv_segment(self, breathing_rate: float, rr_intervals: list[float]):
        """Store RR intervals for one paced-breathing segment."""
        self._hrv_segments[breathing_rate] = rr_intervals

    def set_resonant_frequency(self, frequency: float, amplitudes: dict[float, float]):
        """Store the determined resonant frequency."""
        self._resonant_frequency = frequency
        self._log_event("resonant_frequency_found", {
            "frequency": frequency,
            "amplitudes": {str(k): v for k, v in amplitudes.items()},
        })

    def log_therapy_data(self, heartrate: int, rr_intervals: list[float]):
        """Log therapy session data point."""
        self._therapy_data.append({
            "timestamp": datetime.now().isoformat(),
            "heartrate": heartrate,
            "rr_intervals": rr_intervals,
        })

    def _log_event(self, event_type: str, data: dict | None = None):
        """Log a session event."""
        self._events.append({
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "data": data or {},
        })

    def log_state_change(self, new_state: str):
        """Log a state transition."""
        self._log_event("state_change", {"state": new_state})

    def save(self) -> Path | None:
        """Save the session data to a timestamped JSON file.

        Returns:
            The path to the saved file, or None if no session was active.
        """
        if not self._session_start:
            logger.warning("No active session to save")
            return None

        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = self._session_start.strftime("%Y%m%d_%H%M%S")
        filename = f"session_{timestamp}.json"
        filepath = SESSIONS_DIR / filename

        session_data = {
            "session_start": self._session_start.isoformat(),
            "session_end": datetime.now().isoformat(),
            "baseline": {
                "hr_values": self._baseline_hr_values,
                "mean_hr": self._baseline_mean,
            },
            "hrv_calibration": {
                "segments": {
                    str(rate): intervals
                    for rate, intervals in self._hrv_segments.items()
                },
                "resonant_frequency": self._resonant_frequency,
            },
            "therapy_data": self._therapy_data,
            "full_hr_log": self._hr_log,
            "events": self._events,
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Session saved to {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return None
