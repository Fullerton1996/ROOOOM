import os
import random
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyPKCE

SCOPES = (
    "streaming "
    "user-read-email "
    "user-read-private "
    "user-read-playback-state "
    "user-modify-playback-state "
    "playlist-modify-public "
    "playlist-modify-private"
)

_client: Optional[spotipy.Spotify] = None
_playlist_state: dict[str, dict] = {}  # uri → {tracks: [...], index: int}


def get_client() -> spotipy.Spotify:
    global _client
    if _client is None:
        auth = SpotifyPKCE(
            client_id=os.environ["SPOTIFY_CLIENT_ID"],
            redirect_uri=os.environ["SPOTIFY_REDIRECT_URI"],
            scope=SCOPES,
        )
        _client = spotipy.Spotify(auth_manager=auth)
    return _client


def _to_playlist_id(uri_or_url: str) -> str:
    # Accept both spotify:playlist:ID and https://open.spotify.com/playlist/ID?...
    if uri_or_url.startswith("http"):
        return uri_or_url.split("/playlist/")[-1].split("?")[0]
    return uri_or_url.split(":")[-1]


def get_playlist_tracks(playlist_uri: str) -> list[str]:
    sp = get_client()
    playlist_id = _to_playlist_id(playlist_uri)
    results = sp.playlist_tracks(playlist_id, fields="items(track(uri)),next")
    uris: list[str] = []
    while results:
        uris += [item["track"]["uri"] for item in results["items"] if item["track"]]
        results = sp.next(results) if results.get("next") else None

    if playlist_uri not in _playlist_state:
        shuffled = uris[:]
        random.shuffle(shuffled)
        _playlist_state[playlist_uri] = {"tracks": shuffled, "index": 0}
    return uris


def _next_track_uri(playlist_uri: str) -> Optional[str]:
    state = _playlist_state.get(playlist_uri)
    if not state or not state["tracks"]:
        return None
    track = state["tracks"][state["index"] % len(state["tracks"])]
    state["index"] += 1
    # Re-shuffle once we've cycled through everything
    if state["index"] >= len(state["tracks"]):
        random.shuffle(state["tracks"])
        state["index"] = 0
    return track


def play_track(device_id: str, track_uri: str) -> None:
    get_client().start_playback(device_id=device_id, uris=[track_uri])


def play_next_from_playlist(device_id: str, playlist_uri: str) -> Optional[str]:
    get_playlist_tracks(playlist_uri)
    track_uri = _next_track_uri(playlist_uri)
    if track_uri:
        play_track(device_id, track_uri)
    return track_uri


def set_volume(device_id: str, volume_percent: int) -> None:
    get_client().volume(volume_percent, device_id=device_id)


def queue_track(device_id: str, track_uri: str) -> None:
    get_client().add_to_queue(track_uri, device_id=device_id)


def create_session_playlist(name: str, track_uris: list[str]) -> str:
    sp = get_client()
    user_id = sp.current_user()["id"]
    playlist = sp.user_playlist_create(user_id, name, public=False)
    playlist_id = playlist["id"]
    # Spotify allows max 100 tracks per request
    for i in range(0, len(track_uris), 100):
        sp.playlist_add_items(playlist_id, track_uris[i:i + 100])
    return f"https://open.spotify.com/playlist/{playlist_id}"


def get_active_device_id() -> Optional[str]:
    devices = get_client().devices()
    device_name = os.environ.get("SPOTIFY_DEVICE_NAME", "Read the Room")
    for d in devices.get("devices", []):
        if d["name"] == device_name:
            return d["id"]
    # Fall back to any active device
    for d in devices.get("devices", []):
        if d["is_active"]:
            return d["id"]
    return None
