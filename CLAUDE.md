# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
python main.py
```

Launches the FastAPI server via uvicorn at `http://0.0.0.0:8000`. The virtual environment is in `.venv/` (Python 3.14).

**Manual test utilities** (not a test suite — no automated tests exist):
- `python test_udp.py` — verify UDP broadcast works
- `python listen_beacon.py` — verify server beacon is broadcasting on UDP :15000

## Architecture

This is a **HRV biofeedback control panel** for clinicians running respiratory therapy sessions. It bridges a **Polar H10** heart rate monitor (BLE) with a **Unity VR headset** (WebSocket), with a browser-based diagnostic UI served by FastAPI.

```
Browser Control Panel
        │ WebSocket /ws/panel
        ▼
   app.py (FastAPI)
        │
        ▼
session_manager.py  ──► polar_manager.py  (BLE → Polar H10)
        │           ──► ws_manager.py     (routes msgs to panel/headset)
        │           ──► beacon_manager.py (UDP :15000 → headset discovery)
        │           ──► hrv_analysis.py   (NumPy HRV calculations)
        │           ──► data_store.py     (saves sessions/*.json)
        │
        └──► WebSocket /ws/headset → Unity VR App
```

### Session State Machine

`session_manager.py` drives a 14-state workflow:

```
IDLE → CONNECTING_POLAR → CONNECTING_HEADSET → READY
→ CALIBRATION_TUTORIAL → HR_BASELINE (90s) → BASELINE_COMPLETE
→ HRV_TUTORIAL → HRV_CALIBRATION (5 rates × 12s) → CALIBRATION_COMPLETE
→ THERAPY → COMPLETE
```

- **HR Baseline**: 90 seconds of resting HR collection
- **HRV Calibration**: 5 paced breathing rates (7, 6.5, 6, 5.5, 5 bpm), 12 seconds each — finds the "resonant frequency" (breathing rate with highest HRV amplitude)
- **Therapy**: live HR/RR intervals streamed to VR headset indefinitely

### WebSocket Message Protocol

**Panel → Server** (user actions):
```json
{ "type": "action", "action": "connect_polar" | "next_step" | "skip_tutorial" | "stop_session" | "move_breathing_ball" | "show_fireflies" | "hide_fireflies" | "start_birds_flyover" }
```

**Server → Panel**:
```json
{ "type": "state", "state": "<STATE>", "elapsed": 0, "total": 90 }
{ "type": "hr_update", "heartrate": 72, "rr_intervals": [833], "rmssd": 45.2, "sdnn": 38.1, "timestamp": "..." }
{ "type": "resonant_result", "frequency": 6.0, "amplitudes": { "7.0": 8.2, ... } }
```

**Server → Headset**:
```json
{ "type": "command", "action": "start_therapy", "resonant_frequency": 6.0, "baseline_hr": 68 }
{ "type": "hr_data", "heartrate": 72, "rr_intervals": [833], "timestamp": "..." }
```

### VR Client Notes (see VR_UPDATES.md for full details)

- `move_breathing_ball` is a **no-op** — breathing pacer is now a UI ring
- `show_fireflies` / `hide_fireflies` are **ignored** — fireflies are client-driven (every 180s for 30s)
- `restart_therapy` resets the client state
- HRV color ring shifts based on RMSSD trend using `rr_intervals` from `hr_data` messages

### Key Constants (hardcoded in source)

| Constant | Value | File |
|---|---|---|
| `BREATHING_RATES` | `[7.0, 6.5, 6.0, 5.5, 5.0]` bpm | `session_manager.py` |
| `SEGMENT_DURATION` | 12 seconds | `session_manager.py` |
| `BASELINE_DURATION` | 90 seconds | `session_manager.py` |
| `BEACON_PORT` | 15000 | `beacon_manager.py` |

### Data Output

Sessions are saved to `./sessions/session_<YYYYMMDD_HHMMSS>.json` on session end, containing baseline HR values, HRV calibration segments per breathing rate, full therapy HR stream, and state transition events.
