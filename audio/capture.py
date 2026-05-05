import asyncio
import os
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
WINDOW_SECONDS = 5
WINDOW_FRAMES = SAMPLE_RATE * WINDOW_SECONDS


def _capture_thread(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, device: Optional[int]) -> None:
    buffer: list[np.ndarray] = []
    frames_collected = 0

    def callback(indata: np.ndarray, frames: int, time_info, status) -> None:
        nonlocal frames_collected
        if status:
            print(f"[audio] sounddevice status: {status}")

        chunk = indata[:, 0].copy()
        buffer.append(chunk)
        frames_collected += frames

        if frames_collected >= WINDOW_FRAMES:
            window = np.concatenate(buffer[:])
            # Trim to exactly WINDOW_FRAMES in case of overshoot
            window = window[:WINDOW_FRAMES].astype(np.float32)
            # Schedule onto the event loop — buffer is discarded after this
            buffer.clear()
            frames_collected = 0
            asyncio.run_coroutine_threadsafe(queue.put(window), loop)

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=device,
        blocksize=SAMPLE_RATE // 4,  # 250ms blocks for low latency callback
        callback=callback,
    ):
        # Block until the stop event is set via queue sentinel
        threading.Event().wait()


def start_capture(loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
    device_env = os.environ.get("MIC_DEVICE_INDEX", "").strip()
    device: Optional[int] = int(device_env) if device_env else None

    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    t = threading.Thread(
        target=_capture_thread,
        args=(queue, loop, device),
        daemon=True,
    )
    t.start()
    return queue
