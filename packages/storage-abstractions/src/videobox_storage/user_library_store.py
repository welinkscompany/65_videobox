from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


_BUILT_IN_CAPTION_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "preset_id": "builtin:clean",
        "name": "Clean",
        "scope": "built_in",
        "style": {"font_size": 42, "text_color": "#FFFFFFFF", "font_family": "Noto Sans KR"},
    },
    {
        "preset_id": "builtin:highlight",
        "name": "Highlight",
        "scope": "built_in",
        "style": {"font_size": 46, "text_color": "#FFD54FFF", "font_family": "Noto Sans KR"},
    },
)


class UserLibraryStore:
    """Small user-owned library kept outside individual project artifacts."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "user_library.json"

    def list_caption_presets(self, *, project_id: str) -> list[dict[str, Any]]:
        data = self._read()
        project = data["projects"].get(project_id, {})
        global_presets = list(data["global_presets"].values())
        return deepcopy([*_BUILT_IN_CAPTION_PRESETS, *global_presets, *project.get("presets", {}).values()])

    def get_caption_preset(self, *, project_id: str, preset_id: str) -> dict[str, Any]:
        for preset in self.list_caption_presets(project_id=project_id):
            if preset["preset_id"] == preset_id:
                return preset
        raise KeyError(f"Caption preset not found: {preset_id}")

    def save_caption_preset(self, *, project_id: str, preset_id: str, name: str, style: dict[str, Any], global_scope: bool = False) -> dict[str, Any]:
        if preset_id.startswith("builtin:"):
            raise ValueError("built-in caption presets are immutable")
        expected_prefix = "global:" if global_scope else f"project:{project_id}:"
        if not preset_id.startswith(expected_prefix):
            raise ValueError("preset_id does not match its storage scope")
        preset = {"preset_id": preset_id, "name": name.strip(), "scope": "global" if global_scope else "project", "style": deepcopy(style)}
        if not preset["name"]:
            raise ValueError("name must not be blank")
        data = self._read()
        if global_scope:
            data["global_presets"][preset_id] = preset
        else:
            data["projects"].setdefault(project_id, {"presets": {}, "favorites": [], "recent_preset_ids": []})["presets"][preset_id] = preset
        self._write(data)
        return deepcopy(preset)

    def toggle_favorite(self, *, project_id: str, favorite_id: str, favorite_type: str, enabled: bool) -> dict[str, Any]:
        if not (favorite_id.startswith(f"project:{project_id}:") or favorite_id.startswith("pack:")):
            raise ValueError("favorite_id must be a project or pack canonical ID")
        data = self._read()
        project = data["projects"].setdefault(project_id, {"presets": {}, "favorites": [], "recent_preset_ids": []})
        favorite = {"favorite_id": favorite_id, "favorite_type": favorite_type}
        current = [item for item in project["favorites"] if item["favorite_id"] != favorite_id]
        if enabled:
            current.append(favorite)
        project["favorites"] = current
        self._write(data)
        return {**favorite, "enabled": enabled}

    def list_favorites(self, *, project_id: str) -> list[dict[str, Any]]:
        return deepcopy(self._read()["projects"].get(project_id, {}).get("favorites", []))

    def mark_recent_preset(self, *, project_id: str, preset_id: str) -> list[str]:
        self.get_caption_preset(project_id=project_id, preset_id=preset_id)
        data = self._read()
        project = data["projects"].setdefault(project_id, {"presets": {}, "favorites": [], "recent_preset_ids": []})
        project["recent_preset_ids"] = [preset_id, *[item for item in project["recent_preset_ids"] if item != preset_id]][:10]
        self._write(data)
        return list(project["recent_preset_ids"])

    def list_recent_preset_ids(self, *, project_id: str) -> list[str]:
        return list(self._read()["projects"].get(project_id, {}).get("recent_preset_ids", []))

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"global_presets": {}, "projects": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
