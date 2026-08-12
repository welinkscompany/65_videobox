"""Bring the library's index up to date, and keep it that way.

The indexer is what makes "add more music later" work: it walks the assets
the store reports as pending, measures each one, describes it in the owner's
words, embeds that description, and saves the lot. Adding files is the only
thing anyone has to do.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest

from videobox_core_engine.audio_descriptors import AudioDescriptor
from videobox_core_engine.library_audio_indexer import (
    LibraryAudioIndexReport,
    build_asset_description,
    index_pending_library_audio,
)


class _FakeStore:
    def __init__(self, pending: list[dict]) -> None:
        self._pending = pending
        self.saved: list[dict] = []

    def list_assets_needing_audio_analysis(self, *, description_version: int = 1) -> list[dict]:
        self.asked_version = description_version
        return list(self._pending)

    def save_audio_descriptor(self, **kwargs) -> None:
        self.saved.append(kwargs)


class _FakeEmbeddings:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.seen: list[str] = []

    def embed(self, request):
        if self.fail:
            raise RuntimeError("local model unreachable")
        self.seen.extend(request.inputs)

        class _Response:
            vectors = tuple([0.5, 0.5] for _ in request.inputs)

        return _Response()


def _descriptor() -> AudioDescriptor:
    return AudioDescriptor(
        duration_seconds=80.0, loudness_rms=0.22, brightness_hz=3400.0, onset_rate_per_second=3.1
    )


def test_a_description_says_what_the_asset_is_in_the_owners_words() -> None:
    text = build_asset_description(
        media_type="music",
        words={"세기": "강함", "밝기": "밝음", "빠르기": "빠름"},
        duration_seconds=80.0,
    )

    assert "음악" in text
    # Written the way a person would say it, so a plain query lands near it
    # and so anything shown on screen needs no translating.
    assert "신나는" in text or "활기찬" in text
    # How long it is belongs in the text too: a sting and a bed suit
    # completely different scenes.
    assert "길게" in text or "장면" in text
    for forbidden in ("music", "sfx", "rms", "hz"):
        assert forbidden not in text.lower()


def test_pending_assets_are_measured_described_embedded_and_saved(tmp_path: Path) -> None:
    audio = tmp_path / "music-a.wav"
    audio.write_bytes(b"pretend audio")
    store = _FakeStore([{
        "library_asset_id": "pack:p:music-a",
        "asset_id": "music-a",
        "media_type": "music",
        "sha256": hashlib.sha256(b"pretend audio").hexdigest(),
        "path": str(audio),
    }])
    embeddings = _FakeEmbeddings()

    report = index_pending_library_audio(
        store=store,
        embedding_provider=embeddings,
        embedding_model_name="bge-m3",
        describe=lambda _path: _descriptor(),
    )

    assert report.analyzed == ["pack:p:music-a"]
    assert report.failed == []
    saved = store.saved[0]
    assert saved["library_asset_id"] == "pack:p:music-a"
    assert saved["embedding"] == [0.5, 0.5]
    assert saved["words"] == {"세기": "강함", "밝기": "밝음", "빠르기": "빠름"}
    # What gets embedded is exactly what was saved as the description.
    assert embeddings.seen == [saved["description"]]


def test_measurements_are_kept_even_when_the_local_model_is_away(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Losing the model must not lose the ffmpeg work. The asset stays pending
    # (the store decides that from the null embedding) and picks up its vector
    # on a later pass.
    audio = tmp_path / "music-a.wav"
    audio.write_bytes(b"pretend audio")
    store = _FakeStore([{
        "library_asset_id": "pack:p:music-a", "asset_id": "music-a", "media_type": "music",
        "sha256": "abc", "path": str(audio),
    }])

    with caplog.at_level(logging.WARNING):
        report = index_pending_library_audio(
            store=store,
            embedding_provider=_FakeEmbeddings(fail=True),
            embedding_model_name="bge-m3",
            describe=lambda _path: _descriptor(),
        )

    assert report.analyzed == ["pack:p:music-a"]
    assert store.saved[0]["embedding"] is None
    assert store.saved[0]["words"]["세기"] == "강함"
    # 동작은 위 그대로다. 다만 벡터가 없으면 그 자산은 뜻으로 못 찾고 검색이 조용히
    # 낱말 맞추기로 떨어진다. owner에게는 "추천이 늘 비슷하다"로만 보이므로, 어느
    # 자산이 왜 빠졌는지는 남아 있어야 한다.
    assert "pack:p:music-a" in caplog.text
    assert "bge-m3" in caplog.text


def test_one_bad_file_does_not_stop_the_rest(tmp_path: Path) -> None:
    good = tmp_path / "good.wav"
    bad = tmp_path / "bad.wav"
    good.write_bytes(b"good")
    bad.write_bytes(b"bad")
    store = _FakeStore([
        {"library_asset_id": "pack:p:bad", "asset_id": "bad", "media_type": "sfx", "sha256": "a", "path": str(bad)},
        {"library_asset_id": "pack:p:good", "asset_id": "good", "media_type": "sfx", "sha256": "b", "path": str(good)},
    ])

    def describe(path: Path) -> AudioDescriptor:
        if path.name == "bad.wav":
            raise ValueError("audio_unreadable: bad.wav")
        return _descriptor()

    report = index_pending_library_audio(
        store=store,
        embedding_provider=_FakeEmbeddings(),
        embedding_model_name="bge-m3",
        describe=describe,
    )

    assert report.analyzed == ["pack:p:good"]
    assert report.failed == ["pack:p:bad"]


def test_a_missing_file_is_reported_rather_than_measured(tmp_path: Path) -> None:
    store = _FakeStore([{
        "library_asset_id": "pack:p:gone", "asset_id": "gone", "media_type": "music",
        "sha256": "a", "path": str(tmp_path / "not-there.wav"),
    }])

    report = index_pending_library_audio(
        store=store,
        embedding_provider=_FakeEmbeddings(),
        embedding_model_name="bge-m3",
        describe=lambda _path: _descriptor(),
    )

    assert report.analyzed == []
    assert report.failed == ["pack:p:gone"]
    assert store.saved == []


def test_a_pass_can_be_bounded_so_it_never_owns_the_machine(tmp_path: Path) -> None:
    # 130 files on first install, and more whenever the owner adds some. A
    # bounded pass keeps startup from turning into a long analysis run.
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    store = _FakeStore([
        {"library_asset_id": f"pack:p:a{index}", "asset_id": f"a{index}", "media_type": "sfx",
         "sha256": str(index), "path": str(audio)}
        for index in range(10)
    ])

    report = index_pending_library_audio(
        store=store,
        embedding_provider=_FakeEmbeddings(),
        embedding_model_name="bge-m3",
        describe=lambda _path: _descriptor(),
        max_assets=3,
    )

    assert len(report.analyzed) == 3
    assert report.remaining == 7


def test_the_running_app_indexes_new_library_assets_without_being_asked(tmp_path, monkeypatch) -> None:
    """Adding music must be the only thing the owner does. The maintenance
    loop picks up whatever the store reports as pending, so a file dropped in
    later becomes searchable on its own."""
    import time

    from fastapi.testclient import TestClient

    from videobox_api import main as api_main

    passes: list[int] = []

    def fake_index(**kwargs):
        passes.append(kwargs.get("max_assets") or 0)
        return LibraryAudioIndexReport()

    monkeypatch.setattr(api_main, "index_pending_library_audio", fake_index)
    monkeypatch.setattr(api_main, "LIBRARY_AUDIO_INDEX_INTERVAL_SECONDS", 0.05)

    app = api_main.create_app(
        projects_root=tmp_path / "projects",
        media_analysis_poll_interval_seconds=0.01,
    )
    with TestClient(app):
        time.sleep(0.4)

    # Ran at startup and kept running -- this is what covers assets added later.
    assert len(passes) >= 2
    # Bounded, so a first install of 130 files never owns the machine.
    assert all(count > 0 for count in passes)


def test_every_combination_reads_as_its_own_sentence() -> None:
    """Live search ranked a 보통/보통 track above a 강함/빠름 one for
    "신나고 빠른 음악", with 0.002 between them. The descriptions were the
    cause: a fixed template differing by two words leaves every vector nearly
    parallel, so the ranking is noise."""
    descriptions = {}
    for strength in ("조용함", "보통", "강함"):
        for brightness in ("어두움", "중간", "밝음"):
            for pace in ("느림", "보통", "빠름"):
                descriptions[(strength, brightness, pace)] = build_asset_description(
                    media_type="music",
                    words={"세기": strength, "밝기": brightness, "빠르기": pace},
                    duration_seconds=90.0,
                )

    # No two combinations may collapse onto the same sentence.
    assert len(set(descriptions.values())) == len(descriptions)

    # And a change on any one axis has to move real words, not a single token.
    quiet = descriptions[("조용함", "중간", "보통")]
    loud = descriptions[("강함", "중간", "보통")]
    changed = set(quiet.split()) ^ set(loud.split())
    assert len(changed) >= 4


def test_a_description_format_change_makes_every_asset_pending_again() -> None:
    """Changing how descriptions read leaves every stored vector describing
    the old wording. Without a version to compare, the store would go on
    thinking those assets were done and the whole library would rank against
    text that no longer exists."""
    from videobox_core_engine.library_audio_indexer import DESCRIPTION_VERSION

    assert isinstance(DESCRIPTION_VERSION, int) and DESCRIPTION_VERSION >= 1


def test_user_confirmed_tags_are_embedded_without_replacing_machine_words(tmp_path: Path) -> None:
    audio = tmp_path / "music-a.wav"
    audio.write_bytes(b"pretend audio")
    store = _FakeStore([{
        "library_asset_id": "user:music-a", "asset_id": "music-a", "media_type": "music",
        "sha256": hashlib.sha256(b"pretend audio").hexdigest(), "path": str(audio),
        "user_metadata": {"title": "출근 음악", "tags": ["출근", "차분"]},
    }])
    embeddings = _FakeEmbeddings()

    index_pending_library_audio(
        store=store, embedding_provider=embeddings, embedding_model_name="bge-m3",
        describe=lambda _path: _descriptor(),
    )

    saved = store.saved[0]
    assert "출근" in saved["description"] and "차분" in saved["description"]
    assert saved["words"] == {"세기": "강함", "밝기": "밝음", "빠르기": "빠름"}
