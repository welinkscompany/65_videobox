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
