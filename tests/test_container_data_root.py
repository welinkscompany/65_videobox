from pathlib import Path

from videobox_api.main import create_app
from videobox_core_engine.settings import (
    DEFAULT_PROJECTS_ROOT,
    resolve_database_url,
    resolve_projects_root,
    resolve_user_library_root,
)


def test_projects_root_uses_videobox_data_root_environment(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "managed-data"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(configured))

    assert resolve_projects_root() == configured


def test_projects_root_keeps_host_default_without_override(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOBOX_DATA_ROOT", raising=False)

    assert resolve_projects_root() == DEFAULT_PROJECTS_ROOT


def test_user_library_root_uses_configured_data_root(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "managed-data"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(configured))

    assert resolve_user_library_root() == configured / "videobox-user-library"


def test_user_library_root_keeps_host_default_without_override(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOBOX_DATA_ROOT", raising=False)

    assert resolve_user_library_root() == DEFAULT_PROJECTS_ROOT.parent / "videobox-user-library"


def test_create_app_places_default_libraries_under_configured_data_root(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "managed-data"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(configured))

    app = create_app()

    expected_root = configured / "videobox-user-library"
    assert app.state.user_library_store.root == expected_root
    assert app.state.media_library_store.root == expected_root


def test_create_app_keeps_explicit_projects_root_library_sibling(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "managed-data"))
    projects_root = tmp_path / "explicit-projects"

    app = create_app(projects_root=projects_root)

    expected_root = projects_root.parent / "videobox-user-library"
    assert app.state.user_library_store.root == expected_root
    assert app.state.media_library_store.root == expected_root


def test_database_url_is_opt_in_and_never_has_a_default(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOBOX_DATABASE_URL", raising=False)
    assert resolve_database_url() is None

    monkeypatch.setenv("VIDEOBOX_DATABASE_URL", "postgresql://videobox:secret@postgres/videobox")
    assert resolve_database_url() == "postgresql://videobox:secret@postgres/videobox"
