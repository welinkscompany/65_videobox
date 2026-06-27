from __future__ import annotations

from typing import Any


class CapCutExportAdapter:
    def build_payload(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        subtitle_file_uri: str | None = None,
    ) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "timeline_id": timeline["timeline_id"],
            "export_type": "capcut",
            "adapter": "capcut_v1_mock",
            "subtitle_file_uri": subtitle_file_uri,
            "tracks": timeline.get("tracks", []),
            "review_flags": timeline.get("review_flags", []),
            "notes": [
                "Mock CapCut payload for local post-editing handoff.",
                "CapCut remains an export target, not the internal source of truth.",
            ],
        }
