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

from videobox_capcut_export.host_paths import CapCutHostPathMap
from videobox_core_engine.capcut_host_bridge import (
    CapCutHostBridge,
    CapCutHostBridgeRefused,
    CapCutHostBridgeUnavailable,
)

#: 다리가 안 켜져 있을 때 화면에 그대로 보여 줄 말. **조용히 실패하지 않는다** --
#: "눌렀는데 아무 일도 안 일어난다"는 이 저장소가 여러 번 고친 결함이다.
BRIDGE_UNAVAILABLE_MESSAGE = (
    "캡컷으로 넘기는 준비가 아직 안 됐어요. 바탕화면의 VideoBox 시작 아이콘을 "
    "다시 실행하거나, 이 컴퓨터에서 scripts/start-capcut.ps1 을 실행한 뒤 다시 확인해 주세요."
)
#: 컨테이너 경로를 이 컴퓨터 경로로 옮기지 못했을 때.
BRIDGE_PATH_MAP_MESSAGE = (
    "초안이 있는 자리를 이 컴퓨터의 자리로 옮겨 적지 못했어요. "
    "VIDEOBOX_CAPCUT_HOST_PATH_MAP 설정을 확인한 뒤 다시 시도해 주세요."
)


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
        bridge: CapCutHostBridge | None = None,
        host_path_map: CapCutHostPathMap | None = None,
    ) -> None:
        self.local_app_data = local_app_data or Path(os.environ.get("LOCALAPPDATA") or "")
        self._copytree = copytree
        # `local_app_data`를 손으로 준 호출자는 **그 폴더**를 쓰겠다는 뜻이다
        # (테스트와 호스트에서 직접 도는 다리 자신). 그때는 다리를 안 쓴다.
        self.bridge = bridge if bridge is not None else (
            None if local_app_data is not None else CapCutHostBridge.from_environment()
        )
        self.host_path_map = (
            host_path_map if host_path_map is not None else CapCutHostPathMap.from_environment()
        )

    def register(
        self, *, source_draft_path: Path, export_id: str, ownership_token: str | None = None
    ) -> CapCutHandoffRecord:
        source = Path(source_draft_path)
        if not (source / "draft_content.json").is_file():
            raise CapCutHandoffError("VideoBox CapCut 초안 파일을 찾지 못했습니다. 내보내기를 다시 실행하세요.")

        if self.bridge is not None:
            return self._register_through_bridge(
                source=source, export_id=export_id, ownership_token=ownership_token
            )

        project_root = self._project_root()
        destination = project_root / f"videobox-{export_id}"
        if self._is_owned_destination(destination=destination, export_id=export_id) and self._is_complete_draft(destination):
            # A reclaimed durable lease must supersede the abandoned owner's
            # marker before it can report reuse.  Otherwise that old owner
            # could later pass the marker check and delete a destination now
            # being used by the new request.
            if ownership_token is not None:
                self._write_ownership_marker(
                    destination=destination,
                    export_id=export_id,
                    ownership_token=ownership_token,
                )
            return self._record(
                source=source,
                destination=destination,
                export_id=export_id,
                reused=True,
                ownership_token=ownership_token,
            )
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

    def _register_through_bridge(
        self, *, source: Path, export_id: str, ownership_token: str | None
    ) -> CapCutHandoffRecord:
        assert self.bridge is not None
        host_path = self.host_path_map.map_path(source)
        if not self.host_path_map.maps(source):
            # 옮겨 적지 못한 경로를 그대로 보내면 호스트가 **못 찾거나, 더 나쁘게는
            # 다른 폴더를 찾는다.** 보내기 전에 멈춘다.
            raise CapCutHandoffError(BRIDGE_PATH_MAP_MESSAGE)
        try:
            payload = self.bridge.register(
                draft_host_path=host_path,
                export_id=export_id,
                ownership_token=ownership_token,
            )
        except CapCutHostBridgeUnavailable as exc:
            raise CapCutHandoffError(BRIDGE_UNAVAILABLE_MESSAGE) from exc
        except CapCutHostBridgeRefused as exc:
            raise CapCutHandoffError(
                "캡컷 프로젝트 등록에 실패했습니다. 캡컷 프로젝트 폴더 권한과 디스크 공간을 "
                "확인한 뒤 다시 시도하세요."
            ) from exc
        registered_path = str(payload.get("registered_path") or "").strip()
        if not registered_path:
            raise CapCutHandoffError(
                "캡컷 등록 결과를 읽지 못했습니다. 상태를 확인한 뒤 다시 시도하세요."
            )
        return CapCutHandoffRecord(
            source_path=source,
            registered_path=Path(registered_path),
            export_id=export_id,
            status=str(payload.get("status") or "ready"),
            registered_at=str(payload.get("registered_at") or datetime.now(UTC).isoformat()),
            reused=bool(payload.get("reused", False)),
            ownership_token=ownership_token,
        )

    def cleanup_request_owned_registration(
        self, *, record: CapCutHandoffRecord, ownership_token: str
    ) -> bool:
        """Remove only a destination and marker created by this exact request."""
        if record.reused or record.ownership_token != ownership_token:
            return False
        if self.bridge is not None:
            try:
                payload = self.bridge.cleanup(
                    export_id=record.export_id,
                    registered_host_path=str(record.registered_path),
                    ownership_token=ownership_token,
                )
            except (CapCutHostBridgeUnavailable, CapCutHostBridgeRefused):
                return False
            return bool(payload.get("removed", False))
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
        if self.bridge is not None:
            return self._diagnose_through_bridge()
        return self._diagnose_locally()

    def _diagnose_through_bridge(self) -> CapCutHandoffDiagnostics:
        """다리에게 물어본 그대로 옮긴다. **컨테이너 안을 들여다보고 "캡컷이 없다"고
        말하지 않는다** -- 컨테이너에 캡컷이 없는 건 당연하고, 그건 owner가 고칠
        수 있는 사실이 아니라서 진단이 거짓말이 된다."""
        assert self.bridge is not None
        unreachable_root = Path("")
        try:
            payload = self.bridge.diagnose()
        except (CapCutHostBridgeUnavailable, CapCutHostBridgeRefused):
            return self._diagnostics(
                installation_path=None,
                detected_version=None,
                is_supported=False,
                project_root_path=unreachable_root,
                project_root_exists=False,
                write_access=False,
                recovery_message=BRIDGE_UNAVAILABLE_MESSAGE,
            )
        installation = str(payload.get("installation_path") or "").strip()
        project_root = str(payload.get("project_root_path") or "").strip()
        recovery_message = payload.get("recovery_message")
        if not self.host_path_map.is_empty:
            pass
        elif recovery_message is None:
            # 다리는 준비됐는데 경로 대응이 비어 있으면, 눌러 봐야 등록 단계에서
            # 막힌다. 그 사실을 **누르기 전에** 말한다.
            recovery_message = BRIDGE_PATH_MAP_MESSAGE
        return self._diagnostics(
            installation_path=Path(installation) if installation else None,
            detected_version=(str(payload["detected_version"]) if payload.get("detected_version") else None),
            is_supported=bool(payload.get("is_supported", False)),
            project_root_path=Path(project_root) if project_root else unreachable_root,
            project_root_exists=bool(payload.get("project_root_exists", False)),
            write_access=bool(payload.get("write_access", False)),
            recovery_message=str(recovery_message) if recovery_message else None,
        )

    def _diagnose_locally(self) -> CapCutHandoffDiagnostics:
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
        diagnostics = self._diagnose_locally()
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
    def _supported_version_prefixes() -> tuple[str, ...]:
        """실제로 **열어 본** 캡컷 버전만 적는다. 안 열어 본 것은 막는다.

        여기 값을 코드에만 두면 owner가 캡컷을 올릴 때마다 낡는다 -- 2026-09-07에
        실제로 그랬다: 설치본이 `9.3.0.3970`인데 목록은 `8.7`/`8.9`뿐이라
        진단이 "지원하지 않는 버전"이라고 답했고, 그때 캡컷은 이미 우리 초안을
        멀쩡히 열고 있었다. 그래서 `VIDEOBOX_CAPCUT_SUPPORTED_VERSIONS`로 뺐다.

        `9.3.`을 기본에 넣은 근거: owner가 우리 초안을 그 폴더에 손으로 넣어
        열었고 **소재 3개를 전부 찾았다**(2026-09-07). 안 열어 본 `9.0`·`9.1`은
        여전히 막힌다 -- 이 문은 "새 버전이면 통과"가 아니라 "본 것만 통과"다.
        """
        configured = (os.environ.get("VIDEOBOX_CAPCUT_SUPPORTED_VERSIONS") or "").strip()
        if not configured:
            return ("8.7.", "8.9.", "9.3.")
        return tuple(part.strip() for part in configured.split(",") if part.strip())

    @classmethod
    def _is_supported_version(cls, version: str | None) -> bool:
        return version is not None and any(
            version.startswith(prefix) for prefix in cls._supported_version_prefixes()
        )

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


__all__ = ["BRIDGE_PATH_MAP_MESSAGE", "BRIDGE_UNAVAILABLE_MESSAGE", "CapCutHandoffDiagnostics", "CapCutHandoffError", "CapCutHandoffRecord", "CapCutHandoffService"]
