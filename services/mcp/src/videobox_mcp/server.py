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

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import tools
from .api_client import VideoBoxApiClient, VideoBoxApiError


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

    return server


def main() -> None:
    base_url = os.environ.get("VIDEOBOX_API_BASE_URL", "http://127.0.0.1:8000")
    client = VideoBoxApiClient(base_url=base_url)
    server = build_server(client)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
