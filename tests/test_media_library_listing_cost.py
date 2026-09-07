"""자료실 목록이 자산마다 파일시스템을 몇 번 건드리는지 지킨다.

owner 지적(2026-09-04): "영상 불러오는것 조차도 느리고".

실측으로 원인을 찾았다. 컨테이너의 `/videobox-data`는 Windows `D:\`의 **9p
마운트**라 파일 메타데이터 호출 하나하나가 느리다. 자산 130개 기준:

    stat     290ms
    is_file  275ms
    resolve  1157ms   <- 캐시 키를 만드는 데만 썼다
    ------------------
    합계    ~1722ms

`GET /api/media-library/assets`가 2.5초 걸렸고 그중 대부분이 이것이었다.
`resolve()`는 심볼릭 링크를 풀려고 경로를 끝까지 걸어가는데, 여기서는 **우리
DB가 준 경로**를 쓰고 sha256도 키에 함께 들어가므로 풀 이유가 없다.
`is_file()`도 `stat()`이 이미 답을 갖고 있어 한 번 더 물을 필요가 없다.

여기서 지키는 것은 **자산 하나에 파일 호출 한 번**이다. 다시 늘면 owner가
다시 "느리다"고 말하게 된다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from videobox_storage.media_library_store import MediaLibraryStore


def _store(tmp_path: Path) -> MediaLibraryStore:
    return MediaLibraryStore(tmp_path / "library.sqlite")


def test_verification_touches_the_file_once_per_asset(tmp_path, monkeypatch):
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()

    calls: list[str] = []
    real_stat = Path.stat
    monkeypatch.setattr(Path, "stat", lambda self, *a, **k: (calls.append("stat"), real_stat(self, *a, **k))[1])
    monkeypatch.setattr(Path, "resolve", lambda self, *a, **k: (_ for _ in ()).throw(AssertionError("resolve()는 9p에서 130개에 1157ms다 -- 쓰지 않는다")))
    monkeypatch.setattr(Path, "is_file", lambda self: (_ for _ in ()).throw(AssertionError("stat()이 이미 답을 갖고 있다 -- 한 번 더 묻지 않는다")))

    store = _store(tmp_path)
    assert store._is_currently_verified(target, digest) is True
    assert calls == ["stat"], f"자산 하나에 파일 호출이 한 번이 아니다: {calls}"


def test_still_says_no_when_the_bytes_changed(tmp_path):
    """빨라지려고 정확성을 버리지 않았는지 본다."""
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"payload")
    store = _store(tmp_path)
    assert store._is_currently_verified(target, hashlib.sha256(b"payload").hexdigest()) is True
    assert store._is_currently_verified(target, hashlib.sha256(b"other").hexdigest()) is False


def test_says_no_for_a_missing_file_and_for_a_directory(tmp_path):
    store = _store(tmp_path)
    assert store._is_currently_verified(tmp_path / "gone.mp4", "0" * 64) is False
    # 디렉터리는 파일이 아니다 -- `is_file()`을 뺐으니 이 경우를 놓치면 안 된다.
    (tmp_path / "folder").mkdir()
    assert store._is_currently_verified(tmp_path / "folder", "0" * 64) is False
