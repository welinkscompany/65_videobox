"""The escape hatch the error message names has to be the one the code reads.

A text overlay that cannot find a font raises "set VIDEOBOX_OVERLAY_FONT
before rendering text overlays." The code read `VIDEBOX_OVERLAY_FONT` -- an
`O` short -- so following the instruction changed nothing and the render kept
failing the same way.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer


def _clear(monkeypatch: pytest.MonkeyPatch, **environment: str) -> None:
    monkeypatch.delenv("VIDEOBOX_OVERLAY_FONT", raising=False)
    monkeypatch.delenv("VIDEBOX_OVERLAY_FONT", raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)


def test_the_variable_the_failure_message_names_is_the_one_that_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch, VIDEOBOX_OVERLAY_FONT="/usr/share/fonts/truetype/test/Test.ttf")

    renderer = FfmpegFinalRenderer(store=None)

    assert renderer.overlay_font_file == "/usr/share/fonts/truetype/test/Test.ttf"


def test_the_default_font_is_not_a_windows_path_the_container_can_never_have(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The stack runs in a Linux container. A `C:\Windows\Fonts` default can
    # only ever be missing there, so the very first text overlay fails.
    _clear(monkeypatch)

    renderer = FfmpegFinalRenderer(store=None)

    assert not renderer.overlay_font_file.startswith("C:")
    assert "\\" not in renderer.overlay_font_file
