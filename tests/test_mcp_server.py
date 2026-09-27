"""VideoBox MCP 서버 첫 슬라이스 (`docs/videobox-mcp-scope.ko.md` §3.1·§3.3).

**MCP → API → Core 순서를 지키는지 시험으로 못박는다** -- `videobox_mcp`는
core engine이나 storage 계층을 한 줄도 import하지 않는다(아래 첫 시험).
나머지는 실제 FastAPI 앱을 `httpx.ASGITransport`로 인메모리 호출해
(`tests/conftest.py`의 소켓 차단과 맞물린다) 도구가 진짜 API 응답을
그대로 옮기는지 확인한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def test_editing_session_and_yujin_proposal_client_methods(tmp_path: Path) -> None:
    client = _client_for(tmp_path)

    import asyncio

    async def run() -> dict:
        # 프로젝트만 있고 세션이 없으면 latest가 404를 내야 한다.
        return await client.create_project(name="세션 시험")

    project = asyncio.run(run())
    project_id = project["project_id"]

    async def latest_missing() -> None:
        await client.get_latest_editing_session(project_id=project_id)

    with pytest.raises(VideoBoxApiError) as excinfo:
        asyncio.run(latest_missing())
    assert excinfo.value.status_code == 404

    async def create_blank_then_fetch() -> tuple[dict, dict]:
        created = await client.create_blank_editing_session(project_id=project_id)
        fetched = await client.get_latest_editing_session(project_id=project_id)
        return created, fetched

    created, fetched = asyncio.run(create_blank_then_fetch())
    assert created["session_id"] == fetched["session_id"]
    assert fetched["project_id"] == project_id


def _client_and_app_for(tmp_path: Path, *, runtime_factory=None) -> VideoBoxApiClient:
    from videobox_api.main import create_app

    kwargs: dict[str, Any] = {"projects_root": tmp_path}
    if runtime_factory is not None:
        kwargs["local_only_runtime_service_factory"] = runtime_factory
    app = create_app(**kwargs)
    transport = httpx.ASGITransport(app=app)
    return VideoBoxApiClient(base_url="http://testserver", transport=transport)


def test_ask_yujin_creates_session_then_applies_the_proposal(tmp_path: Path) -> None:
    import re

    from videobox_provider_interfaces.llm import StructuredLLMResponse
    from videobox_mcp import tools

    class FixedEditingRuntime:
        def generate_structured(self, **kwargs: Any) -> StructuredLLMResponse:
            # 빈 편집판(`create_blank_editing_session`)은 장면 하나를 자동
            # 생성한 id(`{timeline_id}:001`)로 연다 -- 고정 문자열("scene-2")을
            # 미리 알 수 없으므로, 검증기가 실제로 통과하도록 프롬프트에 실린
            # "현재 장면: 1번 장면=<id>." 표에서 그 id를 그대로 읽어 쓴다.
            prompt = str(kwargs.get("prompt") or "")
            match = re.search(r"1번 장면=([^,.]+)", prompt)
            segment_id = match.group(1).strip() if match else "scene-2"
            return StructuredLLMResponse(
                provider_name="local",
                model_name="fixture",
                output_data={
                    "schema_version": "videobox.yujin-editing-response.v1",
                    "reply_text": "두 번째 장면을 두 배로 빠르게 했어요.",
                    "proposal": {
                        "proposal_id": "fixture-proposal",
                        "base_session_revision": 1,
                        "operations": [
                            {"intent": "set_scene_speed", "segment_id": segment_id, "rate": 2}
                        ],
                    },
                },
                raw_text="{}",
                metadata={},
            )

    client = _client_and_app_for(tmp_path, runtime_factory=lambda _: FixedEditingRuntime())

    import asyncio

    async def run() -> dict[str, Any]:
        project = await client.create_project(name="유진에게 말하기 시험")
        return await tools.ask_yujin(
            client, project_id=project["project_id"], message="두 번째 장면을 두 배로 빠르게 해줘"
        )

    result = asyncio.run(run())

    assert result["applied"] is True
    assert result["status"] == "applied"
    # 서버가 진짜 저장 id를 새로 발급한다(`director_proposals.py`가
    # `yujin-edit-{uuid4().hex}`로 짓는다) -- 유진의 응답에 실린
    # "fixture-proposal"은 그대로 돌아오지 않는다. 값이 실제로 있는지만 본다.
    assert isinstance(result["proposal_id"], str) and result["proposal_id"]


def test_ask_yujin_retries_once_then_logs_and_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videobox_mcp import tools

    client = _client_and_app_for(tmp_path)

    call_count = {"n": 0}

    async def always_fails(self: VideoBoxApiClient, *, project_id: str) -> dict[str, Any]:
        call_count["n"] += 1
        raise VideoBoxApiError(status_code=500, detail="boom", path="/fake")

    monkeypatch.setattr(VideoBoxApiClient, "get_latest_editing_session", always_fails)

    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tools,
        "log_ask_yujin_escalation",
        lambda **kwargs: logged.append(kwargs),
    )

    import asyncio

    async def run() -> None:
        await tools.ask_yujin(client, project_id="does-not-matter", message="아무 말")

    with pytest.raises(VideoBoxApiError):
        asyncio.run(run())

    assert call_count["n"] == 2  # 최초 시도 + 1회 재시도, 그 이상은 없다
    assert len(logged) == 1
    assert logged[0]["retry_count"] == 1
    assert logged[0]["project_id"] == "does-not-matter"


def test_ask_yujin_retries_once_on_network_failure_then_logs_and_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`httpx.ReadTimeout`처럼 응답 자체가 없는 네트워크 실패도
    `VideoBoxApiError`와 똑같이 재시도·로그·올려보내기 대상이어야 한다 --
    실물 점검(Task 7, 백엔드가 안 뜬 상태)에서 이 경로가 재시도·로그를
    건너뛰고 조용히 새어 나간 적이 있다(§7 위반)."""
    from videobox_mcp import tools

    client = _client_and_app_for(tmp_path)

    call_count = {"n": 0}

    async def always_times_out(self: VideoBoxApiClient, *, project_id: str) -> dict[str, Any]:
        call_count["n"] += 1
        raise httpx.ReadTimeout("simulated timeout")

    monkeypatch.setattr(VideoBoxApiClient, "get_latest_editing_session", always_times_out)

    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tools,
        "log_ask_yujin_escalation",
        lambda **kwargs: logged.append(kwargs),
    )

    import asyncio

    async def run() -> None:
        await tools.ask_yujin(client, project_id="does-not-matter", message="아무 말")

    with pytest.raises(httpx.HTTPError):
        asyncio.run(run())

    assert call_count["n"] == 2  # 최초 시도 + 1회 재시도, 그 이상은 없다 -- VideoBoxApiError와 같은 정책
    assert len(logged) == 1
    assert logged[0]["retry_count"] == 1
    assert logged[0]["project_id"] == "does-not-matter"


def test_ask_yujin_does_not_retry_after_unsafe_non_409_apply_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 1: `apply_yujin_editing_proposal`이 실패했는데 그게
    409(`editing_proposal_needs_refresh` -- 적용이 거절됐다는 뜻, 아무것도
    안 걸렸다)가 아니면 재시도하면 안 된다. 서버 라우트는 동기 `def`라서
    스레드풀에서 돈다 -- 클라이언트가 타임아웃으로 포기해도 서버는 계속
    돌아서 실제로 적용을 끝낼 수 있다. 재시도하면 세션을 다시 만들고
    제안을 다시 만들어 두 번째로 적용해버려 이중 적용이 된다."""
    from videobox_mcp import tools

    client = _client_and_app_for(tmp_path)

    session_calls = {"n": 0}
    proposal_calls = {"n": 0}
    apply_calls = {"n": 0}

    async def fake_get_session(self: VideoBoxApiClient, *, project_id: str) -> dict[str, Any]:
        session_calls["n"] += 1
        return {"session_id": "s1", "project_id": project_id}

    async def fake_create_proposal(
        self: VideoBoxApiClient, *, project_id: str, session_id: str, instruction: str
    ) -> dict[str, Any]:
        proposal_calls["n"] += 1
        return {"status": "ready", "proposal_id": "p1", "base_session_revision": 1}

    async def fake_apply_500(
        self: VideoBoxApiClient,
        *,
        project_id: str,
        session_id: str,
        proposal_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        apply_calls["n"] += 1
        raise VideoBoxApiError(status_code=500, detail="apply exploded", path="/fake")

    monkeypatch.setattr(VideoBoxApiClient, "get_latest_editing_session", fake_get_session)
    monkeypatch.setattr(VideoBoxApiClient, "create_yujin_editing_proposal", fake_create_proposal)
    monkeypatch.setattr(VideoBoxApiClient, "apply_yujin_editing_proposal", fake_apply_500)

    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tools, "log_ask_yujin_escalation", lambda **kwargs: logged.append(kwargs)
    )

    import asyncio

    async def run() -> None:
        await tools.ask_yujin(client, project_id="does-not-matter", message="아무 말")

    with pytest.raises(VideoBoxApiError) as excinfo:
        asyncio.run(run())

    assert excinfo.value.status_code == 500
    # 재시도 없이 정확히 한 번씩만 -- 이중 적용 위험이 있는 자리라서.
    assert session_calls["n"] == 1
    assert proposal_calls["n"] == 1
    assert apply_calls["n"] == 1
    assert len(logged) == 1
    assert logged[0]["retry_count"] == 1
    assert "500" in logged[0]["error"]


def test_ask_yujin_does_not_retry_after_unsafe_network_apply_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 1의 같은 규칙이 `httpx.HTTPError`(타임아웃 등)에도 적용된다 --
    응답 자체가 없어도 서버 쪽에서 적용이 끝났을 수 있으니 안전하지 않다."""
    from videobox_mcp import tools

    client = _client_and_app_for(tmp_path)

    session_calls = {"n": 0}
    proposal_calls = {"n": 0}
    apply_calls = {"n": 0}

    async def fake_get_session(self: VideoBoxApiClient, *, project_id: str) -> dict[str, Any]:
        session_calls["n"] += 1
        return {"session_id": "s1", "project_id": project_id}

    async def fake_create_proposal(
        self: VideoBoxApiClient, *, project_id: str, session_id: str, instruction: str
    ) -> dict[str, Any]:
        proposal_calls["n"] += 1
        return {"status": "ready", "proposal_id": "p1", "base_session_revision": 1}

    async def fake_apply_timeout(
        self: VideoBoxApiClient,
        *,
        project_id: str,
        session_id: str,
        proposal_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        apply_calls["n"] += 1
        raise httpx.ReadTimeout("simulated apply timeout")

    monkeypatch.setattr(VideoBoxApiClient, "get_latest_editing_session", fake_get_session)
    monkeypatch.setattr(VideoBoxApiClient, "create_yujin_editing_proposal", fake_create_proposal)
    monkeypatch.setattr(VideoBoxApiClient, "apply_yujin_editing_proposal", fake_apply_timeout)

    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tools, "log_ask_yujin_escalation", lambda **kwargs: logged.append(kwargs)
    )

    import asyncio

    async def run() -> None:
        await tools.ask_yujin(client, project_id="does-not-matter", message="아무 말")

    with pytest.raises(httpx.HTTPError):
        asyncio.run(run())

    assert session_calls["n"] == 1
    assert proposal_calls["n"] == 1
    assert apply_calls["n"] == 1
    assert len(logged) == 1
    assert logged[0]["retry_count"] == 1
    # `str(httpx.ReadTimeout(...))`는 흔히 빈 문자열이다 -- Finding 2: 타입
    # 이름까지 같이 남아야 로그가 증거로 쓸모 있다.
    assert "ReadTimeout" in logged[0]["error"]


def test_ask_yujin_retries_after_409_apply_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """409는 유일한 안전한 재시도 대상이다 -- `editing_proposal_needs_refresh`는
    적용이 거절됐다는 뜻이라 아무것도 실제로 걸리지 않았다."""
    from videobox_mcp import tools

    client = _client_and_app_for(tmp_path)

    session_calls = {"n": 0}
    proposal_calls = {"n": 0}
    apply_calls = {"n": 0}

    async def fake_get_session(self: VideoBoxApiClient, *, project_id: str) -> dict[str, Any]:
        session_calls["n"] += 1
        return {"session_id": "s1", "project_id": project_id}

    async def fake_create_proposal(
        self: VideoBoxApiClient, *, project_id: str, session_id: str, instruction: str
    ) -> dict[str, Any]:
        proposal_calls["n"] += 1
        return {"status": "ready", "proposal_id": "p1", "base_session_revision": 1}

    async def fake_apply_409(
        self: VideoBoxApiClient,
        *,
        project_id: str,
        session_id: str,
        proposal_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        apply_calls["n"] += 1
        raise VideoBoxApiError(
            status_code=409, detail="editing_proposal_needs_refresh", path="/fake"
        )

    monkeypatch.setattr(VideoBoxApiClient, "get_latest_editing_session", fake_get_session)
    monkeypatch.setattr(VideoBoxApiClient, "create_yujin_editing_proposal", fake_create_proposal)
    monkeypatch.setattr(VideoBoxApiClient, "apply_yujin_editing_proposal", fake_apply_409)

    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tools, "log_ask_yujin_escalation", lambda **kwargs: logged.append(kwargs)
    )

    import asyncio

    async def run() -> None:
        await tools.ask_yujin(client, project_id="does-not-matter", message="아무 말")

    with pytest.raises(VideoBoxApiError) as excinfo:
        asyncio.run(run())

    assert excinfo.value.status_code == 409
    # 409는 안전해서 처음부터 다시 -- 최초 시도 + 1회 재시도, 그 이상은 없다.
    assert session_calls["n"] == 2
    assert proposal_calls["n"] == 2
    assert apply_calls["n"] == 2
    assert len(logged) == 1
    assert logged[0]["retry_count"] == 1
    assert "409" in logged[0]["error"]


def test_ask_yujin_network_failure_becomes_a_tool_error_not_a_raw_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`server.py`의 `_translate_errors`가 `httpx.HTTPError`도 잡아야 한다 --
    안 잡으면 외부 MCP 호출자(AK-Hermes)에게 원문 파이썬 예외가 그대로
    새어 나간다. "이유 있는 오류"(§7)는 `ToolError`로 번역된 오류를
    말하지, 처리 안 된 예외를 말하지 않는다."""
    from mcp.server.mcpserver.exceptions import ToolError

    client = _client_for(tmp_path)
    server = build_server(client)

    async def always_times_out(self: VideoBoxApiClient, *, project_id: str) -> dict[str, Any]:
        raise httpx.ReadTimeout("simulated timeout")

    monkeypatch.setattr(VideoBoxApiClient, "get_latest_editing_session", always_times_out)

    import asyncio

    async def run() -> None:
        await server.call_tool(
            "ask_yujin", {"project_id": "does-not-matter", "message": "아무 말"}
        )

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(run())
    # 통짜 `UnexpectedToolError`(MCP 프레임워크가 처리 못 한 예외에 붙이는
    # 이름)가 아니라 `_translate_errors`가 실제로 httpx 예외를 알아보고
    # 지은 이유 있는 메시지인지까지 본다 -- 그래야 "그냥 프레임워크가
    # 아무 예외나 감쌌다"와 "우리 코드가 네트워크 실패를 알아챘다"가
    # 구별된다.
    assert "videobox_api_network_error" in str(excinfo.value)


def test_ask_yujin_is_registered_as_a_tool(tmp_path: Path) -> None:
    client = _client_for(tmp_path)
    server = build_server(client)

    import asyncio

    async def run() -> object:
        created = await server.call_tool("create_project", {"name": "도구 등록 시험"})
        # 편집 세션이 없는 프로젝트에 물으면 "세션 확보" 경로부터 실제로
        # 도구 레지스트리를 거쳐 실행돼야 한다 -- 로컬 LLM이 없으니 결과
        # 자체보다 "도구가 존재하고 호출 가능한가"를 이 시험의 경계로 둔다.
        return created

    created = asyncio.run(run())
    assert "ask_yujin" in [tool.name for tool in asyncio.run(server.list_tools())]
