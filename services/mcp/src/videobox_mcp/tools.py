"""도구 핸들러. `docs/videobox-mcp-scope.ko.md` §3.1(프로젝트)·§3.3(job_status)의 첫 슬라이스.

각 함수는 순수하게 `VideoBoxApiClient` 하나만 받아 작은 딕셔너리를 돌려준다 --
큰 바이너리는 절대 안 들고, `project_id`·`job_id`·참조 URL만 돌려준다(§1의
네 번째 원칙). `server.py`가 이 함수들을 MCP 도구로 등록한다.

실패는 조용한 빈 값이 아니라 `VideoBoxApiError`를 그대로 올려보낸다 --
"결과 없음"과 "못 읽었음"을 같은 응답으로 만들면 결함이다(§7).
"""

from __future__ import annotations

from typing import Any

from .api_client import VideoBoxApiClient


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
