r"""기본 감시 폴더에 사람 이름이 박혀 있었다 — 2026-09-07.

`DEFAULT_MEDIA_INBOX_WATCH_PATH`가 `C:\Users\atgro\OneDrive\#_videobox`였다.
컨테이너는 환경변수로 덮어쓰므로 실제로 걸리는 자리는 아니지만, **다른 컴퓨터에서
켜면 남의 계정 폴더를 가리킨다.** 옛 값(`G:\내 드라이브\100_videobox`)도 같은
모양이었고, 이번에 그 줄을 손댄 김에 정리한다.

실제 자리는 설정에서 온다(`compose.yaml`의 `VIDEOBOX_MEDIA_INBOX_WATCH_PATH`).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from videobox_core_engine.settings import resolve_media_inbox_watch_path


def test_the_default_follows_whoever_is_logged_in() -> None:
    """**기본값이 이 컴퓨터 주인을 따라가야 한다.**

    처음엔 "결과에 계정 이름이 없어야 한다"고 물었는데 그건 틀린 물음이었다 --
    `Path.home()`은 당연히 그 컴퓨터 주인의 폴더로 풀린다. 진짜로 지킬 것은
    **소스에 특정 계정이 박혀 있지 않다**는 것이다.
    """
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", None)
        default = resolve_media_inbox_watch_path()

    assert default is not None
    assert Path.home() in default.parents, f"집 폴더 아래가 아니다: {default}"

    from videobox_core_engine import settings as settings_module

    text = Path(settings_module.__file__).read_text(encoding="utf-8")
    line = next(
        row for row in text.splitlines()
        if row.startswith("DEFAULT_MEDIA_INBOX_WATCH_PATH =")
    )
    assert "Users" not in line and "\\" not in line, f"소스에 계정 경로가 박혀 있다: {line}"


def test_the_configured_path_still_wins() -> None:
    """설정이 진실이다 -- 컨테이너는 늘 이 길로 온다."""
    with patch.dict(os.environ, {"VIDEOBOX_MEDIA_INBOX_WATCH_PATH": "/videobox-drop"}):
        assert resolve_media_inbox_watch_path() == Path("/videobox-drop")


def test_clearing_it_turns_the_watcher_off() -> None:
    """빈 값은 "감시하지 않는다"이다 -- 있던 계약을 지킨다."""
    with patch.dict(os.environ, {"VIDEOBOX_MEDIA_INBOX_WATCH_PATH": ""}):
        assert resolve_media_inbox_watch_path() is None
