"""`scripts/run_memory_librarian.py`가 프로젝트의 대화 여러 개를 실제로 순회하는지.

`memory_librarian.distill_conversation_memories`(이미 따로 검증함)를 대화마다
부르는 배선만 확인한다 -- **한 대화가 실패해도 나머지는 계속** 돈다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = str(REPOSITORY_ROOT / "scripts")
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)

import run_memory_librarian as librarian_script  # noqa: E402
from videobox_storage.local_project_store import LocalProjectStore  # noqa: E402


class _FakeRuntime:
    def generate_structured(self, **_: Any) -> Any:
        raise AssertionError("이 시험은 LLM까지 안 닿는다 -- 대화가 비어 있어 nothing_new로 끝나야 한다")


def _project_with_two_conversations(store: LocalProjectStore) -> str:
    project = store.bootstrap_project("librarian script")
    session = store.save_editing_session(
        project_id=project.project_id, timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    store.create_director_conversation(
        project_id=project.project_id, session_id=session["session_id"],
        conversation_id="conversation-a",
    )
    store.create_director_conversation(
        project_id=project.project_id, session_id=session["session_id"],
        conversation_id="conversation-b",
    )
    return project.project_id


def test_script_processes_every_conversation_in_the_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = LocalProjectStore(tmp_path)
    project_id = _project_with_two_conversations(store)

    exit_code = librarian_script.main(
        ["--project-id", project_id, "--json"],
        store_factory=lambda _root: store,
        runtime_factory=lambda: _FakeRuntime(),
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["conversations_processed"] == 2
    assert summary["candidates_created"] == 0
    assert {row["conversation_id"] for row in summary["results"]} == {"conversation-a", "conversation-b"}
    assert all(row["status"] == "nothing_new" for row in summary["results"])


def test_one_conversation_failing_does_not_stop_the_others(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = LocalProjectStore(tmp_path)
    project_id = _project_with_two_conversations(store)
    real_list = store.list_director_messages_after

    def _boom(*, project_id, conversation_id, after_message_order):
        if conversation_id == "conversation-a":
            raise RuntimeError("simulated_failure")
        return real_list(project_id=project_id, conversation_id=conversation_id, after_message_order=after_message_order)

    store.list_director_messages_after = _boom

    exit_code = librarian_script.main(
        ["--project-id", project_id, "--json"],
        store_factory=lambda _root: store,
        runtime_factory=lambda: _FakeRuntime(),
    )

    assert exit_code == 1  # 하나는 실패했다고 알린다
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "completed_with_failures"
    by_id = {row["conversation_id"]: row for row in summary["results"]}
    assert by_id["conversation-a"]["status"] == "failed"
    assert by_id["conversation-b"]["status"] == "nothing_new"  # 옆 대화는 그대로 처리됐다
