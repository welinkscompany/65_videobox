from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def test_editor_library_api_persists_project_preset_and_idempotent_media_favorite(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = "project_001"

    preset = client.put(
        f"/api/projects/{project_id}/editor-library/presets/project:{project_id}:focus",
        json={"name": "Focus", "style": {"font_size": 44, "text_color": "#FFFFFFFF"}},
    )
    assert preset.status_code == 200
    assert preset.json()["scope"] == "project"

    first = client.put(
        f"/api/projects/{project_id}/editor-library/favorites/pack:starter:asset_001",
        json={"favorite_type": "media", "enabled": True},
    )
    assert first.status_code == 200
    assert client.put(
        f"/api/projects/{project_id}/editor-library/favorites/pack:starter:asset_001",
        json={"favorite_type": "media", "enabled": True},
    ).status_code == 200
    favorites = client.get(f"/api/projects/{project_id}/editor-library/favorites")
    assert favorites.json() == [{"favorite_id": "pack:starter:asset_001", "favorite_type": "media"}]
