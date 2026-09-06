"""휴지통을 비우려니 절반이 500으로 죽었다 — 실측 2026-09-06.

owner 승인으로 시험용 껍데기 12개를 치우고 완전 삭제를 걸었더니 **6개가 500**을
냈다. 이유는 `library_footage_sources`의 외래키가 `ON DELETE RESTRICT`라서다 --
그 자산에서 잘라 둔 구간이 딸려 있으면 못 지운다.

**그 막음 자체는 옳다**(`test_canonical_library_asset_cannot_be_deleted_while_source_is_derived`).
쓰고 있는 자산을 지우면 잘라 둔 구간이 허공을 가리킨다.

잘못은 둘이다.

1. **막는 것을 500으로 낸다.** 창작자에게는 그냥 "서버 오류"다. 왜 안 되는지
   말해 주지 않는다.
2. **휴지통에 넣은 것까지 그 막음이 걸린다.** 이미 버린 자산은 그 파생물도
   같이 버리는 것이 맞다 -- 안 그러면 휴지통을 영영 못 비운다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from videobox_storage.footage_organizer_store import FootageOrganizerStore
from videobox_storage.media_library_store import MediaLibraryStore


def _asset(store: MediaLibraryStore, asset_id: str, digest: str) -> None:
    store.register_user_asset(
        library_asset_id=asset_id, media_type="broll", origin="user",
        content_sha256=digest, managed_relative_path=f"{asset_id}.mp4",
        byte_count=1, mime_type="video/mp4",
    )


def test_a_trashed_asset_goes_even_though_it_has_cut_ranges(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    _asset(store, "asset-trashed", "1" * 64)
    organizer = FootageOrganizerStore(tmp_path / "library")
    source = organizer.register_source(
        source_id="source-trashed", source_sha256="1" * 64, library_asset_id="asset-trashed"
    )
    organizer.create_source_segment(source_id=source.source_id, start_sec=0.0, end_sec=1.0)
    store.user_asset_store.trash_asset("asset-trashed")

    store.user_asset_store.permanently_delete_asset("asset-trashed")

    assert not [
        item for item in store.user_asset_store.list_assets()
        if item.library_asset_id == "asset-trashed"
    ]


def test_an_asset_still_in_use_is_still_protected(tmp_path: Path) -> None:
    """**버리지 않은 자산은 그대로 막힌다.** 잘라 둔 구간이 허공을 가리키면 안 된다."""
    store = MediaLibraryStore(tmp_path / "library")
    _asset(store, "asset-live", "2" * 64)
    organizer = FootageOrganizerStore(tmp_path / "library")
    source = organizer.register_source(
        source_id="source-live", source_sha256="2" * 64, library_asset_id="asset-live"
    )
    organizer.create_source_segment(source_id=source.source_id, start_sec=0.0, end_sec=1.0)

    with pytest.raises((sqlite3.IntegrityError, ValueError)):
        store.user_asset_store.permanently_delete_asset("asset-live")
