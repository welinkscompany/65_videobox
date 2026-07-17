from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from datetime import UTC, datetime, timedelta

import pytest

from videobox_storage.local_project_store import LocalProjectStore


def test_messages_are_durable_ordered_and_do_not_mutate_editing_session(tmp_path: Path) -> None:
    """Task 13 RED: chat is durable project/session state, never an edit."""
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("conversation")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline",
        session_payload={"segments": [{"segment_id": "seg"}], "history": []},
    )
    before = deepcopy(store.get_editing_session(project_id=project.project_id, session_id=session["session_id"]))
    store.create_director_conversation(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv-1")

    first = store.append_director_message(
        project_id=project.project_id, session_id=session["session_id"], conversation_id="conv-1",
        role="user", text="3번 영상 바꿔줘", client_message_id="client-1",
    )
    second = store.append_director_message(
        project_id=project.project_id, session_id=session["session_id"], conversation_id="conv-1",
        role="assistant", text="어느 3번인가요?", proposal_id="proposal-1",
    )

    restarted = LocalProjectStore(tmp_path / "projects")
    messages = restarted.list_director_messages(project_id=project.project_id, conversation_id="conv-1")
    assert [message["message_id"] for message in messages] == [first["message_id"], second["message_id"]]
    assert messages[1]["proposal_id"] == "proposal-1"
    assert restarted.get_editing_session(project_id=project.project_id, session_id=session["session_id"]) == before


def test_client_message_id_returns_original_persisted_assistant_response(tmp_path: Path) -> None:
    """Retries must not create a second user or assistant message."""
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("idempotent")
    session = store.save_editing_session(project_id=project.project_id, timeline_id="timeline", session_payload={"segments": [], "history": []})
    store.create_director_conversation(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv")
    result = store.append_director_exchange(
        project_id=project.project_id, session_id=session["session_id"], conversation_id="conv",
        client_message_id="client-1", user_text="hello", assistant_text="local response",
    )
    retry = store.append_director_exchange(
        project_id=project.project_id, session_id=session["session_id"], conversation_id="conv",
        client_message_id="client-1", user_text="hello", assistant_text="different retry output",
    )
    assert retry == result
    assert [item["text"] for item in store.list_director_messages(project_id=project.project_id, conversation_id="conv")] == ["hello", "local response"]


def test_exchange_duplicate_cannot_cross_session_boundary(tmp_path: Path) -> None:
    """Store-level duplicate path is the final guard, not just the HTTP precheck."""
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("scope")
    first = store.save_editing_session(project_id=project.project_id, timeline_id="one", session_payload={"segments": [], "history": []})
    second = store.save_editing_session(project_id=project.project_id, timeline_id="two", session_payload={"segments": [], "history": []})
    store.create_director_conversation(project_id=project.project_id, session_id=first["session_id"], conversation_id="conv")
    store.append_director_exchange(project_id=project.project_id, session_id=first["session_id"], conversation_id="conv", client_message_id="same", user_text="one", assistant_text="answer")
    with pytest.raises(ValueError, match="conversation_scope_mismatch"):
        store.append_director_exchange(project_id=project.project_id, session_id=second["session_id"], conversation_id="conv", client_message_id="same", user_text="one", assistant_text="leak")


def test_store_rejects_unknown_session_without_creating_conversation(tmp_path: Path) -> None:
    """A message exchange may only target a conversation created explicitly by the API."""
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("session guard")
    with pytest.raises(KeyError, match="editing_session_missing"):
        store.append_director_exchange(project_id=project.project_id, session_id="missing", conversation_id="conv", client_message_id="once", user_text="hello", assistant_text="never")
    assert store.list_director_messages(project_id=project.project_id, conversation_id="conv") == []


def test_store_rejects_unknown_conversation_without_auto_creating_it(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("conversation guard")
    session = store.save_editing_session(project_id=project.project_id, timeline_id="timeline", session_payload={"segments": [], "history": []})

    with pytest.raises(KeyError, match="director_conversation_missing"):
        store.append_director_exchange(
            project_id=project.project_id, session_id=session["session_id"], conversation_id="not-created",
            client_message_id="once", user_text="hello", assistant_text="never",
        )
    with pytest.raises(KeyError, match="director_conversation_missing"):
        store.get_director_conversation(project_id=project.project_id, conversation_id="not-created")


def test_conversation_api_is_idempotent_and_local_failure_never_edits_session(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from videobox_api.main import create_app
    import videobox_api.main as api_main

    class FailingLocalRuntime:
        routing_mode = "local_only"
        calls = 0
        def generate_structured(self, **_: object) -> object:
            self.calls += 1
            raise RuntimeError("LM Studio unavailable")

    runtime = FailingLocalRuntime()
    external_calls = {"gemini": 0, "http": 0}
    def forbidden_gemini(*_: object, **__: object) -> object:
        external_calls["gemini"] += 1
        raise AssertionError("Gemini is forbidden")
    def forbidden_http(*_: object, **__: object) -> object:
        external_calls["http"] += 1
        raise AssertionError("external HTTP is forbidden")
    monkeypatch.setattr(api_main, "GeminiRESTStructuredProvider", forbidden_gemini, raising=False)
    monkeypatch.setattr(api_main, "urlopen", forbidden_http)
    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: runtime)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "chat"}).json()["project_id"]
    session = app.state.store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [], "history": []})
    before = deepcopy(app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"]))
    conversation = client.post(f"/api/projects/{project_id}/director/conversations", json={"session_id": session["session_id"]}).json()
    payload = {"session_id": session["session_id"], "client_message_id": "once", "text": "hello"}
    first = client.post(f"/api/projects/{project_id}/director/conversations/{conversation['conversation_id']}/messages", json=payload)
    second = client.post(f"/api/projects/{project_id}/director/conversations/{conversation['conversation_id']}/messages", json=payload)
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert runtime.calls == 1
    assert external_calls == {"gemini": 0, "http": 0}
    assert "local_only_blocked" in first.json()["assistant_message"]["text"]
    assert first.json()["assistant_message"]["metadata"]["status"] == "blocked"
    assert first.json()["assistant_message"]["metadata"]["error_code"] == "local_runtime_error"
    assert first.json()["assistant_message"]["metadata"]["provider_trace"]["routing_mode"] == "local_only"
    assert app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == before
    changed = client.post(
        f"/api/projects/{project_id}/director/conversations/{conversation['conversation_id']}/messages",
        json={**payload, "text": "altered"},
    )
    assert changed.status_code == 409


def test_conversation_api_returns_404_for_unknown_or_session_mismatched_conversation(tmp_path: Path) -> None:
    """A client can only read/write a conversation created for its session."""
    from fastapi.testclient import TestClient
    from videobox_api.main import create_app

    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "conversation scope"}).json()["project_id"]
    first = app.state.store.save_editing_session(project_id=project_id, timeline_id="one", session_payload={"segments": [], "history": []})
    second = app.state.store.save_editing_session(project_id=project_id, timeline_id="two", session_payload={"segments": [], "history": []})
    conversation = client.post(f"/api/projects/{project_id}/director/conversations", json={"session_id": first["session_id"]}).json()
    url = f"/api/projects/{project_id}/director/conversations/{conversation['conversation_id']}/messages"

    unknown = f"/api/projects/{project_id}/director/conversations/not-created/messages"
    assert client.get(url).status_code == 422
    assert client.get(f"{unknown}?session_id={first['session_id']}").status_code == 404
    assert client.get(f"{url}?session_id={second['session_id']}").status_code == 404
    assert client.post(unknown, json={"session_id": first["session_id"], "client_message_id": "unknown", "text": "hello"}).status_code == 404
    assert client.post(url, json={"session_id": second["session_id"], "client_message_id": "mismatch", "text": "hello"}).status_code == 404
    assert app.state.store.list_director_messages(project_id=project_id, conversation_id="not-created") == []


def test_resolved_timeline_command_persists_typed_action_intent_without_editing_mutation(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from videobox_api.main import create_app
    from videobox_core_engine.director_proposals import create_proposal
    from videobox_domain_models.director_proposals import DirectorCandidate

    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "intent"}).json()["project_id"]
    session = app.state.store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={"segments": [{"segment_id": "segment-1", "broll_override": {"asset_id": "asset-1"}}], "history": []},
    )
    session_revision = app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"])["session_revision"]
    app.state.store.save_director_proposal(
        project_id,
        create_proposal(
            proposal_id="proposal-immutable", revision=12,
            base_session_revision=session_revision, asset_index_revision=0,
            source_session_id=session["session_id"],
            candidates=[DirectorCandidate(
                candidate_id="candidate-immutable", visible_reference_code="P12-B-03", media_type="broll",
                asset_id="asset-1", library_asset_id=None, reason_chips=(), scores={}, availability="ready",
                review_status="approved", preview_uri=None, controls={}, expected_content_sha256=None,
                media_revision="registered-at", canonical_metadata={},
            )],
        ),
    )
    before = deepcopy(app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"]))
    conversation = client.post(f"/api/projects/{project_id}/director/conversations", json={"session_id": session["session_id"]}).json()

    response = client.post(
        f"/api/projects/{project_id}/director/conversations/{conversation['conversation_id']}/messages",
        json={"session_id": session["session_id"], "client_message_id": "target-1", "text": "P12-B-03 바꿔줘"},
    )

    assert response.status_code == 200
    intent = response.json()["assistant_message"]["metadata"]["action_intent"]
    assert intent["action"] == "replace_media"
    assert intent["target"] == {
        "reference_code": "P12-B-03",
        "immutable_id": "candidate-immutable",
        "source": "proposal",
    }
    assert intent["proposal_preflight"] == {
        "proposal_id": "proposal-immutable",
        "base_session_revision": session_revision,
        "asset_index_revision": 0,
    }
    assert app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == before


def test_concurrent_same_client_message_gets_retryable_202_until_local_result_is_persisted(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from videobox_api.main import create_app
    class BlockingRuntime:
        routing_mode = "local_only"
        calls = 0
        entered, release = Event(), Event()
        def generate_structured(self, **_: object) -> str:
            self.calls += 1
            self.entered.set()
            assert self.release.wait(3)
            return "one answer"
    runtime = BlockingRuntime()
    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: runtime)
    bootstrap = TestClient(app)
    project_id = bootstrap.post("/api/projects", json={"name": "concurrent"}).json()["project_id"]
    session = app.state.store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [], "history": []})
    conversation = bootstrap.post(f"/api/projects/{project_id}/director/conversations", json={"session_id": session["session_id"]}).json()
    url = f"/api/projects/{project_id}/director/conversations/{conversation['conversation_id']}/messages"
    payload = {"session_id": session["session_id"], "client_message_id": "same", "text": "hello"}
    first_claimed, duplicate_observed = Event(), Event()
    original_claim = app.state.store.claim_director_message
    def synchronized_claim(**kwargs: object) -> str | None:
        token = original_claim(**kwargs)
        if token:
            first_claimed.set()
        else:
            duplicate_observed.set()
        return token
    app.state.store.claim_director_message = synchronized_claim
    def post() -> object:
        return TestClient(app).post(url, json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(post)
        assert first_claimed.wait(3)
        assert runtime.entered.wait(3)
        two = pool.submit(post)
        assert duplicate_observed.wait(3)
        duplicate = two.result(timeout=3)
        assert duplicate.status_code == 202
        assert duplicate.json() == {"status": "director_message_in_progress", "retry_after_seconds": 1}
        assert duplicate.headers["Retry-After"] == "1"
        runtime.release.set()
        first_response = one.result(timeout=5)
    retry = bootstrap.post(url, json=payload)
    assert first_response.status_code == retry.status_code == 200
    assert first_response.json() == retry.json()
    assert runtime.calls == 1
    assert len(app.state.store.list_director_messages(project_id=project_id, conversation_id=conversation["conversation_id"])) == 2


def test_stale_claim_is_reclaimed_after_restart_without_duplicate_message_pair(tmp_path: Path) -> None:
    """A crash after claim cannot wedge the same client ID forever."""
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("lease")
    session = store.save_editing_session(project_id=project.project_id, timeline_id="timeline", session_payload={"segments": [], "history": []})
    store.create_director_conversation(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv")
    assert store.claim_director_message(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv", client_message_id="once", user_text="hello")
    connection = store._connection(project.project_id)
    connection.execute("UPDATE director_message_claims SET created_at = ?, heartbeat_at = ? WHERE conversation_id = ?", ("2000-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00", "conv"))
    connection.commit()
    connection.close()
    restarted = LocalProjectStore(tmp_path / "projects")
    assert restarted.claim_director_message(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv", client_message_id="once", user_text="hello")
    restarted.append_director_exchange(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv", client_message_id="once", user_text="hello", assistant_text="recovered")
    assert [item["role"] for item in restarted.list_director_messages(project_id=project.project_id, conversation_id="conv")] == ["user", "assistant"]


def test_live_claim_past_thirty_seconds_is_not_reclaimed(tmp_path: Path) -> None:
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    store = LocalProjectStore(tmp_path / "projects", now=lambda: instant)
    project = store.bootstrap_project("live lease")
    session = store.save_editing_session(project_id=project.project_id, timeline_id="timeline", session_payload={"segments": [], "history": []})
    store.create_director_conversation(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv")
    assert store.claim_director_message(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv", client_message_id="once", user_text="hello")
    later = LocalProjectStore(tmp_path / "projects", now=lambda: instant + timedelta(seconds=31))
    assert not later.claim_director_message(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv", client_message_id="once", user_text="hello")


def test_heartbeat_keeps_owner_past_lease_and_reclaimed_owner_is_fenced(tmp_path: Path) -> None:
    instant = [datetime(2026, 1, 1, tzinfo=UTC)]
    store = LocalProjectStore(tmp_path / "projects", now=lambda: instant[0])
    project = store.bootstrap_project("fence")
    session = store.save_editing_session(project_id=project.project_id, timeline_id="timeline", session_payload={"segments": [], "history": []})
    store.create_director_conversation(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv")
    first = store.claim_director_message(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv", client_message_id="once", user_text="hello")
    assert first
    instant[0] += timedelta(seconds=301)
    assert store.heartbeat_director_message_claim(project_id=project.project_id, conversation_id="conv", client_message_id="once", owner_token=first)
    assert not store.claim_director_message(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv", client_message_id="once", user_text="hello")
    instant[0] += timedelta(seconds=301)
    second = store.claim_director_message(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv", client_message_id="once", user_text="hello")
    assert second and second != first
    with pytest.raises(ValueError, match="claim_lost"):
        store.append_director_exchange(project_id=project.project_id, session_id=session["session_id"], conversation_id="conv", client_message_id="once", user_text="hello", assistant_text="stale", owner_token=first)
