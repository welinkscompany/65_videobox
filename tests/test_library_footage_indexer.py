"""드롭 폴더에 넣은 영상이 저절로 찾을 수 있는 자산이 되는 경로."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest

from videobox_core_engine.library_footage_indexer import (
    FOOTAGE_DESCRIPTION_VERSION,
    build_footage_description,
    index_pending_library_footage,
)


class _FakeStore:
    def __init__(self, pending: list[dict]) -> None:
        self._pending = pending
        self.saved: list[dict] = []
        self.asked_version: int | None = None

    def list_footage_needing_analysis(self, *, paths, description_version: int = 1) -> list[dict]:
        self.asked_version = description_version
        return list(self._pending)

    def save_footage_descriptor(self, **kwargs) -> None:
        self.saved.append(kwargs)


class _SegmentStore(_FakeStore):
    def __init__(self, pending: list[dict]) -> None:
        super().__init__(pending)
        self.marked: list[str] = []

    def get_footage_descriptor(self, *, content_sha256: str):
        return {
            "content_sha256": content_sha256,
            "filename": "canonical.mp4",
            "duration_seconds": 1.0,
            "width": 1920,
            "height": 1080,
            "tags": {},
            "description": "가로 영상. 저장된 장면.",
            "embedding": None,
            "description_version": FOOTAGE_DESCRIPTION_VERSION,
        }

    def mark_footage_segment_indexed(self, *, source_segment_id: str) -> None:
        self.marked.append(source_segment_id)


class _Frame:
    data = b"frame-bytes"


class _ProbeResult:
    duration_sec = 29.1
    width = 1920
    height = 1080
    frames = (_Frame(), _Frame())
    scene_boundaries = (0.0, 29.1)


class _Probe:
    def probe(self, _path):
        return _ProbeResult()


class _Vision:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def analyze_images(self, _request):
        if self.fail:
            raise RuntimeError("vision model unreachable")

        class _Response:
            output_data = {
                "layers": {"place": ["실내 수영장"], "action": ["수영", "놀기"], "weather": ["맑음"]},
                "summary": "아이가 실내 수영장에서 즐겁게 물놀이하는 장면.",
            }

        return _Response()


class _Embeddings:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.seen: list[str] = []

    def embed(self, request):
        if self.fail:
            raise RuntimeError("embedding model unreachable")
        self.seen.extend(request.inputs)

        class _Response:
            vectors = tuple([0.5, 0.5] for _ in request.inputs)

        return _Response()


def _pending(tmp_path: Path, name: str = "a.mp4") -> list[dict]:
    path = tmp_path / name
    path.write_bytes(b"video")
    return [{"content_sha256": "abc", "filename": name, "path": str(path)}]


def _run(store, tmp_path, **overrides):
    kwargs = dict(
        store=store,
        paths=[tmp_path / "a.mp4"],
        media_probe=_Probe(),
        vision_provider=_Vision(),
        vision_model_name="qwen-vision",
        embedding_provider=_Embeddings(),
        embedding_model_name="bge-m3",
    )
    kwargs.update(overrides)
    return index_pending_library_footage(**kwargs)


def test_a_description_reads_in_the_owners_words_and_carries_the_orientation() -> None:
    text = build_footage_description(
        summary="아이가 실내 수영장에서 즐겁게 물놀이하는 장면.",
        layers={"place": ["실내 수영장"], "action": ["수영"], "weather": ["맑음"]},
        width=1080,
        height=1920,
    )

    assert "세로" in text
    assert "수영장" in text
    # 화면에도 그대로 보여줄 수 있어야 하므로 내부 용어가 섞이면 안 된다.
    for forbidden in ("layers", "place", "action", "summary"):
        assert forbidden not in text.lower()


def test_pending_footage_is_probed_analysed_embedded_and_saved(tmp_path: Path) -> None:
    store = _FakeStore(_pending(tmp_path))
    embeddings = _Embeddings()

    report = _run(store, tmp_path, embedding_provider=embeddings)

    assert report.analyzed == ["a.mp4"]
    saved = store.saved[0]
    assert saved["content_sha256"] == "abc"
    assert saved["width"] == 1920 and saved["height"] == 1080
    assert saved["tags"]["layers"]["place"] == ["실내 수영장"]
    assert saved["embedding"] == [0.5, 0.5]
    assert saved["description_version"] == FOOTAGE_DESCRIPTION_VERSION
    # 검색되는 문장과 저장된 문장이 같아야 한다.
    assert embeddings.seen == [saved["description"]]
    assert store.asked_version == FOOTAGE_DESCRIPTION_VERSION


def test_the_vision_model_being_away_leaves_the_clip_for_later(tmp_path: Path) -> None:
    # 화면 분석 없이는 저장할 내용이 없다. 실패로 남겨 다음 차례에 다시 온다.
    store = _FakeStore(_pending(tmp_path))

    report = _run(store, tmp_path, vision_provider=_Vision(fail=True))

    assert report.analyzed == []
    assert report.failed == ["a.mp4"]
    assert store.saved == []


def test_losing_only_the_embedding_still_keeps_the_analysis(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = _FakeStore(_pending(tmp_path))

    with caplog.at_level(logging.WARNING):
        report = _run(store, tmp_path, embedding_provider=_Embeddings(fail=True))

    assert report.analyzed == ["a.mp4"]
    assert store.saved[0]["embedding"] is None
    assert store.saved[0]["tags"]["layers"]["place"] == ["실내 수영장"]
    # 동작은 위 그대로다. 다만 벡터가 없으면 그 촬영본은 뜻으로 못 찾고 검색이 조용히
    # 낱말 맞추기로 떨어진다. 어느 파일이 왜 빠졌는지는 남아 있어야 한다.
    assert "a.mp4" in caplog.text
    assert "bge-m3" in caplog.text


def test_a_pass_is_bounded_so_a_big_drop_never_owns_the_machine(tmp_path: Path) -> None:
    # 화면 분석은 무겁다. 한 번에 몇 개만 처리하고 나머지는 다음 차례로 둔다.
    pending = []
    for index in range(5):
        path = tmp_path / f"clip{index}.mp4"
        path.write_bytes(b"video")
        pending.append({"content_sha256": str(index), "filename": path.name, "path": str(path)})
    store = _FakeStore(pending)

    report = _run(store, tmp_path, max_clips=2)

    assert len(report.analyzed) == 2
    assert report.remaining == 3


def test_the_model_is_asked_for_korean_so_search_and_screen_get_korean(tmp_path: Path) -> None:
    """색인된 실제 촬영본의 요약이 전부 영어로 나왔다. owner는 우리말로 찾고,
    이 문장은 화면에 그대로 보일 수 있다. 같은 언어끼리 맞출 때 점수도 높다 --
    영어 요약으로 검색했을 때 0.52~0.59였고, 우리말 오디오 쪽은 0.68~0.70이었다."""
    seen: list[str] = []

    class _RecordingVision(_Vision):
        def analyze_images(self, request):
            seen.append(request.prompt)
            return super().analyze_images(request)

    store = _FakeStore(_pending(tmp_path))
    _run(store, tmp_path, vision_provider=_RecordingVision())

    assert seen and "한국어" in seen[0]


def test_user_confirmed_footage_tags_are_added_to_machine_description(tmp_path: Path) -> None:
    store = _FakeStore([{
        **_pending(tmp_path)[0],
        "library_asset_id": "user:broll-a",
        "user_metadata": {"title": "출근길", "tags": ["차량", "이동"]},
    }])

    _run(store, tmp_path)

    saved = store.saved[0]
    assert "차량" in saved["description"] and "이동" in saved["description"]
    assert saved["tags"]["layers"]["place"] == ["실내 수영장"]


def test_pending_embedding_reuses_saved_footage_analysis_without_vision(tmp_path: Path) -> None:
    class _Store(_FakeStore):
        def get_footage_descriptor(self, *, content_sha256: str):
            assert content_sha256 == "abc"
            return {
                "content_sha256": "abc", "filename": "a.mp4", "duration_seconds": 29.1,
                "width": 1920, "height": 1080,
                "tags": {"layers": {"place": ["저장된 장소"]}},
                "description": "가로 영상. 저장된 장소.",
                "embedding": None, "description_version": FOOTAGE_DESCRIPTION_VERSION,
            }

    store = _Store(_pending(tmp_path))
    report = _run(
        store, tmp_path, vision_provider=_Vision(fail=True),
        embedding_provider=_Embeddings(),
    )

    assert report.analyzed == ["a.mp4"]
    assert report.failed == []
    assert store.saved[0]["description"] == "가로 영상. 저장된 장소."


def test_replaced_segment_source_fails_closed_before_embedding_or_queue_ack(tmp_path: Path) -> None:
    path = tmp_path / "a.mp4"
    path.write_bytes(b"replacement bytes")
    canonical_sha = hashlib.sha256(b"canonical bytes").hexdigest()
    store = _SegmentStore([{
        "content_sha256": "derived-index-key",
        "source_sha256": canonical_sha,
        "source_segment_id": "segment-1",
        "is_segment": True,
        "filename": path.name,
        "path": str(path),
    }])

    report = _run(
        store,
        tmp_path,
        vision_provider=None,
        vision_model_name=None,
        embedding_provider=_Embeddings(),
    )

    assert report.analyzed == []
    assert report.failed == ["a.mp4"]
    assert store.saved == []
    assert store.marked == []
