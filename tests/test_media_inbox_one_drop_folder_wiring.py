"""한 폴더 분류가 실제로 앱에 배선돼 있는가 (owner 승인 2026-09-07).

부품이 있는 것과 제품이 되는 것은 다르다. `media_inbox_sorter`가 아무리 잘
갈라도 감시 설정이 그걸 안 쓰면 owner에게는 없는 기능이다.
"""

from __future__ import annotations

from pathlib import Path

from videobox_api.main import create_app


def _clear(monkeypatch) -> None:
    for name in (
        "VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED",
        "VIDEOBOX_MEDIA_INBOX_WATCH_INTERVAL_SECONDS",
        "VIDEOBOX_MEDIA_INBOX_WATCH_PATH",
        "VIDEOBOX_MEDIA_INBOX_LIBRARY_ROOT",
        "VIDEOBOX_OWNER_DROP_REJECT_PATH",
        "VIDEOBOX_OWNER_DROP_ARCHIVE_PATH",
        "VIDEOBOX_MEDIA_INBOX_SORT_BY_CONTENT",
        "VIDEOBOX_OWNER_AUDIO_LIBRARY_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_the_one_drop_folder_sorts_by_content_by_default(tmp_path: Path, monkeypatch) -> None:
    _clear(monkeypatch)
    drop = tmp_path / "onedrive" / "#_videobox"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(drop))

    app = create_app()
    config = app.state.media_inbox_watch_config

    assert config.sort_by_content is True
    # `불필요`는 넣는 폴더의 형제다. 안에 있으면 다음 바퀴가 다시 집어 든다.
    assert config.reject_root == tmp_path / "onedrive" / "불필요"
    # 보관함은 **넣는 폴더 안**이다. 넣는 폴더가 컨테이너에서 마운트 뿌리라,
    # 형제로 두면 읽기 전용 루트를 가리켜 원본 옮기기가 전부 실패한다.
    assert config.archive_root == drop / "자산화_완료"
    assert set(config.sorted_library_roots) == {"broll", "image", "music", "sfx"}
    # 네 자리가 서로 달라야 한다. 섞이면 촬영본 색인이 음원을 분석하려 든다.
    assert len(set(config.sorted_library_roots.values())) == 4


def test_every_sorted_destination_is_a_root_the_api_can_serve_from(tmp_path: Path, monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(tmp_path / "onedrive" / "#_videobox"))

    app = create_app()
    served = {Path(root).resolve() for root in app.state.library_asset_managed_roots}

    # 갈라 넣은 자산은 화면에서 미리 듣고 볼 수 있어야 한다. 자리가 서빙 뿌리
    # 밖이면 목록에는 뜨는데 재생만 조용히 404가 된다.
    for root in app.state.media_inbox_sorted_library_roots.values():
        assert Path(root).resolve() in served


def test_the_old_per_kind_folders_are_no_longer_created(tmp_path: Path, monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(tmp_path / "onedrive" / "#_videobox"))

    app = create_app()

    assert all(not config.create_watch_path for config in app.state.owner_audio_watch_configs)


def test_sorting_can_be_turned_off(tmp_path: Path, monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(tmp_path / "onedrive" / "#_videobox"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_SORT_BY_CONTENT", "0")

    app = create_app()
    config = app.state.media_inbox_watch_config

    assert config.sort_by_content is False
    assert config.reject_root is None
    assert all(config.create_watch_path for config in app.state.owner_audio_watch_configs)
