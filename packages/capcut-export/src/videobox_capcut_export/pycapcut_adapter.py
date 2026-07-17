from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
from typing import Any
import wave

from pycapcut.audio_segment import AudioSegment
from pycapcut.local_materials import AudioMaterial, CropSettings, VideoMaterial
from pycapcut.script_file import ScriptFile
from pycapcut.segment import ClipSettings
from pycapcut.text_segment import TextBackground, TextBorder, TextSegment, TextStyle
from pycapcut.time_util import Timerange
from pycapcut.track import TrackType
from pycapcut.video_segment import VideoSegment

from videobox_core_engine.canonical_track import canonical_track_type
from videobox_core_engine.media_controls import normalize_media_controls
from videobox_core_engine.output_source_verifier import OutputSourceStaleError, verify_output_sources
from videobox_core_engine.output_warning_provenance import output_metadata, output_warning_notes
import json
from videobox_domain_models.caption_style import CaptionStyle
from videobox_storage.timeline_clip_source_resolution import (
    TimelineClipSourceError,
    resolve_broll_clip_source,
    resolve_generic_asset_uri,
    resolve_narration_clip_source,
)

_MICROSECONDS_PER_SECOND = 1_000_000


class PyCapCutExportError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CapCutDraftExportResult:
    draft_path: Path
    capcut_compatibility_warnings: list[str]

    def __fspath__(self) -> str:
        return str(self.draft_path)

    @property
    def name(self) -> str:
        return self.draft_path.name

    def exists(self) -> bool:
        return self.draft_path.exists()

    def __truediv__(self, value: str) -> Path:
        return self.draft_path / value


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
    ffmpeg_binary: str = "ffmpeg"
    render_timeout_seconds: int = 1800

    def export_timeline(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        drafts_root: Path,
        draft_name: str,
        subtitle_file_path: Path | None = None,
        editing_session: dict[str, Any] | None = None,
    ) -> CapCutDraftExportResult:
        verify_output_sources(store=self.store, project_id=project_id, timeline=timeline)
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

        warnings: list[str] = []
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
            self._add_bgm_segment(script=script, project_id=project_id, clip=clip, warnings=warnings)
        for clip in sfx_clips:
            self._add_sfx_segment(script=script, project_id=project_id, clip=clip, warnings=warnings)
        for overlay in export_overlays:
            self._add_text_overlay(script=script, overlay=overlay)
        for overlay in image_overlays:
            self._add_image_overlay(script=script, project_id=project_id, overlay=overlay)

        if editing_session is not None:
            script.add_track(TrackType.text, "subtitle")
            warnings.extend(self._add_styled_captions(script=script, editing_session=editing_session))
        elif subtitle_file_path is not None:
            script.import_srt(str(subtitle_file_path), "subtitle")

        script.save()
        metadata = output_metadata(timeline)
        if metadata["warning_provenance"]:
            content_path = draft_path / "draft_content.json"
            content = json.loads(content_path.read_text(encoding="utf-8"))
            content["videobox_output_metadata"] = metadata
            content_path.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        warnings.extend(note for note in output_warning_notes(timeline) if note not in warnings)
        return CapCutDraftExportResult(draft_path=draft_path, capcut_compatibility_warnings=warnings)

    def _add_styled_captions(self, *, script: ScriptFile, editing_session: dict[str, Any]) -> list[str]:
        raw_style = editing_session.get("caption_style")
        style = CaptionStyle.from_dict(raw_style) if isinstance(raw_style, dict) else CaptionStyle()
        warnings = []
        if style.shadow_blur_px:
            warnings.append("shadow_blur_px is not supported by CapCut export")
        red, green, blue, _alpha = style.rgba_floats(style.text_color)
        border_red, border_green, border_blue, border_alpha = style.rgba_floats(style.outline_color)
        background_red, background_green, background_blue, background_alpha = style.rgba_floats(style.background_color)
        alignment = {"left": 0, "center": 1, "right": 2}[style.horizontal_align]
        capcut_style = TextStyle(size=style.font_size_px / 6, color=(red, green, blue), align=alignment, auto_wrapping=True)
        border = TextBorder(color=(border_red, border_green, border_blue), alpha=border_alpha, width=style.outline_width_px * 10)
        background = None
        if background_alpha:
            background = TextBackground(color=f"#{background_red * 255:02.0f}{background_green * 255:02.0f}{background_blue * 255:02.0f}", alpha=background_alpha)
        for segment in editing_session.get("segments", []):
            if not isinstance(segment, dict):
                continue
            text = str(segment.get("caption_text") or "").strip()
            start = float(segment.get("start_sec") or 0)
            end = float(segment.get("end_sec") or 0)
            if text and end > start:
                script.add_segment(TextSegment(text, Timerange(start=_seconds_to_us(start), duration=_seconds_to_us(end - start)), style=capcut_style, border=border, background=background), "subtitle")
        return warnings

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
        target_duration_sec = (
            resolved.target_duration_sec
            if resolved.target_duration_sec is not None
            else resolved.trim_duration_sec or 0.0
        )
        controls = normalize_media_controls(
            clip.get("media_controls"), media_kind="broll", duration_sec=max(target_duration_sec, 0.001)
        )
        crop_settings = self._broll_crop_settings(path=resolved.path, fit=controls["fit"])
        material = VideoMaterial(str(resolved.path), crop_settings=crop_settings)
        placement_start_us = _seconds_to_us(float(clip["start_sec"]))
        needed_duration_us = _seconds_to_us(target_duration_sec)
        if needed_duration_us <= 0:
            raise PyCapCutExportError("B-roll clip must have a positive target duration.")
        if material.duration <= 0:
            raise PyCapCutExportError(f"B-roll source has no usable duration: {resolved.path}")

        source_start_us = _seconds_to_us(
            resolved.trim_start_sec + float(controls.get("in_sec", 0.0)) + controls["trim_start_sec"]
        )
        # MediaInfo and CapCut's serialised duration can differ by up to two
        # final video frames after a non-zero trim. Preserve legacy untrimmed
        # loop duration exactly, but leave headroom for the trim boundary.
        trim_headroom_us = (
            2 * round(_MICROSECONDS_PER_SECOND / self.video_fps)
            if controls["trim_start_sec"]
            else 0
        )
        source_available_us = material.duration - source_start_us - trim_headroom_us
        if "out_sec" in controls:
            source_available_us = min(
                source_available_us,
                _seconds_to_us(float(controls["out_sec"])) - source_start_us,
            )
        if source_available_us <= 0:
            raise PyCapCutExportError(
                f"B-roll trim starts after the source ends: {resolved.path}. Reduce trim_start_sec."
            )

        # PyCapCut rejects a source timerange longer than a material. Keep
        # each source pass editable and use a project-local black pad when
        # looping is intentionally disabled.
        elapsed_us = 0
        while elapsed_us < needed_duration_us and controls["loop"]:
            segment_duration_us = min(source_available_us, needed_duration_us - elapsed_us)
            segment = VideoSegment(
                material,
                Timerange(start=placement_start_us + elapsed_us, duration=segment_duration_us),
                source_timerange=Timerange(start=source_start_us, duration=segment_duration_us),
            )
            script.add_segment(segment, "broll")
            elapsed_us += segment_duration_us
        if not controls["loop"]:
            segment_duration_us = min(source_available_us, needed_duration_us)
            script.add_segment(
                VideoSegment(
                    material,
                    Timerange(start=placement_start_us, duration=segment_duration_us),
                    source_timerange=Timerange(start=source_start_us, duration=segment_duration_us),
                ),
                "broll",
            )
            elapsed_us = segment_duration_us
        if elapsed_us >= needed_duration_us:
            return
        if not controls["pad"]:
            raise PyCapCutExportError(
                "B-roll source is shorter than its timeline window. Enable loop or pad to preserve timeline duration."
            )
        padding_duration_us = needed_duration_us - elapsed_us
        pad_source_duration_us = padding_duration_us + (2 * round(_MICROSECONDS_PER_SECOND / self.video_fps))
        pad_material = VideoMaterial(
            str(self._create_black_pad_material(project_id=project_id, duration_us=pad_source_duration_us))
        )
        script.add_segment(
            VideoSegment(
                pad_material,
                Timerange(start=placement_start_us + elapsed_us, duration=padding_duration_us),
                source_timerange=Timerange(start=0, duration=padding_duration_us),
            ),
            "broll",
        )

    def _broll_crop_settings(self, *, path: Path, fit: str) -> CropSettings:
        if fit == "fit":
            return CropSettings()
        source = VideoMaterial(str(path))
        source_ratio = source.width / source.height
        target_ratio = self.video_width / self.video_height
        if source_ratio > target_ratio:
            inset = (1 - target_ratio / source_ratio) / 2
            return CropSettings(upper_left_x=inset, upper_right_x=1 - inset, lower_left_x=inset, lower_right_x=1 - inset)
        inset = (1 - source_ratio / target_ratio) / 2
        return CropSettings(upper_left_y=inset, upper_right_y=inset, lower_left_y=1 - inset, lower_right_y=1 - inset)

    def _create_black_pad_material(self, *, project_id: str, duration_us: int) -> Path:
        material_path = (
            self.store.project_root(project_id)
            / "capcut_draft_materials"
            / f"videobox_black_pad_{duration_us}_{self.video_width}x{self.video_height}.mp4"
        )
        if material_path.is_file():
            return material_path
        material_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                [
                    self.ffmpeg_binary,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=black:s={self.video_width}x{self.video_height}:r={self.video_fps}",
                    "-t",
                    str(duration_us / _MICROSECONDS_PER_SECOND),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(material_path),
                ],
                capture_output=True,
                text=True,
                timeout=self.render_timeout_seconds,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise PyCapCutExportError("Unable to create the B-roll pad material. Install/configure ffmpeg.") from exc
        if result.returncode != 0:
            raise PyCapCutExportError(f"Unable to create B-roll pad material: {result.stderr[-800:]}")
        return material_path

    def _add_bgm_segment(self, *, script: ScriptFile, project_id: str, clip: dict[str, Any], warnings: list[str]) -> None:
        path = resolve_generic_asset_uri(store=self.store, project_id=project_id, asset_uri=str(clip.get("asset_uri") or ""))
        material = AudioMaterial(str(path))
        placement_start_us = _seconds_to_us(float(clip.get("start_sec", 0.0)))
        needed_duration_us = _seconds_to_us(float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0)))
        source_duration_us = min(needed_duration_us, material.duration) or material.duration
        controls = normalize_media_controls(clip.get("media_controls"), media_kind="audio", duration_sec=max(needed_duration_us / _MICROSECONDS_PER_SECOND, 0.001))
        segment = AudioSegment(
            material,
            Timerange(start=placement_start_us, duration=needed_duration_us),
            source_timerange=Timerange(start=0, duration=source_duration_us),
            volume=0.25 * (10 ** (controls["gain_db"] / 20)),
        )
        if controls["fade_in_sec"] or controls["fade_out_sec"]:
            segment.add_fade(_seconds_to_us(controls["fade_in_sec"]), _seconds_to_us(controls["fade_out_sec"]))
        if controls["ducking"]:
            warnings.append("ducking is not natively supported by CapCut draft export; apply it in CapCut after import")
        script.add_segment(segment, "bgm")

    def _add_sfx_segment(self, *, script: ScriptFile, project_id: str, clip: dict[str, Any], warnings: list[str]) -> None:
        path = resolve_generic_asset_uri(store=self.store, project_id=project_id, asset_uri=str(clip.get("asset_uri") or ""))
        material = AudioMaterial(str(path))
        placement_start_us = _seconds_to_us(float(clip.get("start_sec", 0.0)))
        needed_duration_us = _seconds_to_us(float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0)))
        source_duration_us = min(needed_duration_us, material.duration) or material.duration
        controls = normalize_media_controls(clip.get("media_controls"), media_kind="audio", duration_sec=max(needed_duration_us / _MICROSECONDS_PER_SECOND, 0.001))
        segment = AudioSegment(material, Timerange(start=placement_start_us, duration=needed_duration_us), source_timerange=Timerange(start=0, duration=source_duration_us), volume=10 ** (controls["gain_db"] / 20))
        if controls["fade_in_sec"] or controls["fade_out_sec"]:
            segment.add_fade(_seconds_to_us(controls["fade_in_sec"]), _seconds_to_us(controls["fade_out_sec"]))
        if controls["ducking"]:
            warnings.append("ducking is not natively supported by CapCut draft export; apply it in CapCut after import")
        script.add_segment(segment, "sfx")

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


__all__ = ["CapCutDraftExportResult", "PyCapCutExportError", "PyCapCutRealExportAdapter"]
