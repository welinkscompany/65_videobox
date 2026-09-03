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
from pycapcut import FilterType, TransitionType

from videobox_capcut_export.capcut_looks import capcut_filter_name
from videobox_core_engine.canonical_track import canonical_track_type
from videobox_core_engine.media_controls import normalize_media_controls
from videobox_core_engine.transitions import TRANSITION_TYPES, normalize_transition
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

# 우리 여섯(실제로는 여덟, 방향 짝 포함) 전환 이름을 캡컷 무료 전환으로 옮긴다.
#
# **이 대응은 이름으로만 골랐다 — 실제로 캡컷에서 눈으로 확인하지 않았다.**
# `implementation-plan.ko.md` §4.1.1이 이미 경고한 그대로다: 전환 1,137개
# 중 985개가 유료라 무료 152개 안에서 골라야 안전하고, 그 무료 목록의
# 이름은 전부 중국어라(`Cutout_Flip`처럼 영어인 것도 소수 있지만 우리
# 여섯과 안 겹친다) "이름이 뜻하는 움직임"으로만 짝지었다. `fade`/`wipeleft`/
# `wiperight`는 이름이 사실상 직역이라 확신이 높고, `slideup`/`slidedown`/
# `circleopen`은 상대적으로 확신이 낮다 — 실제로 캡컷을 열어 봐야 안다
# (`docs/handoffs/2026-08-22-videobox-scene-transitions-and-the-frame-rate-trap.ko.md`
# 가 "생김새 판단은 owner 몫이다"라고 이미 적어 둔 것과 같은 이유).
_CAPCUT_TRANSITION_TYPE_BY_KEY: dict[str, TransitionType] = {
    "fade": TransitionType["叠化"],  # 겹쳐 넘기기(dissolve/cross-fade)
    "fadeblack": TransitionType["闪黑"],  # 검게 지나가기(flash to black)
    "dissolve": TransitionType["色彩溶解"],  # 알갱이로 흩어지며 녹아 넘기기
    "wipeleft": TransitionType["向左擦除"],  # 왼쪽으로 쓸어내기 — 이름이 직역
    "wiperight": TransitionType["向右擦除"],  # 오른쪽으로 쓸어내기 — 이름이 직역
    "slideup": TransitionType["向上"],  # 위쪽 방향(정확한 밀기 여부 미확인)
    "slidedown": TransitionType["向下"],  # 아래쪽 방향(정확한 밀기 여부 미확인)
    "circleopen": TransitionType["圆形遮罩"],  # 원형으로 열리는 마스크
}

# 위 대응이 우리 전환 카탈로그와 정확히 짝을 이루는지 부팅 시점에 확인한다.
# 카탈로그에 새 값을 추가하고 여기를 안 고치면, 그 전환은 화면·렌더러에는
# 있는데 캡컷 내보내기에서만 조용히 빠진다 — 그 대신 지금 확실하게 죽는다.
if set(_CAPCUT_TRANSITION_TYPE_BY_KEY) != set(TRANSITION_TYPES):
    raise RuntimeError(
        "pycapcut_adapter's transition map is out of sync with "
        "videobox_core_engine.transitions.TRANSITION_CATALOG."
    )


def _with_look(segment: VideoSegment, controls: dict[str, Any]) -> VideoSegment:
    """고른 색감을 캡컷 쪽 이름표로 얹는다.

    **B-roll 조각을 만드는 자리가 둘이다**(이어 붙이는 쪽과 한 번만 놓는 쪽).
    이 저장소는 그런 짝을 한쪽만 고쳐 같은 결함을 두 번 낸 적이 있어서,
    얹는 일을 여기 한 군데로 모아 둔다.
    """
    name = capcut_filter_name(controls)
    if name is not None:
        segment.add_filter(FilterType[name])
    return segment


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


def _clip_playback_rate(clip: dict[str, Any]) -> float:
    rate = float(clip.get("playback_rate", 1.0))
    if not math.isfinite(rate) or rate <= 0:
        raise PyCapCutExportError("CapCut clip playback_rate must be a positive finite number.")
    return rate


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
        previous_broll_segment: VideoSegment | None = None
        for clip in broll_clips:
            previous_broll_segment = self._add_broll_segment(
                script=script,
                project_id=project_id,
                clip=clip,
                previous_segment=previous_broll_segment,
                warnings=warnings,
            )
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
        capcut_style = TextStyle(
            size=style.font_size_px / 6, color=(red, green, blue), align=alignment, auto_wrapping=True,
            bold=style.bold, italic=style.italic,
            # pycapcut이 안에서 0.05를 곱해 CapCut 자체 단위로 맞춘다(주석 "定义与CapCut中一致") --
            # 여기서 미리 나누지 않는다. 나누면 두 번 줄어든다.
            letter_spacing=style.letter_spacing_px,
        )
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
        # 꺼 둔 레인은 초안에 싣지 않는다(`videobox_capcut_export.adapter`의
        # `dropped_track_types`가 규칙을 갖고 있다). 여기가 **대표가 실제로 여는
        # 초안**을 만드는 자리라, 이걸 빠뜨리면 화면에서 뺀 영상이 캡컷에서
        # 되살아난다.
        from videobox_capcut_export.adapter import dropped_track_types

        dropped = dropped_track_types(timeline)
        for track in timeline.get("tracks", []):
            if not isinstance(track, dict):
                continue
            track_type = canonical_track_type(track.get("track_type"))
            if track_type in dropped:
                continue
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
        playback_rate = _clip_playback_rate(clip)
        target_duration_us = _seconds_to_us(
            resolved.target_duration_sec
            if resolved.target_duration_sec is not None
            else float(clip["end_sec"]) - float(clip["start_sec"])
        )
        if resolved.trim_duration_sec is not None:
            source_duration_us = _seconds_to_us(resolved.trim_duration_sec)
        else:
            source_duration_us = material.duration
        natural_duration_us = min(
            source_duration_us,
            material.duration,
            round(target_duration_us * playback_rate),
        )
        source_timerange = Timerange(
            start=_seconds_to_us(resolved.trim_start_sec),
            duration=natural_duration_us,
        )
        segment = AudioSegment(
            material,
            Timerange(start=placement_start_us, duration=natural_duration_us),
            source_timerange=source_timerange,
            speed=playback_rate,
        )
        script.add_segment(segment, "voiceover")
        padding_duration_us = target_duration_us - round(natural_duration_us / playback_rate)
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
            playback_rate = _clip_playback_rate(clip)
            required_duration_us = max(
                required_duration_us,
                target_duration_us - min(target_duration_us, round(source_duration_us / playback_rate)),
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

    @staticmethod
    def _normalize_export_transition(clip: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return normalize_transition(clip.get("transition"))
        except ValueError as exc:
            raise PyCapCutExportError(f"Invalid scene transition on clip: {exc}") from exc

    def _add_broll_segment(
        self,
        *,
        script: ScriptFile,
        project_id: str,
        clip: dict[str, Any],
        previous_segment: VideoSegment | None,
        warnings: list[str],
    ) -> VideoSegment | None:
        """B-roll 조각 하나를 초안에 놓고, 이 조각의 **마지막** 세그먼트를
        돌려준다 — 다음 조각이 전환을 실어 오면 그 전환을 붙일 자리가
        이것이기 때문이다(`add_transition`은 pycapcut 쪽에서 "앞 조각"에
        건다. 우리 데이터 모델은 반대로 "들어오는 쪽"에 싣는다 -- 방향이
        엇갈려서 여기서 뒤집는다).
        """
        transition = self._normalize_export_transition(clip)
        if transition is not None:
            if previous_segment is None:
                # 첫 B-roll 조각이라 전환을 걸 앞 조각이 없다. 화면·렌더러
                # 에서는 있을 수 있는 값이 이 자리에는 표현할 수 없다는 것을
                # 조용히 넘기지 않는다.
                warnings.append(
                    "a scene transition on the first B-roll clip cannot be represented in CapCut export; skipped"
                )
            else:
                previous_segment.add_transition(
                    _CAPCUT_TRANSITION_TYPE_BY_KEY[transition["type"]],
                    duration=_seconds_to_us(transition["duration_sec"]),
                )
                # `script.add_segment`는 소재 등록(`materials.transitions`)을
                # **넣는 그 순간**의 `segment.transition` 값만 보고 한다. 앞
                # 조각은 이미 놓인 뒤라 그때는 전환이 없었다 -- 지금 뒤늦게
                # 붙였으니 등록도 직접 해야 한다. 안 하면 세그먼트 쪽
                # `extra_material_refs`는 채워지는데 초안 어디에도 그 전환의
                # 실제 정의(`materials.transitions`)가 없어 캡컷이 못 연다.
                if previous_segment.transition not in script.materials:
                    script.materials.transitions.append(previous_segment.transition)
                # 이름으로만 고른 대응이라 실제 캡컷에서 확인 안 됨을 매번 남긴다
                # (모듈 docstring의 `_CAPCUT_TRANSITION_TYPE_BY_KEY` 설명 참고).
                warnings.append(
                    "scene transitions are exported by name match only; verify how each looks in CapCut"
                )
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
        #
        # 배속은 **원본 시간과 화면 시간의 환산비**다. 아래 루프는 화면 시간으로
        # 세므로, 원본이 화면에서 얼마나 버티는지로 한 번 바꿔 두고 그 값으로
        # 자른다. 둘을 섞어 재면 배속을 걸었을 때 길이가 어긋난다.
        speed = float(controls["speed"]) * _clip_playback_rate(clip)
        volume = float(controls["volume"])
        source_available_timeline_us = int(source_available_us / speed)
        if source_available_timeline_us <= 0:
            raise PyCapCutExportError(
                f"B-roll source is too short for the requested speed: {resolved.path}."
            )
        elapsed_us = 0
        last_segment: VideoSegment | None = None
        while elapsed_us < needed_duration_us and controls["loop"]:
            segment_duration_us = min(source_available_timeline_us, needed_duration_us - elapsed_us)
            # `speed`를 함께 주면 pycapcut이 target 길이를 source/speed로 다시
            # 계산한다. 그래서 source에 화면 시간 × 배속을 넣는다.
            segment = _with_look(VideoSegment(
                material,
                Timerange(start=placement_start_us + elapsed_us, duration=segment_duration_us),
                source_timerange=Timerange(start=source_start_us, duration=round(segment_duration_us * speed)),
                speed=speed,
                volume=volume,
            ), controls)
            script.add_segment(segment, "broll")
            last_segment = segment
            elapsed_us += segment_duration_us
        if not controls["loop"]:
            segment_duration_us = min(source_available_timeline_us, needed_duration_us)
            last_segment = _with_look(VideoSegment(
                material,
                Timerange(start=placement_start_us, duration=segment_duration_us),
                source_timerange=Timerange(start=source_start_us, duration=round(segment_duration_us * speed)),
                speed=speed,
                volume=volume,
            ), controls)
            script.add_segment(last_segment, "broll")
            elapsed_us = segment_duration_us
        if elapsed_us >= needed_duration_us:
            return last_segment
        if not controls["pad"]:
            raise PyCapCutExportError(
                "B-roll source is shorter than its timeline window. Enable loop or pad to preserve timeline duration."
            )
        padding_duration_us = needed_duration_us - elapsed_us
        pad_source_duration_us = padding_duration_us + (2 * round(_MICROSECONDS_PER_SECOND / self.video_fps))
        pad_material = VideoMaterial(
            str(self._create_black_pad_material(project_id=project_id, duration_us=pad_source_duration_us))
        )
        # 정지 프레임을 흉내 내는 검은 패드다 -- 다음 조각과 시간상 바로
        # 맞닿는 것은 실제 B-roll 조각이 아니라 이 패드이므로, 다음 전환은
        # (있다면) 이 패드에 걸어야 한다.
        pad_segment = VideoSegment(
            pad_material,
            Timerange(start=placement_start_us + elapsed_us, duration=padding_duration_us),
            source_timerange=Timerange(start=0, duration=padding_duration_us),
        )
        script.add_segment(pad_segment, "broll")
        return pad_segment

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
        playback_rate = _clip_playback_rate(clip)
        source_duration_us = min(round(needed_duration_us * playback_rate), material.duration) or material.duration
        controls = normalize_media_controls(clip.get("media_controls"), media_kind="audio", duration_sec=max(needed_duration_us / _MICROSECONDS_PER_SECOND, 0.001))
        segment = AudioSegment(material, Timerange(start=placement_start_us, duration=needed_duration_us), source_timerange=Timerange(start=0, duration=source_duration_us), speed=playback_rate, volume=10 ** (controls["gain_db"] / 20))
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
