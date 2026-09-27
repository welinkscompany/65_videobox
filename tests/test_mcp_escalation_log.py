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


def test_log_ask_yujin_escalation_uses_env_var_when_path_not_provided(
    tmp_path: Path, monkeypatch
) -> None:
    """환경변수 VIDEOBOX_MCP_ESCALATION_LOG_PATH를 사용하는지 확인."""
    env_log_path = tmp_path / "env-log.jsonl"
    monkeypatch.setenv("VIDEOBOX_MCP_ESCALATION_LOG_PATH", str(env_log_path))

    log_ask_yujin_escalation(
        project_id="project_004",
        message="환경변수로 경로를 지정했어",
        error="test error",
        retry_count=2,
    )

    assert env_log_path.exists()
    lines = env_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["project_id"] == "project_004"
    assert record["message"] == "환경변수로 경로를 지정했어"
    assert record["retry_count"] == 2
    assert "test error" in record["error"]
    assert "timestamp" in record


def test_a_test_that_forgets_to_patch_the_logger_never_writes_the_real_escalation_log() -> None:
    """Tests must never append to the owner's real escalation log.

    2026-09-28: all five lines in `services/mcp/data/ask-yujin-escalations.jsonl`
    were test data (`project_id="does-not-matter"`, `message="아무 말"`,
    `simulated timeout`). They came from
    `test_ask_yujin_network_failure_becomes_a_tool_error_not_a_raw_exception`,
    which drives `ask_yujin` through the server without patching the logger.
    A later reader of that file could not tell a real escalation from a test.

    The guard lives in `tests/conftest.py` (an autouse fixture that points
    `VIDEOBOX_MCP_ESCALATION_LOG_PATH` at a per-test temp file), so a test
    that calls the logger with no path -- exactly what the real tool does --
    lands in the temp file and the real log stays byte-identical.
    """
    import os

    from videobox_mcp.escalation_log import DEFAULT_LOG_PATH

    before = DEFAULT_LOG_PATH.read_bytes() if DEFAULT_LOG_PATH.exists() else None

    log_ask_yujin_escalation(
        project_id="escalation-guard-probe", message="m", error="e", retry_count=1
    )

    after = DEFAULT_LOG_PATH.read_bytes() if DEFAULT_LOG_PATH.exists() else None
    assert after == before, "a test wrote into the real ask_yujin escalation log"

    redirected = Path(os.environ["VIDEOBOX_MCP_ESCALATION_LOG_PATH"])
    assert redirected.resolve() != DEFAULT_LOG_PATH.resolve()
    assert "escalation-guard-probe" in redirected.read_text(encoding="utf-8")
