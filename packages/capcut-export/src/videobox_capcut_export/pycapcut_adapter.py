from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycapcut.audio_segment import AudioSegment
from pycapcut.local_materials import AudioMaterial, VideoMaterial
from pycapcut.script_file import ScriptFile
from pycapcut.text_segment import TextSegment
from pycapcut.time_util import Timerange
from pycapcut.track import TrackType
from pycapcut.video_segment import VideoSegment

from videobox_core_engine.canonical_track import canonical_track_type
from videobox_storage.timeline_clip_source_resolution import (
    TimelineClipSourceError,
    resolve_broll_clip_source,
    resolve_generic_asset_uri,
    resolve_narration_clip_source,
)

_MICROSECONDS_PER_SECOND = 1_000_000


class PyCapCutExportError(RuntimeError):
    pass


def _seconds_to_us(seconds: float) -> int:
    return int(round(seconds * _MICROSECONDS_PER_SECOND))


@dataclass(slots=True)
class PyCapCutRealExportAdapter:
    """Generates a real, CapCut-openable draft folder from a VideoBox timeline.

    Unlike `CapCutExportAdapter` (which emits a generic JSON manifest), this
    writes an actual draft via `pycapcut`, ported from BrollBox's
    `execution/export_capcut.py` track layout (voiceover / broll / subtitle /
    bgm), adapted to VideoBox's timeline schema and asset-resolution model.
    """

    store: Any
    video_width: int = 1280
    video_height: int = 720
    video_fps: int = 30

    def export_timeline(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        drafts_root: Path,
        draft_name: str,
        subtitle_file_path: Path | None = None,
    ) -> Path:
        narration_clips, broll_clips, bgm_clips = self._collect_clips(timeline)
        if not narration_clips:
            raise PyCapCutExportError("Timeline has no narration clips to export.")

        from pycapcut.draft_folder import DraftFolder

        drafts_root.mkdir(parents=True, exist_ok=True)
        draft_folder = DraftFolder(str(drafts_root))
        script = draft_folder.create_draft(
            draft_name,
            self.video_width,
            self.video_height,
            self.video_fps,
            allow_replace=True,
        )
        script.add_track(TrackType.audio, "voiceover")
        script.add_track(TrackType.video, "broll")
        if bgm_clips:
            script.add_track(TrackType.audio, "bgm")
        export_overlays = [item for item in timeline.get("export_overlays", []) if isinstance(item, dict)]
        if export_overlays:
            script.add_track(TrackType.text, "videobox_overlays")

        for clip in narration_clips:
            self._add_narration_segment(script=script, project_id=project_id, timeline=timeline, clip=clip)
        for clip in broll_clips:
            self._add_broll_segment(script=script, project_id=project_id, clip=clip)
        for clip in bgm_clips:
            self._add_bgm_segment(script=script, project_id=project_id, clip=clip)
        for overlay in export_overlays:
            self._add_text_overlay(script=script, overlay=overlay)

        if subtitle_file_path is not None:
            script.import_srt(str(subtitle_file_path), "subtitle")

        script.save()
        return drafts_root / draft_name

    def _collect_clips(
        self, timeline: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        narration_clips: list[dict[str, Any]] = []
        broll_clips: list[dict[str, Any]] = []
        bgm_clips: list[dict[str, Any]] = []
        for track in timeline.get("tracks", []):
            if not isinstance(track, dict):
                continue
            track_type = canonical_track_type(track.get("track_type"))
            clips = track.get("clips", [])
            if not isinstance(clips, list):
                continue
            valid_clips = sorted(
                (clip for clip in clips if isinstance(clip, dict)),
                key=lambda clip: float(clip.get("start_sec", 0.0)),
            )
            if track_type == "narration":
                narration_clips.extend(valid_clips)
            elif track_type == "broll":
                broll_clips.extend(valid_clips)
            elif track_type == "bgm":
                bgm_clips.extend(valid_clips)
        return narration_clips, broll_clips, bgm_clips

    def _add_narration_segment(
        self, *, script: ScriptFile, project_id: str, timeline: dict[str, Any], clip: dict[str, Any]
    ) -> None:
        try:
            resolved = resolve_narration_clip_source(
                store=self.store, project_id=project_id, timeline=timeline, clip=clip
            )
        except TimelineClipSourceError as exc:
            raise PyCapCutExportError(str(exc)) from exc
        material = AudioMaterial(str(resolved.path))
        placement_start_us = _seconds_to_us(float(clip["start_sec"]))
        if resolved.trim_duration_sec is not None:
            duration_us = _seconds_to_us(resolved.trim_duration_sec)
            source_timerange = Timerange(start=_seconds_to_us(resolved.trim_start_sec), duration=duration_us)
        else:
            duration_us = material.duration
            source_timerange = None
        segment = AudioSegment(
            material,
            Timerange(start=placement_start_us, duration=duration_us),
            source_timerange=source_timerange,
        )
        script.add_segment(segment, "voiceover")

    def _add_broll_segment(self, *, script: ScriptFile, project_id: str, clip: dict[str, Any]) -> None:
        resolved = resolve_broll_clip_source(store=self.store, project_id=project_id, clip=clip)
        material = VideoMaterial(str(resolved.path))
        placement_start_us = _seconds_to_us(float(clip["start_sec"]))
        needed_duration_us = _seconds_to_us(resolved.trim_duration_sec or 0.0)
        source_duration_us = min(needed_duration_us, material.duration) or material.duration
        segment = VideoSegment(
            material,
            Timerange(start=placement_start_us, duration=needed_duration_us),
            source_timerange=Timerange(start=0, duration=source_duration_us),
        )
        script.add_segment(segment, "broll")

    def _add_bgm_segment(self, *, script: ScriptFile, project_id: str, clip: dict[str, Any]) -> None:
        path = resolve_generic_asset_uri(store=self.store, project_id=project_id, asset_uri=str(clip.get("asset_uri") or ""))
        material = AudioMaterial(str(path))
        placement_start_us = _seconds_to_us(float(clip.get("start_sec", 0.0)))
        needed_duration_us = _seconds_to_us(float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0)))
        source_duration_us = min(needed_duration_us, material.duration) or material.duration
        segment = AudioSegment(
            material,
            Timerange(start=placement_start_us, duration=needed_duration_us),
            source_timerange=Timerange(start=0, duration=source_duration_us),
            volume=0.25,
        )
        script.add_segment(segment, "bgm")

    def _add_text_overlay(self, *, script: ScriptFile, overlay: dict[str, Any]) -> None:
        text = str(overlay.get("text") or overlay.get("title") or overlay.get("body") or "").strip()
        if not text:
            return
        start_sec = float(overlay.get("start_sec") or 0.0)
        end_sec = float(overlay.get("end_sec") or start_sec)
        if end_sec <= start_sec:
            return
        script.add_segment(
            TextSegment(text, Timerange(start=_seconds_to_us(start_sec), duration=_seconds_to_us(end_sec - start_sec))),
            "videobox_overlays",
        )


__all__ = ["PyCapCutExportError", "PyCapCutRealExportAdapter"]
