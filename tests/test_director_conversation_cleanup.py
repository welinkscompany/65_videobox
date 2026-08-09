"""쌓인 유진 대화를 지울 수 있어야 한다.

대화는 계속 쌓이기만 했다 -- 점검 시점에 28건이었고 지우는 방법이 없었다.
매일 쓰면 늘어나기만 하는 목록은 결국 owner가 자기 기록을 못 찾게 만든다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from videobox_storage.local_project_store import LocalProjectStore


def _store(tmp_path: Path) -> tuple[LocalProjectStore, str, str]:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("대화 정리")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline",
        session_payload={"segments": [{"segment_id": "seg"}], "history": []},
    )
    return store, project.project_id, str(session["session_id"])


def _conversation(store: LocalProjectStore, project_id: str, session_id: str, conversation_id: str) -> None:
    store.create_director_conversation(
        project_id=project_id, session_id=session_id, conversation_id=conversation_id
    )
    


def test_a_conversation_and_its_messages_go_together(tmp_path: Path) -> None:
    # 대화만 지우고 메시지를 남기면 주인 없는 기록이 남는다.
    store, project_id, session_id = _store(tmp_path)
    _conversation(store, project_id, session_id, "conv-1")
    for role, text in (("user", "안녕"), ("assistant", "안녕하세요")):
        store.append_director_message(
            project_id=project_id, session_id=session_id, conversation_id="conv-1",
            role=role, text=text,
        )
    assert len(store.list_director_messages(project_id=project_id, conversation_id="conv-1")) == 2

    removed = store.delete_director_conversation(project_id=project_id, conversation_id="conv-1")

    assert removed is True
    assert store.list_director_messages(project_id=project_id, conversation_id="conv-1") == []
    with pytest.raises(KeyError):
        store.get_director_conversation(project_id=project_id, conversation_id="conv-1")


def test_deleting_one_conversation_leaves_the_others_alone(tmp_path: Path) -> None:
    store, project_id, session_id = _store(tmp_path)
    _conversation(store, project_id, session_id, "conv-keep")
    _conversation(store, project_id, session_id, "conv-drop")

    store.delete_director_conversation(project_id=project_id, conversation_id="conv-drop")

    assert store.get_director_conversation(project_id=project_id, conversation_id="conv-keep")["conversation_id"] == "conv-keep"


def test_deleting_something_that_is_not_there_says_so_rather_than_pretending(tmp_path: Path) -> None:
    store, project_id, session_id = _store(tmp_path)

    assert store.delete_director_conversation(project_id=project_id, conversation_id="conv-missing") is False


def test_conversations_can_be_listed_so_the_owner_can_choose(tmp_path: Path) -> None:
    # 지울 수 있으려면 무엇이 있는지부터 보여야 한다.
    store, project_id, session_id = _store(tmp_path)
    _conversation(store, project_id, session_id, "conv-1")
    _conversation(store, project_id, session_id, "conv-2")
    for role, text in (("user", "질문"), ("assistant", "답")):
        store.append_director_message(
            project_id=project_id, session_id=session_id, conversation_id="conv-2",
            role=role, text=text,
        )

    listed = store.list_director_conversations(project_id=project_id)

    by_id = {item["conversation_id"]: item for item in listed}
    assert set(by_id) == {"conv-1", "conv-2"}
    assert by_id["conv-2"]["message_count"] == 2
    assert by_id["conv-1"]["message_count"] == 0
