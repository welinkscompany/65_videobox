"""촬영본도 라이브러리에 있는 동안 찾을 수 있어야 한다.

지금까지 b-roll은 프로젝트로 가져와야만 분석됐다. 그래서 owner가 드롭 폴더에
영상을 넣어 두어도 가져오기 전에는 유진이 그 영상의 존재조차 모른다. 같은
영상을 여러 프로젝트에서 쓰면 그때마다 다시 분석했다.

색인의 열쇠는 파일 내용 해시다. 새로 넣은 영상은 해시에 기록이 없으니 저절로
대기 목록에 들어가고, 같은 영상은 두 번 분석하지 않는다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from videobox_storage.media_library_store import MediaLibraryStore


def _store(tmp_path: Path) -> MediaLibraryStore:
    return MediaLibraryStore(tmp_path / "library")


def _footage(tmp_path: Path, name: str, payload: bytes) -> Path:
    folder = tmp_path / "footage"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(payload)
    return path


def _save(store: MediaLibraryStore, path: Path, payload: bytes, **overrides) -> None:
    defaults = dict(
        content_sha256=hashlib.sha256(payload).hexdigest(),
        filename=path.name,
        duration_seconds=12.0,
        width=1920,
        height=1080,
        tags={"place": ["수영장"], "action": ["물놀이"]},
        description="가로 영상. 수영장에서 물놀이하는 장면.",
        embedding=[1.0, 0.0],
        description_version=1,
    )
    defaults.update(overrides)
    store.save_footage_descriptor(**defaults)


def test_new_footage_is_pending_and_indexed_footage_is_not(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _footage(tmp_path, "a.mp4", b"aaaa")
    second = _footage(tmp_path, "b.mp4", b"bbbb")

    pending = store.list_footage_needing_analysis(paths=[first, second])
    assert sorted(item["filename"] for item in pending) == ["a.mp4", "b.mp4"]

    _save(store, first, b"aaaa")

    assert [item["filename"] for item in store.list_footage_needing_analysis(paths=[first, second])] == ["b.mp4"]


def test_the_same_footage_under_a_new_name_is_not_analysed_twice(tmp_path: Path) -> None:
    # 같은 영상을 다시 넣거나 이름만 바꿔도 다시 분석하지 않는다.
    store = _store(tmp_path)
    original = _footage(tmp_path, "original.mp4", b"same bytes")
    _save(store, original, b"same bytes")
    renamed = _footage(tmp_path, "renamed.mp4", b"same bytes")

    assert store.list_footage_needing_analysis(paths=[original, renamed]) == []


def test_orientation_is_recorded_from_the_real_size(tmp_path: Path) -> None:
    store = _store(tmp_path)
    landscape = _footage(tmp_path, "wide.mp4", b"wide")
    portrait = _footage(tmp_path, "tall.mp4", b"tall")
    _save(store, landscape, b"wide", width=1920, height=1080)
    _save(store, portrait, b"tall", width=1080, height=1920)

    saved = {
        item["filename"]: item
        for item in [
            store.get_footage_descriptor(content_sha256=hashlib.sha256(b"wide").hexdigest()),
            store.get_footage_descriptor(content_sha256=hashlib.sha256(b"tall").hexdigest()),
        ]
    }
    assert saved["wide.mp4"]["orientation"] == "가로"
    assert saved["tall.mp4"]["orientation"] == "세로"


def test_a_newer_description_version_makes_footage_pending_again(tmp_path: Path) -> None:
    store = _store(tmp_path)
    path = _footage(tmp_path, "a.mp4", b"aaaa")
    _save(store, path, b"aaaa", description_version=1)

    assert store.list_footage_needing_analysis(paths=[path], description_version=1) == []
    assert [item["filename"] for item in store.list_footage_needing_analysis(paths=[path], description_version=2)] == ["a.mp4"]


def test_footage_without_an_embedding_stays_pending(tmp_path: Path) -> None:
    # 화면 분석은 됐는데 임베딩만 못 만든 경우. 분석 결과는 지키고 벡터만
    # 나중에 받으러 다시 온다.
    store = _store(tmp_path)
    path = _footage(tmp_path, "a.mp4", b"aaaa")
    _save(store, path, b"aaaa", embedding=None)

    stored = store.get_footage_descriptor(content_sha256=hashlib.sha256(b"aaaa").hexdigest())
    assert stored["tags"]["place"] == ["수영장"]
    assert [item["filename"] for item in store.list_footage_needing_analysis(paths=[path])] == ["a.mp4"]


def test_search_ranks_footage_and_can_ask_for_one_orientation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    wide_near = _footage(tmp_path, "wide-near.mp4", b"1")
    wide_far = _footage(tmp_path, "wide-far.mp4", b"2")
    tall_near = _footage(tmp_path, "tall-near.mp4", b"3")
    _save(store, wide_near, b"1", embedding=[1.0, 0.0])
    _save(store, wide_far, b"2", embedding=[0.0, 1.0])
    _save(store, tall_near, b"3", embedding=[1.0, 0.0], width=1080, height=1920)

    everything = store.find_footage_matches(query_embedding=[1.0, 0.0], limit=5)
    assert [match["filename"] for match in everything][:2] == ["tall-near.mp4", "wide-near.mp4"] or \
           [match["filename"] for match in everything][:2] == ["wide-near.mp4", "tall-near.mp4"]

    # 숏폼을 만들 때는 세로만 필요하다.
    portrait_only = store.find_footage_matches(query_embedding=[1.0, 0.0], orientation="세로", limit=5)
    assert [match["filename"] for match in portrait_only] == ["tall-near.mp4"]


def test_search_refuses_a_query_it_cannot_rank(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(ValueError):
        store.find_footage_matches(query_embedding=[], limit=3)
    with pytest.raises(ValueError):
        store.find_footage_matches(query_embedding=[0.0, 0.0], limit=3)
