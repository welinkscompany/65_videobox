from __future__ import annotations

from html import escape
from typing import Any


def _normalize_boolish(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    if isinstance(value, bool):
        return value
    return False


def _canonical_recommendation_type(value: object) -> str:
    return str(value or "").strip().lower()


def _canonical_review_status(value: object) -> str:
    return str(value or "approved").strip().lower() or "approved"


def _canonical_track_type(value: object) -> str:
    return str(value or "").strip().lower()


def _canonical_source_uri(value: object) -> str:
    return str(value or "").strip()


VALID_PREVIEW_TRACK_TYPES = {"narration", "broll", "bgm"}


class PreviewRenderer:
    def _promptable_tracks(self, timeline: dict[str, Any]) -> list[dict[str, Any]]:
        promptable_tracks: list[dict[str, Any]] = []
        for track in timeline.get("tracks", []):
            if not isinstance(track, dict):
                continue
            track_type = _canonical_track_type(track.get("track_type"))
            if track_type not in VALID_PREVIEW_TRACK_TYPES:
                continue
            clips = track.get("clips", [])
            if not isinstance(clips, list):
                continue
            valid_clips = [clip for clip in clips if isinstance(clip, dict)]
            promptable_tracks.append(
                {
                    "track_id": str(track.get("track_id") or "").strip(),
                    "track_type": track_type,
                    "clips": valid_clips,
                }
            )
        return promptable_tracks

    def build_preview_payload(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
    ) -> dict[str, Any]:
        player_html = self._build_player_html(project_id=project_id, timeline=timeline)
        promptable_tracks = self._promptable_tracks(timeline)
        return {
            "project_id": project_id,
            "timeline_id": timeline["timeline_id"],
            "artifact_kind": "playable_html_preview",
            "clips": [
                {
                    "track_id": track["track_id"],
                    "track_type": track["track_type"],
                    "clip_count": len(track["clips"]),
                }
                for track in promptable_tracks
            ],
            "player_html": player_html,
            "notes": [
                "Playable local HTML preview generated for operator review.",
                "This preview simulates timing and captions instead of final media rendering.",
            ],
        }

    def _build_player_html(self, *, project_id: str, timeline: dict[str, Any]) -> str:
        tracks = self._promptable_tracks(timeline)
        review_status = _canonical_review_status(timeline.get("review_status", "approved"))
        tts_segments = {
            str(item.get("target_segment_id") or "").strip()
            for item in timeline.get("applied_recommendations", [])
            if isinstance(item, dict)
            and _canonical_recommendation_type(item.get("recommendation_type")) == "tts_replacement"
            and _normalize_boolish(item.get("auto_apply_allowed"))
            and not _normalize_boolish(item.get("review_required"))
        }
        track_items = "".join(
            f"<li><strong>{escape(track['track_type'])}</strong>: {len(track['clips'])} clips</li>"
            for track in tracks
        )
        narration_source_items = "".join(
            (
                "<li>"
                f"{escape(str(clip.get('segment_id', '')).strip())}: "
                f"{escape(self._effective_narration_source_uri(timeline=timeline, clip=clip, tts_segments=tts_segments))}"
                "</li>"
            )
            for track in tracks
            if track["track_type"] == "narration"
            for clip in track["clips"]
        )
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>VideoBox Preview {timeline['timeline_id']}</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f4efe6; color: #1f2933; }}
      .frame {{ max-width: 720px; margin: 0 auto; background: white; padding: 1.5rem; border-radius: 16px; }}
      .stage {{ aspect-ratio: 16/9; background: linear-gradient(135deg, #0f172a, #334155); color: white; display: grid; place-items: center; border-radius: 12px; }}
    </style>
  </head>
  <body>
    <div class="frame">
      <h1>VideoBox Local Preview</h1>
      <p>Project: {escape(str(project_id))}</p>
      <p>Timeline: {escape(str(timeline['timeline_id']))}</p>
      <p>Review status: {escape(str(review_status))}</p>
      <div class="stage">
        <div>
          <h2>Playable placeholder preview</h2>
          <p>This page is an operator-review preview shell before final media render quality upgrades.</p>
        </div>
      </div>
      <h3>Track summary</h3>
      <ul>{track_items}</ul>
      <h3>Narration sources</h3>
      <ul>{narration_source_items}</ul>
    </div>
  </body>
</html>"""

    def _effective_narration_source_uri(
        self,
        *,
        timeline: dict[str, Any],
        clip: dict[str, Any],
        tts_segments: set[str],
    ) -> str:
        segment_id = str(clip.get("segment_id") or "").strip()
        if segment_id in tts_segments:
            return _canonical_source_uri(clip.get("asset_uri"))
        return _canonical_source_uri(timeline.get("narration_source_uri") or clip.get("asset_uri"))
