"""모든 문에 Host·Origin 검사를 둔다 (2026-10-01 보안 점검 H1·M1).

실측: `Host: evil.example`로 보낸 `GET /api/projects`가 200으로 실제 목록을
돌려줬고, 같은 Host·Origin의 `DELETE /api/projects/<id>?confirm=true`가 403이
아니라 삭제 로직(404)까지 들어갔다. DNS 리바인딩으로 악성 페이지가 우리 API를
같은 출처처럼 부를 수 있다는 뜻이다. Origin 검사는 승인 문 넷에만 있었다.

브라우저 밖 호출자(curl·스모크·MCP)는 Origin을 안 붙이므로 그대로 통과해야 한다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(projects_root=tmp_path / "projects"))


def test_unknown_host_is_refused(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/api/projects", headers={"host": "evil.example:5173"})
    assert response.status_code == 400


def test_loopback_hosts_are_served(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for host in ("127.0.0.1:5173", "localhost:5173", "127.0.0.1:8000", "host.docker.internal:5173"):
        assert client.get("/api/projects", headers={"host": host}).status_code == 200, host


def test_cross_origin_write_is_refused_on_every_route(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.delete(
        "/api/projects/whatever?confirm=true", headers={"origin": "https://evil.example"}
    )
    assert response.status_code == 403
    response = client.post(
        "/api/projects", json={"name": "x"}, headers={"origin": "https://evil.example"}
    )
    assert response.status_code == 403


def test_trusted_origin_and_no_origin_writes_pass(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.post(
        "/api/projects", json={"name": "a"}, headers={"origin": "http://127.0.0.1:5173"}
    ).status_code in (200, 201)
    assert client.post("/api/projects", json={"name": "b"}).status_code in (200, 201)


def test_cross_origin_read_is_not_blocked_by_the_origin_check(tmp_path: Path) -> None:
    # 읽기는 Host 검사가 지킨다. GET까지 Origin으로 막으면 <img>·<video> 같은
    # 같은 출처 요청이 아닌 경로를 괜히 깨뜨릴 수 있다.
    response = _client(tmp_path).get("/api/projects", headers={"origin": "https://evil.example"})
    assert response.status_code == 200
