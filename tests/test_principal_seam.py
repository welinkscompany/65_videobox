"""나중에 다중 사용자·구독으로 갈 수 있게 남겨 두는 이음매(seam).

기능이 아니다. **자리**다. 지금 VideoBox는 owner 1인용 로컬 제품이고
(`docs/decisions/2026-09-04-capcut-shell-with-my-assets.ko.md` §3), 결제·구독·
다중 사용자 인증은 `CLAUDE.md` §6에 따라 owner 명시 승인 대상이라 만들지 않는다.

여기서 못박는 것은 딱 두 가지다.

1. **"지금 누구인가"를 답하는 자리가 하나뿐이다** (`principal.resolve_principal`).
2. **"이걸 해도 되는가"를 답하는 자리가 하나뿐이다** (`entitlements.can`).

둘 다 지금은 고정된 1인 owner와 무조건 허용을 돌려준다. 나중에 요금제별로 막을
때 코드 50군데를 뒤지지 않고 이 두 자리만 고치면 되게 하려는 것이다. 그래서 이
테스트가 지키는 것은 "동작"이 아니라 **"읽는 자리가 하나로 남아 있는가"** 다.

동작은 조금도 바뀌면 안 된다 — 아래 API 테스트가 그것을 잰다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_api.principal import get_principal
from videobox_domain_models.entitlements import can
from videobox_domain_models.principal import (
    DEFAULT_OWNER_ID,
    DEFAULT_PLAN,
    Principal,
    resolve_principal,
)


def test_default_principal_is_the_single_local_owner() -> None:
    """설정이 없으면 지금까지와 똑같이 고정된 1인 owner다."""

    principal = resolve_principal(env={})

    assert principal == Principal(owner_id=DEFAULT_OWNER_ID, plan=DEFAULT_PLAN)


def test_the_principal_can_be_moved_by_configuration_not_by_code() -> None:
    """나중에 사용자가 여럿이 되면 코드가 아니라 설정이 바뀌어야 한다.

    로컬 모델 교체가 config로 남아 있는 것과 같은 이유다
    (`videobox-local-model-swap-is-config-not-code`).
    """

    principal = resolve_principal(
        env={"VIDEOBOX_OWNER_ID": "louis", "VIDEOBOX_OWNER_PLAN": "pro"}
    )

    assert principal.owner_id == "louis"
    assert principal.plan == "pro"


def test_blank_configuration_falls_back_instead_of_producing_an_empty_owner() -> None:
    """빈 문자열이 들어와도 소유자가 사라지지 않는다.

    `.env.container`에서 값 없이 이름만 남은 줄이 실제로 있었다
    (`videobox-mem0-approved-but-off`). 빈 owner_id가 통과하면 저장 경로나
    권한 판단이 조용히 빈 키를 쓰게 된다.
    """

    principal = resolve_principal(env={"VIDEOBOX_OWNER_ID": "   ", "VIDEOBOX_OWNER_PLAN": ""})

    assert principal == Principal(owner_id=DEFAULT_OWNER_ID, plan=DEFAULT_PLAN)


def test_a_principal_cannot_be_mutated_after_it_is_resolved() -> None:
    """요청 도중에 주체가 바뀌면 권한 판단이 앞뒤로 달라진다."""

    principal = resolve_principal(env={})

    try:
        principal.owner_id = "someone-else"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Principal이 변경 가능합니다 — frozen이어야 합니다")


def test_every_capability_is_allowed_today() -> None:
    """지금은 전부 허용이다. 막는 것은 요금제가 생길 때 여기 한 곳에서 한다."""

    principal = resolve_principal(env={})

    for capability in ("project.create", "project.list", "anything.at.all", ""):
        assert can(principal, capability) is True


def test_the_api_dependency_answers_with_the_same_default_principal() -> None:
    """API 경계가 다른 답을 들고 있으면 자리가 둘이 된다."""

    assert get_principal() == resolve_principal(env={})


def _project_routes(app: object) -> dict[tuple[str, str], object]:
    routes: dict[tuple[str, str], object] = {}
    for route in app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", None)
        if path != "/api/projects":
            continue
        for method in sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}):
            routes[(method, path)] = route
    return routes


def test_the_project_routes_actually_go_through_the_principal_dependency(tmp_path: Path) -> None:
    """통로를 만들어 놓고 아무도 안 쓰면 나중에 조용히 낡는다.

    `videobox-parts-exist-but-nothing-calls-them` — 부품만 있고 부르는 자리가
    없던 일이 이 저장소에서 반복됐다. 그래서 대표 경로 두 곳이 실제로 이
    의존성을 지나는지 여기서 못박는다.
    """

    app = create_app(projects_root=tmp_path)
    routes = _project_routes(app)

    assert set(routes) == {("GET", "/api/projects"), ("POST", "/api/projects")}
    for key, route in routes.items():
        wired = {
            dependency.call
            for dependency in route.dependant.dependencies  # type: ignore[attr-defined]
        }
        assert get_principal in wired, f"{key[0]} {key[1]}이 주체 통로를 지나지 않습니다"


def test_wiring_the_seam_changes_nothing_the_screen_can_see(tmp_path: Path) -> None:
    """이번 작업의 성공 기준이다 — 화면이 받는 것이 그대로여야 한다.

    의존성이 요청 파라미터를 새로 만들어 버리면(예: 쿼리 하나가 늘면) 기존
    클라이언트가 그대로 깨진다. 그래서 응답뿐 아니라 공개 스키마의 파라미터
    목록까지 함께 잰다.
    """

    client = TestClient(create_app(projects_root=tmp_path))

    created = client.post("/api/projects", json={"name": "첫 영상"})
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {"project_id", "name", "status", "root_storage_uri"}
    assert body["name"] == "첫 영상"
    assert body["status"] == "draft"
    assert body["root_storage_uri"] == f"local://projects/{body['project_id']}"

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    assert [project["project_id"] for project in listed.json()["projects"]] == [body["project_id"]]

def test_flipping_the_single_permission_function_is_enough_to_refuse(
    tmp_path: Path, monkeypatch
) -> None:
    """이음매가 실제로 이음매인지 잰다.

    나중에 요금제로 막을 때 고칠 곳이 정말 `entitlements.can` 하나인지가
    이번 작업의 전부다. 라우터를 건드리지 않고 그 함수만 바꿔서 거절이
    나오면 통로가 살아 있는 것이다. 이건 기본 동작이 아니라 **가정**을 재는
    시험이다 -- 기본값에서는 위 테스트대로 아무도 막히지 않는다.
    """

    from videobox_api.routers import projects as projects_router

    monkeypatch.setattr(projects_router, "can", lambda principal, capability: False)
    client = TestClient(create_app(projects_root=tmp_path))

    assert client.post("/api/projects", json={"name": "첫 영상"}).status_code == 403
    assert client.get("/api/projects").status_code == 403


def test_the_public_schema_gains_no_new_parameters(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))

    schema = client.get("/openapi.json").json()["paths"]["/api/projects"]
    assert [parameter["name"] for parameter in schema["post"].get("parameters", [])] == []
    assert [parameter["name"] for parameter in schema["get"].get("parameters", [])] == [
        "include_archived"
    ]
