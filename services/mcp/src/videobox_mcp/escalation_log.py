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

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ask-yujin-escalations.jsonl"


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
