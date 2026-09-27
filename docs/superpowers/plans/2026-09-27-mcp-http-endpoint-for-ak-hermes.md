# VideoBox MCP HTTP 엔드포인트 (AK-Hermes 연결) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 `services/mcp` VideoBox MCP 서버에 HTTP 전송 모드(Bearer 인증)와
`ask_yujin` 도구를 추가해, 같은 컴퓨터의 AK-System Hermes Claude 세션이
`.mcp.json`으로 붙어 VideoBox에게 자연어로 편집을 요청할 수 있게 한다.

**Architecture:** 신규 서버를 만들지 않는다. `mcp==2.2.0` SDK가 이미 갖고 있는
`streamable-http` 전송을 `services/mcp/src/videobox_mcp/server.py`에 추가 배선하고,
Starlette 미들웨어로 Bearer 토큰을 검사한다. 쓰기는 `ask_yujin` 도구 하나뿐이며
화면 채팅과 같은 API(`POST .../yujin-editing-proposals` → `POST .../apply`)를
그대로 거친다. 컨테이너가 아니라 호스트 프로세스로 `127.0.0.1:8901`에 바인딩한다.

**Tech Stack:** Python, `mcp` SDK(streamable-http transport), Starlette
`BaseHTTPMiddleware`, httpx(AsyncClient/ASGITransport), pytest.

**Spec:** `docs/superpowers/specs/2026-09-27-mcp-http-endpoint-for-ak-hermes-design.ko.md`

## Global Constraints

- MCP는 core engine·storage를 직접 import하지 않는다 — `VideoBoxApiClient`(HTTP)만
  거친다(`tests/test_mcp_server.py::test_videobox_mcp_never_imports_core_engine_or_storage_directly`가
  AST로 강제 — 새 파일도 이 검사 대상이다).
- 타임라인·자산·렌더를 직접 조작하는 도구는 **만들지 않는다**
  (`docs/videobox-mcp-scope.ko.md` §1.1·§4).
- `ask_yujin`은 실패 시 **정확히 1회**만 재시도한다. 그 이상 우회하지 않는다.
- 포트는 **8901**, 바인딩은 **127.0.0.1**만(호스트 프로세스, 컨테이너 아님).
- 실패 기록은 `services/mcp/data/ask-yujin-escalations.jsonl`(append-only, 커밋 안 함).
- backend 검증은 반드시 `.venv/Scripts/python.exe -m pytest`를 쓴다(bare `pytest` 금지).
- 새 파일에 주석은 WHY만 남긴다(WHAT 설명 금지) — CLAUDE.md 기본 규칙.

---

## Task 0: `mcp` SDK를 `.venv`에 설치하고 `test_mcp_server.py`를 정규 스위트에 되돌린다

**배경:** `docs/development-fast-path.ko.md:715-726`가 이미 "설치되면 이 플래그를
빼서 우회를 만료시켜라"고 못박아 뒀다. HTTP 전송을 실제로 쓰려면 이제 설치가
필수다.

**Files:**
- Modify: (없음, `.venv`에 패키지 설치만)
- Modify: `docs/development-fast-path.ko.md:710-730` (플래그 안내 갱신)

- [ ] **Step 1: 설치 여부 확인**

```bash
.venv/Scripts/python.exe -m pip show mcp
```

Expected: `WARNING: Package(s) not found: mcp` (아직 없음을 확인).

- [ ] **Step 2: 두 단계로 설치한다 (한 번에 설치하면 최신 resolver가 충돌로 거부한다)**

```bash
.venv/Scripts/python.exe -m pip install mcp==2.2.0 httpx==0.28.1
.venv/Scripts/python.exe -m pip install starlette==0.38.6 uvicorn==0.30.6
```

Expected: 두 번째 명령이 "dependency resolver does not currently take into
account..." 경고를 찍지만 `Successfully installed`로 끝난다(exit code 0).
`requirements-mcp.txt` 머리말 주석이 이미 이 현상을 문서화해 뒀다.

- [ ] **Step 3: 버전이 FastAPI 쪽 고정값과 같은지 확인**

```bash
.venv/Scripts/python.exe -c "import starlette, uvicorn; print(starlette.__version__, uvicorn.__version__)"
```

Expected: `0.38.6 0.30.6` (requirements-container.txt가 요구하는 값과 동일 —
조용히 올라가지 않았는지 확인).

- [ ] **Step 4: `test_mcp_server.py`가 이제 플래그 없이 수집·통과되는지 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_server.py
```

Expected: `5 passed` (기존 5개 시험, 수집 에러 없음).

- [ ] **Step 5: 문서에서 우회 안내를 만료시킨다**

`docs/development-fast-path.ko.md:715-726`의 "`--ignore=tests/test_mcp_server.py`를
반드시 붙인다..." 문단을 아래로 교체:

```markdown
**2026-09-27에 `mcp`를 `.venv`에 설치했다** — 더 이상 `--ignore`가 필요 없다.
`test_mcp_server.py`도 일반 스위트에 포함해 돈다. 설치 확인:
`.venv/Scripts/python.exe -m pip show mcp`.
```

`729`행의 pytest 예시 명령에서 `--ignore=tests/test_mcp_server.py`를 뺀다.

- [ ] **Step 6: 커밋**

```bash
git add docs/development-fast-path.ko.md
git commit -m "docs: mcp SDK 설치 완료로 test_mcp_server.py 무시 플래그 만료"
```

---

## Task 1: `api_client.py`에 편집 세션·유진 제안 메서드 추가

**Files:**
- Modify: `services/mcp/src/videobox_mcp/api_client.py`
- Test: `tests/test_mcp_server.py` (기존 파일에 추가)

**Interfaces:**
- Produces: `VideoBoxApiClient.get_latest_editing_session(*, project_id: str) -> dict`,
  `.create_blank_editing_session(*, project_id: str) -> dict`,
  `.create_yujin_editing_proposal(*, project_id: str, session_id: str, instruction: str) -> dict`,
  `.apply_yujin_editing_proposal(*, project_id: str, session_id: str, proposal_id: str, expected_revision: int) -> dict`
  — 전부 `VideoBoxApiError`를 그대로 올려보낸다(기존 메서드와 동일 패턴).

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_mcp_server.py` 끝에 추가)

```python
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
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_server.py::test_editing_session_and_yujin_proposal_client_methods
```

Expected: `AttributeError: 'VideoBoxApiClient' object has no attribute 'get_latest_editing_session'`

- [ ] **Step 3: `api_client.py`에 메서드 추가**

`services/mcp/src/videobox_mcp/api_client.py`의 `get_job` 메서드 뒤에 추가:

```python
    async def get_latest_editing_session(self, *, project_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/projects/{project_id}/editing-sessions/latest")

    async def create_blank_editing_session(self, *, project_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/projects/{project_id}/editing-sessions/blank")

    async def create_yujin_editing_proposal(
        self, *, project_id: str, session_id: str, instruction: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals",
            json={"instruction": instruction},
        )

    async def apply_yujin_editing_proposal(
        self, *, project_id: str, session_id: str, proposal_id: str, expected_revision: int
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/projects/{project_id}/editing-sessions/{session_id}"
            f"/yujin-editing-proposals/{proposal_id}/apply",
            json={"expected_revision": expected_revision},
        )
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_server.py::test_editing_session_and_yujin_proposal_client_methods
```

Expected: `1 passed`

- [ ] **Step 5: 커밋**

```bash
git add services/mcp/src/videobox_mcp/api_client.py tests/test_mcp_server.py
git commit -m "feat: MCP api_client에 편집 세션·유진 제안 메서드 추가"
```

---

## Task 2: 실패 기록용 `escalation_log.py`

**Files:**
- Create: `services/mcp/src/videobox_mcp/escalation_log.py`
- Test: `tests/test_mcp_escalation_log.py`
- Modify: `.gitignore` (jsonl 로그 커밋 안 함)

**Interfaces:**
- Produces: `log_ask_yujin_escalation(*, project_id: str, message: str, error: str, retry_count: int, path: Path | None = None) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
"""services/mcp/src/videobox_mcp/escalation_log.py 시험.

새 알림함을 만들지 않는 대신, ask_yujin이 재시도까지 실패하면 이 로그
파일에 한 줄 남는다(스펙 §4) -- 그냥 에러 던지고 사라지면 안 된다는
대표님 지시를 그대로 지키는지 실물 파일로 확인한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from videobox_mcp.escalation_log import log_ask_yujin_escalation


def test_log_ask_yujin_escalation_appends_one_structured_json_line(tmp_path: Path) -> None:
    log_path = tmp_path / "ask-yujin-escalations.jsonl"

    log_ask_yujin_escalation(
        project_id="project_001",
        message="두 번째 장면 빨리감기 해줘",
        error="504 on /api/projects/project_001/.../yujin-editing-proposals: 'timeout'",
        retry_count=1,
        path=log_path,
    )
    log_ask_yujin_escalation(
        project_id="project_002",
        message="자막 다시 맞춰줘",
        error="422 on ...: 'candidate_unavailable'",
        retry_count=1,
        path=log_path,
    )

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["project_id"] == "project_001"
    assert first["message"] == "두 번째 장면 빨리감기 해줘"
    assert first["retry_count"] == 1
    assert "timeout" in first["error"]
    assert "timestamp" in first  # ISO 8601 형식, 값 자체는 시각 의존이라 존재만 확인


def test_log_ask_yujin_escalation_creates_parent_directory(tmp_path: Path) -> None:
    log_path = tmp_path / "nested" / "dir" / "ask-yujin-escalations.jsonl"

    log_ask_yujin_escalation(
        project_id="project_003", message="m", error="e", retry_count=1, path=log_path
    )

    assert log_path.exists()
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_escalation_log.py
```

Expected: `ModuleNotFoundError: No module named 'videobox_mcp.escalation_log'`

- [ ] **Step 3: 구현**

```python
"""ask_yujin이 재시도까지 실패했을 때 남기는 구조화 로그.

`docs/videobox-mcp-scope.ko.md` 확장 스펙(§4)이 정한 대로, VideoBox에는
아직 owner가 보는 범용 "확인 필요" 알림함이 없다. 그래서 새 알림함을
만드는 대신 append-only JSON Lines 파일에 남긴다 -- 나중에 통합 알림함이
생기면 이 파일을 소스로 옮기면 된다. hot path(도구 실행)에 새 인프라를
얹지 않는다는 원칙(CLAUDE.md §1.1)도 같이 지킨다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "ask-yujin-escalations.jsonl"


def log_ask_yujin_escalation(
    *, project_id: str, message: str, error: str, retry_count: int, path: Path | None = None
) -> None:
    target = path or Path(os.environ.get("VIDEOBOX_MCP_ESCALATION_LOG_PATH", str(DEFAULT_LOG_PATH)))
    target.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "message": message,
        "error": error,
        "retry_count": retry_count,
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_escalation_log.py
```

Expected: `2 passed`

- [ ] **Step 5: 런타임 로그 디렉터리를 gitignore에 추가**

`.gitignore`에 추가:

```
services/mcp/data/*.jsonl
```

- [ ] **Step 6: 커밋**

```bash
git add services/mcp/src/videobox_mcp/escalation_log.py tests/test_mcp_escalation_log.py .gitignore
git commit -m "feat: ask_yujin 실패 기록용 escalation_log 추가"
```

---

## Task 3: `tools.ask_yujin` — 세션 확보 → 제안 생성 → 적용, 실패 시 1회 재시도

**Files:**
- Modify: `services/mcp/src/videobox_mcp/tools.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: Task 1의 4개 `VideoBoxApiClient` 메서드, Task 2의 `log_ask_yujin_escalation`.
- Produces: `ask_yujin(client: VideoBoxApiClient, *, project_id: str, message: str) -> dict[str, Any]`
  — 성공 시 `{"status", "reply_text", "applied", "proposal_id"}`, 재시도까지
  실패하면 로그를 남기고 `VideoBoxApiError`를 그대로 올려보낸다(서버 계층이
  `ToolError`로 번역 — 기존 도구들과 같은 패턴, §7 "이유 있는 오류").

- [ ] **Step 1: 실패하는 테스트 작성 (성공 경로 — 세션 없음 → 생성 → 제안 → 적용)**

`tests/test_mcp_server.py`에 추가. `create_app`의
`local_only_runtime_service_factory`로 유진 응답을 고정한다(`tests/test_api_media_director.py`와
같은 패턴, 실제 LLM 없이 결정적으로 시험).

```python
def _client_and_app_for(tmp_path: Path, *, runtime_factory=None):
    from videobox_api.main import create_app

    kwargs: dict[str, Any] = {"projects_root": tmp_path}
    if runtime_factory is not None:
        kwargs["local_only_runtime_service_factory"] = runtime_factory
    app = create_app(**kwargs)
    transport = httpx.ASGITransport(app=app)
    return VideoBoxApiClient(base_url="http://testserver", transport=transport)


def test_ask_yujin_creates_session_then_applies_the_proposal(tmp_path: Path) -> None:
    from videobox_provider_interfaces.llm import StructuredLLMResponse
    from videobox_mcp import tools

    class FixedEditingRuntime:
        def generate_structured(self, **_kwargs: Any) -> StructuredLLMResponse:
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
                            {"intent": "set_scene_speed", "segment_id": "scene-2", "rate": 2}
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
    assert result["proposal_id"] == "fixture-proposal"
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_server.py::test_ask_yujin_creates_session_then_applies_the_proposal
```

Expected: `AttributeError: module 'videobox_mcp.tools' has no attribute 'ask_yujin'`

- [ ] **Step 3: `tools.py`에 구현 추가**

`services/mcp/src/videobox_mcp/tools.py` 끝에 추가:

```python
from .escalation_log import log_ask_yujin_escalation


async def ask_yujin(client: VideoBoxApiClient, *, project_id: str, message: str) -> dict[str, Any]:
    """유진에게 자연어로 편집을 요청한다.

    타임라인·자산을 직접 만지는 도구 대신 이 하나만 연다
    (`docs/videobox-mcp-scope.ko.md` 확장 스펙 §3) -- 화면 채팅과 같은 문
    (`.../yujin-editing-proposals` -> `.../apply`)을 그대로 거친다. 실패는
    정확히 1회만 재시도하고, 그래도 실패하면 성공한 척하지 않고 그대로
    올려보낸다(§7) -- 대표님이 확인한 정책: "재시도 1번 -> 사람에게
    에스컬레이션, 절대 우회하지 않기".
    """
    last_error: VideoBoxApiError | None = None
    for _ in range(2):
        try:
            return await _ask_yujin_once(client, project_id=project_id, message=message)
        except VideoBoxApiError as exc:
            last_error = exc
    assert last_error is not None
    log_ask_yujin_escalation(
        project_id=project_id, message=message, error=str(last_error), retry_count=1
    )
    raise last_error


async def _ask_yujin_once(
    client: VideoBoxApiClient, *, project_id: str, message: str
) -> dict[str, Any]:
    try:
        session = await client.get_latest_editing_session(project_id=project_id)
    except VideoBoxApiError as exc:
        if exc.status_code != 404:
            raise
        session = await client.create_blank_editing_session(project_id=project_id)
    session_id = session["session_id"]

    created = await client.create_yujin_editing_proposal(
        project_id=project_id, session_id=session_id, instruction=message
    )
    proposal = created.get("proposal")
    if proposal is None:
        # 유진이 되물었거나(clarification) 검증이 막았다(rejected) -- 적용할
        # 것이 없다. 성공한 척하지 않고 그 상태를 그대로 돌려준다.
        return {
            "status": created["status"],
            "reply_text": created.get("reply_text"),
            "applied": False,
            "proposal_id": None,
        }

    await client.apply_yujin_editing_proposal(
        project_id=project_id,
        session_id=session_id,
        proposal_id=proposal["proposal_id"],
        expected_revision=proposal["base_session_revision"],
    )
    return {
        "status": "applied",
        "reply_text": None,
        "applied": True,
        "proposal_id": proposal["proposal_id"],
    }
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_server.py::test_ask_yujin_creates_session_then_applies_the_proposal
```

Expected: `1 passed`

- [ ] **Step 5: 실패하는 테스트 작성 (재시도 후에도 실패 → 로그 남기고 올려보냄)**

```python
def test_ask_yujin_retries_once_then_logs_and_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
```

- [ ] **Step 6: 실패 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_server.py::test_ask_yujin_retries_once_then_logs_and_raises
```

Expected: `FAILED` — `call_count["n"] == 2` 전에 이미 통과할 수도 있으니, 이
시험이 Step 3의 구현보다 먼저 있었다면 실패했을 자리다. 지금은 Step 3을
이미 구현했으므로 **이 시험은 바로 통과할 수 있다** — 그렇다면 재시도
횟수(`call_count["n"] == 2`)와 로그 1건이 실제로 맞는지가 이 스텝의
진짜 확인 대상이다. 실패한다면 원인은 재시도 횟수나 로그 호출 누락이다.

- [ ] **Step 7: 통과 확인 및 필요 시 구현 보정**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_server.py::test_ask_yujin_retries_once_then_logs_and_raises
```

Expected: `1 passed`

- [ ] **Step 8: 커밋**

```bash
git add services/mcp/src/videobox_mcp/tools.py tests/test_mcp_server.py
git commit -m "feat: ask_yujin 도구 추가 - 세션 확보/제안/적용 + 1회 재시도"
```

---

## Task 4: `BearerAuthMiddleware` — HTTP 전송 인증

**Files:**
- Create: `services/mcp/src/videobox_mcp/auth.py`
- Test: `tests/test_mcp_auth.py`

**Interfaces:**
- Produces: `BearerAuthMiddleware(app, *, token: str)` — Starlette
  `BaseHTTPMiddleware` 서브클래스. `Authorization: Bearer <token>`이
  `hmac.compare_digest`로 정확히 일치하지 않으면 `401 {"error": "unauthorized"}`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
"""services/mcp/src/videobox_mcp/auth.py 시험 -- Bearer 인증 미들웨어만 확인한다.

MCP 프로토콜 핸드셰이크(session 초기화 등)는 여기서 시험하지 않는다 --
그건 `test_mcp_http_transport.py`(Task 5)의 몫이다. 여기서는 미들웨어가
토큰 없음/틀림에서 401을 내고, 맞으면 다음 앱으로 넘기는지만 본다.
"""

from __future__ import annotations

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from videobox_mcp.auth import BearerAuthMiddleware


def _app_with_auth(token: str) -> Starlette:
    async def ok(_request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/probe", ok, methods=["GET"])])
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": "secret-token"},  # "Bearer " 접두 없음
    ],
)
def test_missing_or_wrong_token_is_rejected(headers: dict[str, str]) -> None:
    app = _app_with_auth("secret-token")
    transport = httpx.ASGITransport(app=app)

    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        response = client.get("/probe", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_correct_token_passes_through() -> None:
    app = _app_with_auth("secret-token")
    transport = httpx.ASGITransport(app=app)

    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        response = client.get("/probe", headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_auth.py
```

Expected: `ModuleNotFoundError: No module named 'videobox_mcp.auth'`

- [ ] **Step 3: 구현**

```python
"""HTTP 전송 전용 Bearer 토큰 인증.

stdio 전송(로컬 프로세스 직접 실행)에는 안 건다 -- 호출자가 이미 같은
기계의 같은 사용자다. HTTP 전송만 밖에서 닿을 수 있으므로 여기만 잠근다.
`hmac.compare_digest`로 비교해 타이밍 공격을 막는다(openmic 패턴 준용,
`docs/superpowers/specs/2026-09-27-mcp-http-endpoint-for-ak-hermes-design.ko.md` §5).
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str) -> None:
        super().__init__(app)
        self._expected = f"Bearer {token}"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        header = request.headers.get("authorization", "")
        if not hmac.compare_digest(header, self._expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_auth.py
```

Expected: `4 passed` (parametrize 3건 + 통과 1건)

- [ ] **Step 5: 커밋**

```bash
git add services/mcp/src/videobox_mcp/auth.py tests/test_mcp_auth.py
git commit -m "feat: MCP HTTP 전송용 Bearer 인증 미들웨어 추가"
```

---

## Task 5: `server.py`에 HTTP 전송 배선 + `ask_yujin` 도구 등록

**Files:**
- Modify: `services/mcp/src/videobox_mcp/server.py`
- Test: `tests/test_mcp_http_transport.py`

**Interfaces:**
- Consumes: Task 3의 `tools.ask_yujin`, Task 4의 `BearerAuthMiddleware`.
- Produces: `build_http_app(client: VideoBoxApiClient, *, token: str, host: str = "127.0.0.1") -> Starlette`,
  `main_http() -> None`. 기존 `build_server`/`main`은 시그니처 유지, `main`은
  `VIDEOBOX_MCP_TRANSPORT` 환경변수로 stdio/http를 가른다.

- [ ] **Step 1: `ask_yujin` 도구 등록 — 실패하는 테스트**

`tests/test_mcp_server.py`에 추가(기존 `build_server` 시험과 같은 스타일):

```python
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
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_server.py::test_ask_yujin_is_registered_as_a_tool
```

Expected: `AssertionError` (`ask_yujin`이 도구 목록에 없음)

- [ ] **Step 3: `server.py`의 `build_server`에 도구 등록 추가**

`services/mcp/src/videobox_mcp/server.py`의 `job_status` 도구 등록 뒤,
`return server` 앞에 추가:

```python
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
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_server.py::test_ask_yujin_is_registered_as_a_tool
```

Expected: `1 passed`

- [ ] **Step 5: HTTP 앱 빌더 — 실패하는 테스트**

```python
"""HTTP 전송 배선 시험. MCP 프로토콜 핸드셰이크가 아니라 인증 게이트가
실제로 이 전송에도 걸려 있는지만 확인한다(Task 4는 미들웨어 단독,
여기는 실제 MCPServer.streamable_http_app과 합쳐졌을 때).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from videobox_mcp.api_client import VideoBoxApiClient
from videobox_mcp.server import build_http_app


def _http_app(tmp_path: Path, token: str):
    from videobox_api.main import create_app

    app = create_app(projects_root=tmp_path)
    transport = httpx.ASGITransport(app=app)
    client = VideoBoxApiClient(base_url="http://testserver", transport=transport)
    return build_http_app(client, token=token, host="127.0.0.1")


def test_http_transport_rejects_missing_token(tmp_path: Path) -> None:
    """기존 `test_mcp_server.py`와 같은 스타일 -- 이 저장소는 async 시험에
    pytest-asyncio/anyio 마커를 쓰지 않고 `asyncio.run()`으로 감싼다.
    새 설정을 추가하지 않는다(YAGNI, 기존 관례 재사용)."""
    import asyncio

    app = _http_app(tmp_path, token="secret-token")
    transport = httpx.ASGITransport(app=app)

    async def run() -> httpx.Response:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8901") as client:
                return await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers={"Accept": "application/json, text/event-stream"},
                )

    response = asyncio.run(run())

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_http_transport_accepts_correct_token_past_auth_layer(tmp_path: Path) -> None:
    import asyncio

    app = _http_app(tmp_path, token="secret-token")
    transport = httpx.ASGITransport(app=app)

    async def run() -> httpx.Response:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8901") as client:
                return await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers={
                        "Authorization": "Bearer secret-token",
                        "Accept": "application/json, text/event-stream",
                    },
                )

    response = asyncio.run(run())

    # 인증은 통과했다 -- MCP 세션 초기화 핸드셰이크를 안 거쳤다는 별개의
    # 프로토콜 오류(400)가 나온다. 401이 아니라는 것 자체가 이 시험의 증거다.
    assert response.status_code != 401
```

- [ ] **Step 6: 실패 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_http_transport.py
```

Expected: `ImportError: cannot import name 'build_http_app'`

- [ ] **Step 7: `server.py`에 HTTP 전송 배선 추가**

`services/mcp/src/videobox_mcp/server.py` 머리에 import 추가:

```python
from .auth import BearerAuthMiddleware
```

`build_server` 함수 뒤, `def main()` 앞에 추가:

```python
def build_http_app(client: VideoBoxApiClient, *, token: str, host: str = "127.0.0.1"):
    """HTTP 전송 앱. 컨테이너 네트워크가 아니라 호스트 프로세스에서 띄운다
    (스펙 §2) -- 그래서 CLAUDE.md §6의 컨테이너 네트워크 경계 승인과 무관하다.
    """
    server = build_server(client)
    app = server.streamable_http_app(streamable_http_path="/mcp", host=host)
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app


def main_http() -> None:
    base_url = os.environ.get("VIDEOBOX_API_BASE_URL", "http://127.0.0.1:8000")
    token = os.environ.get("VIDEOBOX_MCP_HTTP_TOKEN")
    if not token:
        raise RuntimeError(
            "VIDEOBOX_MCP_HTTP_TOKEN이 없다 -- 열쇠 없이 HTTP 전송을 열지 않는다."
        )
    host = os.environ.get("VIDEOBOX_MCP_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("VIDEOBOX_MCP_HTTP_PORT", "8901"))
    client = VideoBoxApiClient(base_url=base_url)
    app = build_http_app(client, token=token, host=host)

    import uvicorn

    uvicorn.run(app, host=host, port=port)
```

`main()`을 아래로 교체:

```python
def main() -> None:
    transport = os.environ.get("VIDEOBOX_MCP_TRANSPORT", "stdio")
    if transport == "http":
        main_http()
        return
    base_url = os.environ.get("VIDEOBOX_API_BASE_URL", "http://127.0.0.1:8000")
    client = VideoBoxApiClient(base_url=base_url)
    server = build_server(client)
    server.run(transport="stdio")
```

- [ ] **Step 8: 통과 확인**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_http_transport.py
```

Expected: `2 passed`

- [ ] **Step 9: 회귀 확인 — MCP 스위트 전체**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_server.py tests/test_mcp_auth.py tests/test_mcp_escalation_log.py tests/test_mcp_http_transport.py
```

Expected: 전부 `passed`, 실패 0건.

- [ ] **Step 10: 커밋**

```bash
git add services/mcp/src/videobox_mcp/server.py tests/test_mcp_http_transport.py tests/test_mcp_server.py
git commit -m "feat: MCP 서버에 streamable-http 전송 배선 + ask_yujin 도구 등록"
```

---

## Task 6: 호스트 실행 스크립트 + AK-Hermes `.mcp.json` 등록 안내 문서

**Files:**
- Create: `scripts/start-videobox-mcp-http.ps1`
- Create: `docs/videobox-mcp-http-setup.ko.md`
- Modify: `docs/videobox-mcp-scope.ko.md` (§9 뒤에 착수 기록 추가)

**Interfaces:** 없음(코드 아님, 운영 스크립트·문서).

- [ ] **Step 1: 실행 스크립트 작성**

```powershell
<#
VideoBox MCP HTTP 전송을 호스트 프로세스로 띄운다 (컨테이너 아님 -- 스펙 §2).
AK-System Hermes 쪽 .mcp.json이 http://127.0.0.1:8901/mcp로 붙는다.
#>
param(
    [string]$VideoBoxApiBaseUrl = "http://127.0.0.1:8000",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8901
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "가상환경이 없습니다: $venvPython (requirements-mcp.txt를 먼저 설치하세요)"
}
if (-not $env:VIDEOBOX_MCP_HTTP_TOKEN) {
    throw "VIDEOBOX_MCP_HTTP_TOKEN 환경변수가 없습니다. AK-Hermes .mcp.json과 같은 값을 먼저 설정하세요."
}

$env:VIDEOBOX_API_BASE_URL = $VideoBoxApiBaseUrl
$env:VIDEOBOX_MCP_HTTP_HOST = $BindHost
$env:VIDEOBOX_MCP_HTTP_PORT = $Port
$env:VIDEOBOX_MCP_TRANSPORT = "http"
$env:PYTHONPATH = Join-Path $repoRoot "services\mcp\src"

Write-Host "VideoBox MCP HTTP 서버를 http://$BindHost`:$Port/mcp 에 띄웁니다..."
& $venvPython -m videobox_mcp.server
```

- [ ] **Step 2: 실물로 띄워서 401/200 확인 (VideoBox API가 먼저 떠 있어야 한다)**

```bash
$env:VIDEOBOX_MCP_HTTP_TOKEN = "local-smoke-test-token"
powershell -File scripts/start-videobox-mcp-http.ps1
```

다른 터미널에서:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8901/mcp -H "Content-Type: application/json" -d "{}"
```

Expected: `401` (토큰 없이 요청).

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8901/mcp -H "Authorization: Bearer local-smoke-test-token" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Expected: `401`이 아닌 값(핸드셰이크 오류일 수 있으나 인증은 통과).
서버 프로세스는 Ctrl+C로 종료.

- [ ] **Step 3: AK-Hermes 쪽 등록 안내 문서 작성**

```markdown
# VideoBox MCP HTTP 서버 — AK-Hermes 연결 설정 (2026-09-27)

## 1. VideoBox 쪽 (이 저장소)

1. 토큰을 하나 정한다(예: `openssl rand -hex 32` 또는 아무 긴 임의 문자열).
2. 그 값을 `VIDEOBOX_MCP_HTTP_TOKEN` 환경변수로 설정한다.
3. `scripts/start-videobox-mcp-http.ps1`을 실행해 `127.0.0.1:8901`에 띄운다.
   VideoBox API(`services/api`)가 먼저 떠 있어야 한다(`VIDEOBOX_API_BASE_URL`
   기본값 `http://127.0.0.1:8000`).

## 2. AK-System Hermes 쪽 (그 저장소)

1. 같은 토큰 값을 그 세션 환경변수 `VIDEOBOX_MCP_HTTP_TOKEN`으로 설정한다.
2. 그 저장소 `.mcp.json`에 아래를 추가한다:

```json
{
  "mcpServers": {
    "videobox": {
      "type": "http",
      "url": "http://127.0.0.1:8901/mcp",
      "headers": {
        "Authorization": "Bearer ${VIDEOBOX_MCP_HTTP_TOKEN}"
      }
    }
  }
}
```

## 3. 노출된 도구

- `create_project`/`list_projects`/`get_project`/`job_status` — 조회.
- `ask_yujin(project_id, message)` — 유진에게 자연어로 편집을 요청한다.
  타임라인을 직접 조작하지 않는다. 실패하면 1회 재시도 후 오류를 낸다
  (`is_error: true`) — 그 시점에 사람에게 확인을 넘겨라, 우회하지 마라.
  반복 실패는 `services/mcp/data/ask-yujin-escalations.jsonl`에 쌓인다.

## 범위 밖

타임라인·자산·렌더를 직접 조작하는 도구는 없다(`docs/videobox-mcp-scope.ko.md`).
```

- [ ] **Step 4: `videobox-mcp-scope.ko.md`에 착수 기록 추가**

`docs/videobox-mcp-scope.ko.md` §9("착수함") 뒤에 새 절 추가:

```markdown
## 9.1 착수함 (2026-09-27) — HTTP 전송 + `ask_yujin`

AK-System Hermes가 같은 컴퓨터에서 MCP로 붙을 수 있도록 `streamable-http`
전송(Bearer 인증)을 추가했다. 타임라인 직접 조작 대신 `ask_yujin`
하나만 열었다 -- 유진을 우회하지 않는다는 §1.1 원칙을 그대로 지킨다.
실패 시 1회 재시도 후 `services/mcp/data/ask-yujin-escalations.jsonl`에
기록하고 그대로 올려보낸다. 상세:
`docs/superpowers/specs/2026-09-27-mcp-http-endpoint-for-ak-hermes-design.ko.md`,
`docs/videobox-mcp-http-setup.ko.md`.
```

- [ ] **Step 5: 커밋**

```bash
git add scripts/start-videobox-mcp-http.ps1 docs/videobox-mcp-http-setup.ko.md docs/videobox-mcp-scope.ko.md
git commit -m "docs: MCP HTTP 서버 실행 스크립트 + AK-Hermes 연결 안내 추가"
```

---

## Task 7: 전체 회귀 확인

**Files:** 없음(검증만).

- [ ] **Step 1: 백엔드 전체 스위트**

```bash
.venv/Scripts/python.exe -m pytest -q
```

Expected: 전부 `passed`(2026-09-21 실측 기준선 5108 근방 + 이번에 추가한
테스트 수만큼 증가, `test_mcp_server.py`도 이제 포함됨). 실패 0건.

- [ ] **Step 2: 프런트엔드 회귀(변경 없음이지만 CLAUDE.md 조각별 검증 넷 중 하나)**

```bash
npm --prefix apps/web test
```

Expected: 기존과 동일하게 `passed`(이번 작업은 `apps/web`을 건드리지
않았으므로 변화 없어야 정상).

- [ ] **Step 3: 실물 배선 확인 (owner-ready 스택이 떠 있는 상태에서)**

```bash
$env:VIDEOBOX_MCP_HTTP_TOKEN = "<실제 배포용 토큰>"
powershell -File scripts/start-videobox-mcp-http.ps1
```

Claude Desktop이나 다른 MCP 클라이언트에서 `.mcp.json`으로 붙여
`ask_yujin`을 실제 프로젝트에 대고 한 번 호출해, 실제로 화면에서 타임라인이
바뀌는지 확인한다(CLAUDE.md §4 "완료는 화면에서 실제로 쓸 수 있는가").

- [ ] **Step 4: 최종 커밋 (변경 사항이 있다면)**

```bash
git status --short
```

여기까지 실패 없이 통과했다면 이 Task는 커밋할 코드 변경이 없다 —
검증 전용이다.
