from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from videobox_core_engine.capcut_handoff import CapCutHandoffError, CapCutHandoffService


def _write_draft(path: Path, content: str = '{"draft": true}') -> Path:
    path.mkdir(parents=True)
    (path / "draft_content.json").write_text(content, encoding="utf-8")
    (path / "draft_meta_info.json").write_text("{}", encoding="utf-8")
    return path


def _configured_service(tmp_path: Path) -> tuple[CapCutHandoffService, Path]:
    local_app_data = tmp_path / "LocalAppData"
    (local_app_data / "CapCut" / "Apps" / "8.7.0" / "CapCut.exe").parent.mkdir(parents=True)
    (local_app_data / "CapCut" / "Apps" / "8.7.0" / "CapCut.exe").write_bytes(b"capcut")
    project_root = local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    project_root.mkdir(parents=True)
    return CapCutHandoffService(local_app_data=local_app_data), project_root


def test_register_copies_draft_without_mutating_source_and_reports_ready_path(tmp_path: Path) -> None:
    service, project_root = _configured_service(tmp_path)
    source = _write_draft(tmp_path / "videobox-source" / "timeline_002", '{"source": "immutable"}')
    source_hash = hashlib.sha256((source / "draft_content.json").read_bytes()).hexdigest()

    result = service.register(source_draft_path=source, export_id="export_002")

    assert result.status == "ready"
    assert result.reused is False
    assert result.source_path == source
    assert result.registered_path == project_root / "videobox-export_002"
    assert (result.registered_path / "draft_content.json").read_text(encoding="utf-8") == '{"source": "immutable"}'
    assert hashlib.sha256((source / "draft_content.json").read_bytes()).hexdigest() == source_hash


def test_register_reuses_complete_matching_destination_idempotently(tmp_path: Path) -> None:
    service, _ = _configured_service(tmp_path)
    source = _write_draft(tmp_path / "source" / "timeline_002")

    first = service.register(source_draft_path=source, export_id="export_002")
    second = service.register(source_draft_path=source, export_id="export_002")

    assert second.status == "ready"
    assert second.reused is True
    assert second.registered_path == first.registered_path


def test_register_replaces_incomplete_collision_and_removes_partial_directory(tmp_path: Path) -> None:
    service, project_root = _configured_service(tmp_path)
    source = _write_draft(tmp_path / "source" / "timeline_002")
    incomplete = project_root / "videobox-export_002"
    incomplete.mkdir()
    (incomplete / "partial.tmp").write_text("broken", encoding="utf-8")

    result = service.register(source_draft_path=source, export_id="export_002")

    assert result.reused is False
    assert (result.registered_path / "draft_content.json").is_file()
    assert not (result.registered_path / "partial.tmp").exists()
    assert not list(project_root.glob(".videobox-export_002.*.tmp"))


def test_register_rolls_back_temporary_copy_failure_without_touching_source(tmp_path: Path) -> None:
    def failing_copy(source: Path, destination: Path) -> None:
        destination.mkdir(parents=True)
        (destination / "partial.tmp").write_text("broken", encoding="utf-8")
        raise OSError("disk full")

    service, project_root = _configured_service(tmp_path)
    source = _write_draft(tmp_path / "source" / "timeline_002")
    service = CapCutHandoffService(local_app_data=service.local_app_data, copytree=failing_copy)

    with pytest.raises(CapCutHandoffError, match="CapCut 프로젝트 등록에 실패"):
        service.register(source_draft_path=source, export_id="export_002")

    assert (source / "draft_content.json").is_file()
    assert not (project_root / "videobox-export_002").exists()
    assert not list(project_root.glob(".videobox-export_002.*.tmp"))


def test_register_reports_recovery_guidance_when_capcut_project_root_is_not_writable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _ = _configured_service(tmp_path)
    source = _write_draft(tmp_path / "source" / "timeline_002")

    def denied_write_probe(*args: object, **kwargs: object) -> None:
        raise PermissionError("access denied")

    monkeypatch.setattr("videobox_core_engine.capcut_handoff.tempfile.NamedTemporaryFile", denied_write_probe)

    with pytest.raises(CapCutHandoffError, match="폴더에 쓸 수 없습니다"):
        service.register(source_draft_path=source, export_id="export_002")


def test_diagnose_reports_the_highest_supported_version_and_removes_its_write_probe(tmp_path: Path) -> None:
    service, project_root = _configured_service(tmp_path)
    newer_executable = service.local_app_data / "CapCut" / "Apps" / "8.10.0.1" / "CapCut.exe"
    newer_executable.parent.mkdir(parents=True)
    newer_executable.write_bytes(b"capcut-newer")

    result = service.diagnose()

    assert result.status == "ready"
    assert result.installation_path == newer_executable
    assert result.detected_version == "8.10.0.1"
    assert result.project_root_path == project_root
    assert result.project_root_exists is True
    assert result.write_access is True
    assert result.recovery_message is None
    assert not list(project_root.glob(".videobox-write-check-*"))


@pytest.mark.parametrize(
    ("setup", "expected_message"),
    [
        ("missing_capcut", "CapCut 설치를 확인"),
        ("missing_project_root", "CapCut을 한 번 실행"),
    ],
)
def test_diagnose_returns_korean_recovery_for_missing_capcut_prerequisites(
    tmp_path: Path, setup: str, expected_message: str
) -> None:
    local_app_data = tmp_path / "LocalAppData"
    if setup == "missing_project_root":
        executable = local_app_data / "CapCut" / "Apps" / "8.7.0" / "CapCut.exe"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"capcut")

    result = CapCutHandoffService(local_app_data=local_app_data).diagnose()

    assert result.status == "failed"
    assert result.write_access is False
    assert expected_message in (result.recovery_message or "")


def test_diagnose_returns_korean_recovery_when_write_probe_is_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _ = _configured_service(tmp_path)

    def denied_write_probe(*args: object, **kwargs: object) -> None:
        raise PermissionError("access denied")

    monkeypatch.setattr("videobox_core_engine.capcut_handoff.tempfile.NamedTemporaryFile", denied_write_probe)

    result = service.diagnose()

    assert result.status == "failed"
    assert result.write_access is False
    assert "권한과 디스크 공간" in (result.recovery_message or "")


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("missing_capcut", "CapCut 설치를 확인"),
        ("missing_project_root", "CapCut 프로젝트 폴더를 확인"),
        ("missing_source", "VideoBox CapCut 초안 파일을 찾지 못했습니다"),
    ],
)
def test_register_reports_explicit_recovery_guidance_for_missing_prerequisites(
    tmp_path: Path, setup: str, message: str
) -> None:
    local_app_data = tmp_path / "LocalAppData"
    source = _write_draft(tmp_path / "source" / "timeline_002")
    if setup != "missing_capcut":
        executable = local_app_data / "CapCut" / "Apps" / "8.7.0" / "CapCut.exe"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"capcut")
    if setup == "missing_source":
        project_root = local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        project_root.mkdir(parents=True)
        source = tmp_path / "missing" / "timeline_002"
    service = CapCutHandoffService(local_app_data=local_app_data)

    with pytest.raises(CapCutHandoffError, match=message):
        service.register(source_draft_path=source, export_id="export_002")
