from __future__ import annotations

from typing import Any


def normalize_media_controls(
    controls: object,
    *,
    media_kind: str,
    duration_sec: float,
) -> dict[str, Any]:
    payload = controls if isinstance(controls, dict) else {}
    if duration_sec <= 0:
        raise ValueError("Media control duration must be positive.")
    if media_kind == "audio":
        gain_db = float(payload.get("gain_db", 0.0))
        fade_in_sec = float(payload.get("fade_in_sec", 0.0))
        fade_out_sec = float(payload.get("fade_out_sec", 0.0))
        if fade_in_sec < 0 or fade_out_sec < 0 or fade_in_sec + fade_out_sec > duration_sec:
            raise ValueError("Audio fade durations must fit within the clip duration.")
        return {
            "gain_db": gain_db,
            "fade_in_sec": fade_in_sec,
            "fade_out_sec": fade_out_sec,
            "ducking": bool(payload.get("ducking", False)),
        }
    if media_kind == "broll":
        fit = str(payload.get("fit", "fit")).strip().lower()
        if fit not in {"fit", "crop"}:
            raise ValueError("B-roll fit must be either 'fit' or 'crop'.")
        trim_start_sec = float(payload.get("trim_start_sec", 0.0))
        if trim_start_sec < 0:
            raise ValueError("B-roll trim_start_sec must not be negative.")
        return {
            "fit": fit,
            "loop": bool(payload.get("loop", True)),
            "pad": bool(payload.get("pad", False)),
            "trim_start_sec": trim_start_sec,
        }
    raise ValueError(f"Unsupported media control kind: {media_kind}")
