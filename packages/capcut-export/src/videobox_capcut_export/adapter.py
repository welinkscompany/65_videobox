from __future__ import annotations

from typing import Any


def _normalize_boolish(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    if isinstance(value, bool):
        return value
    return False


def _canonical_recommendation_type(value: object) -> str:
    return str(value or "").strip().lower()


def _canonical_track_type(value: object) -> str:
    return str(value or "").strip().lower()


def _canonical_source_uri(value: object) -> str:
    return str(value or "").strip()


VALID_EXPORT_TRACK_TYPES = {"narration", "broll", "bgm", "sfx"}


# 소리만 내는 레인. 꺼 두었으면 **넘기지 않는다** -- 이 만듦새에는 음소거를
# 표현할 칸이 없어서(`track_name`·`track_role`·`source_uri`·`segments`뿐)
# 넣으면 대표가 지운 소리가 캡컷에서 되살아난다. `broll`은 여기 없다:
# 음소거해도 그림은 남겨야 하므로 트랙을 빼면 안 된다.
SOUND_ONLY_TRACK_TYPES = {"narration", "bgm", "sfx"}


def dropped_track_types(timeline: dict[str, Any]) -> set[str]:
    """캡컷으로 넘기지 않을 레인(`track_states.py`).

    **캡컷으로 나가는 길이 둘이라 규칙을 여기 하나만 둔다** -- 매니페스트
    (`CapCutExportAdapter`)와 실제 초안(`PyCapCutRealExportAdapter`). 2026-08-23에
    한쪽만 고쳐 놓고 "캡컷이 지운 것을 되살리지 않는다"고 적었는데, 고친 쪽은
    UI가 더 이상 안 부르는 옛 길이었고 실제 초안은 그대로였다.
    """
    from videobox_core_engine.track_states import hidden_lanes, muted_lanes

    return set(hidden_lanes(timeline)) | (set(muted_lanes(timeline)) & SOUND_ONLY_TRACK_TYPES)


class CapCutExportAdapter:
    def _dropped_track_types(self, timeline: dict[str, Any]) -> set[str]:
        return dropped_track_types(timeline)

    def _promptable_tracks(self, timeline: dict[str, Any]) -> list[dict[str, Any]]:
        promptable_tracks: list[dict[str, Any]] = []
        dropped = self._dropped_track_types(timeline)
        for track in timeline.get("tracks", []):
            if not isinstance(track, dict):
                continue
            track_type = _canonical_track_type(track.get("track_type"))
            if track_type not in VALID_EXPORT_TRACK_TYPES:
                continue
            if track_type in dropped:
                continue
            clips = track.get("clips", [])
            if not isinstance(clips, list):
                continue
            valid_clips = [clip for clip in clips if isinstance(clip, dict)]
            promptable_tracks.append(
                {
                    **track,
                    "track_type": track_type,
                    "clips": valid_clips,
                }
            )
        return promptable_tracks

    def build_payload(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        subtitle_file_uri: str | None = None,
    ) -> dict[str, Any]:
        tracks = self._promptable_tracks(timeline)
        # **내용이 들어오는 길이 셋이다**: 트랙, 자막 파일, 글자 오버레이.
        # 완성본에서 자막만 고치고 오버레이를 놓쳐 같은 실패를 두 번 냈다.
        dropped = self._dropped_track_types(timeline)
        if "caption" in dropped:
            subtitle_file_uri = None
        export_overlays = [] if "overlay" in dropped else timeline.get("export_overlays", [])
        canonical_subtitle_file_uri = _canonical_source_uri(subtitle_file_uri) if subtitle_file_uri else None
        return {
            "project_id": project_id,
            "timeline_id": timeline["timeline_id"],
            "export_type": "capcut",
            "adapter": "capcut_v1_port",
            "subtitle_file_uri": canonical_subtitle_file_uri,
            "tracks": tracks,
            "review_flags": timeline.get("review_flags", []),
            "capcut_tracks": self._build_capcut_tracks(
                tracks=tracks,
                narration_source_uri=_canonical_source_uri(timeline.get("narration_source_uri")),
                subtitle_file_uri=canonical_subtitle_file_uri,
                export_overlays=export_overlays,
                narration_override_segments={
                    str(item.get("target_segment_id") or "").strip()
                    for item in timeline.get("applied_recommendations", [])
                    if isinstance(item, dict)
                    and _canonical_recommendation_type(item.get("recommendation_type")) == "tts_replacement"
                    and _normalize_boolish(item.get("auto_apply_allowed"))
                    and not _normalize_boolish(item.get("review_required"))
                },
            ),
            "notes": [
                "CapCut export manifest generated for local post-editing handoff.",
            ],
        }

    def _build_capcut_tracks(
        self,
        *,
        tracks: list[dict[str, Any]],
        narration_source_uri: str,
        subtitle_file_uri: str | None,
        export_overlays: Any,
        narration_override_segments: set[str],
    ) -> list[dict[str, Any]]:
        capcut_tracks: list[dict[str, Any]] = []
        deferred_audio_tracks: list[dict[str, Any]] = []

        for track in tracks:
            track_type = _canonical_track_type(track.get("track_type"))
            if track_type == "narration":
                capcut_tracks.append(
                    self._build_clip_track(
                        {**track, "source_uri": narration_source_uri},
                        track_name="voiceover",
                        track_role="audio",
                        override_segment_ids=narration_override_segments,
                    )
                )
            elif track_type == "broll":
                capcut_tracks.append(
                    self._build_clip_track(
                        track,
                        track_name="broll",
                        track_role="video",
                    )
                )
            elif track_type == "bgm":
                deferred_audio_tracks.append(
                    self._build_clip_track(
                        track,
                        track_name="bgm",
                        track_role="audio",
                    )
                )
            elif track_type == "sfx":
                deferred_audio_tracks.append(
                    self._build_clip_track(
                        track,
                        track_name="sfx",
                        track_role="audio",
                    )
                )

        if subtitle_file_uri:
            capcut_tracks.append(
                {
                    "track_name": "subtitle",
                    "track_role": "text",
                    "source_track_id": None,
                    "source_uri": _canonical_source_uri(subtitle_file_uri),
                    "segments": [],
                }
            )

        if isinstance(export_overlays, list):
            overlay_segments = [
                {
                    "overlay_type": str(item.get("overlay_type") or "").strip(),
                    "text": str(item.get("text") or "").strip(),
                    "start_sec": float(item.get("start_sec") or 0.0),
                    "end_sec": float(item.get("end_sec") or 0.0),
                }
                for item in export_overlays
                if isinstance(item, dict)
                and str(item.get("overlay_type") or "").strip()
                and str(item.get("text") or "").strip()
            ]
            ordered_overlay_types: list[str] = []
            for segment in overlay_segments:
                overlay_type = segment["overlay_type"]
                if overlay_type not in ordered_overlay_types:
                    ordered_overlay_types.append(overlay_type)
            for overlay_type in ordered_overlay_types:
                segments = [segment for segment in overlay_segments if segment["overlay_type"] == overlay_type]
                capcut_tracks.append(
                    {
                        "track_name": overlay_type,
                        "track_role": "text",
                        "source_track_id": None,
                        "segments": segments,
                    }
                )

        capcut_tracks.extend(deferred_audio_tracks)
        return capcut_tracks

    def _build_clip_track(
        self,
        track: dict[str, Any],
        *,
        track_name: str,
        track_role: str,
        override_segment_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        if track_name == "broll":
            return self._build_broll_track(track, track_name=track_name, track_role=track_role)

        segments = []
        track_source_uri = _canonical_source_uri(track.get("source_uri"))
        effective_override_segment_ids = override_segment_ids or set()
        for clip in track.get("clips", []):
            start_sec = float(clip.get("start_sec") or 0.0)
            end_sec = float(clip.get("end_sec") or 0.0)
            source_uri = track_source_uri or _canonical_source_uri(clip.get("asset_uri"))
            if str(clip.get("segment_id") or "").strip() in effective_override_segment_ids:
                source_uri = _canonical_source_uri(clip.get("asset_uri") or source_uri)
            segments.append(
                {
                    "clip_id": str(clip.get("clip_id") or ""),
                    "segment_id": str(clip.get("segment_id") or "").strip(),
                    "source_uri": source_uri,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "duration_sec": max(0.0, end_sec - start_sec),
                    "clip_type": str(clip.get("clip_type") or ""),
                    "recommendation_id": clip.get("recommendation_id"),
                }
            )
        return {
            "track_name": track_name,
            "track_role": track_role,
            "source_track_id": track.get("track_id"),
            "segments": segments,
        }

    def _build_broll_track(
        self,
        track: dict[str, Any],
        *,
        track_name: str,
        track_role: str,
    ) -> dict[str, Any]:
        segments = []
        clips_by_segment: dict[str, list[dict[str, Any]]] = {}
        for clip in track.get("clips", []):
            segment_id = str(clip.get("segment_id") or "").strip()
            clips_by_segment.setdefault(segment_id, []).append(clip)

        segment_windows = sorted(
            (
                (
                    min(float(item.get("start_sec") or 0.0) for item in clips),
                    segment_id,
                    sorted(
                        clips,
                        key=lambda item: (
                            float(item.get("start_sec") or 0.0),
                            float(item.get("end_sec") or 0.0),
                            str(item.get("clip_id") or ""),
                        ),
                    ),
                )
                for segment_id, clips in clips_by_segment.items()
            ),
            key=lambda item: (item[0], item[1]),
        )

        for window_start_sec, segment_id, sorted_clips in segment_windows:
            window_end_sec = max(float(item.get("end_sec") or 0.0) for item in sorted_clips)
            remaining_sec = max(0.0, window_end_sec - window_start_sec)
            next_start_sec = window_start_sec

            for index, clip in enumerate(sorted_clips):
                if remaining_sec <= 0:
                    break
                source_duration_value = clip.get("source_duration_sec")
                if source_duration_value is None:
                    remaining_clips = max(1, len(sorted_clips) - index)
                    source_duration_sec = remaining_sec / remaining_clips
                else:
                    source_duration_sec = float(source_duration_value)
                planned_duration_sec = min(source_duration_sec, remaining_sec)
                planned_end_sec = next_start_sec + planned_duration_sec
                segments.append(
                    {
                        "clip_id": str(clip.get("clip_id") or ""),
                        "segment_id": segment_id,
                        "source_uri": _canonical_source_uri(clip.get("asset_uri")),
                        "start_sec": float(clip.get("start_sec") or 0.0),
                        "end_sec": float(clip.get("end_sec") or 0.0),
                        "planned_start_sec": next_start_sec,
                        "planned_end_sec": planned_end_sec,
                        "duration_sec": max(0.0, float(clip.get("end_sec") or 0.0) - float(clip.get("start_sec") or 0.0)),
                        "planned_duration_sec": planned_duration_sec,
                        "clip_type": str(clip.get("clip_type") or ""),
                        "recommendation_id": clip.get("recommendation_id"),
                    }
                )
                next_start_sec = planned_end_sec
                remaining_sec = max(0.0, window_end_sec - next_start_sec)

        return {
            "track_name": track_name,
            "track_role": track_role,
            "source_track_id": track.get("track_id"),
            "placement_mode": "sequential_fill",
            "allow_empty_gaps": True,
            "segments": segments,
        }
