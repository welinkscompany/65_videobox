from __future__ import annotations

from typing import Any


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
        track_items = "".join(
            f"<li><strong>{track['track_type']}</strong>: {len(track.get('clips', []))} clips</li>"
            for track in tracks
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
      <p>Project: {project_id}</p>
      <p>Timeline: {timeline['timeline_id']}</p>
      <p>Review status: {review_status}</p>
      <div class="stage">
        <div>
          <h2>Playable placeholder preview</h2>
          <p>This page is an operator-review preview shell before final media render quality upgrades.</p>
        </div>
      </div>
      <h3>Track summary</h3>
      <ul>{track_items}</ul>
    </div>
  </body>
</html>"""
