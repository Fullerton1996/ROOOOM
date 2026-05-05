import os
import threading
import time
from typing import Any

import yaml

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "moods.yaml")
_POLL_INTERVAL = 5.0

_lock = threading.Lock()
_config: dict[str, Any] = {}
_last_mtime: float = 0.0


def _load() -> dict[str, Any]:
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _poll_loop() -> None:
    global _config, _last_mtime
    while True:
        time.sleep(_POLL_INTERVAL)
        try:
            mtime = os.path.getmtime(_CONFIG_PATH)
            if mtime != _last_mtime:
                new_config = _load()
                with _lock:
                    _config = new_config
                    _last_mtime = mtime
                print("[config] moods.yaml reloaded")
        except Exception as e:
            print(f"[config] failed to reload moods.yaml: {e}")


def init() -> None:
    global _config, _last_mtime
    _config = _load()
    _last_mtime = os.path.getmtime(_CONFIG_PATH)
    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()


def get_config() -> dict[str, Any]:
    with _lock:
        return _config
