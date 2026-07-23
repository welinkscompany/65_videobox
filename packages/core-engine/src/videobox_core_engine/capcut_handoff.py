from __future__ import annotations

import os
import json
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class CapCutHandoffError(RuntimeError):
    """A recoverable Windows CapCut draft registration failure."""


@dataclass(frozen=True, slots=True)
class CapCutHandoffDiagnostics:
    status: str
    installation_path: Path | None
    detected_version: str | None
    is_supported: bool
    project_root_path: Path
    project_root_exists: bool
    write_access: bool
    recovery_message: str | None
    checked_at: str


@dataclass(frozen=True, slots=True)
class CapCutHandoffRecord:
    source_path: Path
    registered_path: Path
    export_id: str
    status: str
    registered_at: str
    reused: bool
    ownership_token: str | None = None


class CapCutHandoffService:
    """Register immutable VideoBox drafts in the supported local CapCut root."""

    def __init__(
        self,
        *,
        local_app_data: Path | None = None,
        copytree: Callable[[Path, Path], object] = shutil.copytree,
    ) -> None:
        self.local_app_data = local_app_data or Path(os.environ.get("LOCALAPPDATA") or "")
        self._copytree = copytree

    def register(
        self, *, source_draft_path: Path, export_id: str, ownership_token: str | None = None
    ) -> CapCutHandoffRecord:
        source = Path(source_draft_path)
        if not (source / "draft_content.json").is_file():
            raise CapCutHandoffError("VideoBox CapCut 초안 파일을 찾지 못했습니다. 내보내기를 다시 실행하세요.")

        project_root = self._project_root()
        destination = project_root / f"videobox-{export_id}"
        if self._is_owned_destination(destination=destination, export_id=export_id) and self._is_complete_draft(destination):
            return self._record(source=source, destination=destination, export_id=export_id, reused=True)
        if destination.exists():
            if not self._is_owned_destination(destination=destination, export_id=export_id):
                raise CapCutHandoffError(
                    "동일한 CapCut 프로젝트 폴더가 이미 있습니다. 해당 폴더를 확인하거나 이름을 바꾼 뒤 다시 시도하세요."
                )
            shutil.rmtree(destination)

        temporary = project_root / f".{destination.name}.{uuid4().hex}.tmp"
        created_destination = False
        try:
            self._copytree(source, temporary)
            if not self._is_complete_draft(temporary):
                raise OSError("copied CapCut draft is incomplete")
            temporary.replace(destination)
            created_destination = True
            self._write_ownership_marker(
                destination=destination,
                export_id=export_id,
                ownership_token=ownership_token,
            )
        except Exception as exc:
            shutil.rmtree(temporary, ignore_errors=True)
            if created_destination:
                shutil.rmtree(destination, ignore_errors=True)
            raise CapCutHandoffError(
                "CapCut 프로젝트 등록에 실패했습니다. 디스크 공간과 프로젝트 폴더 권한을 확인한 뒤 다시 시도하세요."
            ) from exc
        return self._record(
            source=source,
            destination=destination,
            export_id=export_id,
            reused=False,
            ownership_token=ownership_token,
        )

    def cleanup_request_owned_registration(
        self, *, record: CapCutHandoffRecord, ownership_token: str
    ) -> bool:
        """Remove only a destination and marker created by this exact request."""
        if record.reused or record.ownership_token != ownership_token:
            return False
        marker_path = self._ownership_marker_path(record.export_id)
        expected_marker = {
            "export_id": record.export_id,
            "registered_path": str(record.registered_path),
            "ownership_token": ownership_token,
        }
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if marker != expected_marker:
            return False
        try:
            marker_path.unlink()
            shutil.rmtree(record.registered_path, ignore_errors=False)
        except OSError:
            return False
        return True

    def diagnose(self) -> CapCutHandoffDiagnostics:
        project_root = self.local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        installation = self._find_installation()
        if installation is None:
            return self._diagnostics(
                installation_path=None,
                detected_version=None,
                is_supported=False,
                project_root_path=project_root,
                project_root_exists=project_root.is_dir(),
                write_access=False,
                recovery_message="CapCut 설치를 확인한 뒤 다시 진단하세요.",
            )
        detected_version = self._version_for(installation)
        if not self._is_supported_version(detected_version):
            return self._diagnostics(
                installation_path=installation,
                detected_version=detected_version,
                is_supported=False,
                project_root_path=project_root,
                project_root_exists=project_root.is_dir(),
                write_access=False,
                recovery_message="지원하는 CapCut 버전을 확인한 뒤 다시 진단하세요.",
            )
        if not project_root.is_dir():
            return self._diagnostics(
                installation_path=installation,
                detected_version=detected_version,
                is_supported=True,
                project_root_path=project_root,
                project_root_exists=False,
                write_access=False,
                recovery_message="CapCut을 한 번 실행해 프로젝트 폴더를 만든 뒤 다시 진단하세요.",
            )
        try:
            with tempfile.NamedTemporaryFile(dir=project_root, prefix=".videobox-write-check-", delete=True):
                pass
        except OSError:
            return self._diagnostics(
                installation_path=installation,
                detected_version=detected_version,
                is_supported=True,
                project_root_path=project_root,
                project_root_exists=True,
                write_access=False,
                recovery_message="CapCut 프로젝트 폴더 권한과 디스크 공간을 확인한 뒤 다시 진단하세요.",
            )
        return self._diagnostics(
            installation_path=installation,
            detected_version=detected_version,
            is_supported=True,
            project_root_path=project_root,
            project_root_exists=True,
            write_access=True,
            recovery_message=None,
        )

    def _project_root(self) -> Path:
        diagnostics = self.diagnose()
        if diagnostics.installation_path is None:
            raise CapCutHandoffError("CapCut 설치를 확인한 뒤 다시 시도하세요.")
        if not diagnostics.is_supported:
            raise CapCutHandoffError("지원하는 CapCut 버전을 확인한 뒤 다시 시도하세요.")
        if not diagnostics.project_root_exists:
            raise CapCutHandoffError("CapCut 프로젝트 폴더를 확인한 뒤 CapCut을 한 번 실행하세요.")
        if not diagnostics.write_access:
            raise CapCutHandoffError("CapCut 프로젝트 폴더에 쓸 수 없습니다. 폴더 권한을 확인한 뒤 다시 시도하세요.")
        return diagnostics.project_root_path

    def _find_installation(self) -> Path | None:
        apps_root = self.local_app_data / "CapCut" / "Apps"
        if not apps_root.is_dir():
            return None
        candidates = [path for path in apps_root.rglob("CapCut.exe") if path.is_file()]
        if not candidates:
            return None
        return max(candidates, key=self._installation_sort_key)

    @staticmethod
    def _version_for(executable: Path) -> str | None:
        name = executable.parent.name
        return name if all(part.isdigit() for part in name.split(".")) else None

    @classmethod
    def _installation_sort_key(cls, executable: Path) -> tuple[int, tuple[int, ...], str]:
        version = cls._version_for(executable)
        return (1 if version else 0, tuple(int(part) for part in version.split(".")) if version else (), str(executable))

    @staticmethod
    def _is_supported_version(version: str | None) -> bool:
        return version is not None and any(version.startswith(prefix) for prefix in ("8.7.", "8.9."))

    def _ownership_marker_path(self, export_id: str) -> Path:
        return self.local_app_data / "VideoBox" / "capcut-handoffs" / f"{export_id}.json"

    def _is_owned_destination(self, *, destination: Path, export_id: str) -> bool:
        marker_path = self._ownership_marker_path(export_id)
        if not marker_path.is_file():
            return False
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(marker, dict) and (
            marker.get("export_id") == export_id
            and marker.get("registered_path") == str(destination)
        )

    def _write_ownership_marker(
        self, *, destination: Path, export_id: str, ownership_token: str | None = None
    ) -> None:
        marker_path = self._ownership_marker_path(export_id)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = marker_path.with_suffix(".tmp")
        marker = {"export_id": export_id, "registered_path": str(destination)}
        if ownership_token is not None:
            marker["ownership_token"] = ownership_token
        temporary.write_text(
            json.dumps(marker),
            encoding="utf-8",
        )
        temporary.replace(marker_path)

    @staticmethod
    def _diagnostics(
        *,
        installation_path: Path | None,
        detected_version: str | None,
        is_supported: bool,
        project_root_path: Path,
        project_root_exists: bool,
        write_access: bool,
        recovery_message: str | None,
    ) -> CapCutHandoffDiagnostics:
        return CapCutHandoffDiagnostics(
            status="ready" if recovery_message is None else "failed",
            installation_path=installation_path,
            detected_version=detected_version,
            is_supported=is_supported,
            project_root_path=project_root_path,
            project_root_exists=project_root_exists,
            write_access=write_access,
            recovery_message=recovery_message,
            checked_at=datetime.now(UTC).isoformat(),
        )

    @staticmethod
    def _is_complete_draft(path: Path) -> bool:
        return path.is_dir() and (path / "draft_content.json").is_file()

    @staticmethod
    def _record(
        *, source: Path, destination: Path, export_id: str, reused: bool, ownership_token: str | None = None
    ) -> CapCutHandoffRecord:
        return CapCutHandoffRecord(
            source_path=source,
            registered_path=destination,
            export_id=export_id,
            status="ready",
            registered_at=datetime.now(UTC).isoformat(),
            reused=reused,
            ownership_token=ownership_token,
        )


__all__ = ["CapCutHandoffDiagnostics", "CapCutHandoffError", "CapCutHandoffRecord", "CapCutHandoffService"]
