"""도구 핸들러. `docs/videobox-mcp-scope.ko.md` §3.1(프로젝트)·§3.3(job_status)의 첫 슬라이스.

각 함수는 순수하게 `VideoBoxApiClient` 하나만 받아 작은 딕셔너리를 돌려준다 --
큰 바이너리는 절대 안 들고, `project_id`·`job_id`·참조 URL만 돌려준다(§1의
네 번째 원칙). `server.py`가 이 함수들을 MCP 도구로 등록한다.

실패는 조용한 빈 값이 아니라 `VideoBoxApiError`를 그대로 올려보낸다 --
"결과 없음"과 "못 읽었음"을 같은 응답으로 만들면 결함이다(§7).
"""

from __future__ import annotations

from typing import Any

from .api_client import VideoBoxApiClient, VideoBoxApiError
from .escalation_log import log_ask_yujin_escalation


async def create_project(client: VideoBoxApiClient, *, name: str) -> dict[str, Any]:
    project = await client.create_project(name=name)
    return {
        "project_id": project["project_id"],
        "name": project["name"],
        "status": project["status"],
    }


async def list_projects(client: VideoBoxApiClient, *, include_archived: bool = False) -> dict[str, Any]:
    result = await client.list_projects(include_archived=include_archived)
    return {
        "projects": [
            {"project_id": p["project_id"], "name": p["name"], "status": p["status"]}
            for p in result["projects"]
        ]
    }


async def get_project(client: VideoBoxApiClient, *, project_id: str) -> dict[str, Any]:
    project = await client.get_project(project_id=project_id)
    summary = await client.get_home_summary(project_id=project_id)
    return {
        "project_id": project["project_id"],
        "name": project["name"],
        "status": project["status"],
        "finished_video_count": summary["finished_video_count"],
        "has_draft": summary["has_draft"],
        "asset_gap_count": summary["asset_gap_count"],
    }


async def job_status(client: VideoBoxApiClient, *, project_id: str, job_id: str) -> dict[str, Any]:
    job = await client.get_job(project_id=project_id, job_id=job_id)
    return {
        "job_id": job["job_id"],
        "project_id": job["project_id"],
        "job_type": job["job_type"],
        "status": job["status"],
        "output_ref": job.get("output_ref"),
        "error_message": job.get("error_message"),
        "progress_percent": job.get("progress_percent"),
    }


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
    # `.../yujin-editing-proposals`는 만들어졌을 때 제안을 감싸지 않고
    # (`director_proposals.py`의 `payload()` -- `proposal_to_payload(proposal)
    # | {"status": "ready", ...}`) 그 필드를 응답 맨 위에 그대로 편다.
    # 되묻거나(clarification) 검증이 막았을(rejected) 때만 `{"status": ...,
    # "reply_text": ..., "proposal": None}` 모양이 된다 -- 그래서 "제안이
    # 실제로 나왔는가"는 `status == "ready"` 로 가른다.
    if created.get("status") != "ready":
        # 적용할 것이 없다. 성공한 척하지 않고 그 상태를 그대로 돌려준다.
        return {
            "status": created["status"],
            "reply_text": created.get("reply_text"),
            "applied": False,
            "proposal_id": None,
        }

    proposal_id = created["proposal_id"]
    await client.apply_yujin_editing_proposal(
        project_id=project_id,
        session_id=session_id,
        proposal_id=proposal_id,
        expected_revision=created["base_session_revision"],
    )
    return {
        "status": "applied",
        "reply_text": None,
        "applied": True,
        "proposal_id": proposal_id,
    }
