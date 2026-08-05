"""CapCut draft export is off in the container for the same reason speech-to-text
was: `create_app` runs with no arguments there, so the exporter resolves to None
and no draft is ever produced.

Output size is environment-driven because the owner shoots 1920x1080 and will
also want vertical output for shortform.
"""

import pytest

from videobox_core_engine.settings import (
    CapCutDraftExportConfig,
    resolve_capcut_draft_export_config,
)


def _clear_capcut_environment(monkeypatch) -> None:
    for name in (
        "VIDEOBOX_CAPCUT_ENABLED",
        "VIDEOBOX_CAPCUT_WIDTH",
        "VIDEOBOX_CAPCUT_HEIGHT",
        "VIDEOBOX_CAPCUT_FPS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_capcut_stays_disabled_when_nothing_is_configured(monkeypatch) -> None:
    _clear_capcut_environment(monkeypatch)

    assert resolve_capcut_draft_export_config().enabled is False


def test_capcut_enables_from_the_environment(monkeypatch) -> None:
    _clear_capcut_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_CAPCUT_ENABLED", "1")

    assert resolve_capcut_draft_export_config().enabled is True


def test_capcut_reads_output_size_from_the_environment(monkeypatch) -> None:
    _clear_capcut_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_CAPCUT_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_CAPCUT_WIDTH", "1920")
    monkeypatch.setenv("VIDEOBOX_CAPCUT_HEIGHT", "1080")
    monkeypatch.setenv("VIDEOBOX_CAPCUT_FPS", "30")

    config = resolve_capcut_draft_export_config()

    assert (config.video_width, config.video_height, config.video_fps) == (1920, 1080, 30)


def test_capcut_supports_a_vertical_canvas(monkeypatch) -> None:
    """Shortform output is vertical; the resolver must not assume landscape."""
    _clear_capcut_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_CAPCUT_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_CAPCUT_WIDTH", "1080")
    monkeypatch.setenv("VIDEOBOX_CAPCUT_HEIGHT", "1920")

    config = resolve_capcut_draft_export_config()

    assert config.video_height > config.video_width


@pytest.mark.parametrize("value", ["", "   ", "not-a-number", "0", "-5"])
def test_unusable_size_values_fall_back_to_defaults(monkeypatch, value: str) -> None:
    _clear_capcut_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_CAPCUT_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_CAPCUT_WIDTH", value)

    assert resolve_capcut_draft_export_config().video_width == CapCutDraftExportConfig().video_width
