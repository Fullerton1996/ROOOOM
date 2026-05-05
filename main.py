import asyncio
import os
import signal
import sys
import time

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from audio.capture import start_capture
from audio.features import extract
from mood.classifier import classify
from mood.config import init as init_config
from session import logger as session_log
from spotify import player as spotify
from web.server import app, broadcast_mood, set_end_session_callback

_session_name = os.environ.get("SESSION_NAME", "Read the Room")
_current_mood: str = "arrival"


async def _end_session() -> None:
    print("\n[session] ending session...")
    track_uris = session_log.export_uris()
    tracks = session_log.get_all_tracks()

    print(f"[session] {len(track_uris)} unique tracks played")
    for t in tracks:
        print(f"  {t.artist} — {t.track_name}  [{t.mood}]")

    if not track_uris:
        print("[session] no tracks to save")
        return

    try:
        playlist_url = spotify.create_session_playlist(_session_name, track_uris)
        print(f"[session] playlist created: {playlist_url}")
    except Exception as e:
        print(f"[session] failed to create playlist: {e}")
        return

    # Notifications are opt-in — populate these lists via your own config/UI
    sms_numbers: list[str] = []
    email_addresses: list[str] = []

    if sms_numbers:
        try:
            from notify.sms import send_playlist_link
            send_playlist_link(sms_numbers, playlist_url, _session_name)
        except Exception as e:
            print(f"[notify] sms failed: {e}")

    if email_addresses:
        try:
            from notify.email import send_playlist_link
            send_playlist_link(email_addresses, playlist_url, _session_name)
        except Exception as e:
            print(f"[notify] email failed: {e}")


async def _mood_loop(audio_queue: asyncio.Queue) -> None:
    global _current_mood

    while True:
        try:
            raw_audio = await asyncio.wait_for(audio_queue.get(), timeout=10.0)
        except asyncio.TimeoutError:
            print("[main] waiting for audio...")
            continue

        vector = extract(raw_audio)
        del raw_audio  # never persisted

        now = time.time()
        mood = classify(vector, now)

        vector_dict = {
            "energy": vector.energy,
            "warmth": vector.warmth,
            "density": vector.density,
            "laughter_rate": vector.laughter_rate,
        }

        print(
            f"[{time.strftime('%H:%M:%S')}] "
            f"energy={vector.energy:.2f} warmth={vector.warmth:.2f} "
            f"density={vector.density:.2f} laughter={vector.laughter_rate:.2f} "
            f"→ {mood}"
        )

        # Always broadcast — browser handles mood_change and initiates crossfade
        # which then sends request_playlist_switch back to trigger the actual track change
        await broadcast_mood(mood, vector_dict)
        _current_mood = mood


def _find_ssl_certs() -> tuple[str, str] | None:
    # Look for mkcert-generated certs in the project root
    cert = Path("localhost.pem")
    key = Path("localhost-key.pem")
    if cert.exists() and key.exists():
        return str(cert), str(key)
    return None


async def main() -> None:
    init_config()
    set_end_session_callback(_end_session)

    from web.server import set_playlist_switch_callback, set_track_log_callback
    from session import logger as session_log

    async def _do_playlist_switch(mood: str) -> None:
        from mood.config import get_config
        cfg = get_config()
        playlist_uri = cfg.get("moods", {}).get(mood, {}).get("playlist_uri", "")
        if playlist_uri and "FILL_ME" not in playlist_uri:
            try:
                device_id = spotify.get_active_device_id()
                if device_id:
                    track_uri = spotify.play_next_from_playlist(device_id, playlist_uri)
                    if track_uri:
                        print(f"[spotify] ▶ {track_uri} ({mood})")
            except Exception as e:
                print(f"[spotify] playback error: {e}")

    set_playlist_switch_callback(_do_playlist_switch)
    set_track_log_callback(session_log.log_track)

    loop = asyncio.get_running_loop()
    audio_queue = start_capture(loop)

    ssl_certs = _find_ssl_certs()
    protocol = "https" if ssl_certs else "http"
    print(f"[main] session: {_session_name}")
    print("[main] audio capture started — listening...")
    print(f"[main] web interface: {protocol}://localhost:8000")
    if not ssl_certs:
        print("[main] tip: run `mkcert localhost` to enable HTTPS (required for Spotify on some browsers)")
    print("[main] Ctrl+C to end session and create playlist\n")

    shutdown_event = asyncio.Event()

    def _on_sigint(*_) -> None:
        print("\n[main] SIGINT received")
        shutdown_event.set()

    signal.signal(signal.SIGINT, _on_sigint)

    ssl_kwargs = {"ssl_certfile": ssl_certs[0], "ssl_keyfile": ssl_certs[1]} if ssl_certs else {}
    server_config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",
        **ssl_kwargs,
    )
    server = uvicorn.Server(server_config)

    mood_task = asyncio.create_task(_mood_loop(audio_queue))
    server_task = asyncio.create_task(server.serve())

    await shutdown_event.wait()

    mood_task.cancel()
    server.should_exit = True

    await asyncio.gather(mood_task, server_task, return_exceptions=True)
    await _end_session()
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
