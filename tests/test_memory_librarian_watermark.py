"""기억 사서의 워터마크(어디까지 읽었는지)와 새 메시지 조회.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md`에서
이어지는 작업. Rumi Wiki Librarian이 실제로 겪은 실패("성공 실행이 이전
실행의 카운터를 물려받아 마치 자기가 한 것처럼 보임")를 코드로 막는지가
핵심이다 -- 모든 종료 경로에서 **통째로 덮어쓴다.**
"""

from __future__ import annotations

from pathlib import Path

from videobox_storage.local_project_store import LocalProjectStore


def _seed_conversation_with_two_messages(store: LocalProjectStore):
    project = store.bootstrap_project("librarian watermark")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    conversation = store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=f"conversation-{project.project_id}",
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation["conversation_id"],
        client_message_id="seed-1",
        user_text="영상 템포를 조금 빠르게 해줘.",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    assert run["dispatch"] is True
    assert store.complete_director_hermes_run(
        project_id=project.project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text="빠른 컷과 짧은 호흡을 제안합니다.",
        public_text="",
        retryable=False,
    )
    return project.project_id, conversation["conversation_id"]


def test_get_memory_librarian_watermark_is_none_before_any_run(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, conversation_id = _seed_conversation_with_two_messages(store)

    watermark = store.get_memory_librarian_watermark(
        project_id=project_id, conversation_id=conversation_id
    )

    assert watermark is None  # "0부터"와 "실행한 적 없음"은 다르다


def test_list_director_messages_after_returns_only_newer_messages(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, conversation_id = _seed_conversation_with_two_messages(store)
    all_messages = store.list_director_messages_after(
        project_id=project_id, conversation_id=conversation_id, after_message_order=0
    )
    assert len(all_messages) == 2
    first_order = all_messages[0]["message_order"]

    newer_only = store.list_director_messages_after(
        project_id=project_id, conversation_id=conversation_id, after_message_order=first_order
    )

    assert len(newer_only) == 1
    assert newer_only[0]["role"] == "assistant"


def test_record_memory_librarian_run_persists_and_is_read_back(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, conversation_id = _seed_conversation_with_two_messages(store)

    recorded = store.record_memory_librarian_run(
        project_id=project_id,
        conversation_id=conversation_id,
        last_message_order=2,
        status="succeeded",
        candidates_created=1,
    )

    assert recorded["last_message_order"] == 2
    assert recorded["last_run_status"] == "succeeded"
    assert recorded["last_candidates_created"] == 1

    watermark = store.get_memory_librarian_watermark(
        project_id=project_id, conversation_id=conversation_id
    )
    assert watermark == recorded


def test_a_later_run_completely_overwrites_the_previous_one() -> None:
    """Rumi가 실제로 겪은 실패: 조용한 성공 실행이 이전 실행의 숫자를
    물려받아 마치 자기가 한 것처럼 보였다. 매 실행은 이전 값을 하나도 안
    남기고 통째로 덮어써야 한다."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        store = LocalProjectStore(Path(tmp))
        project_id, conversation_id = _seed_conversation_with_two_messages(store)
        store.record_memory_librarian_run(
            project_id=project_id, conversation_id=conversation_id,
            last_message_order=2, status="succeeded", candidates_created=3,
        )

        # 다음 실행: 새 메시지가 없었다 -- 후보 0개, 그런데 워터마크는 "succeeded"
        # 실행의 흔적(candidates_created=3)을 하나도 안 물려받아야 한다.
        second = store.record_memory_librarian_run(
            project_id=project_id, conversation_id=conversation_id,
            last_message_order=2, status="nothing_new", candidates_created=0,
        )

        assert second["last_run_status"] == "nothing_new"
        assert second["last_candidates_created"] == 0  # 이전 3을 안 물려받았다


def test_record_memory_librarian_run_rejects_an_unknown_status(tmp_path: Path) -> None:
    import pytest

    store = LocalProjectStore(tmp_path)
    project_id, conversation_id = _seed_conversation_with_two_messages(store)

    with pytest.raises(ValueError):
        store.record_memory_librarian_run(
            project_id=project_id, conversation_id=conversation_id,
            last_message_order=2, status="ok", candidates_created=0,  # "ok"는 안 받는다
        )
