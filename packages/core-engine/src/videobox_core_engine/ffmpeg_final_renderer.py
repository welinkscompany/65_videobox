from __future__ import annotations

import subprocess
import tempfile
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videobox_core_engine.canonical_track import canonical_track_type
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.timeline_clip_source_resolution import (
    ResolvedClipSource,
    TimelineClipSourceError,
    resolve_broll_clip_source,
    resolve_generic_asset_uri,
    resolve_narration_clip_source,
)


class FinalRenderError(RuntimeError):
    pass


@dataclass(slots=True)
class FfmpegFinalRenderer:
    store: LocalProjectStore
    ffmpeg_binary: str = "ffmpeg"
    render_timeout_seconds: int = 1800
    video_width: int = 1280
    video_height: int = 720
    video_fps: int = 30
    bgm_volume: float = 0.25
    overlay_font_file: str = os.environ.get("VIDEBOX_OVERLAY_FONT", r"C:\Windows\Fonts\malgun.ttf")

    def _run(self, command: list[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.render_timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise FinalRenderError(f"'{self.ffmpeg_binary}' binary was not found. Install ffmpeg.") from exc
        except subprocess.TimeoutExpired as exc:
            raise FinalRenderError(f"ffmpeg timed out after {self.render_timeout_seconds}s.") from exc

    def _resolve_narration_clip_source(
        self, *, project_id: str, timeline: dict[str, Any], clip: dict[str, Any]
    ) -> ResolvedClipSource:
        try:
            return resolve_narration_clip_source(store=self.store, project_id=project_id, timeline=timeline, clip=clip)
        except TimelineClipSourceError as exc:
            raise FinalRenderError(str(exc)) from exc

    def _resolve_broll_clip_source(self, *, project_id: str, clip: dict[str, Any]) -> ResolvedClipSource:
        return resolve_broll_clip_source(store=self.store, project_id=project_id, clip=clip)

    def _resolve_generic_asset_uri(self, *, project_id: str, asset_uri: str) -> Path:
        return resolve_generic_asset_uri(store=self.store, project_id=project_id, asset_uri=asset_uri)

    def _extract_segment(self, *, source: ResolvedClipSource, output_path: Path, video: bool) -> None:
        command = [self.ffmpeg_binary, "-y"]
        if source.trim_start_sec:
            command += ["-ss", str(source.trim_start_sec)]
        if video and source.target_duration_sec is not None:
            command += ["-stream_loop", "-1"]
        command += ["-i", str(source.path)]
        output_duration_sec = source.target_duration_sec if source.target_duration_sec is not None else source.trim_duration_sec
        if output_duration_sec is not None:
            command += ["-t", str(output_duration_sec)]
        if video:
            command += [
                "-an",
                "-vf",
                f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=decrease,"
                f"pad={self.video_width}:{self.video_height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                "-r",
                str(self.video_fps),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
            ]
        else:
            command += ["-vn"]
            if output_duration_sec is not None:
                command += ["-af", f"apad,atrim=duration={output_duration_sec}"]
            command += ["-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le"]
        command.append(str(output_path))
        result = self._run(command)
        if result.returncode != 0:
            raise FinalRenderError(f"ffmpeg failed extracting segment from '{source.path}': {result.stderr[-800:]}")

    def _concat(self, *, segment_paths: list[Path], output_path: Path, work_dir: Path) -> None:
        list_path = work_dir / f"{output_path.stem}_concat_list.txt"
        list_path.write_text(
            "\n".join(f"file '{segment_path.as_posix()}'" for segment_path in segment_paths),
            encoding="utf-8",
        )
        command = [
            self.ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output_path),
        ]
        result = self._run(command)
        if result.returncode != 0:
            raise FinalRenderError(f"ffmpeg failed concatenating segments into '{output_path}': {result.stderr[-800:]}")

    def _apply_export_overlays(
        self,
        *,
        project_id: str,
        video_path: Path,
        overlays: list[dict[str, Any]],
        work_dir: Path,
    ) -> Path:
        text_filters: list[str] = []
        image_overlays: list[tuple[Path, float, float]] = []
        for overlay in overlays:
            overlay_type = str(overlay.get("overlay_type") or "").strip().lower()
            start_sec = float(overlay.get("start_sec") or 0.0)
            end_sec = float(overlay.get("end_sec") or start_sec)
            if end_sec <= start_sec:
                continue
            if overlay_type in {"image", "image_card", "image_overlay", "visual_overlay", "hook_title"}:
                asset_uri = str(overlay.get("asset_uri") or "").strip()
                asset_id = str(overlay.get("asset_id") or "").strip()
                if not asset_uri and asset_id:
                    asset_uri = f"local://projects/{project_id}/assets/{asset_id}"
                if asset_uri:
                    image_overlays.append(
                        (self._resolve_generic_asset_uri(project_id=project_id, asset_uri=asset_uri), start_sec, end_sec)
                    )
            text = str(overlay.get("text") or overlay.get("title") or overlay.get("body") or "").strip()
            if not text:
                continue
            escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
            font_file = self.overlay_font_file.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            text_filters.append(
                f"drawtext=fontfile='{font_file}':text='{escaped}':x=(w-text_w)/2:y=h-(text_h*3):fontsize=36:fontcolor=white:"
                f"box=1:boxcolor=black@0.65:boxborderw=12:enable='between(t,{start_sec},{end_sec})'"
            )
        if not text_filters and not image_overlays:
            return video_path
        overlaid_path = work_dir / "broll_with_overlays.mp4"
        command = [self.ffmpeg_binary, "-y", "-i", str(video_path)]
        for image_path, _start_sec, _end_sec in image_overlays:
            command += ["-loop", "1", "-i", str(image_path)]
        current_label = "[0:v]"
        filter_parts: list[str] = []
        for index, (_image_path, start_sec, end_sec) in enumerate(image_overlays, start=1):
            next_label = f"[overlay_{index}]"
            filter_parts.append(
                f"{current_label}[{index}:v]overlay=x=(main_w-overlay_w)/2:y=(main_h-overlay_h)/2:"
                f"enable='between(t,{start_sec},{end_sec})':eof_action=repeat:shortest=1{next_label}"
            )
            current_label = next_label
        for index, text_filter in enumerate(text_filters, start=1):
            next_label = f"[text_{index}]"
            filter_parts.append(f"{current_label}{text_filter}{next_label}")
            current_label = next_label
        command += [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            current_label,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            str(overlaid_path),
        ]
        result = self._run(command)
        if result.returncode != 0:
            raise FinalRenderError(f"ffmpeg failed applying export overlays: {result.stderr[-800:]}")
        return overlaid_path

    def render_timeline_to_mp4(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        output_path: Path,
        subtitle_file_path: Path | None = None,
        subtitle_ass_path: Path | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> Path:
        def report_progress(percent: int) -> None:
            if on_progress is not None:
                on_progress(percent)
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

        if not narration_clips:
            raise FinalRenderError("Timeline has no narration clips to render.")
        if not broll_clips:
            raise FinalRenderError("Timeline has no broll clips to render.")

        with tempfile.TemporaryDirectory(prefix="videobox_render_") as raw_work_dir:
            work_dir = Path(raw_work_dir)

            narration_segment_paths = []
            for index, clip in enumerate(narration_clips, start=1):
                source = self._resolve_narration_clip_source(project_id=project_id, timeline=timeline, clip=clip)
                segment_path = work_dir / f"narration_{index:03d}.wav"
                self._extract_segment(source=source, output_path=segment_path, video=False)
                narration_segment_paths.append(segment_path)
            narration_path = work_dir / "narration_full.wav"
            self._concat(segment_paths=narration_segment_paths, output_path=narration_path, work_dir=work_dir)
            report_progress(25)

            broll_segment_paths = []
            for index, clip in enumerate(broll_clips, start=1):
                source = self._resolve_broll_clip_source(project_id=project_id, clip=clip)
                segment_path = work_dir / f"broll_{index:03d}.mp4"
                self._extract_segment(source=source, output_path=segment_path, video=True)
                broll_segment_paths.append(segment_path)
            video_path = work_dir / "broll_full.mp4"
            self._concat(segment_paths=broll_segment_paths, output_path=video_path, work_dir=work_dir)
            video_path = self._apply_export_overlays(
                project_id=project_id,
                video_path=video_path,
                overlays=[item for item in timeline.get("export_overlays", []) if isinstance(item, dict)],
                work_dir=work_dir,
            )
            report_progress(60)

            audio_path = narration_path
            if bgm_clips:
                bgm_source = self._resolve_generic_asset_uri(
                    project_id=project_id, asset_uri=str(bgm_clips[0].get("asset_uri") or "")
                )
                mixed_path = work_dir / "audio_with_bgm.wav"
                command = [
                    self.ffmpeg_binary,
                    "-y",
                    "-i",
                    str(narration_path),
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(bgm_source),
                    "-filter_complex",
                    f"[1:a]volume={self.bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]",
                    "-map",
                    "[aout]",
                    str(mixed_path),
                ]
                result = self._run(command)
                if result.returncode != 0:
                    raise FinalRenderError(f"ffmpeg failed mixing bgm: {result.stderr[-800:]}")
                audio_path = mixed_path
            if sfx_clips:
                mixed_path = work_dir / "audio_with_sfx.wav"
                command = [self.ffmpeg_binary, "-y", "-i", str(audio_path)]
                filter_parts = ["[0:a]anull[base]"]
                mix_inputs = "[base]"
                for index, clip in enumerate(sfx_clips, start=1):
                    source = self._resolve_generic_asset_uri(
                        project_id=project_id, asset_uri=str(clip.get("asset_uri") or "")
                    )
                    command += ["-i", str(source)]
                    start_ms = int(float(clip.get("start_sec", 0.0)) * 1000)
                    duration_sec = float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0))
                    filter_parts.append(f"[{index}:a]atrim=duration={duration_sec},adelay={start_ms}|{start_ms}[sfx{index}]")
                    mix_inputs += f"[sfx{index}]"
                filter_parts.append(f"{mix_inputs}amix=inputs={len(sfx_clips) + 1}:duration=first[aout]")
                command += ["-filter_complex", ";".join(filter_parts), "-map", "[aout]", str(mixed_path)]
                result = self._run(command)
                if result.returncode != 0:
                    raise FinalRenderError(f"ffmpeg failed mixing sfx: {result.stderr[-800:]}")
                audio_path = mixed_path
            report_progress(80)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                self.ffmpeg_binary,
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
            ]
            if subtitle_file_path is not None and subtitle_ass_path is None:
                command += ["-i", str(subtitle_file_path), "-c:s", "mov_text", "-map", "2:s"]
            if subtitle_ass_path is not None:
                escaped_ass_path = subtitle_ass_path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
                command += ["-vf", f"subtitles=filename='{escaped_ass_path}'"]
            command += [
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "libx264" if subtitle_ass_path is not None else "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(output_path),
            ]
            result = self._run(command)
            if result.returncode != 0:
                raise FinalRenderError(f"ffmpeg failed muxing final output: {result.stderr[-800:]}")
            report_progress(100)

        return output_path


__all__ = ["FfmpegFinalRenderer", "FinalRenderError"]
