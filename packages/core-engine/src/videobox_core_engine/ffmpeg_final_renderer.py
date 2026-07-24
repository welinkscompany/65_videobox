from __future__ import annotations

import subprocess
import tempfile
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from math import ceil
from pathlib import Path
from typing import Any

from videobox_core_engine.canonical_track import canonical_track_type
from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.media_controls import normalize_media_controls
from videobox_core_engine.output_source_verifier import OutputSourceStaleError, verify_output_sources
from videobox_core_engine.output_warning_provenance import output_warning_notes
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


@dataclass(frozen=True, slots=True)
class CompositionRenderInputs:
    """The one immutable composition/caption input accepted by every renderer."""

    composition_plan: CompositionPlan
    captions: tuple[Any, ...]


@dataclass(slots=True)
class FfmpegFinalRenderer:
    store: LocalProjectStore
    ffmpeg_binary: str = "ffmpeg"
    render_timeout_seconds: int = 1800
    video_width: int = 1280
    video_height: int = 720
    video_fps: int | str = 30
    video_sar: str = "1:1"
    bgm_volume: float = 0.25
    overlay_font_file: str = os.environ.get("VIDEBOX_OVERLAY_FONT", r"C:\Windows\Fonts\malgun.ttf")
    ffprobe_binary: str = "ffprobe"

    def extract_composition_plan(
        self, *, timeline: dict[str, Any], captions: list[dict[str, Any]] | None = None
    ) -> CompositionPlan:
        """Return the pure composition authority shared with exact preview.

        Task 1 intentionally leaves the established ffmpeg command path
        untouched.  Task 2 will pass this exact object into both final/proxy
        command construction before claiming command-level parity.
        """
        return CompositionPlan.from_timeline(timeline=timeline, captions=captions or [])

    def build_final_render_inputs(self, *, composition_plan: CompositionPlan) -> CompositionRenderInputs:
        return CompositionRenderInputs(composition_plan=composition_plan, captions=composition_plan.captions)

    def build_exact_preview_inputs(self, *, composition_plan: CompositionPlan) -> CompositionRenderInputs:
        # This is intentionally the same value object as final output.  A
        # proxy is a different profile, never a different composition.
        return CompositionRenderInputs(composition_plan=composition_plan, captions=composition_plan.captions)

    def build_plan_filter_graph(
        self, *, composition_plan: CompositionPlan, source_indices: dict[str, int],
        export_overlay_indices: dict[int, int] | None = None,
        track_overlay_indices: dict[str, int] | None = None,
    ) -> str:
        """Build the shared timeline placement graph.

        Video policy is intentionally deterministic: an all-black canvas
        starts at PTS zero, each B-roll source is placed at its canonical
        timeline PTS, and later `(start_sec, clip_id)` overlays win where
        intervals overlap.  That preserves leading/internal gaps instead of
        concatenating unrelated source segments.
        """
        duration = max(composition_plan.duration_sec, 0.001)
        sar = composition_plan.sample_aspect_ratio.replace(":", "/")
        filters = [
            f"color=c=black:s={self.video_width}x{self.video_height}:r={self.video_fps}:d={duration}[canvas0]"
        ]
        canvas = "canvas0"
        broll = sorted(
            (item for item in composition_plan.items if item.track_type == "broll"),
            key=lambda item: (item.start_sec, item.clip_id),
        )
        for ordinal, item in enumerate(broll, start=1):
            index = source_indices[item.clip_id]
            label = f"v_{item.clip_id}"
            duration_sec = item.end_sec - item.start_sec
            controls = normalize_media_controls(item.media_controls, media_kind="broll", duration_sec=max(duration_sec, 0.001))
            if controls["fit"] == "crop":
                transform = f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=increase,crop={self.video_width}:{self.video_height}"
            else:
                transform = f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=decrease,pad={self.video_width}:{self.video_height}:(ow-iw)/2:(oh-ih)/2"
            source_window_sec = item.source_out_sec - item.source_in_sec
            if controls["pad"] and not controls["loop"]:
                transform += f",tpad=stop_mode=add:stop_duration={max(0.0, duration_sec - source_window_sec)}"
            source_filter = (
                f"[{index}:v]trim=start={item.source_in_sec}:end={item.source_out_sec},setpts=PTS-STARTPTS"
            )
            if controls["loop"] and source_window_sec < duration_sec:
                numerator, separator, denominator = str(self.video_fps).partition("/")
                frames_per_second = float(numerator) / float(denominator) if separator else float(numerator)
                loop_frames = max(1, ceil(source_window_sec * frames_per_second))
                source_filter += (
                    f",fps={self.video_fps},loop=loop=-1:size={loop_frames}:start=0,"
                    f"trim=duration={duration_sec},setpts=PTS-STARTPTS"
                )
            filters.append(
                f"{source_filter},{transform},setsar={sar},setpts=PTS+{item.start_sec}/TB[{label}]"
            )
            next_canvas = f"canvas{ordinal}"
            filters.append(f"[{canvas}][{label}]overlay=eof_action=pass:repeatlast=0[{next_canvas}]")
            canvas = next_canvas
        track_overlays = sorted(
            (item for item in composition_plan.items if item.track_type == "overlay"),
            key=lambda item: (item.start_sec, item.clip_id),
        )
        for ordinal, item in enumerate(track_overlays, start=1):
            if track_overlay_indices is None or item.clip_id not in track_overlay_indices:
                raise FinalRenderError(
                    "Exact preview overlay source is unavailable. Restore a local image or video source and retry."
                )
            index = track_overlay_indices[item.clip_id]
            label = f"track_overlay_{ordinal}"
            next_canvas = f"canvas_track_overlay_{ordinal}"
            filters.append(
                f"[{index}:v]trim=start={item.source_in_sec}:end={item.source_out_sec},setpts=PTS-STARTPTS,"
                f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=decrease,"
                f"setsar={sar},setpts=PTS+{item.start_sec}/TB[{label}]"
            )
            filters.append(
                f"[{canvas}][{label}]overlay=(W-w)/2:(H-h)/2:eof_action=pass:repeatlast=0[{next_canvas}]"
            )
            canvas = next_canvas
        for overlay_index, overlay in enumerate(composition_plan.export_overlays):
            if export_overlay_indices is None or overlay_index not in export_overlay_indices:
                continue
            start_sec, end_sec = float(overlay.get("start_sec") or 0.0), float(overlay.get("end_sec") or 0.0)
            if end_sec <= start_sec:
                continue
            source_index = export_overlay_indices[overlay_index]
            label = f"export_overlay_{overlay_index}"
            next_canvas = f"canvas_export_{overlay_index}"
            filters.append(
                f"[{source_index}:v]trim=duration={end_sec - start_sec},setpts=PTS-STARTPTS,"
                f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=decrease,"
                f"setpts=PTS+{start_sec}/TB[{label}]"
            )
            filters.append(f"[{canvas}][{label}]overlay=(W-w)/2:(H-h)/2:eof_action=pass:repeatlast=0[{next_canvas}]")
            canvas = next_canvas
        for overlay_index, overlay in enumerate(composition_plan.export_overlays):
            if overlay.get("asset_uri") or overlay.get("asset_id"):
                continue
            text = str(overlay.get("text") or overlay.get("title") or overlay.get("body") or "").strip()
            if not text:
                continue
            start_sec, end_sec = float(overlay.get("start_sec") or 0.0), float(overlay.get("end_sec") or 0.0)
            if end_sec <= start_sec:
                continue
            if not Path(self.overlay_font_file).is_file():
                raise FinalRenderError("Overlay font is missing; set VIDEOBOX_OVERLAY_FONT before rendering text overlays.")
            escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
            font = self.overlay_font_file.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            next_canvas = f"canvas_text_{overlay_index}"
            filters.append(
                f"[{canvas}]drawtext=fontfile='{font}':text='{escaped}':x=(w-text_w)/2:y=h-(text_h*3):"
                f"fontsize=36:fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=12:"
                f"enable='between(t,{start_sec},{end_sec})'[{next_canvas}]"
            )
            canvas = next_canvas
        filters.append(f"[{canvas}]null[vout]")
        return ";".join(filters)

    def build_plan_audio_filter_graph(
        self, *, composition_plan: CompositionPlan, source_indices: dict[str, int]
    ) -> str:
        """Shared audio placement/control graph for final and proxy output."""
        duration = max(composition_plan.duration_sec, 0.001)
        narration = [item for item in composition_plan.items if item.track_type == "narration"]
        filters: list[str] = []
        narration_labels: list[str] = []
        for item in narration:
            label = f"a_{item.clip_id}"
            delay = max(0, round(item.start_sec * 1000))
            filters.append(f"[{source_indices[item.clip_id]}:a]atrim=start={item.source_in_sec}:end={item.source_out_sec},asetpts=PTS-STARTPTS,adelay={delay}|{delay}[{label}]")
            narration_labels.append(f"[{label}]")
        if not narration_labels:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration}[narration_mix]")
        elif len(narration_labels) == 1:
            filters.append(f"{narration_labels[0]}anull[narration_mix]")
        else:
            filters.append(f"{''.join(narration_labels)}amix=inputs={len(narration_labels)}:duration=longest[narration_mix]")

        has_ducked_bgm = any(
            item.track_type == "bgm"
            and normalize_media_controls(
                item.media_controls,
                media_kind="audio",
                duration_sec=max(item.end_sec - item.start_sec, 0.001),
            )["ducking"]
            for item in composition_plan.items
        )
        narration_sidechain = "[narration_mix]"
        labels = ["[narration_mix]"]
        if has_ducked_bgm:
            filters.append("[narration_mix]asplit=2[narration_final][narration_sidechain]")
            narration_sidechain = "[narration_sidechain]"
            labels = ["[narration_final]"]
        for item in composition_plan.items:
            if item.track_type == "broll":
                controls = normalize_media_controls(item.media_controls, media_kind="broll", duration_sec=max(item.end_sec - item.start_sec, 0.001))
                if not controls["preserve_source_audio"]:
                    continue
                label = f"a_{item.clip_id}"
                delay = max(0, round(item.start_sec * 1000))
                source_window_sec = item.source_out_sec - item.source_in_sec
                timeline_duration_sec = item.end_sec - item.start_sec
                source_filter = f"[{source_indices[item.clip_id]}:a]atrim=start={item.source_in_sec}:end={item.source_out_sec}"
                if controls["loop"] and source_window_sec < timeline_duration_sec:
                    # Normalize before aloop so its sample count exactly spans
                    # the selected source window, not an input-dependent rate.
                    source_filter += (
                        f",aresample=48000,aloop=loop=-1:size={max(1, ceil(source_window_sec * 48000))}:start=0,"
                        f"atrim=duration={timeline_duration_sec}"
                    )
                filters.append(f"{source_filter},asetpts=PTS-STARTPTS,adelay={delay}|{delay}[{label}]")
                labels.append(f"[{label}]")
            elif item.track_type in {"bgm", "sfx"}:
                controls = normalize_media_controls(item.media_controls, media_kind="audio", duration_sec=max(item.end_sec - item.start_sec, 0.001))
                label = f"a_{item.clip_id}"
                delay = max(0, round(item.start_sec * 1000))
                effect = f"volume={controls['gain_db']}dB"
                if controls["fade_in_sec"]:
                    effect += f",afade=t=in:st=0:d={controls['fade_in_sec']}"
                if controls["fade_out_sec"]:
                    effect += f",afade=t=out:st={max(0.0, item.end_sec - item.start_sec - controls['fade_out_sec'])}:d={controls['fade_out_sec']}"
                filters.append(f"[{source_indices[item.clip_id]}:a]atrim=start={item.source_in_sec}:end={item.source_out_sec},{effect},asetpts=PTS-STARTPTS,adelay={delay}|{delay}[{label}]")
                if item.track_type == "bgm" and controls["ducking"]:
                    ducked = f"duck_{item.clip_id}"
                    filters.append(f"[{label}]{narration_sidechain}sidechaincompress=threshold=0.05:ratio=8[{ducked}]")
                    labels.append(f"[{ducked}]")
                else:
                    labels.append(f"[{label}]")
        filters.append(
            f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest,"
            f"apad=whole_dur={duration},atrim=duration={duration},asetpts=PTS-STARTPTS[aout]"
        )
        return ";".join(filters)

    @staticmethod
    def _timeline_from_plan(*, composition_plan: CompositionPlan, timeline_context: dict[str, Any]) -> dict[str, Any]:
        """Rehydrate only the source-resolution shape from the authoritative plan."""
        tracks: dict[str, list[dict[str, Any]]] = {}
        for item in composition_plan.items:
            controls = dict(item.media_controls)
            # Range normalization has already shifted source time exactly once.
            # Put that resolved source in on the source-reading contract; do
            # not consult the mutable timeline again for placement/trim.
            if item.track_type == "broll":
                controls["in_sec"] = item.source_in_sec
            tracks.setdefault(item.track_type, []).append({
                "clip_id": item.clip_id,
                "asset_id": item.asset_id,
                "asset_uri": item.asset_uri,
                "start_sec": item.start_sec,
                "end_sec": item.end_sec,
                "source_in_sec": item.source_in_sec,
                "source_out_sec": item.source_out_sec,
                "media_controls": controls,
                "expected_content_sha256": item.expected_content_sha256,
                "media_revision": item.media_revision,
                "overlay_type": item.overlay_type,
                "overlay_payload": dict(item.overlay_payload),
            })
        return {
            "output": {
                "width": composition_plan.width, "height": composition_plan.height,
                "fps_num": composition_plan.fps_num, "fps_den": composition_plan.fps_den,
                "sample_aspect_ratio": composition_plan.sample_aspect_ratio,
                "rotation": composition_plan.rotation,
            },
            "narration_source_uri": timeline_context.get("narration_source_uri"),
            "tracks": [{"track_type": kind, "clips": clips} for kind, clips in tracks.items()],
            "export_overlays": [dict(item) for item in composition_plan.export_overlays],
        }

    def render_exact_preview_to_mp4(
        self,
        *,
        project_id: str,
        composition_plan: CompositionPlan,
        timeline_context: dict[str, Any],
        output_path: Path,
        subtitle_ass_path: Path | None,
    ) -> Path:
        """Render a 720-long-edge, current-plan proxy with burned ASS captions."""
        inputs = self.build_exact_preview_inputs(composition_plan=composition_plan)
        if not inputs.composition_plan.items:
            raise FinalRenderError("Exact preview has no composable clips. Restore missing source media and retry.")
        if composition_plan.width >= composition_plan.height:
            width, height = 720, max(2, round((composition_plan.height * 720 / composition_plan.width) / 2) * 2)
        else:
            width, height = max(2, round((composition_plan.width * 720 / composition_plan.height) / 2) * 2), 720
        proxy_renderer = replace(
            self, video_width=width, video_height=height,
            video_fps=f"{composition_plan.fps_num}/{composition_plan.fps_den}",
            video_sar=composition_plan.sample_aspect_ratio,
        )
        return proxy_renderer.render_timeline_to_mp4(
            project_id=project_id,
            timeline=proxy_renderer._timeline_from_plan(composition_plan=inputs.composition_plan, timeline_context=timeline_context),
            output_path=output_path,
            subtitle_ass_path=subtitle_ass_path,
            composition_plan=inputs.composition_plan,
            proxy_profile=True,
        )

    def _render_composition_plan_to_mp4(
        self,
        *,
        project_id: str,
        composition_plan: CompositionPlan,
        timeline_context: dict[str, Any],
        output_path: Path,
        subtitle_file_path: Path | None,
        subtitle_ass_path: Path | None,
        proxy_profile: bool,
    ) -> Path:
        """Render the canonical plan directly; never sequentially concatenate it."""
        if not composition_plan.items:
            raise FinalRenderError("Timeline has no composable clips to render.")
        generated_ass: Path | None = None
        verify_output_sources(store=self.store, project_id=project_id, timeline=timeline_context)
        source_paths: list[tuple[Path, bool, bool]] = []
        source_indices: dict[str, int] = {}
        track_overlay_indices: dict[str, int] = {}
        audio_items = []
        for item in composition_plan.items:
            if item.track_type == "overlay":
                # Overlay items are represented in the canonical plan but need
                # a visual source.  Fail closed rather than silently omit one.
                if not item.asset_uri:
                    raise FinalRenderError("Exact preview overlay source is missing. Restore it and retry.")
                source = self._resolve_generic_asset_uri(project_id=project_id, asset_uri=item.asset_uri)
                if not source.is_file():
                    raise FinalRenderError(f"Exact preview source is missing: '{source}'. Restore or re-import it and retry.")
                is_image = source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
                if not is_image and not self._has_visual_stream(source):
                    raise FinalRenderError("Exact preview overlay source must be a local image or video. Restore it and retry.")
                track_overlay_indices[item.clip_id] = len(source_paths)
                source_indices[item.clip_id] = len(source_paths)
                source_paths.append((source, is_image, False))
                continue
            elif item.track_type == "narration":
                source = self._resolve_narration_clip_source(
                    project_id=project_id, timeline=timeline_context,
                    clip={"asset_uri": item.asset_uri, "start_sec": item.start_sec, "end_sec": item.end_sec},
                ).path
                audio_items.append(item)
                should_loop = False
            elif item.track_type == "broll":
                source = self._resolve_generic_asset_uri(project_id=project_id, asset_uri=str(item.asset_uri or ""))
                controls = normalize_media_controls(item.media_controls, media_kind="broll", duration_sec=max(item.end_sec - item.start_sec, 0.001))
                available_source_window = min(self._probe_media_duration(source), item.source_out_sec) - item.source_in_sec
                if available_source_window <= 0:
                    raise FinalRenderError("B-roll source bounds are outside the available media. Adjust trim or source controls.")
                if available_source_window < item.end_sec - item.start_sec and not controls["loop"] and not controls["pad"]:
                    raise FinalRenderError("B-roll source is shorter than its timeline window. Enable loop or pad to preserve timeline duration.")
                if controls["preserve_source_audio"]:
                    audio_items.append(item)
                should_loop = controls["loop"]
            elif item.track_type in {"bgm", "sfx"}:
                source = self._resolve_generic_asset_uri(project_id=project_id, asset_uri=str(item.asset_uri or ""))
                audio_items.append(item)
                should_loop = item.track_type == "bgm"
            else:
                continue
            if not source.is_file():
                raise FinalRenderError(f"Exact preview source is missing: '{source}'. Restore or re-import it and retry.")
            source_indices[item.clip_id] = len(source_paths)
            source_paths.append((source, False, should_loop))
        export_overlay_indices: dict[int, int] = {}
        for overlay_index, overlay in enumerate(composition_plan.export_overlays):
            asset_uri = str(overlay.get("asset_uri") or "")
            asset_id = str(overlay.get("asset_id") or "")
            if not asset_uri and asset_id:
                asset_uri = f"local://projects/{project_id}/assets/{asset_id}"
            if not asset_uri:
                continue
            try:
                source = self._resolve_generic_asset_uri(project_id=project_id, asset_uri=asset_uri)
            except FinalRenderError:
                raise FinalRenderError("Exact preview export overlay source is unavailable. Restore it and retry.") from None
            if not source.is_file():
                raise FinalRenderError("Exact preview export overlay source is missing. Restore it and retry.")
            export_overlay_indices[overlay_index] = len(source_paths)
            source_paths.append((source, source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}, False))
        graph = self.build_plan_filter_graph(
            composition_plan=composition_plan, source_indices=source_indices,
            export_overlay_indices=export_overlay_indices,
            track_overlay_indices=track_overlay_indices,
        )
        duration = max(composition_plan.duration_sec, 0.001)
        graph += ";" + self.build_plan_audio_filter_graph(composition_plan=composition_plan, source_indices=source_indices)
        video_label = "vout"
        if subtitle_file_path is not None and subtitle_ass_path is None:
            generated_ass = self.convert_legacy_subtitle_to_ass(
                subtitle_file_path=subtitle_file_path, output_dir=output_path.parent
            )
            subtitle_ass_path = generated_ass
        if subtitle_ass_path is not None:
            escaped = subtitle_ass_path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
            graph += f";[vout]subtitles=filename='{escaped}'[vburned]"
            video_label = "vburned"
        sar = composition_plan.sample_aspect_ratio.replace(":", "/")
        graph += f";[{video_label}]setsar={sar},setpts=PTS-STARTPTS[vfinal]"
        video_label = "vfinal"
        command = [self.ffmpeg_binary, "-y"]
        for path, is_image, should_loop in source_paths:
            if should_loop:
                command += ["-stream_loop", "-1"]
            if is_image:
                command += ["-loop", "1", "-framerate", str(self.video_fps)]
            command += ["-i", str(path)]
        command += [
            "-filter_complex", graph, "-map", f"[{video_label}]", "-map", "[aout]",
            "-r", str(self.video_fps), "-c:v", "libx264", "-bf", "0", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-t", str(duration),
            "-movflags", "+faststart" if proxy_profile else "+faststart",
            "-avoid_negative_ts", "disabled", "-muxpreload", "0", "-muxdelay", "0",
            "-metadata:s:v:0", f"rotate={composition_plan.rotation}",
            str(output_path),
        ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = self._run(command)
        finally:
            if generated_ass is not None:
                generated_ass.unlink(missing_ok=True)
        if result.returncode != 0:
            raise FinalRenderError(f"ffmpeg failed rendering canonical composition: {result.stderr[-800:]}")
        return output_path

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

    def convert_legacy_subtitle_to_ass(self, *, subtitle_file_path: Path, output_dir: Path) -> Path:
        """Convert session-less SRT/WebVTT-style input to the renderer's ASS input."""
        source = Path(subtitle_file_path)
        if not source.is_file():
            raise FinalRenderError("Legacy subtitle artifact is missing; regenerate subtitles before final render.")
        output_dir.mkdir(parents=True, exist_ok=True)
        ass_path = output_dir / f".legacy_subtitle_{uuid.uuid4().hex}.ass"
        result = self._run([self.ffmpeg_binary, "-y", "-i", str(source), "-f", "ass", str(ass_path)])
        if result.returncode != 0 or not ass_path.is_file():
            ass_path.unlink(missing_ok=True)
            raise FinalRenderError(f"Unable to convert legacy subtitle artifact to ASS: {result.stderr[-800:]}")
        return ass_path

    def _has_visual_stream(self, path: Path) -> bool:
        """Accept non-image overlays only when ffprobe confirms a video stream."""
        try:
            result = subprocess.run(
                [
                    self.ffprobe_binary,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise FinalRenderError("Unable to inspect overlay media. Install/configure ffprobe.") from exc
        return result.returncode == 0 and result.stdout.strip() == "video"

    def _probe_media_duration(self, path: Path) -> float:
        try:
            result = subprocess.run(
                [
                    self.ffprobe_binary,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=min(self.render_timeout_seconds, 60),
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise FinalRenderError("Unable to inspect B-roll duration. Install/configure ffprobe.") from exc
        if result.returncode != 0:
            raise FinalRenderError(f"Unable to inspect B-roll duration for '{path}': {result.stderr[-800:]}")
        try:
            duration = float(result.stdout.strip())
        except ValueError as exc:
            raise FinalRenderError(f"B-roll source has no readable duration: '{path}'.") from exc
        if duration <= 0:
            raise FinalRenderError(f"B-roll source has no usable duration: '{path}'.")
        return duration

    def _resolve_narration_clip_source(
        self, *, project_id: str, timeline: dict[str, Any], clip: dict[str, Any]
    ) -> ResolvedClipSource:
        try:
            return resolve_narration_clip_source(store=self.store, project_id=project_id, timeline=timeline, clip=clip)
        except TimelineClipSourceError as exc:
            raise FinalRenderError(str(exc)) from exc

    def _resolve_broll_clip_source(self, *, project_id: str, clip: dict[str, Any]) -> ResolvedClipSource:
        try:
            return resolve_broll_clip_source(store=self.store, project_id=project_id, clip=clip)
        except (TimelineClipSourceError, KeyError, OSError, ValueError) as exc:
            raise FinalRenderError(
                f"Unable to resolve B-roll media for '{clip.get('asset_uri')}'. Re-select or re-import the asset."
            ) from exc

    def _resolve_generic_asset_uri(self, *, project_id: str, asset_uri: str) -> Path:
        try:
            return resolve_generic_asset_uri(store=self.store, project_id=project_id, asset_uri=asset_uri)
        except (TimelineClipSourceError, KeyError, OSError, ValueError) as exc:
            raise FinalRenderError(
                f"Unable to resolve media asset '{asset_uri}'. Re-select or re-import the asset."
            ) from exc

    def _extract_segment(self, *, source: ResolvedClipSource, output_path: Path, video: bool, media_controls: dict[str, Any] | None = None) -> None:
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
            controls = normalize_media_controls(media_controls, media_kind="broll", duration_sec=float(output_duration_sec or 0.001))
            source_start_sec = float(source.trim_start_sec or 0.0) + float(controls.get("in_sec", 0.0)) + controls["trim_start_sec"]
            if source_start_sec:
                command = [self.ffmpeg_binary, "-y", "-ss", str(source_start_sec)] + command[2:]
            if not controls["loop"]:
                command = [item for index, item in enumerate(command) if not (item == "-stream_loop" or (index and command[index - 1] == "-stream_loop"))]
            available_duration_sec = self._probe_media_duration(source.path) - source_start_sec
            if "out_sec" in controls:
                available_duration_sec = min(available_duration_sec, float(controls["out_sec"]) - source_start_sec)
            if available_duration_sec <= 0:
                raise FinalRenderError(f"B-roll trim starts after the source ends: '{source.path}'. Reduce trim_start_sec.")
            needs_padding = bool(
                output_duration_sec is not None
                and not controls["loop"]
                and float(output_duration_sec) > available_duration_sec
            )
            if needs_padding and not controls["pad"]:
                raise FinalRenderError(
                    "B-roll source is shorter than its timeline window. Enable loop or pad to preserve timeline duration."
                )
            if controls["fit"] == "crop":
                video_filter = f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=increase,crop={self.video_width}:{self.video_height},setsar={self.video_sar.replace(':', '/')}"
            else:
                video_filter = f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=decrease,pad={self.video_width}:{self.video_height}:(ow-iw)/2:(oh-ih)/2,setsar={self.video_sar.replace(':', '/')}"
            if needs_padding:
                video_filter += f",tpad=stop_mode=add:stop_duration={float(output_duration_sec) - available_duration_sec}"
            command += [
                "-vf",
                video_filter,
                "-r",
                str(self.video_fps),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
            ]
            if controls["preserve_source_audio"]:
                command += ["-map", "0:v:0", "-map", "0:a:0?", "-c:a", "aac", "-ar", "48000", "-ac", "2"]
            else:
                command += ["-an"]
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
            if not Path(self.overlay_font_file).is_file():
                raise FinalRenderError(
                    f"Overlay font is missing: '{self.overlay_font_file}'. Install the font or set VIDEOBOX_OVERLAY_FONT."
                )
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
        composition_plan: CompositionPlan | None = None,
        proxy_profile: bool = False,
    ) -> Path:
        if composition_plan is not None:
            plan_renderer = self if proxy_profile else replace(
                self,
                video_width=composition_plan.width,
                video_height=composition_plan.height,
                video_fps=f"{composition_plan.fps_num}/{composition_plan.fps_den}",
                video_sar=composition_plan.sample_aspect_ratio,
            )
            return plan_renderer._render_composition_plan_to_mp4(
                project_id=project_id, composition_plan=composition_plan, timeline_context=timeline,
                output_path=output_path, subtitle_file_path=subtitle_file_path,
                subtitle_ass_path=subtitle_ass_path, proxy_profile=proxy_profile,
            )
        verify_output_sources(store=self.store, project_id=project_id, timeline=timeline)
        # Keep extraction on the final-render path now so source/timeline
        # shapes are validated by its existing regression suite.  The proxy
        # renderer is deliberately not introduced in this task.
        inputs = self.build_final_render_inputs(
            composition_plan=composition_plan or self.extract_composition_plan(timeline=timeline)
        )
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
                if composition_plan is not None and str(clip.get("asset_uri") or "").startswith("local://projects/"):
                    source = ResolvedClipSource(
                        path=source.path,
                        trim_start_sec=float(clip.get("source_in_sec") or 0.0),
                        trim_duration_sec=float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0)),
                        target_duration_sec=float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0)),
                    )
                segment_path = work_dir / f"narration_{index:03d}.wav"
                self._extract_segment(source=source, output_path=segment_path, video=False)
                narration_segment_paths.append(segment_path)
            narration_path = work_dir / "narration_full.wav"
            self._concat(segment_paths=narration_segment_paths, output_path=narration_path, work_dir=work_dir)
            report_progress(25)

            broll_segment_paths = []
            preserve_broll_source_audio = all(
                normalize_media_controls(
                    clip.get("media_controls"),
                    media_kind="broll",
                    duration_sec=max(float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0)), 0.001),
                )["preserve_source_audio"]
                for clip in broll_clips
            )
            for index, clip in enumerate(broll_clips, start=1):
                source = self._resolve_broll_clip_source(project_id=project_id, clip=clip)
                segment_path = work_dir / f"broll_{index:03d}.mp4"
                self._extract_segment(source=source, output_path=segment_path, video=True, media_controls=clip.get("media_controls") if isinstance(clip.get("media_controls"), dict) else None)
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
            if preserve_broll_source_audio:
                mixed_path = work_dir / "audio_with_broll_source.wav"
                command = [
                    self.ffmpeg_binary,
                    "-y",
                    "-i",
                    str(narration_path),
                    "-i",
                    str(video_path),
                    "-filter_complex",
                    "[0:a][1:a]amix=inputs=2:duration=first[aout]",
                    "-map",
                    "[aout]",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-c:a",
                    "pcm_s16le",
                    str(mixed_path),
                ]
                result = self._run(command)
                if result.returncode != 0:
                    raise FinalRenderError(f"ffmpeg failed mixing B-roll source audio: {result.stderr[-800:]}")
                audio_path = mixed_path
            if bgm_clips:
                bgm_source = self._resolve_generic_asset_uri(
                    project_id=project_id, asset_uri=str(bgm_clips[0].get("asset_uri") or "")
                )
                mixed_path = work_dir / "audio_with_bgm.wav"
                bgm_clip = bgm_clips[0]
                bgm_duration = float(bgm_clip.get("end_sec", 0.0)) - float(bgm_clip.get("start_sec", 0.0))
                bgm_controls = normalize_media_controls(bgm_clip.get("media_controls"), media_kind="audio", duration_sec=max(bgm_duration, 0.001))
                bgm_filter = f"volume={bgm_controls['gain_db']}dB"
                if bgm_controls["fade_in_sec"]:
                    bgm_filter += f",afade=t=in:st=0:d={bgm_controls['fade_in_sec']}"
                if bgm_controls["fade_out_sec"]:
                    bgm_filter += f",afade=t=out:st={max(0.0, bgm_duration - bgm_controls['fade_out_sec'])}:d={bgm_controls['fade_out_sec']}"
                mix_filter = f"[1:a]{bgm_filter}[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]"
                if bgm_controls["ducking"]:
                    mix_filter = f"[1:a]{bgm_filter}[bgm];[bgm][0:a]sidechaincompress=threshold=0.05:ratio=8[ducked];[0:a][ducked]amix=inputs=2:duration=first[aout]"
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
                    mix_filter,
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
                    controls = normalize_media_controls(clip.get("media_controls"), media_kind="audio", duration_sec=max(duration_sec, 0.001))
                    sfx_filter = f"[{index}:a]volume={controls['gain_db']}dB,atrim=duration={duration_sec}"
                    if controls["fade_in_sec"]:
                        sfx_filter += f",afade=t=in:st=0:d={controls['fade_in_sec']}"
                    if controls["fade_out_sec"]:
                        sfx_filter += f",afade=t=out:st={max(0.0, duration_sec - controls['fade_out_sec'])}:d={controls['fade_out_sec']}"
                    filter_parts.append(f"{sfx_filter},adelay={start_ms}|{start_ms}[sfx{index}]")
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
                "-c:v", "libx264" if (subtitle_ass_path is not None or proxy_profile) else "copy",
                "-c:a",
                "aac",
            ]
            if proxy_profile:
                command += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-metadata:s:v:0", f"rotate={inputs.composition_plan.rotation}"]
            for note in output_warning_notes(timeline):
                command += ["-metadata", f"comment={note}"]
            command += [
                "-shortest",
                str(output_path),
            ]
            result = self._run(command)
            if result.returncode != 0:
                raise FinalRenderError(f"ffmpeg failed muxing final output: {result.stderr[-800:]}")
            report_progress(100)

        return output_path


__all__ = ["FfmpegFinalRenderer", "FinalRenderError"]
