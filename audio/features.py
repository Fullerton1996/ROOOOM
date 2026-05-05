from collections import deque
from dataclasses import dataclass

import librosa
import numpy as np

SAMPLE_RATE = 16000

# dB floor/ceiling tuned for a typical room (ambient ~-40dB, loud room ~-10dB)
ENERGY_DB_FLOOR = -40.0
ENERGY_DB_CEILING = -10.0

# Spectral centroid range for a room: ~200Hz (warm bass-heavy) to ~4000Hz (bright/speech-dense)
CENTROID_LOW_HZ = 200.0
CENTROID_HIGH_HZ = 4000.0

_SMOOTHING_WINDOW = 3
_energy_history: deque[float] = deque(maxlen=_SMOOTHING_WINDOW)
_warmth_history: deque[float] = deque(maxlen=_SMOOTHING_WINDOW)
_density_history: deque[float] = deque(maxlen=_SMOOTHING_WINDOW)
_laughter_history: deque[float] = deque(maxlen=_SMOOTHING_WINDOW)


@dataclass
class EmotionVector:
    energy: float
    warmth: float
    density: float
    laughter_rate: float


def _smooth(history: deque[float], value: float) -> float:
    history.append(value)
    return float(np.mean(history))


def _compute_energy(audio: np.ndarray) -> float:
    rms = np.sqrt(np.mean(audio**2))
    if rms < 1e-10:
        return 0.0
    db = 20.0 * np.log10(rms)
    normalized = (db - ENERGY_DB_FLOOR) / (ENERGY_DB_CEILING - ENERGY_DB_FLOOR)
    return float(np.clip(normalized, 0.0, 1.0))


def _compute_warmth(audio: np.ndarray) -> float:
    centroid = librosa.feature.spectral_centroid(y=audio, sr=SAMPLE_RATE)
    mean_centroid = float(np.mean(centroid))
    # Invert: low centroid (warm/bassy) → high warmth score
    normalized = (mean_centroid - CENTROID_LOW_HZ) / (CENTROID_HIGH_HZ - CENTROID_LOW_HZ)
    normalized = float(np.clip(normalized, 0.0, 1.0))
    return 1.0 - normalized


def _compute_density(audio: np.ndarray) -> float:
    # ZCR variance across short frames — higher variance means more overlapping speech patterns
    zcr = librosa.feature.zero_crossing_rate(audio, frame_length=512, hop_length=256)
    zcr_variance = float(np.var(zcr))
    # Empirically: quiet room ~0.0001, busy room ~0.005+
    normalized = zcr_variance / 0.005
    return float(np.clip(normalized, 0.0, 1.0))


def _compute_laughter_rate(audio: np.ndarray) -> float:
    # Split audio into 250ms sub-windows, compute RMS per sub-window,
    # then measure variance of that envelope — laughter produces rhythmic bursts
    sub_window_size = SAMPLE_RATE // 4  # 250ms
    n_sub = len(audio) // sub_window_size
    if n_sub < 2:
        return 0.0
    rms_envelope = np.array([
        np.sqrt(np.mean(audio[i * sub_window_size:(i + 1) * sub_window_size] ** 2))
        for i in range(n_sub)
    ])
    envelope_variance = float(np.var(rms_envelope))
    # Empirically: laughter variance is typically 0.001–0.01 in normalized float32 audio
    normalized = envelope_variance / 0.005
    return float(np.clip(normalized, 0.0, 1.0))


def extract(audio: np.ndarray) -> EmotionVector:
    energy = _smooth(_energy_history, _compute_energy(audio))
    warmth = _smooth(_warmth_history, _compute_warmth(audio))
    density = _smooth(_density_history, _compute_density(audio))
    laughter_rate = _smooth(_laughter_history, _compute_laughter_rate(audio))
    return EmotionVector(
        energy=round(energy, 4),
        warmth=round(warmth, 4),
        density=round(density, 4),
        laughter_rate=round(laughter_rate, 4),
    )
