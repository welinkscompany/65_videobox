"""owner가 유진(Hermes)에게 준 권한 하나(한 대화·한 실행)를 즉시 무효로 만든다.

`revoke_issued_hermes_capabilities`(저장 계층, 트랜잭션 잠금·감사 기록까지 이미
갖춘 함수)는 있었지만, 그걸 부르는 자리가 시험 밖에는 없었다
(`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §2 Phase 4).
이 스크립트가 그 자리다 -- 새 로직은 짜지 않는다, 이미 있는 저장 계층 함수를
owner가 터미널에서 부를 수 있게 이어 줄 뿐이다.

**서명 키 회전과는 다른 문제다.** 키 자체를 바꾸려면
`scripts/new-hermes-yujin-secrets.ps1 -Force`를 쓴다(이미 있다, 잠긴 계약
`key_replacement_mode: coordinated_single_key_only`가 그 방식을 못박아 둔다 --
`tests/test_hermes_capability_authority_contract.py`). 이 스크립트는 키가
아니라 **아직 살아 있는 개별 권한**(만료 전 5분 이내 토큰)을 지운다 -- 예를
들어 유진 실행이 이상하게 도는 걸 봤을 때, 5분을 기다리지 않고 바로 끊는 용도.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    REPOSITORY_ROOT / "packages" / "storage-abstractions" / "src",
    REPOSITORY_ROOT / "packages" / "core-engine" / "src",
):
    path_text = str(source_root)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def _default_store(projects_root_override: str | None) -> Any:
    from videobox_core_engine.settings import resolve_database_url, resolve_projects_root
    from videobox_storage.local_project_store import LocalProjectStore
    from videobox_storage.postgres_project_store import PostgresProjectStore

    projects_root = (
        Path(projects_root_override) if projects_root_override else resolve_projects_root()
    )
    database_url = resolve_database_url()
    if database_url is not None:
        return PostgresProjectStore(projects_root, database_url=database_url)
    return LocalProjectStore(projects_root)


def _parse_cli_arguments(arguments: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "유진에게 준 권한 하나(project_id·conversation_id·run_id로 정해지는 "
            "read_context/publish_proposal 둘)를 즉시 무효로 만든다."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--projects-root", default=None, help="생략하면 운영과 같은 방식으로 찾는다.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(list(arguments))


def main(
    argv: Sequence[str] | None = None,
    *,
    store_factory: Callable[[str | None], Any] = _default_store,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in arguments
    try:
        parsed = _parse_cli_arguments(arguments)
        json_mode = bool(parsed.json)
        store = store_factory(parsed.projects_root)
        try:
            revoked_count = store.revoke_issued_hermes_capabilities(
                project_id=parsed.project_id,
                conversation_id=parsed.conversation_id,
                run_id=parsed.run_id,
                reason="hermes_capability_revoked",
            )
        finally:
            close = getattr(store, "close", None)
            if callable(close):
                close()
        result = {"status": "ok", "revoked_count": revoked_count}
        if json_mode:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"무효로 만든 권한: {revoked_count}개")
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 -- CLI 경계, 원인을 코드 하나로 좁혀 보고한다
        # 이 저장소의 관례: 저장 계층은 `ValueError("machine_readable_code")`로
        # 실패 사유를 코드성 문구로 싣는다(예: `hermes_capability_audit_reason_invalid`).
        error_code = str(exc) or type(exc).__name__
        result = {"status": "error", "error_code": str(error_code)}
        if json_mode:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"실패: {error_code}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
