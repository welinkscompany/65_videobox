"""캡컷 초안을 **이 컴퓨터의 캡컷 폴더**에 넣어 주는 다리.

컨테이너는 `C:/Users/<사람>/AppData/Local/CapCut/...`을 못 본다. 그래서 목소리
복제(8199)·그림 생성(8188)과 같은 방식으로, 이 컴퓨터에서 도는 작은 서비스를
둔다. 캡컷은 **8200**이다.

    pwsh -File scripts/start-capcut.ps1

## 하는 일은 셋뿐이다

    GET  /diagnostics  이 컴퓨터의 캡컷 상태(설치·버전·프로젝트 폴더·쓰기 권한)
    POST /register     초안 폴더를 캡컷 프로젝트 폴더로 복사
    POST /cleanup      이 요청이 만든 등록만 되돌림

셋 다 `CapCutHandoffService`를 그대로 쓴다 -- 등록 규칙(덮어쓰기 금지, 소유
표식, 원자적 교체)을 여기서 다시 짜지 않는다.

## 받은 경로를 그대로 믿지 않는다

`--allow-root`로 준 폴더 **안**에 있는 초안만 받는다. 기본값은
`.env.container`의 `VIDEOBOX_CONTAINER_DATA_ROOT`/runtime이다. 컨테이너가 자기
자료 밖의 아무 폴더나 캡컷에 복사하도록 시킬 수 없어야 한다.

## owner의 실제 캡컷 자료를 건드리지 않는다

`CapCutHandoffService`가 이미 지키는 규칙이다: 남이 만든 같은 이름의 폴더가
있으면 **덮어쓰지 않고 거절한다.** 지우는 것은 이 서비스가 자기 표식을 남긴
등록뿐이다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
for _package in ("core-engine", "capcut-export", "domain-models", "storage-abstractions", "provider-interfaces"):
    _source = _REPOSITORY_ROOT / "packages" / _package / "src"
    if _source.is_dir() and str(_source) not in sys.path:
        sys.path.insert(0, str(_source))

from videobox_core_engine.capcut_handoff import (  # noqa: E402
    CapCutHandoffError,
    CapCutHandoffRecord,
    CapCutHandoffService,
)

DEFAULT_PORT = 8200
#: 이 컴퓨터 밖으로는 열지 않는다.
BIND_HOST = "127.0.0.1"


def _service() -> CapCutHandoffService:
    """`local_app_data`를 손으로 준다 -- 그래야 이 서비스가 **자기 자신을 다시
    다리로 부르는 일**이 없다(`CapCutHandoffService`가 그 규칙을 지킨다)."""
    return CapCutHandoffService(local_app_data=Path(os.environ.get("LOCALAPPDATA") or ""))


def _is_inside(candidate: Path, roots: tuple[Path, ...]) -> bool:
    if not roots:
        return True
    resolved = candidate.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        return True
    return False


def diagnostics_payload() -> tuple[int, dict[str, object]]:
    """`GET /diagnostics`가 돌려줄 것. **소켓과 떼어 놓았다** -- 이 저장소의 시험은
    연결을 못 열게 막혀 있고(`tests/conftest.py`), 그 울타리는 옳다. 판단은 여기서
    하고, 아래 handler는 그걸 실어 나르기만 한다."""
    diagnostics = _service().diagnose()
    payload = asdict(diagnostics)
    payload["installation_path"] = (
        str(diagnostics.installation_path) if diagnostics.installation_path else None
    )
    payload["project_root_path"] = str(diagnostics.project_root_path)
    return 200, payload


def register_payload(
    body: dict[str, object], *, allowed_roots: tuple[Path, ...]
) -> tuple[int, dict[str, object]]:
    """`POST /register`가 돌려줄 것."""
    raw_path = str(body.get("draft_host_path") or "").strip()
    export_id = str(body.get("export_id") or "").strip()
    ownership_token = body.get("ownership_token")
    if not raw_path or not export_id:
        return 400, {"error": "draft_host_path_and_export_id_are_required"}
    draft_path = Path(raw_path)
    if not draft_path.is_dir():
        return 400, {"error": "draft_not_found", "detail": raw_path}
    if not _is_inside(draft_path, allowed_roots):
        return 403, {"error": "draft_outside_allowed_root", "detail": raw_path}
    try:
        record = _service().register(
            source_draft_path=draft_path,
            export_id=export_id,
            ownership_token=str(ownership_token) if ownership_token else None,
        )
    except CapCutHandoffError as exc:
        return 409, {"error": "capcut_registration_failed", "detail": str(exc)}
    return 200, {
        "registered_path": str(record.registered_path),
        "status": record.status,
        "registered_at": record.registered_at,
        "reused": record.reused,
    }


def cleanup_payload(body: dict[str, object]) -> tuple[int, dict[str, object]]:
    """`POST /cleanup`가 돌려줄 것. 이 요청이 만든 등록만 되돌린다."""
    export_id = str(body.get("export_id") or "").strip()
    registered = str(body.get("registered_host_path") or "").strip()
    ownership_token = str(body.get("ownership_token") or "").strip()
    if not export_id or not registered or not ownership_token:
        return 400, {"error": "export_id_registered_host_path_and_token_are_required"}
    record = CapCutHandoffRecord(
        source_path=Path(registered),
        registered_path=Path(registered),
        export_id=export_id,
        status="ready",
        registered_at="",
        reused=False,
        ownership_token=ownership_token,
    )
    removed = _service().cleanup_request_owned_registration(
        record=record, ownership_token=ownership_token
    )
    return 200, {"removed": bool(removed)}


class _Handler(BaseHTTPRequestHandler):
    server_version = "VideoBoxCapCutBridge/1.0"
    allowed_roots: tuple[Path, ...] = ()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        sys.stderr.write("[capcut-bridge] " + (format % args) + "\n")

    def _reply(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        decoded = json.loads(self.rfile.read(length).decode("utf-8"))
        return decoded if isinstance(decoded, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/diagnostics":
            self._reply(404, {"error": "unknown_path"})
            return
        self._reply(*diagnostics_payload())

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._payload()
        except (ValueError, OSError):
            self._reply(400, {"error": "unreadable_request"})
            return
        if self.path == "/register":
            self._reply(*register_payload(payload, allowed_roots=self.allowed_roots))
        elif self.path == "/cleanup":
            self._reply(*cleanup_payload(payload))
        else:
            self._reply(404, {"error": "unknown_path"})


def build_server(*, port: int, allowed_roots: tuple[Path, ...]) -> ThreadingHTTPServer:
    handler = type("_BoundHandler", (_Handler,), {"allowed_roots": allowed_roots})
    return ThreadingHTTPServer((BIND_HOST, port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VideoBox CapCut hand-off bridge (host side).")
    parser.add_argument("--port", type=int, default=int(os.environ.get("VIDEOBOX_CAPCUT_BRIDGE_PORT") or DEFAULT_PORT))
    parser.add_argument(
        "--allow-root",
        action="append",
        default=[],
        help="이 폴더 안의 초안만 받는다. 여러 번 줄 수 있다. 안 주면 전부 받는다.",
    )
    arguments = parser.parse_args(argv)
    roots = tuple(Path(value) for value in arguments.allow_root if str(value).strip())
    server = build_server(port=arguments.port, allowed_roots=roots)
    diagnostics = _service().diagnose()
    print(f"[capcut-bridge] listening on http://{BIND_HOST}:{arguments.port}", flush=True)
    print(f"[capcut-bridge] capcut status: {diagnostics.status}", flush=True)
    if diagnostics.recovery_message:
        print(f"[capcut-bridge] {diagnostics.recovery_message}", flush=True)
    for root in roots:
        print(f"[capcut-bridge] allowed root: {root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
