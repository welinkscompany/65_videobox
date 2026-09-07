"""한 폴더에 넣은 것을 실제로 갈라 넣는 한 바퀴 (owner 승인 2026-09-07).

계약: `docs/decisions/2026-09-07-one-drop-folder-sorted-for-me.ko.md`

- 영상 / 그림 / 음악 / 효과음은 각자의 자리로 들어간다.
- 자산 가치가 없는 것만 `불필요`로 **옮긴다.** 지우지 않는다.
- 원본은 자산으로 들어간 것을 **확인한 뒤에** 보관함으로 옮긴다.

여기 파일도 전부 ffmpeg가 만든 진짜 미디어다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.media_inbox import MediaInboxConfig, run_inbox_cycle
from videobox_storage.library_user_asset_store import LibraryUserAssetStore


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe가 없으면 실물로 잴 수 없다",
)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, timeout=120)


def _fill_drop_folder(drop: Path) -> None:
    drop.mkdir(parents=True, exist_ok=True)
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=2",
            "-pix_fmt", "yuv420p", str(drop / "촬영본.mp4"))
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x180:rate=1:duration=1",
            "-frames:v", "1", str(drop / "사진.png"))
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=880:duration=1.0", str(drop / "딸깍.wav"))
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=30", str(drop / "브금.wav"))
    (drop / "메모.txt").write_text("자산이 아니다", encoding="utf-8")
    (drop / "깨진영상.mp4").write_bytes(b"\x00\x01\x02" * 4096)


def _sorted_config(tmp_path: Path) -> tuple[MediaInboxConfig, dict[str, Path], Path, Path]:
    drop = tmp_path / "#_videobox"
    archive = tmp_path / "자산화_완료"
    reject = tmp_path / "불필요"
    roots = {
        "broll": tmp_path / "library" / "media-inbox",
        "image": tmp_path / "library" / "user",
        "music": tmp_path / "library" / "owner-audio" / "music",
        "sfx": tmp_path / "library" / "owner-audio" / "sfx",
    }
    store = LibraryUserAssetStore(tmp_path / "library" / ".videobox-library-state")
    config = MediaInboxConfig(
        watch_path=drop,
        library_root=roots["broll"],
        archive_root=archive,
        reject_root=reject,
        sort_by_content=True,
        sorted_library_roots=roots,
        copy_only=True,
        archive_source=True,
        ingest_store=store,
    )
    return config, roots, archive, reject


def _library_types(store_root: Path) -> dict[str, str]:
    store = LibraryUserAssetStore(store_root)
    return {
        str(asset.user_metadata.get("filename")): asset.media_type.value
        for asset in store.list_assets()
    }


def test_one_drop_folder_is_sorted_by_content(tmp_path: Path) -> None:
    config, roots, archive, reject = _sorted_config(tmp_path)
    _fill_drop_folder(config.watch_path)

    report = run_inbox_cycle(config, is_settled=lambda path: True)

    assert sorted(report.moved) == ["딸깍.wav", "브금.wav", "사진.png", "촬영본.mp4"]
    assert sorted(report.rejected) == ["깨진영상.mp4", "메모.txt"]
    assert report.failed == []

    kinds = _library_types(tmp_path / "library" / ".videobox-library-state")
    assert kinds == {
        "촬영본.mp4": "broll",
        "사진.png": "image",
        "딸깍.wav": "sfx",
        "브금.wav": "music",
    }
    # 종류마다 바이트가 사는 자리가 다르다. 한군데 섞이면 촬영본 색인이 음원을
    # 영상으로 알고 화면 분석을 시도한다.
    assert list(roots["music"].rglob("*.wav"))
    assert list(roots["sfx"].rglob("*.wav"))
    assert list(roots["broll"].rglob("*.mp4"))
    assert list(roots["image"].rglob("*.png"))


def test_originals_are_archived_and_rejects_are_moved_not_deleted(tmp_path: Path) -> None:
    config, _roots, archive, reject = _sorted_config(tmp_path)
    _fill_drop_folder(config.watch_path)

    run_inbox_cycle(config, is_settled=lambda path: True)

    # 넣는 폴더는 비었고, 파일은 하나도 사라지지 않았다.
    assert [path.name for path in config.watch_path.rglob("*") if path.is_file()] == []
    assert sorted(path.name for path in archive.iterdir()) == [
        "딸깍.wav", "브금.wav", "사진.png", "촬영본.mp4",
    ]
    assert sorted(path.name for path in reject.iterdir()) == ["깨진영상.mp4", "메모.txt"]


def test_content_we_already_have_goes_to_the_reject_folder(tmp_path: Path) -> None:
    config, _roots, archive, reject = _sorted_config(tmp_path)
    config.watch_path.mkdir(parents=True, exist_ok=True)
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=2",
            "-pix_fmt", "yuv420p", str(config.watch_path / "촬영본.mp4"))

    run_inbox_cycle(config, is_settled=lambda path: True)
    # 같은 내용을 이름만 바꿔 다시 넣는다.
    shutil.copy2(archive / "촬영본.mp4", config.watch_path / "촬영본-복사본.mp4")

    second = run_inbox_cycle(config, is_settled=lambda path: True)

    assert second.duplicates == ["촬영본-복사본.mp4"]
    assert second.moved == []
    assert [path.name for path in reject.iterdir()] == ["촬영본-복사본.mp4"]


def test_a_second_pass_does_not_re_ingest_what_it_already_took(tmp_path: Path) -> None:
    config, _roots, _archive, _reject = _sorted_config(tmp_path)
    _fill_drop_folder(config.watch_path)

    run_inbox_cycle(config, is_settled=lambda path: True)
    second = run_inbox_cycle(config, is_settled=lambda path: True)

    assert (second.moved, second.duplicates, second.rejected, second.failed) == ([], [], [], [])
    store = LibraryUserAssetStore(tmp_path / "library" / ".videobox-library-state")
    assert len(store.list_assets()) == 4


def test_an_unsettled_file_is_left_alone(tmp_path: Path) -> None:
    config, _roots, _archive, reject = _sorted_config(tmp_path)
    config.watch_path.mkdir(parents=True, exist_ok=True)
    (config.watch_path / "받는중.mp4").write_bytes(b"\x00" * 128)

    report = run_inbox_cycle(config, is_settled=lambda path: False)

    assert report.skipped == ["받는중.mp4"]
    assert (config.watch_path / "받는중.mp4").is_file()
    assert not reject.exists()
