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
        normalized = {
            "fit": fit,
            "loop": bool(payload.get("loop", True)),
            "pad": bool(payload.get("pad", False)),
            "trim_start_sec": trim_start_sec,
            "preserve_source_audio": bool(payload.get("preserve_source_audio", False)),
        }
        # Source-window controls come from a selected local asset.  They are
        # distinct from timeline trim and must survive Director apply so both
        # FFmpeg and CapCut read the same original bytes.
        if "in_sec" in payload:
            in_sec = float(payload["in_sec"])
            if in_sec < 0:
                raise ValueError("B-roll in_sec must not be negative.")
            normalized["in_sec"] = in_sec
        if "out_sec" in payload:
            out_sec = float(payload["out_sec"])
            if out_sec <= float(normalized.get("in_sec", 0.0)):
                raise ValueError("B-roll out_sec must be after in_sec.")
            normalized["out_sec"] = out_sec
        return normalized
    raise ValueError(f"Unsupported media control kind: {media_kind}")
