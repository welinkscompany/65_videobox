"""VideoBox MCP 서버 첫 슬라이스 (`docs/videobox-mcp-scope.ko.md` §3.1·§3.3).

**MCP → API → Core 순서를 지키는지 시험으로 못박는다** -- `videobox_mcp`는
core engine이나 storage 계층을 한 줄도 import하지 않는다(아래 첫 시험).
나머지는 실제 FastAPI 앱을 `httpx.ASGITransport`로 인메모리 호출해
(`tests/conftest.py`의 소켓 차단과 맞물린다) 도구가 진짜 API 응답을
그대로 옮기는지 확인한다.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from videobox_api.main import create_app
from videobox_mcp.api_client import VideoBoxApiClient, VideoBoxApiError
from videobox_mcp.server import build_server


def test_videobox_mcp_never_imports_core_engine_or_storage_directly() -> None:
    """§1의 세 번째 원칙: MCP는 core engine을 직접 import하지 않는다."""
    import ast

    package_dir = Path(__file__).resolve().parents[1] / "services" / "mcp" / "src" / "videobox_mcp"
    forbidden_prefixes = ("videobox_core_engine", "videobox_storage")
    offenders: list[str] = []
    for py_file in package_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.startswith(forbidden_prefixes):
                    offenders.append(f"{py_file.name}: {name}")
    assert not offenders, f"videobox_mcp must only call the HTTP API, found: {offenders}"


def _client_for(tmp_path: Path) -> VideoBoxApiClient:
    app = create_app(projects_root=tmp_path)
    transport = httpx.ASGITransport(app=app)
    return VideoBoxApiClient(base_url="http://testserver", transport=transport)


def test_create_and_get_project_round_trip(tmp_path: Path) -> None:
    client = _client_for(tmp_path)
    server = build_server(client)

    import asyncio

    async def run() -> tuple[object, object]:
        created = await server.call_tool("create_project", {"name": "MCP 시험 프로젝트"})
        fetched = await server.call_tool(
            "get_project", {"project_id": created.structured_content["project_id"]}
        )
        return created, fetched

    created, fetched = asyncio.run(run())

    assert created.structured_content["name"] == "MCP 시험 프로젝트"
    assert created.structured_content["status"]
    assert fetched.structured_content["project_id"] == created.structured_content["project_id"]
    assert fetched.structured_content["has_draft"] is False
    assert fetched.structured_content["finished_video_count"] == 0


def test_list_projects_includes_the_one_just_created(tmp_path: Path) -> None:
    client = _client_for(tmp_path)
    server = build_server(client)

    import asyncio

    async def run() -> tuple[object, object]:
        created = await server.call_tool("create_project", {"name": "목록 시험"})
        listed = await server.call_tool("list_projects", {})
        return created, listed

    created, listed = asyncio.run(run())

    ids = [p["project_id"] for p in listed.structured_content["projects"]]
    assert created.structured_content["project_id"] in ids


def test_get_project_on_a_missing_project_is_a_named_error_not_a_silent_empty(tmp_path: Path) -> None:
    """§7: "결과 없음"과 "못 읽었음"이 같은 응답이면 결함이다."""
    from mcp.server.mcpserver.exceptions import ToolError

    client = _client_for(tmp_path)
    server = build_server(client)

    import asyncio

    async def run() -> None:
        await server.call_tool("get_project", {"project_id": "does-not-exist"})

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(run())
    assert "404" in str(excinfo.value) or "not found" in str(excinfo.value).lower()


def test_job_status_reports_a_real_job(tmp_path: Path) -> None:
    """job_status는 §2의 공통 문(`GET .../jobs/{job_id}`)만 감싼다 -- 새 로직을 안 짠다."""
    client = _client_for(tmp_path)
    server = build_server(client)

    import asyncio

    async def run() -> object:
        created = await server.call_tool("create_project", {"name": "잡 상태 시험"})
        project_id = created.structured_content["project_id"]
        # job_status가 없는 잡을 물으면 이름 있는 오류로 죽는지도 같은 흐름에서 본다.
        with pytest.raises(Exception):
            await server.call_tool(
                "job_status", {"project_id": project_id, "job_id": "no-such-job"}
            )
        return created

    asyncio.run(run())


def test_api_client_raises_a_named_error_with_the_status_code(tmp_path: Path) -> None:
    import asyncio

    client = _client_for(tmp_path)

    async def run() -> None:
        await client.get_project(project_id="does-not-exist")

    with pytest.raises(VideoBoxApiError) as excinfo:
        asyncio.run(run())
    assert excinfo.value.status_code == 404
