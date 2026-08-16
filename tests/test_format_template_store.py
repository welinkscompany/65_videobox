from __future__ import annotations

from pathlib import Path

import pytest

from videobox_storage.format_template_store import FormatTemplateStore


def _template(name: str = "내 기본 포맷") -> dict:
    return {
        "name": name,
        "caption_style": {"font_size_px": 48},
        "width": 1920, "height": 1080,
        "average_scene_sec": 5.5, "scene_count": 4,
        "music_asset_id": "asset_music",
    }


def test_a_saved_format_can_be_found_again(tmp_path: Path) -> None:
    # 포맷은 프로젝트에 매이지 않는다. 다음 영상은 보통 새 프로젝트다.
    store = FormatTemplateStore(tmp_path)

    saved = store.save_template(template=_template())
    listed = store.list_templates()

    assert saved["template_id"]
    assert [item["name"] for item in listed] == ["내 기본 포맷"]
    assert store.get_template(template_id=saved["template_id"])["caption_style"]["font_size_px"] == 48


def test_saving_the_same_name_twice_updates_it_instead_of_piling_up(tmp_path: Path) -> None:
    # 같은 이름이 여러 개면 owner가 어느 것을 고를지 알 수 없다.
    store = FormatTemplateStore(tmp_path)

    first = store.save_template(template=_template())
    second = store.save_template(template={**_template(), "caption_style": {"font_size_px": 64}})

    assert first["template_id"] == second["template_id"]
    assert len(store.list_templates()) == 1
    assert store.get_template(template_id=first["template_id"])["caption_style"]["font_size_px"] == 64


def test_a_format_that_was_never_saved_is_reported_as_missing(tmp_path: Path) -> None:
    store = FormatTemplateStore(tmp_path)

    with pytest.raises(KeyError):
        store.get_template(template_id="template_missing")


def test_deleting_a_format_removes_it_from_the_list(tmp_path: Path) -> None:
    store = FormatTemplateStore(tmp_path)
    saved = store.save_template(template=_template())

    store.delete_template(template_id=saved["template_id"])

    assert store.list_templates() == []


def test_formats_come_back_newest_first(tmp_path: Path) -> None:
    # 방금 만든 포맷을 맨 아래에서 찾게 하지 않는다.
    store = FormatTemplateStore(tmp_path)
    store.save_template(template=_template("먼저"))
    store.save_template(template=_template("나중"))

    assert [item["name"] for item in store.list_templates()] == ["나중", "먼저"]
