from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from videobox_core_engine.asset_browser_preview import (
    BrowserPreviewError,
    FFmpegBrowserPreviewRenderer,
    FFprobeBrowserPreviewProbe,
)


def _result(*, stdout: str = "", stderr: str = "", returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _probe_payload(*, codec: str = "h264", pixel: str = "yuv420p", audio: str | None = "aac", format_name: str = "mov,mp4,m4a,3gp,3g2,mj2") -> str:
    streams = [{"codec_type": "video", "codec_name": codec, "pix_fmt": pixel, "width": 1920, "height": 1080}]
    if audio is not None:
        streams.append({"codec_type": "audio", "codec_name": audio})
    return json.dumps({"streams": streams, "format": {"format_name": format_name}})


def test_probe_reads_only_stream_and_format_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict]] = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return _result(stdout=_probe_payload())

    monkeypatch.setattr("videobox_core_engine.asset_browser_preview.subprocess.run", run)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")

    result = FFprobeBrowserPreviewProbe().probe(source)

    assert result.video_codec == "h264"
    assert result.pixel_format == "yuv420p"
    assert result.audio_codec == "aac"
    assert result.width == 1920
    assert result.height == 1080
    assert result.browser_compatible is True
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:7] == ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json"]
    assert command[-1] == str(source)
    assert kwargs == {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace", "timeout": 30, "check": False}


@pytest.mark.parametrize(
    ("codec", "pixel", "audio", "format_name", "compatible"),
    [
        ("h264", "yuv420p", "aac", "mov,mp4,m4a,3gp,3g2,mj2", True),
        ("h264", "yuv420p", None, "mov,mp4,m4a,3gp,3g2,mj2", True),
        ("hevc", "yuv420p", "aac", "mov,mp4,m4a,3gp,3g2,mj2", False),
        ("h264", "yuv422p", "aac", "mov,mp4,m4a,3gp,3g2,mj2", False),
        ("h264", "yuv420p", "opus", "mov,mp4,m4a,3gp,3g2,mj2", False),
        ("h264", "yuv420p", "aac", "matroska,webm", False),
    ],
)
def test_probe_uses_strict_browser_compatibility_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, codec: str, pixel: str, audio: str | None, format_name: str, compatible: bool) -> None:
    monkeypatch.setattr(
        "videobox_core_engine.asset_browser_preview.subprocess.run",
        lambda *_args, **_kwargs: _result(stdout=_probe_payload(codec=codec, pixel=pixel, audio=audio, format_name=format_name)),
    )
    source = tmp_path / "source.bin"
    source.write_bytes(b"video")
    assert FFprobeBrowserPreviewProbe().probe(source).browser_compatible is compatible


def test_renderer_builds_bounded_browser_proxy_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        Path(command[-1]).write_bytes(b"proxy")
        return _result()

    monkeypatch.setattr("videobox_core_engine.asset_browser_preview.subprocess.run", run)
    source = tmp_path / "source.mov"
    destination = tmp_path / "preview.tmp.mp4"
    source.write_bytes(b"video")

    FFmpegBrowserPreviewRenderer().render(source, destination)

    command = captured["command"]
    assert command[:6] == ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i"]
    assert ["-map", "0:v:0"] == command[command.index("-map"):command.index("-map") + 2]
    assert "0:a:0?" in command
    assert "libx264" in command
    assert "yuv420p" in command
    assert "aac" in command
    assert "avc1" in command
    assert "+faststart" in command
    assert "1280" in command[command.index("-vf") + 1]
    assert command[-1] == str(destination)
    assert captured["kwargs"] == {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace", "timeout": 3600, "check": False}


@pytest.mark.parametrize("failure", [OSError("C:/private/ffmpeg missing"), _result(stderr="C:/private/source.mov: secret failure", returncode=1)])
def test_probe_and_renderer_fail_with_bounded_error_codes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure) -> None:
    def run(*_args, **_kwargs):
        if isinstance(failure, BaseException):
            raise failure
        return failure

    monkeypatch.setattr("videobox_core_engine.asset_browser_preview.subprocess.run", run)
    source = tmp_path / "private-source.mov"
    source.write_bytes(b"video")

    with pytest.raises(BrowserPreviewError) as exc_info:
        if isinstance(failure, BaseException):
            FFprobeBrowserPreviewProbe().probe(source)
        else:
            FFmpegBrowserPreviewRenderer().render(source, tmp_path / "preview.tmp.mp4")

    assert exc_info.value.code in {"PREVIEW_PROBE_UNAVAILABLE", "PREVIEW_RENDER_FAILED"}
    assert "private" not in str(exc_info.value).lower()
