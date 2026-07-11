from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any
import wave

from pycapcut.audio_segment import AudioSegment
from pycapcut.local_materials import AudioMaterial, VideoMaterial
from pycapcut.script_file import ScriptFile
from pycapcut.segment import ClipSettings
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
        narration_clips, broll_clips, bgm_clips, sfx_clips = self._collect_clips(timeline)
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
        draft_path = drafts_root / draft_name
        silence_path = self._create_silence_material(
            project_id=project_id,
            duration_us=self._required_silence_padding_duration(
                project_id=project_id,
                timeline=timeline,
                narration_clips=narration_clips,
            ),
        )
        script.add_track(TrackType.audio, "voiceover")
        script.add_track(TrackType.video, "broll")
        if bgm_clips:
            script.add_track(TrackType.audio, "bgm")
        if sfx_clips:
            script.add_track(TrackType.audio, "sfx")
        export_overlays = [item for item in timeline.get("export_overlays", []) if isinstance(item, dict)]
        if export_overlays:
            script.add_track(TrackType.text, "videobox_overlays")
        image_overlays = [
            item for item in export_overlays if str(item.get("asset_id") or "").strip()
        ]
        if image_overlays:
            script.add_track(TrackType.video, "videobox_image_overlays", relative_index=1)

        for clip in narration_clips:
            self._add_narration_segment(
                script=script,
                project_id=project_id,
                timeline=timeline,
                clip=clip,
                silence_path=silence_path,
            )
        for clip in broll_clips:
            self._add_broll_segment(script=script, project_id=project_id, clip=clip)
        for clip in bgm_clips:
            self._add_bgm_segment(script=script, project_id=project_id, clip=clip)
        for clip in sfx_clips:
            self._add_sfx_segment(script=script, project_id=project_id, clip=clip)
        for overlay in export_overlays:
            self._add_text_overlay(script=script, overlay=overlay)
        for overlay in image_overlays:
            self._add_image_overlay(script=script, project_id=project_id, overlay=overlay)

        if subtitle_file_path is not None:
            script.import_srt(str(subtitle_file_path), "subtitle")

        script.save()
        return draft_path

    def _collect_clips(
        self, timeline: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        narration_clips: list[dict[str, Any]] = []
        broll_clips: list[dict[str, Any]] = []
        bgm_clips: list[dict[str, Any]] = []
        sfx_clips: list[dict[str, Any]] = []
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
            elif track_type == "sfx":
                sfx_clips.extend(valid_clips)
        return narration_clips, broll_clips, bgm_clips, sfx_clips

    def _add_narration_segment(
        self,
        *,
        script: ScriptFile,
        project_id: str,
        timeline: dict[str, Any],
        clip: dict[str, Any],
        silence_path: Path | None,
    ) -> None:
        try:
            resolved = resolve_narration_clip_source(
                store=self.store, project_id=project_id, timeline=timeline, clip=clip
            )
        except TimelineClipSourceError as exc:
            raise PyCapCutExportError(str(exc)) from exc
        material = AudioMaterial(str(resolved.path))
        placement_start_us = _seconds_to_us(float(clip["start_sec"]))
        target_duration_us = _seconds_to_us(
            resolved.target_duration_sec
            if resolved.target_duration_sec is not None
            else float(clip["end_sec"]) - float(clip["start_sec"])
        )
        if resolved.trim_duration_sec is not None:
            source_duration_us = _seconds_to_us(resolved.trim_duration_sec)
        else:
            source_duration_us = material.duration
        natural_duration_us = min(source_duration_us, material.duration, target_duration_us)
        source_timerange = Timerange(
            start=_seconds_to_us(resolved.trim_start_sec),
            duration=natural_duration_us,
        )
        segment = AudioSegment(
            material,
            Timerange(start=placement_start_us, duration=natural_duration_us),
            source_timerange=source_timerange,
        )
        script.add_segment(segment, "voiceover")
        padding_duration_us = target_duration_us - natural_duration_us
        if padding_duration_us <= 0:
            return
        if silence_path is None:
            raise PyCapCutExportError("Missing draft-local silence material for short narration padding.")
        silence_material = AudioMaterial(str(silence_path))
        script.add_segment(
            AudioSegment(
                silence_material,
                Timerange(start=placement_start_us + natural_duration_us, duration=padding_duration_us),
                source_timerange=Timerange(start=0, duration=padding_duration_us),
            ),
            "voiceover",
        )

    def _required_silence_padding_duration(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        narration_clips: list[dict[str, Any]],
    ) -> int:
        required_duration_us = 0
        for clip in narration_clips:
            try:
                resolved = resolve_narration_clip_source(
                    store=self.store, project_id=project_id, timeline=timeline, clip=clip
                )
            except TimelineClipSourceError as exc:
                raise PyCapCutExportError(str(exc)) from exc
            target_duration_us = _seconds_to_us(
                resolved.target_duration_sec
                if resolved.target_duration_sec is not None
                else float(clip["end_sec"]) - float(clip["start_sec"])
            )
            material_duration_us = AudioMaterial(str(resolved.path)).duration
            source_duration_us = (
                min(_seconds_to_us(resolved.trim_duration_sec), material_duration_us)
                if resolved.trim_duration_sec is not None
                else material_duration_us
            )
            required_duration_us = max(
                required_duration_us,
                target_duration_us - min(source_duration_us, target_duration_us),
            )
        return required_duration_us

    def _create_silence_material(self, *, project_id: str, duration_us: int) -> Path | None:
        if duration_us <= 0:
            return None
        # CapCut material paths remain project-local source references, just
        # like narration and B-roll assets.  Do not put the generated pad in
        # the temporary draft folder: the pipeline copies that folder and then
        # deletes the temporary source after export.
        material_path = (
            self.store.project_root(project_id)
            / "capcut_draft_materials"
            / f"videobox_silence_{duration_us}.wav"
        )
        if material_path.is_file():
            return material_path
        material_path.parent.mkdir(parents=True, exist_ok=True)
        frame_count = math.ceil(duration_us * 8_000 / _MICROSECONDS_PER_SECOND)
        with wave.open(str(material_path), "wb") as silence_file:
            silence_file.setnchannels(1)
            silence_file.setsampwidth(1)
            silence_file.setframerate(8_000)
            remaining = frame_count
            while remaining:
                chunk_size = min(remaining, 65_536)
                silence_file.writeframesraw(b"\x80" * chunk_size)
                remaining -= chunk_size
        return material_path

    def _add_broll_segment(self, *, script: ScriptFile, project_id: str, clip: dict[str, Any]) -> None:
        resolved = resolve_broll_clip_source(store=self.store, project_id=project_id, clip=clip)
        material = VideoMaterial(str(resolved.path))
        placement_start_us = _seconds_to_us(float(clip["start_sec"]))
        needed_duration_us = _seconds_to_us(
            resolved.target_duration_sec
            if resolved.target_duration_sec is not None
            else resolved.trim_duration_sec or 0.0
        )
        if needed_duration_us <= 0:
            raise PyCapCutExportError("B-roll clip must have a positive target duration.")
        if material.duration <= 0:
            raise PyCapCutExportError(f"B-roll source has no usable duration: {resolved.path}")

        # PyCapCut rejects a source timerange longer than a material.  Repeat
        # the source as adjacent, non-overlapping segments instead of relying
        # on a single stretched segment, which keeps the draft editable in
        # CapCut and fills the requested timeline window exactly.
        elapsed_us = 0
        while elapsed_us < needed_duration_us:
            segment_duration_us = min(material.duration, needed_duration_us - elapsed_us)
            segment = VideoSegment(
                material,
                Timerange(start=placement_start_us + elapsed_us, duration=segment_duration_us),
                source_timerange=Timerange(start=0, duration=segment_duration_us),
            )
            script.add_segment(segment, "broll")
            elapsed_us += segment_duration_us

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

    def _add_sfx_segment(self, *, script: ScriptFile, project_id: str, clip: dict[str, Any]) -> None:
        path = resolve_generic_asset_uri(store=self.store, project_id=project_id, asset_uri=str(clip.get("asset_uri") or ""))
        material = AudioMaterial(str(path))
        placement_start_us = _seconds_to_us(float(clip.get("start_sec", 0.0)))
        needed_duration_us = _seconds_to_us(float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0)))
        source_duration_us = min(needed_duration_us, material.duration) or material.duration
        script.add_segment(
            AudioSegment(material, Timerange(start=placement_start_us, duration=needed_duration_us), source_timerange=Timerange(start=0, duration=source_duration_us)),
            "sfx",
        )

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

    def _add_image_overlay(self, *, script: ScriptFile, project_id: str, overlay: dict[str, Any]) -> None:
        asset_id = str(overlay.get("asset_id") or "").strip()
        if not asset_id:
            return
        start_sec = float(overlay.get("start_sec") or 0.0)
        end_sec = float(overlay.get("end_sec") or start_sec)
        if end_sec <= start_sec:
            return
        try:
            asset = self.store.get_asset(project_id=project_id, asset_id=asset_id)
            path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
        except (KeyError, OSError, ValueError) as exc:
            raise PyCapCutExportError(f"Unable to resolve image overlay asset '{asset_id}'.") from exc

        material = VideoMaterial(str(path))
        duration_us = _seconds_to_us(end_sec - start_sec)
        if material.duration < duration_us:
            raise PyCapCutExportError(
                f"Image overlay asset '{asset_id}' is shorter than its requested timeline window."
            )
        script.add_segment(
            VideoSegment(
                material,
                Timerange(start=_seconds_to_us(start_sec), duration=duration_us),
                source_timerange=Timerange(start=0, duration=duration_us),
                clip_settings=ClipSettings(scale_x=0.5, scale_y=0.5, transform_y=-0.35),
            ),
            "videobox_image_overlays",
        )


__all__ = ["PyCapCutExportError", "PyCapCutRealExportAdapter"]
