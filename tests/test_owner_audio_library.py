"""owner가 직접 넣은 음악·효과음이 라이브러리 자산이 되는 지점.

**폴더에 넣는 것만으로는 부족하다.** `index_pending_library_audio`는 폴더를
훑지 않고 `store.list_assets_needing_audio_analysis(...)`로 라이브러리 DB를
읽는다(`library_audio_indexer.py:114`). 그 질의는 `media_packs`를 조인해
`active = 1 AND verified = 1`을 요구한다. 그래서 파일만 옮겨 놓으면 색인도
검색도 되지 않고, owner에게는 "넣었는데 아무 일도 안 일어난다"로 보인다.

여기서 검증하는 것은 그 한 줄이다 -- 옮겨진 파일이 **활성·검증된 팩의
자산으로 등록되어** 색인 대기 목록에 실제로 나타나는가.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from videobox_core_engine.owner_audio_library import (
    OWNER_AUDIO_PACK_ID,
    OWNER_AUDIO_PACK_VERSION,
    register_owner_audio_library,
)
from videobox_storage.media_library_store import MediaLibraryStore


def _roots(tmp_path: Path) -> dict[str, Path]:
    music = tmp_path / "owner-audio" / "music"
    sfx = tmp_path / "owner-audio" / "sfx"
    music.mkdir(parents=True)
    sfx.mkdir(parents=True)
    return {"music": music, "sfx": sfx}


def _register(store: MediaLibraryStore, tmp_path: Path, roots: dict[str, Path]):
    return register_owner_audio_library(
        store=store,
        roots=roots,
        install_path=tmp_path / "owner-audio",
        probe_duration=lambda path: 12.5,
    )


def test_a_dropped_track_becomes_an_asset_the_indexer_will_pick_up(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    roots = _roots(tmp_path)
    (roots["music"] / "봄날의 아침.mp3").write_bytes(b"music bytes")

    report = _register(store, tmp_path, roots)

    assert report.registered == ["owner:music:봄날의 아침.mp3"]
    assert report.failed == []
    # 색인기가 실제로 읽는 질의. 여기 안 나오면 검색에도 영원히 안 나온다.
    pending = store.list_assets_needing_audio_analysis()
    assert [item["library_asset_id"] for item in pending] == ["owner:music:봄날의 아침.mp3"]
    assert pending[0]["media_type"] == "music"
    assert pending[0]["sha256"] == hashlib.sha256(b"music bytes").hexdigest()
    assert Path(pending[0]["path"]) == roots["music"] / "봄날의 아침.mp3"


def test_the_folder_decides_music_or_effect(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    roots = _roots(tmp_path)
    (roots["music"] / "배경.mp3").write_bytes(b"music bytes")
    (roots["sfx"] / "딸깍.wav").write_bytes(b"effect bytes")

    _register(store, tmp_path, roots)

    kinds = {
        str(item["library_asset_id"]): str(item["media_type"])
        for item in store.list_assets_needing_audio_analysis()
    }
    assert kinds == {"owner:music:배경.mp3": "music", "owner:sfx:딸깍.wav": "sfx"}


def test_a_later_drop_adds_to_the_earlier_ones_instead_of_replacing_them(tmp_path: Path) -> None:
    """`index_verified_pack(active=True)`는 같은 pack_id의 **다른 버전**을
    비활성으로 내린다. 버전을 고정해 두지 않으면 이번에 넣은 음악이 지난번에
    넣은 음악을 통째로 지워 버린다."""
    store = MediaLibraryStore(tmp_path / "library")
    roots = _roots(tmp_path)
    (roots["music"] / "먼저.mp3").write_bytes(b"first")
    _register(store, tmp_path, roots)

    (roots["music"] / "나중.mp3").write_bytes(b"second")
    second = _register(store, tmp_path, roots)

    assert second.registered == ["owner:music:나중.mp3"]
    assert sorted(
        str(item["library_asset_id"]) for item in store.list_assets_needing_audio_analysis()
    ) == ["owner:music:나중.mp3", "owner:music:먼저.mp3"]


def test_an_unchanged_folder_costs_nothing_on_the_next_pass(tmp_path: Path) -> None:
    """이 검사는 60초마다 도는 정비 한 바퀴 안에서 돈다. 매번 폴더 전체를
    해시하고 ffprobe로 재면, 화면에는 아무것도 안 보이는 채로 owner의 음악
    라이브러리를 하루 종일 다시 읽는다 -- 이 저장소가 이미 한 번 치른 값이다.
    """
    store = MediaLibraryStore(tmp_path / "library")
    roots = _roots(tmp_path)
    (roots["music"] / "그대로.mp3").write_bytes(b"unchanged")
    _register(store, tmp_path, roots)

    probed: list[Path] = []
    second = register_owner_audio_library(
        store=store,
        roots=roots,
        install_path=tmp_path / "owner-audio",
        probe_duration=lambda path: probed.append(path) or 1.0,
    )

    assert second.registered == []
    assert probed == []


def test_the_owner_s_own_file_claims_no_licence_it_does_not_have(tmp_path: Path) -> None:
    """owner 자기 파일에는 외부 라이선스도, 캡처해 둔 증거도 없다.

    URL이나 증거 시각을 지어내면 있지도 않은 근거가 있는 것처럼 기록된다.
    비워 두는 것이 사실이고, 화면은 이미 빈 값을 "라이선스 정보 없음"으로
    보여 준다(`editorAssetProjection.ts:106`).
    """
    store = MediaLibraryStore(tmp_path / "library")
    roots = _roots(tmp_path)
    (roots["music"] / "내 노래.mp3").write_bytes(b"mine")

    _register(store, tmp_path, roots)

    asset = store.search()[0]
    assert asset["official_license_url"] == ""
    assert asset["evidence_timestamp"] == ""
    assert asset["evidence_sha256"] == ""
    assert asset["attribution_required"] is False
    assert asset["attribution_text"] == ""
    # 어디서 왔는지는 사실대로 적는다.
    assert asset["source"] == "직접 넣은 파일"
    # 화면이 이름 대신 보여 줄 값이라 파일 이름 그대로여야 한다.
    assert asset["asset_id"] == "내 노래"


def test_a_file_we_cannot_measure_is_reported_not_silently_dropped(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    roots = _roots(tmp_path)
    (roots["music"] / "깨진 파일.mp3").write_bytes(b"not really audio")

    def broken_probe(path: Path) -> float:
        raise ValueError("ffprobe failed")

    report = register_owner_audio_library(
        store=store,
        roots=roots,
        install_path=tmp_path / "owner-audio",
        probe_duration=broken_probe,
    )

    assert report.registered == []
    assert report.failed == ["owner:music:깨진 파일.mp3"]


def test_the_pack_identity_stays_put_so_reruns_accumulate(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    roots = _roots(tmp_path)
    (roots["sfx"] / "쿵.wav").write_bytes(b"thud")
    _register(store, tmp_path, roots)

    pack = store.get_pack(pack_id=OWNER_AUDIO_PACK_ID, version=OWNER_AUDIO_PACK_VERSION)
    assert pack is not None
    assert bool(pack["active"]) is True
    assert bool(pack["verified"]) is True
