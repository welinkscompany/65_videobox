from __future__ import annotations

from typing import Any


class PreviewRenderer:
    def build_preview_payload(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "timeline_id": timeline["timeline_id"],
            "artifact_kind": "mock_preview_bundle",
            "clips": [
                {
                    "track_id": track["track_id"],
                    "track_type": track["track_type"],
                    "clip_count": len(track.get("clips", [])),
                }
                for track in timeline.get("tracks", [])
            ],
            "notes": [
                "Preview render is a structured local artifact in this phase.",
                "It is intentionally explicit about being a mock render bundle.",
            ],
        }
