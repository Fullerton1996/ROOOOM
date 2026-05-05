import time
from typing import Optional

from audio.features import EmotionVector
from mood.config import get_config

_current_mood: Optional[str] = None
_candidate_mood: Optional[str] = None
_candidate_since: float = 0.0


def _match_mood(name: str, cfg: dict, vector: EmotionVector) -> bool:
    energy_ok = vector.energy <= cfg.get("energy_max", 1.0)
    density_ok = vector.density <= cfg.get("density_max", 1.0)
    warmth_ok = vector.warmth >= cfg.get("warmth_min", 0.0)
    return energy_ok and density_ok and warmth_ok


def classify(vector: EmotionVector, now: Optional[float] = None) -> str:
    global _current_mood, _candidate_mood, _candidate_since

    if now is None:
        now = time.time()

    config = get_config()
    moods = config.get("moods", {})
    default_hysteresis = float(config.get("hysteresis_seconds", 45))

    # If we're in afterglow and it's sticky, only leave if energy spikes hard
    if _current_mood == "afterglow":
        afterglow_cfg = moods.get("afterglow", {})
        if afterglow_cfg.get("sticky", False):
            exit_threshold = float(afterglow_cfg.get("sticky_exit_energy", 0.5))
            if vector.energy < exit_threshold:
                return "afterglow"

    # Find all matching moods, pick lowest priority
    candidates = []
    for name, cfg in moods.items():
        if _match_mood(name, cfg, vector):
            candidates.append((cfg.get("priority", 99), name))

    if not candidates:
        if _current_mood:
            return _current_mood
        sorted_moods = sorted(moods.items(), key=lambda x: x[1].get("priority", 99))
        _current_mood = sorted_moods[0][0] if sorted_moods else "arrival"
        return _current_mood

    candidates.sort()
    best_mood = candidates[0][1]

    if best_mood == _current_mood:
        _candidate_mood = None
        _candidate_since = 0.0
        return _current_mood

    # Track how long the candidate has been stable
    if best_mood != _candidate_mood:
        _candidate_mood = best_mood
        _candidate_since = now

    # Use per-mood hysteresis if defined, otherwise fall back to global
    mood_hysteresis = float(moods.get(best_mood, {}).get("hysteresis_seconds", default_hysteresis))

    stable_seconds = now - _candidate_since
    if stable_seconds >= mood_hysteresis:
        old_mood = _current_mood
        _current_mood = best_mood
        _candidate_mood = None
        _candidate_since = 0.0
        print(f"[mood] {old_mood} → {_current_mood} (stable for {stable_seconds:.0f}s)")

    return _current_mood if _current_mood else best_mood


def reset_session() -> None:
    global _current_mood, _candidate_mood, _candidate_since
    _current_mood = None
    _candidate_mood = None
    _candidate_since = 0.0
