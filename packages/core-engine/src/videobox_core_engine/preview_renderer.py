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


class PreviewRenderer:
    def build_preview_payload(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
    ) -> dict[str, Any]:
        player_html = self._build_player_html(project_id=project_id, timeline=timeline)
        return {
            "project_id": project_id,
            "timeline_id": timeline["timeline_id"],
            "artifact_kind": "playable_html_preview",
            "clips": [
                {
                    "track_id": track["track_id"],
                    "track_type": track["track_type"],
                    "clip_count": len(track.get("clips", [])),
                }
                for track in timeline.get("tracks", [])
            ],
            "player_html": player_html,
            "notes": [
                "Playable local HTML preview generated for operator review.",
                "This preview simulates timing and captions instead of final media rendering.",
            ],
        }

    def _build_player_html(self, *, project_id: str, timeline: dict[str, Any]) -> str:
        tracks = timeline.get("tracks", [])
        review_status = timeline.get("review_status", "approved")
        tts_segments = {
            str(item.get("target_segment_id") or "").strip()
            for item in timeline.get("applied_recommendations", [])
            if isinstance(item, dict)
            and _canonical_recommendation_type(item.get("recommendation_type")) == "tts_replacement"
            and _normalize_boolish(item.get("auto_apply_allowed"))
            and not _normalize_boolish(item.get("review_required"))
        }
        track_items = "".join(
            f"<li><strong>{escape(str(track['track_type']))}</strong>: {len(track.get('clips', []))} clips</li>"
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
            if track.get("track_type") == "narration"
            for clip in track.get("clips", [])
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
            return str(clip.get("asset_uri") or "")
        return str(timeline.get("narration_source_uri") or clip.get("asset_uri") or "")
