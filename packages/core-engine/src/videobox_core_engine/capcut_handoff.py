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

    def _project_root(self) -> Path:
        apps_root = self.local_app_data / "CapCut" / "Apps"
        if not apps_root.is_dir() or not any(apps_root.rglob("CapCut.exe")):
            raise CapCutHandoffError("CapCut 설치를 확인한 뒤 다시 시도하세요.")
        project_root = self.local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        if not project_root.is_dir():
            raise CapCutHandoffError("CapCut 프로젝트 폴더를 확인한 뒤 CapCut을 한 번 실행하세요.")
        try:
            with tempfile.NamedTemporaryFile(dir=project_root, prefix=".videobox-write-check-", delete=True):
                pass
        except OSError as exc:
            raise CapCutHandoffError(
                "CapCut 프로젝트 폴더에 쓸 수 없습니다. 폴더 권한을 확인한 뒤 다시 시도하세요."
            ) from exc
        return project_root

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


__all__ = ["CapCutHandoffError", "CapCutHandoffRecord", "CapCutHandoffService"]
