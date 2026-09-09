"""기억 사서의 실제 진입점(`distill_conversation_memories`)을 통째로 관통해서 시험한다.

부품(정형구 필터, 워터마크)은 이미 따로 검증했다 -- 여기서는 **배선**이
실제로 맞는지: 새 메시지만 골라 필터를 거치고, LLM이 낸 사실이 승인
큐에 실제로 쌓이고, 실패하면 워터마크가 안 밀리는지를 진짜 `LocalProjectStore`로
관통해서 본다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from videobox_core_engine.memory_librarian import distill_conversation_memories
from videobox_provider_interfaces.llm import LLMTaskType
from videobox_storage.local_project_store import LocalProjectStore

NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


class _FakeStructuredResponse:
    def __init__(self, output_data: dict[str, Any]) -> None:
        self.output_data = output_data


class _FakeRuntime:
    def __init__(self, facts: list[dict[str, str]] | None = None, *, raise_error: bool = False) -> None:
        self._facts = facts or []
        self._raise_error = raise_error
        self.calls: list[dict[str, Any]] = []

    def generate_structured(self, *, project_id, task_type, prompt, response_schema):
        self.calls.append({"project_id": project_id, "task_type": task_type, "prompt": prompt})
        if self._raise_error:
            raise RuntimeError("local_runtime_unreachable")
        return _FakeStructuredResponse({"facts": self._facts})


def _new_project_with_conversation(store: LocalProjectStore):
    project = store.bootstrap_project("librarian distill")
    session = store.save_editing_session(
        project_id=project.project_id, timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    conversation = store.create_director_conversation(
        project_id=project.project_id, session_id=session["session_id"],
        conversation_id=f"conversation-{project.project_id}",
    )
    return project.project_id, session["session_id"], conversation["conversation_id"]


def _exchange(store: LocalProjectStore, *, project_id, session_id, conversation_id, seq, user_text):
    run = store.begin_director_hermes_run(
        project_id=project_id, session_id=session_id, conversation_id=conversation_id,
        client_message_id=f"msg-{seq}", user_text=user_text,
        expected_session_revision=1, expected_asset_index_revision=0,
    )
    assert run["dispatch"] is True
    assert store.complete_director_hermes_run(
        project_id=project_id, run_id=run["run_id"], owner_token=run["owner_token"],
        status="completed", assistant_text="참조를 확인했습니다.", public_text="", retryable=False,
    )


def test_no_new_messages_records_nothing_new_and_creates_no_candidate(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project_id, session_id, conversation_id = _new_project_with_conversation(store)
    runtime = _FakeRuntime()

    result = distill_conversation_memories(
        store, project_id=project_id, conversation_id=conversation_id, runtime=runtime, as_of=NOW,
    )

    assert result == {"status": "nothing_new", "candidates_created": 0}
    assert runtime.calls == []  # 새 메시지가 없으면 LLM을 아예 안 부른다


def test_a_real_preference_becomes_a_pending_memory_candidate(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project_id, session_id, conversation_id = _new_project_with_conversation(store)
    _exchange(store, project_id=project_id, session_id=session_id, conversation_id=conversation_id,
              seq=1, user_text="저는 빠른 컷 편집을 좋아해요.")
    runtime = _FakeRuntime(facts=[{"category": "pacing", "text": "빠른 컷 편집을 선호합니다."}])

    result = distill_conversation_memories(
        store, project_id=project_id, conversation_id=conversation_id, runtime=runtime, as_of=NOW,
    )

    assert result == {"status": "succeeded", "candidates_created": 1}
    candidates = store.list_yujin_memory_candidates(project_id=project_id)
    assert len(candidates) == 1
    assert candidates[0]["category"] == "pacing"
    assert candidates[0]["proposed_text"] == "빠른 컷 편집을 선호합니다."
    assert candidates[0]["status"] == "pending"  # 바로 mem0로 안 감 -- 승인 큐에 대기


def test_running_twice_does_not_reprocess_the_same_messages(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project_id, session_id, conversation_id = _new_project_with_conversation(store)
    _exchange(store, project_id=project_id, session_id=session_id, conversation_id=conversation_id,
              seq=1, user_text="저는 빠른 컷 편집을 좋아해요.")
    runtime = _FakeRuntime(facts=[{"category": "pacing", "text": "빠른 컷 편집을 선호합니다."}])
    distill_conversation_memories(
        store, project_id=project_id, conversation_id=conversation_id, runtime=runtime, as_of=NOW,
    )

    second = distill_conversation_memories(
        store, project_id=project_id, conversation_id=conversation_id, runtime=runtime, as_of=NOW,
    )

    assert second == {"status": "nothing_new", "candidates_created": 0}
    assert len(runtime.calls) == 1  # 두 번째 실행은 LLM을 다시 안 불렀다


def test_repeated_fixed_reply_is_filtered_as_boilerplate_not_a_preference(tmp_path: Path) -> None:
    """"참조를 확인했습니다."는 고정 응답이다 -- 반복되면 정형구로 걸러져야
    하고, 어차피 역할이 assistant라 사용자 발화로도 안 잡힌다. 대신 여러
    번 반복되는 **사용자** 발화가 그 자체로 취향처럼 오인되지 않는지 본다."""
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project_id, session_id, conversation_id = _new_project_with_conversation(store)
    for index in range(3):
        _exchange(store, project_id=project_id, session_id=session_id, conversation_id=conversation_id,
                  seq=index, user_text="짧게 부탁해요.")  # 3번 반복 -- 짧은 문단 기준(3)에 걸림
    runtime = _FakeRuntime(facts=[])

    result = distill_conversation_memories(
        store, project_id=project_id, conversation_id=conversation_id, runtime=runtime, as_of=NOW,
    )

    assert result == {"status": "nothing_new", "candidates_created": 0}
    assert runtime.calls == []  # 전부 정형구로 걸러져서 LLM 호출조차 없었다


def test_a_failed_llm_call_does_not_advance_the_watermark(tmp_path: Path) -> None:
    """실패하면 다음 실행이 같은 메시지를 다시 시도할 수 있어야 한다."""
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project_id, session_id, conversation_id = _new_project_with_conversation(store)
    _exchange(store, project_id=project_id, session_id=session_id, conversation_id=conversation_id,
              seq=1, user_text="저는 빠른 컷 편집을 좋아해요.")
    runtime = _FakeRuntime(raise_error=True)

    with pytest.raises(RuntimeError):
        distill_conversation_memories(
            store, project_id=project_id, conversation_id=conversation_id, runtime=runtime, as_of=NOW,
        )

    watermark = store.get_memory_librarian_watermark(project_id=project_id, conversation_id=conversation_id)
    assert watermark["last_run_status"] == "failed"
    assert watermark["last_message_order"] == 0  # 안 밀렸다
    assert store.list_yujin_memory_candidates(project_id=project_id) == []


def test_an_out_of_scope_category_from_the_model_is_dropped_not_stored(tmp_path: Path) -> None:
    """모델이 지어낸 category는 저장하지 않는다 -- 스키마가 받아 주는 다섯 개뿐."""
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project_id, session_id, conversation_id = _new_project_with_conversation(store)
    _exchange(store, project_id=project_id, session_id=session_id, conversation_id=conversation_id,
              seq=1, user_text="저는 빠른 컷 편집을 좋아해요.")
    runtime = _FakeRuntime(facts=[{"category": "not_a_real_category", "text": "무언가"}])

    result = distill_conversation_memories(
        store, project_id=project_id, conversation_id=conversation_id, runtime=runtime, as_of=NOW,
    )

    assert result == {"status": "succeeded", "candidates_created": 0}
    assert store.list_yujin_memory_candidates(project_id=project_id) == []
