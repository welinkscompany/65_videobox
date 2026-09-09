"""owner가 수동으로 돌리는 기억 사서 첫 버전.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md`에서
이어지는 작업 -- **자동 야간 스케줄링은 아직 안 넣었다**(컨테이너에 크론이
있는지 미확인, 있어도 §6 승인 대상일 수 있음). 이 스크립트로 먼저
파이프라인이 실제로 잘 도는지 owner가 직접 확인한 뒤 자동화를 논의한다.

프로젝트의 **대화 전부**를 훑는다 -- `create_yujin_memory_candidate`가
대화 하나 단위로만 후보를 만들 수 있어서(source_message_ids가 같은
대화 안에서만 검증됨), 실제로는 대화마다 `distill_conversation_memories`를
따로 부른다.
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
    REPOSITORY_ROOT / "services" / "api" / "src",
    REPOSITORY_ROOT / "packages" / "storage-abstractions" / "src",
    REPOSITORY_ROOT / "packages" / "core-engine" / "src",
    REPOSITORY_ROOT / "packages" / "provider-interfaces" / "src",
    REPOSITORY_ROOT / "packages" / "domain-models" / "src",
    REPOSITORY_ROOT / "packages" / "timeline-schema" / "src",
    REPOSITORY_ROOT / "packages" / "capcut-export" / "src",
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


def _default_runtime() -> Any:
    from videobox_api.orchestration import LocalOnlyRuntimeService, build_local_qwen_structured_provider
    from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig

    # 밤사이 여러 대화·여러 메시지를 한 번에 증류하는 프롬프트는 1턴 대화보다
    # 훨씬 길다 -- 기본 30초로는 모자랄 수 있다(`infographic_html`이 같은
    # 이유로 이미 따로 상한을 준 전례가 있다).
    config = LocalOpenAICompatibleRuntimeConfig(timeout_seconds=120)
    return LocalOnlyRuntimeService(
        local_provider=build_local_qwen_structured_provider(
            local_runtime_config=config,
            local_http_client=__import__("urllib.request", fromlist=["urlopen"]).urlopen,
        ),
        local_runtime_config=config,
    )


def _parse_cli_arguments(arguments: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="한 프로젝트의 대화들을 훑어 기억 후보(승인 대기)를 만든다.",
        allow_abbrev=False,
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--projects-root", default=None)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(list(arguments))


def main(
    argv: Sequence[str] | None = None,
    *,
    store_factory: Callable[[str | None], Any] = _default_store,
    runtime_factory: Callable[[], Any] = _default_runtime,
) -> int:
    from videobox_core_engine.memory_librarian import distill_conversation_memories

    arguments = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in arguments
    try:
        parsed = _parse_cli_arguments(arguments)
        json_mode = bool(parsed.json)
        store = store_factory(parsed.projects_root)
        runtime = runtime_factory()
        conversations = store.list_director_conversations(project_id=parsed.project_id)
        results = []
        had_failure = False
        for conversation in conversations:
            conversation_id = str(conversation["conversation_id"])
            try:
                outcome = distill_conversation_memories(
                    store,
                    project_id=parsed.project_id,
                    conversation_id=conversation_id,
                    runtime=runtime,
                )
                results.append({"conversation_id": conversation_id, **outcome})
            except Exception as exc:  # noqa: BLE001 -- 한 대화가 죽어도 나머지는 계속
                had_failure = True
                results.append({
                    "conversation_id": conversation_id,
                    "status": "failed",
                    "error": str(exc),
                })
        summary = {
            "status": "completed_with_failures" if had_failure else "completed",
            "conversations_processed": len(results),
            "candidates_created": sum(r.get("candidates_created", 0) for r in results),
            "results": results,
        }
        if json_mode:
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print(f"대화 {len(results)}개 처리, 새 기억 후보 {summary['candidates_created']}개(승인 대기).")
            for row in results:
                if row["status"] not in ("nothing_new",):
                    print(f"  - {row['conversation_id']}: {row['status']}")
        return 1 if had_failure else 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 -- CLI 경계
        result = {"status": "error", "error_code": str(exc)}
        if json_mode:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"실패: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
