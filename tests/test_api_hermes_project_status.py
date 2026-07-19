from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from videobox_api.hermes_capabilities import HermesCapabilitySigner, HermesCapabilityVerifier
from videobox_api.main import create_app


CAPABILITY_KEY = b"hermes-status-test-key-must-be-at-least-thirty-two-bytes"


def _client(tmp_path: Path, *, now: datetime) -> tuple[TestClient, HermesCapabilitySigner]:
    verifier = HermesCapabilityVerifier(
        keys={"test-2026-07": CAPABILITY_KEY},
        now=lambda: now,
    )
    app = create_app(projects_root=tmp_path, hermes_capability_verifier=verifier)
    return TestClient(app), HermesCapabilitySigner(key_id="test-2026-07", key=CAPABILITY_KEY, now=lambda: now)


def _token(signer: HermesCapabilitySigner, *, project_id: str, now: datetime, **overrides: object) -> str:
    claims = {
        "iss": "videobox-agent-gateway",
        "sub": "yujin-video-director",
        "aud": "videobox-api",
        "op": "get_project_status",
        "project_id": project_id,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=2)).timestamp()),
        "jti": "capability-jti-0001",
    }
    claims.update(overrides)
    return signer.sign(claims)


def test_hermes_status_is_absent_without_an_explicit_verifier(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    assert client.get("/internal/hermes/projects/anything/status").status_code == 404
    assert "/internal/hermes/projects/{project_id}/status" not in client.get("/openapi.json").json()["paths"]


def test_hermes_capability_key_material_is_fail_closed() -> None:
    with pytest.raises(ValueError, match="hermes_capability_verifier_invalid"):
        HermesCapabilityVerifier(keys={"bad": b"short"})
    with pytest.raises(ValueError, match="hermes_capability_verifier_invalid"):
        HermesCapabilityVerifier(keys={"bad": "not-bytes"})  # type: ignore[arg-type]


def test_hermes_status_requires_a_single_use_scoped_capability_and_hides_storage_uri(tmp_path: Path) -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    client, signer = _client(tmp_path, now=now)
    project = client.post("/api/projects", json={"name": "물놀이"}).json()

    unauthenticated = client.get(f"/internal/hermes/projects/{project['project_id']}/status")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"] == "hermes_capability_missing"

    token = _token(signer, project_id=project["project_id"], now=now)
    response = client.get(
        f"/internal/hermes/projects/{project['project_id']}/status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "project_id": project["project_id"],
        "name": "물놀이",
        "status": "draft",
        "updated_at": payload["updated_at"],
        "has_editing_session": False,
        "latest_session_revision": None,
    }
    assert payload["updated_at"]
    assert "root_storage_uri" not in response.text
    replay = client.get(
        f"/internal/hermes/projects/{project['project_id']}/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replay.status_code == 401
    assert replay.json()["detail"] == "hermes_capability_replayed"


def test_hermes_status_rejects_expired_wrong_project_and_wrong_operation(tmp_path: Path) -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    client, signer = _client(tmp_path, now=now)
    first = client.post("/api/projects", json={"name": "첫 장면"}).json()
    second = client.post("/api/projects", json={"name": "둘째 장면"}).json()

    expired = _token(signer, project_id=first["project_id"], now=now, exp=int((now - timedelta(seconds=1)).timestamp()))
    assert client.get(
        f"/internal/hermes/projects/{first['project_id']}/status",
        headers={"Authorization": f"Bearer {expired}"},
    ).json()["detail"] == "hermes_capability_expired"

    cross_project = _token(signer, project_id=first["project_id"], now=now, jti="capability-jti-0002")
    assert client.get(
        f"/internal/hermes/projects/{second['project_id']}/status",
        headers={"Authorization": f"Bearer {cross_project}"},
    ).json()["detail"] == "hermes_capability_project_forbidden"

    wrong_operation = _token(signer, project_id=first["project_id"], now=now, op="render_project", jti="capability-jti-0003")
    assert client.get(
        f"/internal/hermes/projects/{first['project_id']}/status",
        headers={"Authorization": f"Bearer {wrong_operation}"},
    ).json()["detail"] == "hermes_capability_operation_forbidden"
