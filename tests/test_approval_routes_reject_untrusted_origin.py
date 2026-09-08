"""승인 문 다섯 개가 크로스오리진 CSRF POST를 거절한다.

2026-09-07 전체 점검 §1-7: 검토 승인·촬영본 세그먼트 승인·가상 시퀀스 승인·
유진 기억 승인·director 제안 적용은 principal 검사가 없어 CORS 미들웨어도
없는 상태에서 어떤 Origin의 크로스오리진 POST든 그대로 실행됐다. owner가
악성 웹페이지를 열어 두면 그 페이지가 owner 대신 승인을 누를 수 있었다
(2026-09-08 인계 §2-2 후속 조치, owner 승인 2026-09-08 대화).

`Origin` 헤더가 아예 없는 요청(curl·스모크 스크립트·MCP 도구)은 그대로 통과해야
한다 -- 이 시험은 신뢰 목록 밖 Origin만 거절되는 것과, Origin이 없는 요청은
막히지 않는 것을 같이 잰다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(projects_root=tmp_path / "projects"))


def test_review_approval_rejects_a_cross_origin_request(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/api/projects/does-not-exist/review-approvals/does-not-exist/approve",
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {"reason": "untrusted_origin"}


def test_review_approval_with_no_origin_header_reaches_the_real_handler(tmp_path: Path) -> None:
    # 신뢰 목록에 없는 Origin만 막는다 -- Origin이 없으면(curl 등) 통과해서
    # 평소 로직(여기서는 존재하지 않는 프로젝트라 404/422)까지 간다.
    client = _client(tmp_path)

    response = client.post("/api/projects/does-not-exist/review-approvals/does-not-exist/approve")

    assert response.status_code != 403


def test_footage_proposal_approval_rejects_a_cross_origin_request(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/api/footage/proposals/does-not-exist/approve",
        json={"expected_revision": 1, "idempotency_key": "x"},
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {"reason": "untrusted_origin"}


def test_footage_virtual_sequence_approval_rejects_a_cross_origin_request(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/api/footage/sequences/does-not-exist/approve",
        json={"expected_revision": 1, "idempotency_key": "x"},
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {"reason": "untrusted_origin"}


def test_yujin_memory_candidate_approval_rejects_a_cross_origin_request(tmp_path: Path) -> None:
    client = _client(tmp_path)
    project_id = client.post("/api/projects", json={"name": "csrf guard"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/director/memory-candidates/does-not-exist/approve",
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {"reason": "untrusted_origin"}


def test_director_proposal_apply_rejects_a_cross_origin_request(tmp_path: Path) -> None:
    client = _client(tmp_path)
    project_id = client.post("/api/projects", json={"name": "csrf guard"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/director/proposals/does-not-exist/apply",
        json={},
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {"reason": "untrusted_origin"}


def test_trusted_dev_origin_is_not_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/api/projects/does-not-exist/review-approvals/does-not-exist/approve",
        headers={"origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code != 403
