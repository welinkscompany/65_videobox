from __future__ import annotations

import pytest

from videobox_storage.user_library_store import UserLibraryStore


def test_builtin_caption_presets_are_immutable_and_project_snapshot_survives_reload(tmp_path) -> None:
    store = UserLibraryStore(tmp_path / "videobox-user-library")

    built_in = store.list_caption_presets(project_id="project_001")
    assert built_in[0]["preset_id"] == "builtin:clean"
    with pytest.raises(ValueError, match="built-in"):
        store.save_caption_preset(
            project_id="project_001",
            preset_id="builtin:clean",
            name="Mutated",
            style={"font_size": 99},
        )

    saved = store.save_caption_preset(
        project_id="project_001",
        preset_id="project:project_001:focus",
        name="Focus",
        style={"font_size": 44, "text_color": "#FFFFFFFF"},
    )
    assert saved["scope"] == "project"
    reloaded = UserLibraryStore(tmp_path / "videobox-user-library")
    assert reloaded.get_caption_preset(project_id="project_001", preset_id=saved["preset_id"])["style"]["font_size"] == 44


def test_favorite_toggle_is_idempotent_and_uses_canonical_ids(tmp_path) -> None:
    store = UserLibraryStore(tmp_path / "videobox-user-library")

    assert store.toggle_favorite(project_id="project_001", favorite_id="pack:starter:asset_001", favorite_type="media", enabled=True)["enabled"] is True
    assert store.toggle_favorite(project_id="project_001", favorite_id="pack:starter:asset_001", favorite_type="media", enabled=True)["enabled"] is True
    assert store.list_favorites(project_id="project_001") == [{"favorite_id": "pack:starter:asset_001", "favorite_type": "media"}]
    assert store.toggle_favorite(project_id="project_001", favorite_id="pack:starter:asset_001", favorite_type="media", enabled=False)["enabled"] is False
    with pytest.raises(ValueError, match="favorite_id"):
        store.toggle_favorite(project_id="project_001", favorite_id="asset_001", favorite_type="media", enabled=True)


def test_global_snapshot_and_recent_preset_survive_reload(tmp_path) -> None:
    root = tmp_path / "videobox-user-library"
    store = UserLibraryStore(root)

    store.save_caption_preset(
        project_id="project_001",
        preset_id="global:brand",
        name="Brand",
        style={"font_size": 48},
        global_scope=True,
    )
    store.mark_recent_preset(project_id="project_001", preset_id="global:brand")

    reloaded = UserLibraryStore(root)
    assert reloaded.get_caption_preset(project_id="project_001", preset_id="global:brand")["scope"] == "global"
    assert reloaded.list_recent_preset_ids(project_id="project_001") == ["global:brand"]
