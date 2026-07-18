from pathlib import Path

from videobox_core_engine.settings import DEFAULT_PROJECTS_ROOT, resolve_projects_root


def test_projects_root_uses_videobox_data_root_environment(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "managed-data"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(configured))

    assert resolve_projects_root() == configured


def test_projects_root_keeps_host_default_without_override(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOBOX_DATA_ROOT", raising=False)

    assert resolve_projects_root() == DEFAULT_PROJECTS_ROOT
