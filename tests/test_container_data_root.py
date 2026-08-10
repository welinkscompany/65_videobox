from pathlib import Path

from videobox_api.main import create_app
from videobox_core_engine.settings import (
    DEFAULT_PROJECTS_ROOT,
    resolve_database_url,
    resolve_projects_root,
    resolve_user_library_root,
)
from videobox_storage.local_project_store import LocalProjectStore
import pytest


def test_startup_records_which_store_it_opened(monkeypatch, tmp_path: Path, caplog) -> None:
    """The store is chosen at runtime: VIDEOBOX_DATABASE_URL means Postgres,
    its absence means a local SQLite file. A missing line in the environment
    therefore does not fail -- the API starts cleanly and reads an empty local
    database instead of the owner's real one, which on screen looks exactly
    like every project having vanished. Recording the choice at startup turns
    that from a mystery into one line of the log."""
    import logging

    monkeypatch.delenv("VIDEOBOX_DATABASE_URL", raising=False)

    with caplog.at_level(logging.INFO, logger="videobox_api.main"):
        create_app(projects_root=tmp_path / "projects")

    records = [record.getMessage() for record in caplog.records]
    assert any("파일 저장소" in message for message in records), records


def test_recorded_database_location_never_carries_the_password() -> None:
    """The database URL carries POSTGRES_PASSWORD. Logs leave the container, so
    the startup line keeps the host and database name and drops the rest."""
    from videobox_api.main import _redact_database_url

    redacted = _redact_database_url(
        "postgresql://videobox:s3cr3t-pw@videobox-postgres:5432/videobox"
    )

    assert "s3cr3t-pw" not in redacted
    assert "videobox" in redacted
    assert redacted == "videobox-postgres:5432/videobox"


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


def test_create_app_refuses_database_mode_without_a_verified_snapshot(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("VIDEOBOX_SNAPSHOT_ROOT", str(tmp_path / "snapshot"))
    monkeypatch.setenv("VIDEOBOX_DATABASE_URL", "postgresql://videobox:secret@postgres/videobox")

    with pytest.raises(ValueError, match="verified container snapshot"):
        create_app()


def test_create_app_refuses_container_mode_without_a_database_url(monkeypatch, tmp_path: Path) -> None:
    """컨테이너 모드인데 주소가 없으면 뜨지 않아야 한다.

    폴백이 남아 있으면 프로그램은 멀쩡히 뜨고 빈 파일 저장소를 연다. 화면에서
    그것은 "프로젝트가 전부 사라짐"과 구분되지 않는다. 판별 기준은 "주소가
    없는가"가 아니라 "컨테이너 모드인가"다 -- 손으로 돌리는 개발 실행은
    여전히 파일 저장소를 쓸 수 있어야 한다.
    """
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("VIDEOBOX_SNAPSHOT_ROOT", str(tmp_path / "snapshot"))
    monkeypatch.delenv("VIDEOBOX_DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="VIDEOBOX_DATABASE_URL"):
        create_app()


def test_create_app_keeps_host_sqlite_mode_without_container_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("VIDEOBOX_DATABASE_URL", raising=False)
    monkeypatch.delenv("VIDEOBOX_SNAPSHOT_ROOT", raising=False)
    monkeypatch.delenv("VIDEOBOX_DATA_ROOT", raising=False)

    app = create_app(projects_root=tmp_path / "host-projects")

    assert isinstance(app.state.store, LocalProjectStore)
