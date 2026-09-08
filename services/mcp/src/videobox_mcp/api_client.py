"""VideoBox API를 부르는 얇은 문. MCP는 core engine을 직접 import하지 않는다.

`docs/videobox-mcp-scope.ko.md` §1의 세 번째 원칙: **MCP → API → Core 순서를
지킨다.** 화면과 에이전트가 같은 문을 쓰게 하려는 것이고, 그래야 한쪽만
조용히 달라지지 않는다. 그래서 이 클라이언트는 core engine이나 storage
계층을 한 줄도 import하지 않고, 오직 HTTP로만 API를 부른다.

비동기다 -- MCP 도구 실행 자체가 비동기이고, 시험에서는 `transport`에
`httpx.ASGITransport(app=create_app(...))`를 넣어 실제 소켓을 열지 않고
같은 FastAPI 앱을 인메모리로 부른다(`tests/conftest.py`의 소켓 차단
픽스처와 맞물린다). 운영에서는 `base_url`만 주면 기본 전송이 실제
소켓을 연다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class VideoBoxApiError(Exception):
    """API가 2xx가 아닌 응답을 돌려줬다. 상태 코드와 원문 detail을 그대로 들고 있는다."""

    def __init__(self, *, status_code: int, detail: object, path: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.path = path
        super().__init__(f"{status_code} on {path}: {detail!r}")


@dataclass
class VideoBoxApiClient:
    """`docs/videobox-mcp-scope.ko.md` §3.1·§3.3이 정한 첫 도구 셋이 부르는 문만 감싼다."""

    base_url: str = "http://127.0.0.1:8000"
    transport: httpx.AsyncBaseTransport | None = None
    timeout: float = 30.0

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, transport=self.transport, timeout=self.timeout)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with self._client() as client:
            response = await client.request(method, path, **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise VideoBoxApiError(status_code=response.status_code, detail=detail, path=path)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def create_project(self, *, name: str) -> dict[str, Any]:
        return await self._request("POST", "/api/projects", json={"name": name})

    async def list_projects(self, *, include_archived: bool = False) -> dict[str, Any]:
        return await self._request(
            "GET", "/api/projects", params={"include_archived": include_archived}
        )

    async def get_project(self, *, project_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/projects/{project_id}")

    async def get_home_summary(self, *, project_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/projects/{project_id}/home-summary")

    async def get_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/projects/{project_id}/jobs/{job_id}")
