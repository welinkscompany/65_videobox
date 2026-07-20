"""Canonical, renderer-neutral representation of a timeline composition.

Both a final render and a revision-bound proxy must start here.  This module
does not resolve files or invoke ffmpeg: keeping it pure makes the range and
fingerprint fences independently testable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Iterable


COMPOSITION_VERSION = "videobox_composition_v1"
_SUPPORTED_TRACKS = frozenset({"narration", "broll", "bgm", "sfx", "overlay"})


def _number(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not isfinite(parsed):
        raise ValueError("composition_plan_invalid_number")
    return parsed


@dataclass(frozen=True, slots=True)
class CompositionItem:
    clip_id: str
    track_type: str
    asset_uri: str | None
    asset_id: str | None
    start_sec: float
    end_sec: float
    source_in_sec: float
    source_out_sec: float
    media_controls: dict[str, Any] = field(default_factory=dict)
    overlay_type: str | None = None
    overlay_payload: dict[str, Any] = field(default_factory=dict)

    def clipped(self, *, start_sec: float, end_sec: float) -> "CompositionItem | None":
        left, right = max(self.start_sec, start_sec), min(self.end_sec, end_sec)
        if right <= left:
            return None
        # Shift source only by the left-hand clipping amount.  The resulting
        # output is already zero based; callers must not apply another offset.
        source_start = self.source_in_sec + (left - self.start_sec)
        return CompositionItem(
            clip_id=self.clip_id, track_type=self.track_type, asset_uri=self.asset_uri, asset_id=self.asset_id,
            start_sec=left - start_sec, end_sec=right - start_sec,
            source_in_sec=source_start, source_out_sec=source_start + (right - left),
            media_controls=dict(self.media_controls), overlay_type=self.overlay_type,
            overlay_payload=dict(self.overlay_payload),
        )


@dataclass(frozen=True, slots=True)
class CaptionCue:
    start_sec: float
    end_sec: float
    text: str
    style: dict[str, Any] = field(default_factory=dict)
    segment_id: str | None = None

    def clipped(self, *, start_sec: float, end_sec: float) -> "CaptionCue | None":
        left, right = max(self.start_sec, start_sec), min(self.end_sec, end_sec)
        if right <= left:
            return None
        return CaptionCue(left - start_sec, right - start_sec, self.text, dict(self.style), self.segment_id)


@dataclass(frozen=True, slots=True)
class CompositionPlan:
    width: int
    height: int
    fps_num: int
    fps_den: int
    sample_aspect_ratio: str
    rotation: int
    items: tuple[CompositionItem, ...]
    captions: tuple[CaptionCue, ...] = ()
    export_overlays: tuple[dict[str, Any], ...] = ()
    version: str = COMPOSITION_VERSION

    @property
    def duration_sec(self) -> float:
        return max([item.end_sec for item in self.items] + [cue.end_sec for cue in self.captions] + [0.0])

    @classmethod
    def from_timeline(cls, *, timeline: dict[str, Any], captions: Iterable[dict[str, Any] | CaptionCue] = ()) -> "CompositionPlan":
        output = timeline.get("output") if isinstance(timeline.get("output"), dict) else {}
        raw_items: list[CompositionItem] = []
        for track in timeline.get("tracks", []):
            if not isinstance(track, dict):
                continue
            track_type = str(track.get("track_type") or "").strip().lower()
            if track_type not in _SUPPORTED_TRACKS:
                continue
            for index, raw in enumerate(track.get("clips", []) if isinstance(track.get("clips"), list) else []):
                if not isinstance(raw, dict):
                    continue
                start, end = _number(raw.get("start_sec")), _number(raw.get("end_sec"))
                if end <= start:
                    continue
                source_in = _number(raw.get("source_in_sec", raw.get("in_sec", 0.0)))
                source_out = _number(raw.get("source_out_sec", raw.get("out_sec", source_in + (end - start))))
                if source_out < source_in:
                    source_out = source_in + (end - start)
                raw_items.append(CompositionItem(
                    clip_id=str(raw.get("clip_id") or f"{track_type}-{index}"), track_type=track_type,
                    asset_uri=str(raw["asset_uri"]) if raw.get("asset_uri") is not None else None,
                    asset_id=str(raw["asset_id"]) if raw.get("asset_id") is not None else None,
                    start_sec=start, end_sec=end, source_in_sec=source_in, source_out_sec=source_out,
                    media_controls=dict(raw.get("media_controls") or {}) if isinstance(raw.get("media_controls"), dict) else {},
                    overlay_type=str(raw.get("overlay_type")) if raw.get("overlay_type") is not None else None,
                    overlay_payload=dict(raw.get("overlay_payload") or {}) if isinstance(raw.get("overlay_payload"), dict) else {},
                ))
        cues: list[CaptionCue] = []
        for raw in captions:
            if isinstance(raw, CaptionCue):
                cues.append(raw)
            elif isinstance(raw, dict):
                start, end = _number(raw.get("start_sec")), _number(raw.get("end_sec"))
                if end > start:
                    cues.append(CaptionCue(start, end, str(raw.get("text") or raw.get("caption_text") or ""), dict(raw.get("style") or {}) if isinstance(raw.get("style"), dict) else {}, str(raw["segment_id"]) if raw.get("segment_id") else None))
        overlays = tuple(
            dict(overlay)
            for overlay in timeline.get("export_overlays", [])
            if isinstance(overlay, dict) and _number(overlay.get("end_sec"), _number(overlay.get("start_sec"))) > _number(overlay.get("start_sec"))
        )
        return cls(
            width=max(1, int(_number(output.get("width") or timeline.get("video_width") or 1280))),
            height=max(1, int(_number(output.get("height") or timeline.get("video_height") or 720))),
            fps_num=max(1, int(_number(output.get("fps_num") or timeline.get("fps_num") or 30))),
            fps_den=max(1, int(_number(output.get("fps_den") or timeline.get("fps_den") or 1))),
            sample_aspect_ratio=str(output.get("sample_aspect_ratio") or timeline.get("sample_aspect_ratio") or "1:1"),
            rotation=int(output.get("rotation") or timeline.get("rotation") or 0),
            items=tuple(sorted(raw_items, key=lambda item: (item.start_sec, item.track_type, item.clip_id))),
            captions=tuple(sorted(cues, key=lambda cue: (cue.start_sec, cue.end_sec, cue.segment_id or ""))),
            export_overlays=overlays,
        )

    def for_range(self, *, start_sec: float, end_sec: float) -> "CompositionPlan":
        if not isfinite(float(start_sec)) or not isfinite(float(end_sec)) or start_sec < 0 or end_sec <= start_sec or end_sec > self.duration_sec:
            raise ValueError("composition_plan_invalid_range")
        overlays = []
        for overlay in self.export_overlays:
            left, right = max(_number(overlay.get("start_sec")), start_sec), min(_number(overlay.get("end_sec")), end_sec)
            if right > left:
                shifted = dict(overlay)
                shifted["start_sec"], shifted["end_sec"] = left - start_sec, right - start_sec
                overlays.append(shifted)
        return CompositionPlan(self.width, self.height, self.fps_num, self.fps_den, self.sample_aspect_ratio, self.rotation,
            tuple(item for source in self.items if (item := source.clipped(start_sec=start_sec, end_sec=end_sec)) is not None),
            tuple(cue for source in self.captions if (cue := source.clipped(start_sec=start_sec, end_sec=end_sec)) is not None),
            tuple(overlays), self.version)

    def canonical_dict(self) -> dict[str, Any]:
        return {"version": self.version, "canvas": {"width": self.width, "height": self.height, "fps_num": self.fps_num, "fps_den": self.fps_den, "sample_aspect_ratio": self.sample_aspect_ratio, "rotation": self.rotation}, "items": [asdict(item) for item in self.items], "captions": [asdict(cue) for cue in self.captions], "export_overlays": list(self.export_overlays)}


__all__ = ["COMPOSITION_VERSION", "CaptionCue", "CompositionItem", "CompositionPlan"]
