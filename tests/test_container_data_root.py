from pathlib import Path

from videobox_core_engine.settings import (
    DEFAULT_PROJECTS_ROOT,
    resolve_database_url,
    resolve_projects_root,
)


def test_projects_root_uses_videobox_data_root_environment(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "managed-data"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(configured))

    assert resolve_projects_root() == configured


def test_projects_root_keeps_host_default_without_override(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOBOX_DATA_ROOT", raising=False)

    assert resolve_projects_root() == DEFAULT_PROJECTS_ROOT


def test_database_url_is_opt_in_and_never_has_a_default(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOBOX_DATABASE_URL", raising=False)
    assert resolve_database_url() is None

    monkeypatch.setenv("VIDEOBOX_DATABASE_URL", "postgresql://videobox:secret@postgres/videobox")
    assert resolve_database_url() == "postgresql://videobox:secret@postgres/videobox"
