"""
FastAPI application for the HRV Biofeedback Control Panel.
Serves the control panel UI and provides WebSocket endpoints.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from polar_manager import PolarManager
from ws_manager import WSManager
from session_manager import SessionManager
from beacon_manager import BeaconManager

# ── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App Setup ───────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

app = FastAPI(title="HRV Biofeedback Control Panel")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# ── Shared Instances ────────────────────────────────────────────
ws_manager = WSManager()
polar_manager = PolarManager()
beacon_manager = BeaconManager(ws_port=8000)
session_manager = SessionManager(ws=ws_manager, polar=polar_manager, beacon=beacon_manager)


# ── Routes ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the control panel page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/ws/panel")
async def ws_panel(websocket: WebSocket):
    """WebSocket endpoint for the diagnost's control panel browser."""
    await ws_manager.connect_panel(websocket)

    # Send initial state
    await ws_manager.send_to_panel({
        "type": "state",
        "state": session_manager.state.value,
        "elapsed": 0,
        "total": 0,
    })
    await ws_manager.send_to_panel({
        "type": "connection_status",
        "polar": polar_manager.connected,
        "headset": ws_manager.headset_connected,
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from panel: %s", raw)
                continue

            if message.get("type") == "action":
                action = message.get("action", "")
                await session_manager.handle_action(action)
    except WebSocketDisconnect:
        ws_manager.disconnect_panel()
        logger.info("Panel WebSocket disconnected")


@app.websocket("/ws/headset")
async def ws_headset(websocket: WebSocket):
    """WebSocket endpoint for the Unity VR headset."""
    await ws_manager.connect_headset(websocket)

    # Notify session manager — this stops the beacon and advances state
    await session_manager.on_headset_connected()

    # Notify panel that headset is connected
    await ws_manager.send_to_panel({
        "type": "connection_status",
        "polar": polar_manager.connected,
        "headset": True,
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from headset: %s", raw)
                continue

            await session_manager.handle_headset_message(message)
    except WebSocketDisconnect:
        ws_manager.disconnect_headset()
        # Notify panel that headset disconnected
        await ws_manager.send_to_panel({
            "type": "connection_status",
            "polar": polar_manager.connected,
            "headset": False,
        })
        logger.info("Headset WebSocket disconnected")
