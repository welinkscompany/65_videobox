from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_agent_gateway.memory_gateway import MemoryWriteOutcome


def _seed(app, client: TestClient):
    project_id = client.post("/api/projects", json={"name": "memory"}).json()[
        "project_id"
    ]
    session = app.state.store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    conversation = client.post(
        f"/api/projects/{project_id}/director/conversations",
        json={"session_id": session["session_id"]},
    ).json()
    first = app.state.store.append_director_message(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation["conversation_id"],
        role="user",
        text="영상 템포를 조금 빠르게 해줘.",
    )
    second = app.state.store.append_director_message(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation["conversation_id"],
        role="assistant",
        text="빠른 컷과 짧은 호흡을 제안합니다.",
    )
    return project_id, session, conversation["conversation_id"], first, second


def _payload(conversation_id: str, *message_ids: str) -> dict[str, object]:
    return {
        "conversation_id": conversation_id,
        "client_request_id": "request-1",
        "source_message_ids": list(message_ids),
        "memory_scope": "creator",
        "category": "pacing",
        "proposed_text": "빠른 컷과 짧은 호흡을 선호합니다.",
    }


def test_create_and_list_are_pending_only_with_zero_external_calls_or_edit_mutation(
    tmp_path: Path,
) -> None:
    network_calls = 0

    def forbidden_network(*_args, **_kwargs):
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("D1 must not call a network/provider/gateway")

    with patch("videobox_api.main.urlopen", forbidden_network):
        app = create_app(projects_root=tmp_path)
        with TestClient(app) as client:
            project_id, session, conversation_id, first, second = _seed(app, client)
            before = app.state.store.get_editing_session(
                project_id=project_id,
                session_id=session["session_id"],
            )
            response = client.post(
                f"/api/projects/{project_id}/director/memory-candidates",
                json=_payload(
                    conversation_id,
                    first["message_id"],
                    second["message_id"],
                ),
            )
            listed = client.get(
                f"/api/projects/{project_id}/director/memory-candidates"
                f"?conversation_id={conversation_id}"
            )
            after = app.state.store.get_editing_session(
                project_id=project_id,
                session_id=session["session_id"],
            )

    assert response.status_code == 201
    candidate = response.json()
    assert set(candidate) == {
        "candidate_id",
        "project_id",
        "conversation_id",
        "client_request_id",
        "source_message_ids",
        "memory_scope",
        "category",
        "proposed_text",
        "status",
        "storage_status",
        "retryable",
        "created_at",
        "updated_at",
    }
    assert candidate["candidate_id"].startswith("memory-candidate-")
    assert candidate["status"] == "pending"
    assert listed.json() == {"candidates": [candidate]}
    assert before == after
    assert network_calls == 0
    assert app.state.hermes_run_service is None


def test_list_filters_current_conversation_before_limit_and_restores_storage(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, session, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        current = client.post(
            base, json=_payload(conversation_id, first["message_id"])
        ).json()
        client.post(f"{base}/{current['candidate_id']}/approve")
        app.state.yujin_memory_service._gateway = SimpleNamespace(
            add_approved_memory=lambda _request: None
        )
        claim_token = "claim-" + "a" * 64
        app.state.store.claim_yujin_memory_store(
            project_id=project_id,
            candidate_id=current["candidate_id"],
            client_request_id="store-current",
            claim_token=claim_token,
        )
        app.state.store.mark_yujin_memory_store_call_started(
            project_id=project_id,
            candidate_id=current["candidate_id"],
            claim_token=claim_token,
        )
        app.state.store.record_yujin_memory_provider_outcome(
            project_id=project_id,
            candidate_id=current["candidate_id"],
            claim_token=claim_token,
            status="failed_retryable",
            memory_ref=None,
            event_ref=None,
        )
        other_conversation = app.state.store.create_director_conversation(
            project_id=project_id,
            session_id=session["session_id"],
            conversation_id="conversation-other",
        )
        other_message = app.state.store.append_director_message(
            project_id=project_id,
            session_id=session["session_id"],
            conversation_id=other_conversation["conversation_id"],
            role="user",
            text="다른 대화의 편집 요청입니다.",
        )
        for index in range(101):
            app.state.store.create_yujin_memory_candidate(
                project_id=project_id,
                conversation_id=other_conversation["conversation_id"],
                client_request_id=f"other-{index:03d}",
                source_message_ids=(other_message["message_id"],),
                memory_scope="creator",
                category="pacing",
                proposed_text=f"빠른 컷 선호 {index:03d}",
            )

        listed = client.get(
            f"{base}?conversation_id={conversation_id}"
        )
        missing = client.get(base)
        unknown = client.get(
            f"{base}?conversation_id=conversation-missing"
        )

    assert listed.status_code == 200
    assert listed.json() == {
        "candidates": [
            {
                **current,
                "status": "approved",
                "storage_status": "failed_retryable",
                "retryable": True,
                "updated_at": listed.json()["candidates"][0]["updated_at"],
            }
        ]
    }
    assert "provider" not in listed.text
    assert "memory_ref" not in listed.text
    assert missing.status_code == 422
    assert unknown.status_code == 404
    assert unknown.json() == {
        "detail": "memory_candidate_conversation_missing"
    }


def test_approve_reject_are_explicit_idempotent_and_never_schedule_write(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        approved_candidate = client.post(
            base,
            json=_payload(conversation_id, first["message_id"]),
        ).json()
        rejected_candidate = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "request-2",
                "proposed_text": "짧은 인트로를 선호합니다.",
                "category": "tone",
            },
        ).json()

        approved = client.post(
            f"{base}/{approved_candidate['candidate_id']}/approve"
        )
        approved_again = client.post(
            f"{base}/{approved_candidate['candidate_id']}/approve"
        )
        approve_conflict = client.post(
            f"{base}/{approved_candidate['candidate_id']}/reject"
        )
        rejected = client.post(
            f"{base}/{rejected_candidate['candidate_id']}/reject"
        )
        rejected_again = client.post(
            f"{base}/{rejected_candidate['candidate_id']}/reject"
        )
        reject_conflict = client.post(
            f"{base}/{rejected_candidate['candidate_id']}/approve"
        )

    assert approved.json()["status"] == "approved"
    assert approved_again.json() == approved.json()
    assert rejected.json()["status"] == "rejected"
    assert rejected_again.json() == rejected.json()
    assert approve_conflict.status_code == 409
    assert approve_conflict.json() == {
        "detail": "memory_candidate_terminal_conflict"
    }
    assert reject_conflict.status_code == 409
    assert not hasattr(app.state, "memory_provider")
    assert not hasattr(app.state, "memory_write_queue")


def test_request_is_strict_and_scope_failures_do_not_leak(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        sentinel = "SENTINEL-DO-NOT-ECHO"
        extra = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "private_extra": sentinel,
            },
        )
        duplicate = client.post(
            base,
            json=_payload(
                conversation_id,
                first["message_id"],
                first["message_id"],
            ),
        )
        missing_conversation = client.post(
            base,
            json=_payload("missing", first["message_id"]),
        )
        missing_message = client.post(
            base,
            json=_payload(conversation_id, "missing"),
        )
        unknown_candidate = client.post(f"{base}/missing/approve")
        invalid_request_id = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "../escape",
            },
        )
        invalid_scope = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "memory_scope": "project",
            },
        )
        invalid_text_type = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "proposed_text": {"private": sentinel},
            },
        )

    assert extra.status_code == 422
    assert extra.json() == {"detail": "memory_candidate_request_invalid"}
    assert sentinel not in extra.text
    assert duplicate.status_code == 422
    assert invalid_request_id.status_code == 422
    assert invalid_scope.status_code == 422
    assert invalid_text_type.status_code == 422
    assert invalid_text_type.json() == {
        "detail": "memory_candidate_request_invalid"
    }
    assert sentinel not in invalid_text_type.text
    assert missing_conversation.status_code == 404
    assert missing_message.status_code == 404
    assert missing_conversation.json() == missing_message.json() == {
        "detail": "memory_candidate_source_missing"
    }
    assert unknown_candidate.status_code == 404
    assert unknown_candidate.json() == {"detail": "memory_candidate_missing"}


def test_api_policy_rejects_full_source_and_sensitive_text(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        full_source = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "proposed_text": "영상 템포를 조금 빠르게 해줘.",
            },
        )
        sensitive = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "request-2",
                "proposed_text": "API_KEY=secret",
            },
        )
        control_sentinel = "SENTINEL-CONTROL"
        control = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "request-3",
                "proposed_text": f"safe\u0000{control_sentinel}",
            },
        )
        provider_token = "sk-proj-abcdefghijklmnopqrstuvwxyz"
        unlabeled_secret = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "request-4",
                "proposed_text": provider_token,
            },
        )

    assert full_source.status_code == 422
    assert full_source.json() == {
        "detail": "memory_candidate_full_source_message_forbidden"
    }
    assert sensitive.status_code == 422
    assert sensitive.json() == {
        "detail": "memory_candidate_sensitive_text_forbidden"
    }
    assert control.status_code == 422
    assert control.json() == {
        "detail": "memory_candidate_control_character_forbidden"
    }
    assert unlabeled_secret.status_code == 422
    assert unlabeled_secret.json() == {
        "detail": "memory_candidate_sensitive_text_forbidden"
    }
    assert "API_KEY" not in sensitive.text
    assert control_sentinel not in control.text
    assert provider_token not in unlabeled_secret.text
    connection = app.state.store._connection(project_id)
    try:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM yujin_memory_candidates"
        ).fetchone()["count"] == 0
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM yujin_memory_candidate_audit"
        ).fetchone()["count"] == 0
    finally:
        connection.close()


def test_create_request_idempotency_and_conflict_are_stable(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        payload = _payload(conversation_id, first["message_id"])
        created = client.post(base, json=payload)
        repeated = client.post(base, json=payload)
        conflict = client.post(
            base,
            json={**payload, "category": "tone"},
        )

    assert created.status_code == 201
    assert repeated.status_code == 201
    assert repeated.json() == created.json()
    assert conflict.status_code == 409
    assert conflict.json() == {
        "detail": "memory_candidate_request_conflict"
    }


def test_configured_gateway_is_never_called_by_d1_endpoints(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class TrapGateway:
        def __getattr__(self, name: str):
            def trap(*_args, **_kwargs):
                calls.append(name)
                raise AssertionError("D1 external call")

            return trap

    with patch(
        "videobox_api.main._hermes_capability_verifier_from_environment",
        return_value=SimpleNamespace(),
    ):
        app = create_app(
            projects_root=tmp_path,
            agent_gateway_url="http://videobox-agent-gateway:8081",
            agent_gateway_service_token="service-token-that-is-at-least-thirty-two",
            agent_gateway_http_client_factory=lambda **_: TrapGateway(),
        )
    app.state.hermes_run_service.gateway_client = TrapGateway()
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        created = client.post(
            base,
            json=_payload(conversation_id, first["message_id"]),
        )
        candidate_id = created.json()["candidate_id"]
        assert client.get(
            base,
            params={"conversation_id": conversation_id},
        ).status_code == 200
        assert client.post(f"{base}/{candidate_id}/approve").status_code == 200
        rejected = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "request-2",
                "proposed_text": "차분한 도입을 선호합니다.",
                "category": "tone",
            },
        )
        assert client.post(
            f"{base}/{rejected.json()['candidate_id']}/reject"
        ).status_code == 200

    assert calls == []


def test_unknown_store_errors_are_fixed_and_never_echoed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sentinel = "SENTINEL-PRIVATE-STORE-ERROR"
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"

        monkeypatch.setattr(
            app.state.store,
            "create_yujin_memory_candidate",
            lambda **_: (_ for _ in ()).throw(ValueError(sentinel)),
        )
        create = client.post(
            base,
            json=_payload(conversation_id, first["message_id"]),
        )

        monkeypatch.setattr(
            app.state.store,
            "transition_yujin_memory_candidate",
            lambda **_: (_ for _ in ()).throw(ValueError(sentinel)),
        )
        transition = client.post(f"{base}/candidate/approve")

    assert create.status_code == 503
    assert transition.status_code == 503
    assert create.json() == transition.json() == {
        "detail": "memory_candidate_unavailable"
    }
    assert sentinel not in create.text
    assert sentinel not in transition.text


def test_store_requires_explicit_request_and_returns_no_provider_reference(
    tmp_path: Path,
) -> None:
    calls = []

    class Gateway:
        async def add_approved_memory(self, request):
            calls.append(request)
            return MemoryWriteOutcome(
                status="stored", memory_ref="provider-private"
            )

        async def reconcile_memory(self, request):
            raise AssertionError("first store must add")

    app = create_app(projects_root=tmp_path)
    app.state.yujin_memory_service._gateway = Gateway()
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        created = client.post(
            base, json=_payload(conversation_id, first["message_id"])
        ).json()
        approved = client.post(
            f"{base}/{created['candidate_id']}/approve"
        )
        missing_request = client.post(
            f"{base}/{created['candidate_id']}/store", json={}
        )
        stored = client.post(
            f"{base}/{created['candidate_id']}/store",
            json={"client_request_id": "store-request-1"},
        )

    assert approved.status_code == 200
    assert len(calls) == 1
    assert missing_request.status_code == 422
    assert stored.status_code == 200
    assert stored.json() == {
        "candidate_id": created["candidate_id"],
        "status": "approved",
        "storage_status": "stored",
        "retryable": False,
    }
    assert "provider-private" not in stored.text


def test_store_failure_is_fixed_and_never_echoes_internal_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sentinel = "PRIVATE-PROVIDER-DETAIL"
    app = create_app(projects_root=tmp_path)

    async def fail(**_kwargs):
        from videobox_api.yujin_memory_service import MemoryStoreUnavailable

        raise MemoryStoreUnavailable(sentinel)

    monkeypatch.setattr(
        app.state.yujin_memory_service, "store_candidate", fail
    )
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        created = client.post(
            base, json=_payload(conversation_id, first["message_id"])
        ).json()
        response = client.post(
            f"{base}/{created['candidate_id']}/store",
            json={"client_request_id": "store-request-1"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "memory_save_unavailable"}
    assert sentinel not in response.text


def test_delete_uses_candidate_handle_only_and_hides_private_mapping(
    tmp_path: Path,
) -> None:
    delete_calls = []

    class Gateway:
        async def add_approved_memory(self, _request):
            return MemoryWriteOutcome(
                status="stored", memory_ref="provider-private"
            )

        async def reconcile_memory(self, _request):
            raise AssertionError("first store must add")

        async def delete_memory(self, request):
            delete_calls.append(request)
            return {"deleted": True}

    app = create_app(projects_root=tmp_path)
    app.state.yujin_memory_service._gateway = Gateway()
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        created = client.post(
            base, json=_payload(conversation_id, first["message_id"])
        ).json()
        candidate_id = created["candidate_id"]
        assert client.post(f"{base}/{candidate_id}/approve").status_code == 200
        assert (
            client.post(
                f"{base}/{candidate_id}/store",
                json={"client_request_id": "store-request-1"},
            ).status_code
            == 200
        )
        deleted = client.delete(f"{base}/{candidate_id}/stored-memory")

    assert deleted.status_code == 200
    assert deleted.json() == {
        "candidate_id": candidate_id,
        "status": "approved",
        "storage_status": "deleted",
        "retryable": False,
    }
    assert len(delete_calls) == 1
    assert delete_calls[0].memory_ref == "provider-private"
    assert delete_calls[0].allow_absent is False
    assert "provider-private" not in deleted.text
    assert "external_ref" not in deleted.text

    rejected_restore = client.post(
        f"{base}/{candidate_id}/store",
        json={"client_request_id": "store-request-2"},
    )
    repeated_delete = client.delete(
        f"{base}/{candidate_id}/stored-memory"
    )
    assert rejected_restore.status_code == 409
    assert rejected_restore.json() == {
        "detail": "memory_candidate_deleted"
    }
    assert repeated_delete.status_code == 200
    assert repeated_delete.json() == deleted.json()
    assert len(delete_calls) == 1


def test_delete_retries_after_local_finalize_failure(
    tmp_path: Path, monkeypatch
) -> None:
    delete_calls = []

    class Gateway:
        async def add_approved_memory(self, _request):
            return MemoryWriteOutcome(
                status="stored", memory_ref="provider-private"
            )

        async def reconcile_memory(self, _request):
            raise AssertionError("first store must add")

        async def delete_memory(self, request):
            delete_calls.append(request)
            return {"deleted": True}

    app = create_app(projects_root=tmp_path)
    app.state.yujin_memory_service._gateway = Gateway()
    with TestClient(app, raise_server_exceptions=False) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        created = client.post(
            base, json=_payload(conversation_id, first["message_id"])
        ).json()
        candidate_id = created["candidate_id"]
        client.post(f"{base}/{candidate_id}/approve")
        client.post(
            f"{base}/{candidate_id}/store",
            json={"client_request_id": "store-request-1"},
        )
        original = app.state.store.mark_yujin_memory_deleted
        monkeypatch.setattr(
            app.state.store,
            "mark_yujin_memory_deleted",
            lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("crash after provider delete")
            ),
        )
        failed = client.delete(f"{base}/{candidate_id}/stored-memory")
        monkeypatch.setattr(
            app.state.store, "mark_yujin_memory_deleted", original
        )
        retried = client.delete(f"{base}/{candidate_id}/stored-memory")
        repeated = client.delete(f"{base}/{candidate_id}/stored-memory")

    assert failed.status_code == 503
    assert failed.json() == {"detail": "memory_delete_unavailable"}
    assert retried.status_code == 200
    assert retried.json()["storage_status"] == "deleted"
    assert repeated.json() == retried.json()
    assert len(delete_calls) == 2
    assert [call.allow_absent for call in delete_calls] == [False, True]
