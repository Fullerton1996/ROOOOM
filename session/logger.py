import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PlayedTrack:
    track_uri: str
    track_name: str
    artist: str
    mood: str
    timestamp: float = field(default_factory=time.time)


_played: list[PlayedTrack] = []
_seen_uris: set[str] = set()


def log_track(
    track_uri: str,
    track_name: str,
    artist: str,
    mood: str,
    timestamp: Optional[float] = None,
) -> None:
    if track_uri in _seen_uris:
        return
    _seen_uris.add(track_uri)
    _played.append(PlayedTrack(
        track_uri=track_uri,
        track_name=track_name,
        artist=artist,
        mood=mood,
        timestamp=timestamp or time.time(),
    ))


def get_all_tracks() -> list[PlayedTrack]:
    return list(_played)


def export_uris() -> list[str]:
    return [t.track_uri for t in _played]


def track_count() -> int:
    return len(_played)
