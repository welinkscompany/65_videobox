"""VideoBox MCP 서버. stdio 전송만 쓴다 -- `docs/videobox-mcp-scope.ko.md` §1-2.

**MCP는 제어면이다.** 여기서 core engine을 import하지 않는다. 모든 도구는
`VideoBoxApiClient`를 거쳐 이미 떠 있는 VideoBox API를 부른다.

**첫 슬라이스만 연다** (§3.1 프로젝트 + §3.3의 `job_status`). 자산 등록·
잡 시작류·타임라인·결과물 도구는 `docs/videobox-mcp-scope.ko.md` §6-3의
`list_project_assets` 결정이 나온 뒤 이어서 연다. §4가 절대 만들지 말라고
못박은 도구(승인 문, 삭제 문, 전면 적용 문)는 여기 없다 -- 앞으로도 없다.
"""

from __future__ import annotations

import functools
import os
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from . import tools
from .api_client import DEFAULT_API_BASE_URL, VideoBoxApiClient, VideoBoxApiError
from .auth import BearerAuthMiddleware


def _translate_errors(fn):
    # `functools.wraps` keeps the original signature visible to
    # `inspect.signature` (via `__wrapped__`) -- `MCPServer.tool()` reads
    # that signature to build each tool's input schema. A plain
    # `*args, **kwargs` wrapper without this erases the real parameter
    # names/types and every call fails schema validation.
    @functools.wraps(fn)
    async def wrapped(*args: object, **kwargs: object) -> object:
        try:
            return await fn(*args, **kwargs)
        except VideoBoxApiError as exc:
            raise ToolError(f"videobox_api_error status={exc.status_code} detail={exc.detail!r}") from exc
        except httpx.HTTPError as exc:
            # HTTP 응답 자체가 없는 네트워크 수준 실패(타임아웃·연결 끊김 등)다
            # -- `VideoBoxApiError`는 응답이 왔을 때만 던져진다. 실물 점검
            # (Task 7, 백엔드가 안 뜬 상태)에서 이 exception이 그대로 새어
            # 나가 MCP 프레임워크가 처리 못 한 파이썬 예외로 떨어졌다 --
            # "이유 있는 오류"(§7) 원칙과 정반대다.
            raise ToolError(f"videobox_api_network_error {exc!r}") from exc

    return wrapped


def build_server(client: VideoBoxApiClient) -> MCPServer:
    """도구를 등록한 `MCPServer`를 돌려준다. 시험은 `call_tool`을 직접 부른다."""
    server = MCPServer(
        name="videobox",
        title="VideoBox",
        instructions=(
            "VideoBox 프로젝트를 만들고 상태를 묻는 첫 도구 셋. "
            "타임라인 세부 편집, 승인, 삭제는 여기 없다 -- 사람 또는 유진의 몫이다."
        ),
    )

    @server.tool(name="create_project", description="새 VideoBox 프로젝트를 만든다.", structured_output=True)
    @_translate_errors
    async def create_project(name: str) -> dict[str, Any]:
        return await tools.create_project(client, name=name)

    @server.tool(name="list_projects", description="VideoBox 프로젝트 목록을 가져온다.", structured_output=True)
    @_translate_errors
    async def list_projects(include_archived: bool = False) -> dict[str, Any]:
        return await tools.list_projects(client, include_archived=include_archived)

    @server.tool(name="get_project", description="프로젝트 하나의 상태와 홈 요약을 가져온다.", structured_output=True)
    @_translate_errors
    async def get_project(project_id: str) -> dict[str, Any]:
        return await tools.get_project(client, project_id=project_id)

    @server.tool(
        name="job_status",
        description="잡 하나의 상태를 종류와 상관없이 같은 모양으로 가져온다. 결과 본문은 안 준다 -- 상태만.",
        structured_output=True,
    )
    @_translate_errors
    async def job_status(project_id: str, job_id: str) -> dict[str, Any]:
        return await tools.job_status(client, project_id=project_id, job_id=job_id)

    @server.tool(
        name="ask_yujin",
        description=(
            "유진에게 자연어로 편집을 요청한다. 타임라인을 직접 만지지 않는다 -- "
            "유진이 프로젝트 안에서 실제로 적용한다. 실패하면 1회 재시도 후 "
            "이유 있는 오류를 낸다(우회하지 않는다)."
        ),
        structured_output=True,
    )
    @_translate_errors
    async def ask_yujin(project_id: str, message: str) -> dict[str, Any]:
        return await tools.ask_yujin(client, project_id=project_id, message=message)

    return server


def build_http_app(client: VideoBoxApiClient, *, token: str, host: str = "127.0.0.1", port: int = 8901):
    """HTTP 전송 앱. 컨테이너 네트워크가 아니라 호스트 프로세스에서 띄운다
    (스펙 §2) -- 그래서 CLAUDE.md §6의 컨테이너 네트워크 경계 승인과 무관하다.

    **바인드 주소는 그대로 `host`(기본 127.0.0.1)다 -- 밖으로 여는 게 아니다.**
    `host.docker.internal:<port>`는 허용 Host 이름 목록에만 추가한다. AK-System
    쪽 직원이 도커 컨테이너 안에서 `http://host.docker.internal:<port>/mcp`로
    들어올 때, `mcp` SDK의 DNS 리바인딩 방지가 Host 헤더를 그 이름으로는
    못 보고 421을 냈다(2026-09-28 실사용 발견). `transport_security`를 직접
    만들어서 그 SDK의 기본값(`host`가 로컬일 때 자동으로 여는
    `127.0.0.1:*`/`localhost:*`/`[::1]:*`)에 이 한 항목만 더한다 -- 토큰
    인증은 그대로 필수, 다른 이름은 여전히 421이다.
    """
    server = build_server(client)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", f"host.docker.internal:{port}"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
    )
    app = server.streamable_http_app(streamable_http_path="/mcp", host=host, transport_security=security)
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app


def main_http() -> None:
    base_url = os.environ.get("VIDEOBOX_API_BASE_URL", DEFAULT_API_BASE_URL)
    token = os.environ.get("VIDEOBOX_MCP_HTTP_TOKEN")
    if not token:
        raise RuntimeError(
            "VIDEOBOX_MCP_HTTP_TOKEN이 없다 -- 열쇠 없이 HTTP 전송을 열지 않는다."
        )
    host = os.environ.get("VIDEOBOX_MCP_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("VIDEOBOX_MCP_HTTP_PORT", "8901"))
    client = VideoBoxApiClient(base_url=base_url)
    app = build_http_app(client, token=token, host=host, port=port)

    import uvicorn

    uvicorn.run(app, host=host, port=port)


def main() -> None:
    transport = os.environ.get("VIDEOBOX_MCP_TRANSPORT", "stdio")
    if transport == "http":
        main_http()
        return
    base_url = os.environ.get("VIDEOBOX_API_BASE_URL", DEFAULT_API_BASE_URL)
    client = VideoBoxApiClient(base_url=base_url)
    server = build_server(client)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
