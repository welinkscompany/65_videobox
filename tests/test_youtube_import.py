from __future__ import annotations

from pathlib import Path

import pytest

from videobox_core_engine.youtube_import import (
    YoutubeImportError,
    download_youtube_video,
    is_youtube_url,
)


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "http://m.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
])
def test_recognizes_real_youtube_url_shapes(url: str) -> None:
    assert is_youtube_url(url)


@pytest.mark.parametrize("url", [
    "https://vimeo.com/12345",
    "https://example.com/watch?v=dQw4w9WgXcQ",
    "not a url at all",
    "",
    "https://evil.example.com/youtube.com/watch?v=dQw4w9WgXcQ",
])
def test_rejects_anything_that_is_not_actually_youtube(url: str) -> None:
    assert not is_youtube_url(url)


def test_download_rejects_a_non_youtube_url_before_touching_the_network(tmp_path: Path) -> None:
    with pytest.raises(YoutubeImportError):
        download_youtube_video("https://vimeo.com/12345", tmp_path)


class _FakeYoutubeDL:
    """실제 네트워크에 안 닿는다 -- yt-dlp가 파일을 실제로 받았다고 흉내만 낸다."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def __enter__(self) -> "_FakeYoutubeDL":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = True) -> dict:
        destination = Path(self.options["outtmpl"].replace("%(id)s", "abc123").replace("%(ext)s", "mp4"))
        destination.write_bytes(b"fake mp4 bytes")
        return {"id": "abc123", "ext": "mp4"}

    def prepare_filename(self, info: dict) -> str:
        return self.options["outtmpl"].replace("%(id)s", info["id"]).replace("%(ext)s", info["ext"])


def test_download_returns_the_produced_file_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import yt_dlp

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYoutubeDL)

    result = download_youtube_video("https://youtu.be/dQw4w9WgXcQ", tmp_path)

    assert result.is_file()
    assert result.read_bytes() == b"fake mp4 bytes"


class _FailingYoutubeDL(_FakeYoutubeDL):
    def extract_info(self, url: str, download: bool = True) -> dict:
        raise RuntimeError("video unavailable")


def test_download_wraps_yt_dlp_failures_in_a_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import yt_dlp

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FailingYoutubeDL)

    with pytest.raises(YoutubeImportError):
        download_youtube_video("https://youtu.be/dQw4w9WgXcQ", tmp_path)
