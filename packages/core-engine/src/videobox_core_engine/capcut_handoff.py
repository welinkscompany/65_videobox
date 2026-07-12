from __future__ import annotations

import os
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
    project_root_path: Path
    project_root_exists: bool
    write_access: bool
    recovery_message: str | None
    checked_at: str


@dataclass(frozen=True, slots=True)
class CapCutHandoffRecord:
    source_path: Path
    registered_path: Path
    status: str
    registered_at: str
    reused: bool


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

    def register(self, *, source_draft_path: Path, export_id: str) -> CapCutHandoffRecord:
        source = Path(source_draft_path)
        if not (source / "draft_content.json").is_file():
            raise CapCutHandoffError("VideoBox CapCut 초안 파일을 찾지 못했습니다. 내보내기를 다시 실행하세요.")

        project_root = self._project_root()
        destination = project_root / f"videobox-{export_id}"
        if self._is_complete_draft(destination):
            return self._record(source=source, destination=destination, reused=True)
        if destination.exists():
            shutil.rmtree(destination)

        temporary = project_root / f".{destination.name}.{uuid4().hex}.tmp"
        try:
            self._copytree(source, temporary)
            if not self._is_complete_draft(temporary):
                raise OSError("copied CapCut draft is incomplete")
            temporary.replace(destination)
        except Exception as exc:
            shutil.rmtree(temporary, ignore_errors=True)
            raise CapCutHandoffError(
                "CapCut 프로젝트 등록에 실패했습니다. 디스크 공간과 프로젝트 폴더 권한을 확인한 뒤 다시 시도하세요."
            ) from exc
        return self._record(source=source, destination=destination, reused=False)

    def diagnose(self) -> CapCutHandoffDiagnostics:
        project_root = self.local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        installation = self._find_installation()
        if installation is None:
            return self._diagnostics(
                installation_path=None,
                detected_version=None,
                project_root_path=project_root,
                project_root_exists=project_root.is_dir(),
                write_access=False,
                recovery_message="CapCut 설치를 확인한 뒤 다시 진단하세요.",
            )
        if not project_root.is_dir():
            return self._diagnostics(
                installation_path=installation,
                detected_version=self._version_for(installation),
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
                detected_version=self._version_for(installation),
                project_root_path=project_root,
                project_root_exists=True,
                write_access=False,
                recovery_message="CapCut 프로젝트 폴더 권한과 디스크 공간을 확인한 뒤 다시 진단하세요.",
            )
        return self._diagnostics(
            installation_path=installation,
            detected_version=self._version_for(installation),
            project_root_path=project_root,
            project_root_exists=True,
            write_access=True,
            recovery_message=None,
        )

    def _project_root(self) -> Path:
        diagnostics = self.diagnose()
        if diagnostics.installation_path is None:
            raise CapCutHandoffError("CapCut 설치를 확인한 뒤 다시 시도하세요.")
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
    def _diagnostics(
        *,
        installation_path: Path | None,
        detected_version: str | None,
        project_root_path: Path,
        project_root_exists: bool,
        write_access: bool,
        recovery_message: str | None,
    ) -> CapCutHandoffDiagnostics:
        return CapCutHandoffDiagnostics(
            status="ready" if recovery_message is None else "failed",
            installation_path=installation_path,
            detected_version=detected_version,
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
    def _record(*, source: Path, destination: Path, reused: bool) -> CapCutHandoffRecord:
        return CapCutHandoffRecord(
            source_path=source,
            registered_path=destination,
            status="ready",
            registered_at=datetime.now(UTC).isoformat(),
            reused=reused,
        )


__all__ = ["CapCutHandoffDiagnostics", "CapCutHandoffError", "CapCutHandoffRecord", "CapCutHandoffService"]
