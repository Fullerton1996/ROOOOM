import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

_connected_clients: list[WebSocket] = []
_current_mood: str = "arrival"
_current_vector: dict[str, float] = {}
_session_start: float = time.time()
_track_count: int = 0

_end_session_callback: Optional[Callable] = None
_playlist_switch_callback: Optional[Callable] = None  # set by main.py
_track_log_callback: Optional[Callable] = None         # set by main.py


def set_end_session_callback(fn: Callable) -> None:
    global _end_session_callback
    _end_session_callback = fn


def set_playlist_switch_callback(fn: Callable) -> None:
    global _playlist_switch_callback
    _playlist_switch_callback = fn


def set_track_log_callback(fn: Callable) -> None:
    global _track_log_callback
    _track_log_callback = fn


async def broadcast_mood(mood: str, vector: dict[str, float]) -> None:
    global _current_mood, _current_vector
    _current_mood = mood
    _current_vector = vector
    payload = {"type": "mood_change", "mood": mood, "vector": vector}
    dead: list[WebSocket] = []
    for ws in _connected_clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connected_clients.remove(ws)


async def _handle_client_message(msg: dict) -> None:
    msg_type = msg.get("type")

    if msg_type == "track_playing":
        # Browser reports what's now playing — log it
        if _track_log_callback:
            global _track_count
            _track_count += 1
            _track_log_callback(
                track_uri=msg.get("uri", ""),
                track_name=msg.get("name", ""),
                artist=msg.get("artist", ""),
                mood=_current_mood,
            )

    elif msg_type == "request_playlist_switch":
        # Browser has faded out and is ready for the new track
        mood = msg.get("mood", _current_mood)
        if _playlist_switch_callback:
            await _playlist_switch_callback(mood)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _connected_clients.append(ws)
    await ws.send_json({
        "type": "mood_change",
        "mood": _current_mood,
        "vector": _current_vector,
    })
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                await _handle_client_message(msg)
            except (json.JSONDecodeError, Exception):
                pass
    except WebSocketDisconnect:
        if ws in _connected_clients:
            _connected_clients.remove(ws)


@app.get("/token")
async def spotify_token() -> JSONResponse:
    # Serve the current Spotify access token to the browser so player.js
    # doesn't need it hardcoded — fetched once on page load.
    try:
        from spotify.player import get_client
        token_info = get_client().auth_manager.get_access_token(as_dict=True)
        return JSONResponse({"access_token": token_info["access_token"]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/session/end")
async def session_end() -> JSONResponse:
    if _end_session_callback:
        asyncio.create_task(_end_session_callback())
    return JSONResponse({"status": "end_session_triggered"})


@app.get("/status")
async def status() -> JSONResponse:
    elapsed = time.time() - _session_start
    return JSONResponse({
        "mood": _current_mood,
        "vector": _current_vector,
        "session_duration_seconds": round(elapsed),
        "track_count": _track_count,
    })


_static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
