from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from videobox_api.agent_gateway_client import (
    AgentGatewayEvent,
    AgentGatewayReservation,
    AgentGatewayUnavailable,
)
from videobox_api.hermes_capabilities import (
    HermesCapabilityError,
    HermesCapabilityUnavailableError as HermesVerifierUnavailableError,
)
from videobox_api.hermes_run_service import (
    HermesContextPreparationUnavailable,
    HermesRunService,
)
from videobox_api.main import _media_analysis_lifespan, _recover_hermes_runs
from videobox_api.yujin_memory_service import YujinMemoryService
from videobox_domain_models.assets import AssetType
from videobox_domain_models.director_proposals import DirectorCandidate, DirectorProposal
from videobox_core_engine.yujin_creator_proposal_adapter import (
    MANUAL_FALLBACK,
    activate_yujin_media_projection,
    parse_and_project_yujin_creator_output,
)
from videobox_core_engine.yujin_creator_context import build_yujin_creator_context
from videobox_domain_models.yujin_creator_context import YujinCreatorContext
from videobox_storage.local_project_store import LocalProjectStore, sha256_file
from videobox_storage.postgres_compat import translate_sql


def _persisted_proposal_id(*, project_id: str, run_id: str) -> str:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        derive_yujin_persisted_proposal_id,
    )

    return derive_yujin_persisted_proposal_id(
        project_id=project_id,
        run_id=run_id,
    )


@pytest.fixture(autouse=True)
def _bounded_test_context(monkeypatch: pytest.MonkeyPatch) -> None:
    def build(**kwargs):
        payload = {
            "schema_version": "videobox.yujin-context.v1",
            "project_id": kwargs["project_id"],
            "session_id": kwargs["session_id"],
            "session_revision": kwargs["expected_session_revision"],
            "asset_index_revision": 0,
        }
        return SimpleNamespace(
            session_revision=kwargs["expected_session_revision"],
            asset_index_revision=0,
            model_dump=lambda **_: payload,
        )

    monkeypatch.setattr(
        "videobox_api.hermes_run_service.build_yujin_creator_context",
        build,
    )
    original_init = HermesRunService.__init__

    def test_init(self, *args, **kwargs):
        store = kwargs["store"]
        gateway = kwargs["gateway_client"]
        if not hasattr(store, "register_hermes_run_capabilities"):
            registrations: dict[str, dict] = {}

            def register_hermes_run_capabilities(**values):
                registrations[str(values["run_id"])] = values

            def get_expected_hermes_capability(**values):
                registered = registrations.get(str(values["run_id"]))
                if registered is None:
                    return None
                metadata = next(
                    item
                    for item in registered["capabilities"]
                    if item["action"] == values["action"]
                )
                return {
                    "capability_id": metadata["capability_id"],
                    "project_id": registered["project_id"],
                    "conversation_id": registered["conversation_id"],
                    "run_id": registered["run_id"],
                    "session_id": registered["session_id"],
                    "session_revision": registered[
                        "session_revision"
                    ],
                    "asset_index_revision": registered[
                        "asset_index_revision"
                    ],
                    "action": metadata["action"],
                    "state": "issued",
                    "expires_at": metadata["expires_at"],
                }

            store.register_hermes_run_capabilities = (
                register_hermes_run_capabilities
            )
            store.get_expected_hermes_capability = (
                get_expected_hermes_capability
            )
            store.consume_registered_hermes_capability = (
                lambda **_: "accepted"
            )
            store.record_hermes_capability_denial = lambda **values: values
            store.revoke_issued_hermes_capabilities = lambda **_: 0
        if not hasattr(gateway, "reserve_run"):
            async def reserve_run(**values):
                return _gateway_reservation(str(values["run_id"]))

            gateway.reserve_run = reserve_run
        if not hasattr(gateway, "attach_run_context"):
            async def attach_run_context(**values):
                prepare = getattr(gateway, "prepare_run", None)
                if prepare is not None:
                    await prepare(**values)

            gateway.attach_run_context = attach_run_context
        kwargs.setdefault(
            "capability_verifier",
            _CapabilityVerifier([]),
        )
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(HermesRunService, "__init__", test_init)


def _scope(tmp_path: Path, *, now=None):
    store = LocalProjectStore(tmp_path / "projects", now=now)
    project = store.bootstrap_project("hermes")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [
                {
                    "segment_id": "segment-1",
                    "start_sec": 0.0,
                    "end_sec": 5.0,
                    "caption_text": "첫 장면",
                }
            ],
            "history": [],
        },
    )
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conv",
    )
    return store, project.project_id, session["session_id"]


class _Gateway:
    def __init__(self, events=None) -> None:
        self.calls = 0
        self.events = events or [
            AgentGatewayEvent("text_delta", "안녕"),
            AgentGatewayEvent("run_completed", "안녕하세요"),
        ]
        self.preparations = 0

    async def prepare_run(self, **_):
        self.preparations += 1

    async def stream_run(self, **_):
        self.calls += 1
        for event in self.events:
            yield event


class _MemorySearchGateway(_Gateway):
    def __init__(self, *, search_delay: float = 0) -> None:
        super().__init__()
        self.search_delay = search_delay
        self.search_requests = []

    async def search_memory(self, request):
        self.search_requests.append(request)
        if self.search_delay:
            await asyncio.sleep(self.search_delay)
        return {"memories": []}


def _memory_test_context(**kwargs) -> YujinCreatorContext:
    return YujinCreatorContext.model_validate(
        {
            "schema_version": "videobox.yujin-context.v1",
            "project_id": kwargs["project_id"],
            "session_id": kwargs["session_id"],
            "session_revision": kwargs["expected_session_revision"],
            "asset_index_revision": 0,
            "timeline_id": "timeline",
            "timeline_version": "v001",
            "selected_script_id": None,
            "selected_segment_id": kwargs.get("selected_segment_id"),
            "segment_summaries": (),
            "media_candidates": (),
            "approved_tts_candidates": (),
            "memories": (),
            "timeline_summary": {
                "duration_sec": 0.0,
                "track_count": 0,
                "clip_count": 0,
                "gap_count": 0,
            },
            "supported_controls": (),
        }
    )


def _retrieval_row(project_id: str) -> dict[str, str]:
    return {
        "candidate_id": "candidate-a",
        "project_id": project_id,
        "conversation_id": "conv",
        "status": "approved",
        "storage_status": "stored",
        "memory_ref": "memory-a",
        "external_ref": "ext-" + "a" * 64,
        "text": "빠른 컷 편집을 선호합니다.",
        "category": "pacing",
    }


def test_memory_search_runs_once_only_after_new_owned_durable_dispatch(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    store.list_yujin_memory_retrieval_rows = (
        lambda **_: [_retrieval_row(project_id)]
    )
    gateway = _MemorySearchGateway()
    memory_service = YujinMemoryService(store=store, gateway=gateway)
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=_memory_test_context,
        memory_service=memory_service,
    )

    async def scenario() -> None:
        arguments = {
            "project_id": project_id,
            "session_id": session_id,
            "conversation_id": "conv",
            "client_message_id": "owned-new-dispatch",
            "text": "편집 템포를 추천해 줘",
        }
        run = await service.create_run(**arguments)
        await asyncio.wait_for(run.task, timeout=1)
        replay = await service.create_run(**arguments)
        assert replay is run
        with pytest.raises(
            ValueError,
            match="client_message_id_reused_with_different_content",
        ):
            await service.create_run(**{**arguments, "text": "위조 재생"})
        exact_action = await service.create_run(
            **{
                **arguments,
                "client_message_id": "memory-create-action",
                "text": "기억 후보 만들기",
            }
        )
        await asyncio.wait_for(exact_action.task, timeout=1)
        await service.shutdown()

    asyncio.run(scenario())

    assert len(gateway.search_requests) == 1
    assert gateway.search_requests[0].limit == 5
    assert gateway.calls == 2


def test_memory_search_timeout_does_not_block_run_or_manual_fallback(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    store.list_yujin_memory_retrieval_rows = (
        lambda **_: [_retrieval_row(project_id)]
    )
    gateway = _MemorySearchGateway(search_delay=1)
    memory_service = YujinMemoryService(store=store, gateway=gateway)
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=_memory_test_context,
        memory_service=memory_service,
    )

    async def scenario() -> float:
        started = asyncio.get_running_loop().time()
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="timeout-dispatch",
            text="편집 템포를 추천해 줘",
        )
        elapsed = asyncio.get_running_loop().time() - started
        await asyncio.wait_for(run.task, timeout=1)
        await service.shutdown()
        return elapsed

    elapsed = asyncio.run(scenario())

    assert elapsed < 0.9
    assert len(gateway.search_requests) == 1
    assert gateway.calls == 1


class _BlockingGateway:
    def __init__(self) -> None:
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.preparations = 0
        self.cancellations: list[str] = []

    async def prepare_run(self, **_):
        self.preparations += 1

    async def stream_run(self, **_):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        yield AgentGatewayEvent("run_completed", "answer")

    async def cancel_run(self, *, run_id: str):
        self.cancellations.append(run_id)
        await asyncio.sleep(0)
        return True


class _ThreadBlockedStore:
    def __init__(self) -> None:
        self.begin_entered = threading.Event()
        self.begin_release = threading.Event()
        self.completions: list[dict] = []

    def begin_director_hermes_run(self, **kwargs):
        self.begin_entered.set()
        assert self.begin_release.wait(timeout=3)
        return {
            "run_id": str(kwargs["client_message_id"]),
            "status": "pending",
            "owner_token": "owner",
            "dispatch": True,
        }

    def complete_director_hermes_run(self, **kwargs):
        self.completions.append(kwargs)
        return True


def _gateway_reservation(run_id: str) -> AgentGatewayReservation:
    return AgentGatewayReservation.model_validate(
        {
            "run_id": run_id,
            "attach_context": "a" * 64,
            "expires_in_seconds": 30,
            "read_capability_token": "header.read.signature",
            "capabilities": (
                {
                    "capability_id": f"{run_id}-cap-read",
                    "action": "read_context",
                    "expires_at": 2_000_000_300,
                },
                {
                    "capability_id": f"{run_id}-cap-publish",
                    "action": "publish_proposal",
                    "expires_at": 2_000_000_300,
                },
            ),
        }
    )


def _complete_director_hermes_run_with_publish(
    store,
    *,
    proposal: DirectorProposal,
    **completion,
):
    project_id = str(completion["project_id"])
    run_id = str(completion["run_id"])
    durable = store.get_director_hermes_run(
        project_id=project_id,
        run_id=run_id,
    )
    now_epoch = int(store._clock().timestamp())
    read_id = f"{run_id}-test-read"
    publish_id = f"{run_id}-test-publish"
    store.register_hermes_run_capabilities(
        project_id=project_id,
        conversation_id=str(durable["conversation_id"]),
        run_id=run_id,
        session_id=str(durable["session_id"]),
        session_revision=proposal.base_session_revision,
        asset_index_revision=proposal.asset_index_revision,
        capabilities=(
            {
                "capability_id": read_id,
                "action": "read_context",
                "expires_at": now_epoch + 300,
            },
            {
                "capability_id": publish_id,
                "action": "publish_proposal",
                "expires_at": now_epoch + 300,
            },
        ),
    )
    return store.complete_director_hermes_run(
        **completion,
        proposal=proposal,
        verified_publish_capability={
            "capability_id": publish_id,
            "project_id": project_id,
            "conversation_id": str(durable["conversation_id"]),
            "run_id": run_id,
            "session_id": str(durable["session_id"]),
            "session_revision": proposal.base_session_revision,
            "asset_index_revision": proposal.asset_index_revision,
            "action": "publish_proposal",
            "issued_at": now_epoch,
            "not_before": now_epoch,
            "expires_at": now_epoch + 300,
        },
    )


class _CapabilityAdmissionStore:
    def __init__(self, calls: list[str], *, fail_at: str | None = None) -> None:
        self.calls = calls
        self.fail_at = fail_at
        self.completions: list[dict] = []
        self.denials: list[dict] = []
        self.registrations: dict[str, dict] = {}
        self.states: dict[str, str] = {}

    def begin_director_hermes_run(self, **kwargs):
        self.calls.append("begin")
        return {
            "run_id": str(kwargs["client_message_id"]),
            "status": "pending",
            "owner_token": "owner",
            "dispatch": True,
        }

    def register_hermes_run_capabilities(self, **kwargs):
        self.calls.append("register")
        if self.fail_at == "register":
            raise OSError("registration unavailable")
        self.registrations[str(kwargs["run_id"])] = kwargs
        for capability in kwargs["capabilities"]:
            self.states[str(capability["capability_id"])] = "issued"

    def get_expected_hermes_capability(self, **kwargs):
        self.calls.append("expected")
        if self.fail_at == "expected":
            return None
        registered = self.registrations[str(kwargs["run_id"])]
        metadata = next(
            capability
            for capability in registered["capabilities"]
            if capability["action"] == kwargs["action"]
        )
        return {
            "capability_id": metadata["capability_id"],
            "project_id": kwargs["project_id"],
            "conversation_id": kwargs["conversation_id"],
            "run_id": kwargs["run_id"],
            "session_id": registered["session_id"],
            "session_revision": registered["session_revision"],
            "asset_index_revision": registered["asset_index_revision"],
            "action": "read_context",
            "state": "issued",
            "expires_at": metadata["expires_at"],
        }

    def consume_registered_hermes_capability(self, **kwargs):
        self.calls.append("consume")
        if self.fail_at == "consume":
            return "hermes_capability_replayed"
        if self.fail_at == "scope":
            return "hermes_capability_scope_forbidden"
        if self.fail_at == "audit":
            raise OSError("capability audit unavailable")
        self.states[str(kwargs["capability_id"])] = "consumed"
        return "accepted"

    def record_hermes_capability_denial(self, **kwargs):
        self.calls.append("denial")
        self.denials.append(kwargs)
        return kwargs

    def revoke_issued_hermes_capabilities(self, **_):
        self.calls.append("revoke")
        revoked = 0
        for capability_id, state in tuple(self.states.items()):
            if state == "issued":
                self.states[capability_id] = "revoked"
                revoked += 1
        return revoked

    def complete_director_hermes_run(self, **kwargs):
        self.calls.append("blocked")
        self.completions.append(kwargs)
        for capability_id, state in tuple(self.states.items()):
            if state == "issued":
                self.states[capability_id] = "revoked"
        return True


class _CapabilityGateway:
    def __init__(
        self,
        calls: list[str],
        *,
        fail_at: str | None = None,
        block_stream: bool = False,
    ) -> None:
        self.calls = calls
        self.fail_at = fail_at
        self.block_stream = block_stream
        self.stream_entered = asyncio.Event()
        self.stream_release = asyncio.Event()
        self.provider_calls = 0
        self.releases: list[str] = []
        self.cancellations: list[str] = []

    async def reserve_run(self, **kwargs):
        self.calls.append("reserve")
        if self.fail_at == "reserve":
            raise AgentGatewayUnavailable("agent_gateway_unavailable")
        if self.fail_at == "malformed":
            return SimpleNamespace(run_id=str(kwargs["run_id"]))
        return _gateway_reservation(str(kwargs["run_id"]))

    async def attach_run_context(self, **_):
        self.calls.append("attach")
        if self.fail_at == "attach":
            raise AgentGatewayUnavailable("agent_gateway_unavailable")

    async def stream_run(self, **_):
        self.calls.append("dispatch")
        self.provider_calls += 1
        self.stream_entered.set()
        if self.block_stream:
            await self.stream_release.wait()
        yield AgentGatewayEvent("run_completed", "answer")

    async def release_run(self, *, run_id: str):
        self.calls.append("release")
        self.releases.append(run_id)

    async def cancel_run(self, *, run_id: str):
        self.calls.append("cancel")
        self.cancellations.append(run_id)
        self.stream_release.set()


class _CapabilityVerifier:
    def __init__(
        self,
        calls: list[str],
        *,
        fail: bool = False,
        unavailable: bool = False,
        fail_action: str | None = None,
        wrong_scope_action: str | None = None,
    ) -> None:
        self.calls = calls
        self.fail = fail
        self.unavailable = unavailable
        self.fail_action = fail_action
        self.wrong_scope_action = wrong_scope_action

    def verify(self, token: str, *, expected):
        self.calls.append("verify")
        if self.unavailable:
            raise HermesVerifierUnavailableError(
                "private verifier clock unavailable"
            )
        if self.fail or expected.action == self.fail_action:
            raise HermesCapabilityError(
                "hermes_capability_signature_invalid"
            )
        return SimpleNamespace(
            capability_id=expected.capability_id,
            project_id=(
                "wrong-project"
                if expected.action == self.wrong_scope_action
                else expected.project_id
            ),
            conversation_id=expected.conversation_id,
            run_id=expected.run_id,
            session_id=expected.session_id,
            session_revision=expected.session_revision,
            asset_index_revision=expected.asset_index_revision,
            action=expected.action,
            issued_at=2_000_000_000,
            not_before=2_000_000_000,
            expires_at=2_000_000_300,
        )


class _RegistrationBarrierStore(_CapabilityAdmissionStore):
    def __init__(self, calls: list[str]) -> None:
        super().__init__(calls)
        self.registration_entered = threading.Event()
        self.registration_release = threading.Event()

    def register_hermes_run_capabilities(self, **kwargs):
        super().register_hermes_run_capabilities(**kwargs)
        self.registration_entered.set()
        assert self.registration_release.wait(timeout=3)


class _TwoRegistrationBarrierStore(_CapabilityAdmissionStore):
    def __init__(self, calls: list[str]) -> None:
        super().__init__(calls)
        self._registration_count = 0
        self._registration_lock = threading.Lock()
        self.registrations_entered = threading.Event()
        self.registration_release = threading.Event()

    def register_hermes_run_capabilities(self, **kwargs):
        super().register_hermes_run_capabilities(**kwargs)
        with self._registration_lock:
            self._registration_count += 1
            if self._registration_count == 2:
                self.registrations_entered.set()
        assert self.registration_release.wait(timeout=3)


def test_admission_capability_order_precedes_dispatch() -> None:
    calls: list[str] = []
    store = _CapabilityAdmissionStore(calls)
    gateway = _CapabilityGateway(calls)
    verifier = _CapabilityVerifier(calls)
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        capability_verifier=verifier,
    )

    async def scenario() -> None:
        run = await service.create_run(
            project_id="p",
            session_id="s",
            conversation_id="c",
            client_message_id="ordered",
            text="q",
        )
        await run.task
        await service.shutdown()

    asyncio.run(scenario())

    assert calls[:8] == [
        "begin",
        "reserve",
        "register",
        "expected",
        "verify",
        "consume",
        "attach",
        "dispatch",
    ]
    assert gateway.provider_calls == 1


@pytest.mark.parametrize("audit_fails", (False, True))
def test_missing_capability_verifier_audits_unavailable_before_dispatch(
    audit_fails: bool,
) -> None:
    calls: list[str] = []
    store = _CapabilityAdmissionStore(calls)
    gateway = _CapabilityGateway(calls)
    if audit_fails:
        def fail_denial(**_kwargs):
            calls.append("denial")
            raise OSError("private capability audit failure")

        store.record_hermes_capability_denial = fail_denial
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        capability_verifier=None,
    )

    async def scenario() -> None:
        with pytest.raises(
            HermesContextPreparationUnavailable,
            match="^hermes_context_preparation_unavailable$",
        ):
            await service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id=f"missing-verifier-{audit_fails}",
                text="q",
            )

    asyncio.run(scenario())

    assert calls[:3] == ["begin", "reserve", "denial"]
    assert "register" not in calls
    assert "expected" not in calls
    assert "verify" not in calls
    assert "consume" not in calls
    assert "attach" not in calls
    assert gateway.provider_calls == 0
    assert len(store.completions) == 1
    assert store.completions[0]["status"] == "blocked"
    if audit_fails:
        assert store.denials == []
    else:
        assert store.denials == [
            {
                "project_id": "p",
                "conversation_id": "c",
                "run_id": f"missing-verifier-{audit_fails}",
                "action": "read_context",
                "reason": "hermes_capability_unavailable",
                "use_registered_capability_id": False,
            }
        ]


@pytest.mark.parametrize(
    "fail_at",
    [
        "reserve",
        "malformed",
        "register",
        "expected",
        "verify",
        "verify_unavailable",
        "consume",
        "scope",
        "audit",
        "attach",
    ],
)
def test_capability_admission_failure_releases_revokes_and_blocks_without_dispatch(
    fail_at: str,
) -> None:
    calls: list[str] = []
    store = _CapabilityAdmissionStore(calls, fail_at=fail_at)
    gateway = _CapabilityGateway(
        calls,
        fail_at=(
            fail_at
            if fail_at in {"reserve", "malformed", "attach"}
            else None
        ),
    )
    verifier = _CapabilityVerifier(
        calls,
        fail=fail_at == "verify",
        unavailable=fail_at == "verify_unavailable",
    )
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        capability_verifier=verifier,
    )

    async def scenario() -> None:
        with pytest.raises(Exception):
            await service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id=f"failed-{fail_at}",
                text="q",
            )

    asyncio.run(scenario())

    assert gateway.provider_calls == 0
    assert gateway.releases == [f"failed-{fail_at}"]
    assert calls.count("revoke") == 0
    assert "blocked" in calls
    assert set(store.states.values()).issubset({"consumed", "revoked"})
    assert len(store.completions) == 1
    assert store.completions[0]["status"] == "blocked"
    assert "Manual Director remains available" in store.completions[0][
        "assistant_text"
    ]
    if fail_at in {"verify", "verify_unavailable"}:
        assert len(store.denials) == 1
        assert store.denials[0]["reason"] == (
            "hermes_capability_unavailable"
            if fail_at == "verify_unavailable"
            else "hermes_capability_signature_invalid"
        )


def test_read_context_registration_race_blocks_before_attach_and_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    store, project_id, session_id = _scope(tmp_path)
    gateway = _CapabilityGateway(calls)
    original_register = store.register_hermes_run_capabilities

    def register_then_advance_session(**kwargs):
        original_register(**kwargs)
        current = store.get_editing_session(
            project_id=project_id,
            session_id=session_id,
        )
        store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload={
                "segments": current["segments"],
                "history": current["history"],
            },
            expected_revision=current["session_revision"],
        )

    monkeypatch.setattr(
        store,
        "register_hermes_run_capabilities",
        register_then_advance_session,
    )
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        capability_verifier=_CapabilityVerifier(calls),
    )

    async def scenario() -> None:
        with pytest.raises(
            HermesContextPreparationUnavailable,
            match="^hermes_context_preparation_unavailable$",
        ):
            await service.create_run(
                project_id=project_id,
                session_id=session_id,
                conversation_id="conv",
                client_message_id="read-context-session-race",
                text="q",
                expected_session_revision=1,
            )

    asyncio.run(scenario())

    assert "attach" not in calls
    assert "dispatch" not in calls
    assert gateway.provider_calls == 0
    assert len(gateway.releases) == 1
    assert store.list_director_proposals(project_id) == []
    session = store.get_editing_session(
        project_id=project_id,
        session_id=session_id,
    )
    assert session["session_revision"] == 2
    assert session["history"] == []
    messages = store.list_director_messages(
        project_id=project_id,
        conversation_id="conv",
    )
    assert "Manual Director remains available" in messages[-1]["text"]
    with store._connection(project_id) as connection:
        states = {
            str(row["state"])
            for row in connection.execute(
                "SELECT state FROM hermes_capability_ledger "
                "WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        }
        denials = [
            str(row["reason"])
            for row in connection.execute(
                "SELECT reason FROM hermes_capability_audit "
                "WHERE project_id = ? AND outcome = 'denied'",
                (project_id,),
            ).fetchall()
        ]
    assert states == {"revoked"}
    assert denials == ["hermes_capability_scope_forbidden"]


def test_cancelled_admission_after_issuance_releases_revokes_and_blocks() -> None:
    calls: list[str] = []
    store = _RegistrationBarrierStore(calls)
    gateway = _CapabilityGateway(calls)
    verifier = _CapabilityVerifier(calls)
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        capability_verifier=verifier,
    )

    async def scenario() -> None:
        create_task = asyncio.create_task(
            service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id="cancelled-admission",
                text="q",
            )
        )
        assert await asyncio.to_thread(
            store.registration_entered.wait,
            1,
        )
        async with service.reconciliation_scope() as excluded:
            assert excluded == {"p": ("cancelled-admission",)}
        create_task.cancel()
        await asyncio.sleep(0)
        store.registration_release.set()
        with pytest.raises(asyncio.CancelledError):
            await create_task

    asyncio.run(scenario())

    assert calls[:3] == ["begin", "reserve", "register"]
    assert "expected" not in calls
    assert "verify" not in calls
    assert "consume" not in calls
    assert "attach" not in calls
    assert gateway.provider_calls == 0
    assert gateway.releases == ["cancelled-admission"]
    assert calls.count("revoke") == 0
    assert set(store.states.values()) == {"revoked"}
    assert len(store.completions) == 1
    assert store.completions[0]["status"] == "blocked"


def test_reconciliation_scope_blocks_only_new_durable_begin() -> None:
    store = _ThreadBlockedStore()
    gateway = _Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)
    context_entered = threading.Event()
    context_release = threading.Event()
    context_finished = threading.Event()

    def build_context(**kwargs):
        context_entered.set()
        assert context_release.wait(timeout=3)
        context_finished.set()
        return SimpleNamespace(
            session_revision=kwargs["expected_session_revision"],
            asset_index_revision=0,
            model_dump=lambda **_: {},
        )

    service._context_builder = build_context

    async def scenario() -> None:
        async with service.reconciliation_scope() as excluded:
            assert excluded == {}
            create = asyncio.create_task(
                service.create_run(
                    project_id="p",
                    session_id="s",
                    conversation_id="c",
                    client_message_id="after-recovery",
                    text="q",
                )
            )
            assert await asyncio.to_thread(context_entered.wait, 1)
            assert service.diagnostics()["admissions"] == 1
            context_release.set()
            assert await asyncio.to_thread(context_finished.wait, 1)
            assert not store.begin_entered.is_set()
            store.begin_release.set()
        run = await asyncio.wait_for(create, timeout=1)
        assert run.task is not None
        await asyncio.wait_for(run.task, timeout=1)
        await asyncio.wait_for(service.shutdown(), timeout=1)

    asyncio.run(scenario())
    assert gateway.calls == 1


def test_reconciliation_scope_duplicate_cancel_and_shutdown_do_not_deadlock() -> None:
    store = _ThreadBlockedStore()
    store.begin_release.set()
    gateway = _Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario() -> None:
        arguments = {
            "project_id": "p",
            "session_id": "s",
            "conversation_id": "c",
            "client_message_id": "shared-during-recovery",
            "text": "q",
        }
        async with service.reconciliation_scope():
            cancelled = asyncio.create_task(service.create_run(**arguments))
            remaining = asyncio.create_task(service.create_run(**arguments))
            await asyncio.sleep(0)
            cancelled.cancel()
            shutdown = asyncio.create_task(service.shutdown())
            await asyncio.sleep(0)
            assert not store.begin_entered.is_set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(cancelled, timeout=1)
        run = await asyncio.wait_for(remaining, timeout=1)
        await asyncio.wait_for(shutdown, timeout=1)
        assert run.terminal is True
        assert service.diagnostics()["admissions"] == 0

    asyncio.run(scenario())
    assert gateway.calls == 0


def test_reconciliation_scope_groups_same_admission_run_id_by_project() -> None:
    calls: list[str] = []
    store = _TwoRegistrationBarrierStore(calls)
    gateway = _CapabilityGateway(calls)
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        capability_verifier=_CapabilityVerifier(calls),
    )

    async def scenario() -> None:
        shared = {
            "session_id": "s",
            "conversation_id": "c",
            "client_message_id": "same-run-id",
            "text": "q",
        }
        first = asyncio.create_task(
            service.create_run(project_id="project-a", **shared)
        )
        second = asyncio.create_task(
            service.create_run(project_id="project-b", **shared)
        )
        assert await asyncio.to_thread(
            store.registrations_entered.wait,
            1,
        )
        async with service.reconciliation_scope() as exclusions:
            assert exclusions == {
                "project-a": ("same-run-id",),
                "project-b": ("same-run-id",),
            }
        first.cancel()
        second.cancel()
        store.registration_release.set()
        results = await asyncio.wait_for(
            asyncio.gather(first, second, return_exceptions=True),
            timeout=1,
        )
        assert all(
            isinstance(result, asyncio.CancelledError)
            for result in results
        )
        await asyncio.wait_for(service.shutdown(), timeout=1)

    asyncio.run(scenario())


def test_recovery_holds_durable_begin_fence_through_store_reconciliation() -> None:
    class Store(_ThreadBlockedStore):
        def __init__(self) -> None:
            super().__init__()
            self.recovery_entered = threading.Event()
            self.recovery_release = threading.Event()

        def list_projects(self):
            self.recovery_entered.set()
            assert self.recovery_release.wait(timeout=3)
            return []

    store = Store()
    store.begin_release.set()
    service = HermesRunService(store=store, gateway_client=_Gateway())
    app = SimpleNamespace(
        state=SimpleNamespace(store=store, hermes_run_service=service)
    )

    async def scenario() -> None:
        recovery = asyncio.create_task(_recover_hermes_runs(app))
        assert await asyncio.to_thread(store.recovery_entered.wait, 1)
        create = asyncio.create_task(
            service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id="after-store-recovery",
                text="q",
            )
        )
        await asyncio.sleep(0)
        assert not store.begin_entered.is_set()
        store.recovery_release.set()
        await asyncio.wait_for(recovery, timeout=1)
        run = await asyncio.wait_for(create, timeout=1)
        assert run.task is not None
        await asyncio.wait_for(run.task, timeout=1)
        await asyncio.wait_for(service.shutdown(), timeout=1)

    asyncio.run(scenario())


def test_reconciliation_scope_absorbs_repeated_cancel_until_recovery_thread_ends() -> None:
    class Store(_ThreadBlockedStore):
        def __init__(self) -> None:
            super().__init__()
            self.recovery_entered = threading.Event()
            self.recovery_release = threading.Event()

        def list_projects(self):
            return [{"project_id": "p"}]

        def recover_interrupted_director_hermes_runs(self, **_):
            self.recovery_entered.set()
            assert self.recovery_release.wait(timeout=3)
            return []

    store = Store()
    store.begin_release.set()
    service = HermesRunService(store=store, gateway_client=_Gateway())
    app = SimpleNamespace(
        state=SimpleNamespace(store=store, hermes_run_service=service)
    )

    async def scenario() -> tuple[bool, bool]:
        owner = asyncio.create_task(_recover_hermes_runs(app))
        assert await asyncio.to_thread(store.recovery_entered.wait, 1)
        create = asyncio.create_task(
            service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id="after-repeated-cancel",
                text="q",
            )
        )
        await asyncio.sleep(0)
        owner.cancel()
        await asyncio.sleep(0)
        owner.cancel()
        await asyncio.sleep(0.05)
        begin_before_release = store.begin_entered.is_set()
        owner_done_before_release = owner.done()
        store.recovery_release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(owner, timeout=1)
        run = await asyncio.wait_for(create, timeout=1)
        assert run.task is not None
        await asyncio.wait_for(run.task, timeout=1)
        assert not any(
            task.get_name() == "videobox-hermes-reconciliation"
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task()
        )
        await asyncio.wait_for(service.shutdown(), timeout=1)
        return begin_before_release, owner_done_before_release

    begin_before_release, owner_done_before_release = asyncio.run(scenario())
    assert begin_before_release is False
    assert owner_done_before_release is False


def test_reconciliation_scope_propagates_recovery_error_without_orphan_task() -> None:
    class Store(_ThreadBlockedStore):
        def list_projects(self):
            raise OSError("recovery ledger unavailable")

    store = Store()
    service = HermesRunService(store=store, gateway_client=_Gateway())
    app = SimpleNamespace(
        state=SimpleNamespace(store=store, hermes_run_service=service)
    )

    async def scenario() -> None:
        with pytest.raises(OSError, match="recovery ledger unavailable"):
            await _recover_hermes_runs(app)
        assert not any(
            task.get_name() == "videobox-hermes-reconciliation"
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task()
        )
        await asyncio.wait_for(service.shutdown(), timeout=1)

    asyncio.run(scenario())


def test_reconciliation_scope_survives_lifespan_cancel_until_recovery_thread_ends() -> None:
    class Store(_ThreadBlockedStore):
        def __init__(self) -> None:
            super().__init__()
            self.recovery_calls = 0
            self.recovery_entered = threading.Event()
            self.recovery_release = threading.Event()

        def list_projects(self):
            return [{"project_id": "p"}]

        def recover_interrupted_director_hermes_runs(self, **_):
            self.recovery_calls += 1
            if self.recovery_calls >= 2:
                self.recovery_entered.set()
                assert self.recovery_release.wait(timeout=3)
            return []

        def recover_orphaned_media_analysis_jobs(self, **_):
            return []

        def prune_director_hermes_run_events(self, **_):
            return 0

    store = Store()
    store.begin_release.set()
    service = HermesRunService(store=store, gateway_client=_Gateway())
    app = SimpleNamespace(
        state=SimpleNamespace(
            store=store,
            hermes_run_service=service,
            media_analysis_dispatcher=None,
            media_analysis_poll_interval_seconds=0.01,
        )
    )

    async def scenario() -> None:
        lifespan = _media_analysis_lifespan(app)
        await lifespan.__aenter__()
        assert await asyncio.to_thread(store.recovery_entered.wait, 1)
        create = asyncio.create_task(
            service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id="cancelled-lifespan-recovery",
                text="q",
            )
        )
        await asyncio.sleep(0)
        assert service.diagnostics()["admissions"] == 1
        close = asyncio.create_task(lifespan.__aexit__(None, None, None))
        await asyncio.sleep(0.05)
        try:
            assert not store.begin_entered.is_set()
            assert not close.done()
        finally:
            store.recovery_release.set()
        await asyncio.wait_for(close, timeout=1)
        run = await asyncio.wait_for(create, timeout=1)
        assert run.terminal is True

    asyncio.run(scenario())


def test_recover_interrupted_reconciliation_scope_is_project_scoped_for_same_run_id(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path / "projects")

    def project_scope(name: str):
        project = store.bootstrap_project(name)
        session = store.save_editing_session(
            project_id=project.project_id,
            timeline_id=f"timeline-{name}",
            session_payload={"segments": [], "history": []},
        )
        conversation_id = f"conversation-{name}"
        store.create_director_conversation(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
        )
        return project.project_id, session, conversation_id

    project_a, session_a, conversation_a = project_scope("live-a")
    project_b, session_b, conversation_b = project_scope("orphan-b")
    gateway = _BlockingGateway()
    service = HermesRunService(store=store, gateway_client=gateway)
    now_epoch = int(datetime.now(UTC).timestamp())

    async def scenario() -> tuple[str, str, set[str], set[str]]:
        live = await service.create_run(
            project_id=project_a,
            session_id=session_a["session_id"],
            conversation_id=conversation_a,
            client_message_id="live-a",
            text="q",
            expected_session_revision=session_a["session_revision"],
        )
        await asyncio.wait_for(gateway.entered.wait(), timeout=1)
        orphan = store.begin_director_hermes_run(
            project_id=project_b,
            session_id=session_b["session_id"],
            conversation_id=conversation_b,
            client_message_id="orphan-b",
            user_text="q",
            expected_session_revision=session_b["session_revision"],
            expected_asset_index_revision=0,
        )
        connection = store._connection(project_b)
        try:
            connection.execute(
                "UPDATE director_hermes_runs SET run_id = ? "
                "WHERE project_id = ? AND run_id = ?",
                (live.run_id, project_b, orphan["run_id"]),
            )
            connection.commit()
        finally:
            connection.close()
        store.register_hermes_run_capabilities(
            project_id=project_b,
            conversation_id=conversation_b,
            run_id=live.run_id,
            session_id=session_b["session_id"],
            session_revision=session_b["session_revision"],
            asset_index_revision=0,
            capabilities=(
                {
                    "capability_id": "orphan-b-read",
                    "action": "read_context",
                    "expires_at": now_epoch + 300,
                },
                {
                    "capability_id": "orphan-b-publish",
                    "action": "publish_proposal",
                    "expires_at": now_epoch + 300,
                },
            ),
        )
        app = SimpleNamespace(
            state=SimpleNamespace(
                store=store,
                hermes_run_service=service,
            )
        )
        await _recover_hermes_runs(app)
        live_status = store.get_director_hermes_run(
            project_id=project_a,
            run_id=live.run_id,
        )["status"]
        orphan_status = store.get_director_hermes_run(
            project_id=project_b,
            run_id=live.run_id,
        )["status"]

        def states(project_id: str) -> set[str]:
            scoped = store._connection(project_id)
            try:
                return {
                    str(row["state"])
                    for row in scoped.execute(
                        "SELECT state FROM hermes_capability_ledger "
                        "WHERE project_id = ? AND run_id = ?",
                        (project_id, live.run_id),
                    ).fetchall()
                }
            finally:
                scoped.close()

        live_states = states(project_a)
        orphan_states = states(project_b)
        await service.shutdown()
        return live_status, orphan_status, live_states, orphan_states

    live_status, orphan_status, live_states, orphan_states = asyncio.run(
        scenario()
    )
    assert live_status in {"pending", "streaming"}
    assert orphan_status == "interrupted"
    assert live_states == {"consumed", "issued"}
    assert orphan_states == {"revoked"}
    assert gateway.calls == 1


def test_public_cancel_revokes_only_the_unconsumed_publish_capability() -> None:
    calls: list[str] = []
    store = _CapabilityAdmissionStore(calls)
    gateway = _CapabilityGateway(calls, block_stream=True)
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        capability_verifier=_CapabilityVerifier(calls),
    )

    async def scenario() -> None:
        run = await service.create_run(
            project_id="p",
            session_id="s",
            conversation_id="c",
            client_message_id="public-cancel",
            text="q",
        )
        await gateway.stream_entered.wait()
        await service.cancel(
            run.run_id,
            project_id="p",
            conversation_id="c",
        )
        await asyncio.gather(run.task, return_exceptions=True)
        await service.shutdown()

    asyncio.run(scenario())

    assert gateway.provider_calls == 1
    assert gateway.cancellations == ["public-cancel"]
    assert store.states["public-cancel-cap-read"] == "consumed"
    assert store.states["public-cancel-cap-publish"] == "revoked"
    assert calls.count("revoke") == 0
    assert len(store.completions) == 1
    assert store.completions[0]["status"] == "interrupted"


def test_run_persists_user_before_dispatch_and_final_before_terminal_event(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    gateway = _Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="client-1",
            text="질문",
        )
        assert [
            item["role"]
            for item in store.list_director_messages(
                project_id=project_id, conversation_id="conv"
            )
        ] == ["user"]
        await run.task
        events = [event async for event in service.subscribe(run.run_id)]
        retry = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="client-1",
            text="질문",
        )
        return run, retry, events

    run, retry, events = asyncio.run(scenario())
    assert retry.run_id == run.run_id
    assert gateway.calls == 1
    assert [event.event_type for event in events] == [
        "run_started",
        "text_delta",
        "run_completed",
    ]
    messages = store.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )
    assert [(item["role"], item["text"]) for item in messages] == [
        ("user", "질문"),
        ("assistant", "안녕하세요"),
    ]
    assert messages[1]["metadata"]["hermes_status"] == "completed"


def test_completed_run_replays_from_store_after_process_restart(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    service = HermesRunService(store=store, gateway_client=_Gateway())

    async def finish():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="restart-replay",
            text="질문",
        )
        await run.task
        return run.run_id

    run_id = asyncio.run(finish())
    restarted = HermesRunService(store=store, gateway_client=_Gateway())

    async def replay():
        return [
            event
            async for event in restarted.subscribe(
                run_id,
                project_id=project_id,
                conversation_id="conv",
                after_event_id=1,
            )
        ]

    events = asyncio.run(replay())
    assert [event.event_type for event in events] == [
        "text_delta",
        "run_completed",
    ]
    assert [event.event_id for event in events] == [2, 3]


def test_closing_one_subscription_does_not_cancel_provider_run(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    gateway = _BlockingGateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="disconnect",
            text="질문",
        )
        await gateway.entered.wait()
        subscription = service.subscribe(run.run_id)
        assert (await anext(subscription)).event_type == "run_started"
        await subscription.aclose()
        durable = store.get_director_hermes_run(
            project_id=project_id, run_id=run.run_id
        )
        gateway.release.set()
        await run.task
        return durable, [
            event async for event in service.subscribe(run.run_id)
        ]

    durable, replay = asyncio.run(scenario())
    assert durable["status"] in {"pending", "streaming"}
    assert replay[-1].event_type == "run_completed"


def test_explicit_cancel_interrupts_upstream_then_persists_interrupted_once(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    gateway = _BlockingGateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="cancel-streaming",
            text="질문",
        )
        await gateway.entered.wait()
        await asyncio.gather(
            service.cancel(
                run.run_id,
                project_id=project_id,
                conversation_id="conv",
            ),
            service.cancel(
                run.run_id,
                project_id=project_id,
                conversation_id="conv",
            ),
        )
        await service.cancel(
            run.run_id,
            project_id=project_id,
            conversation_id="conv",
        )
        return run, [
            event
            async for event in service.subscribe(
                run.run_id,
                project_id=project_id,
                conversation_id="conv",
            )
        ]

    run, events = asyncio.run(scenario())
    durable = store.get_director_hermes_run(
        project_id=project_id, run_id=run.run_id
    )
    assert gateway.cancellations == [run.run_id]
    assert durable["status"] == "interrupted"
    assert events[-1].event_type == "blocked"
    assert events[-1].retryable is True


def test_explicit_cancel_intent_wins_inline_provider_blocked_terminal(
    tmp_path: Path,
) -> None:
    class InlineBlockedGateway:
        def __init__(self) -> None:
            self.calls = 0
            self.preparations = 0
            self.cancellations: list[str] = []
            self.entered = asyncio.Event()
            self.interrupted = asyncio.Event()
            self.service: HermesRunService | None = None

        async def prepare_run(self, **_) -> None:
            self.preparations += 1

        async def stream_run(self, **_):
            self.calls += 1
            self.entered.set()
            await self.interrupted.wait()
            yield AgentGatewayEvent("blocked", "")

        async def cancel_run(self, *, run_id: str) -> bool:
            self.cancellations.append(run_id)
            self.interrupted.set()
            assert self.service is not None
            while not self.service.get_run(run_id).terminal:
                await asyncio.sleep(0)
            return True

    store, project_id, session_id = _scope(tmp_path)
    gateway = InlineBlockedGateway()
    service = HermesRunService(store=store, gateway_client=gateway)
    gateway.service = service

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="cancel-inline-blocked",
            text="질문",
        )
        await gateway.entered.wait()
        await service.cancel(
            run.run_id,
            project_id=project_id,
            conversation_id="conv",
        )
        await service.cancel(
            run.run_id,
            project_id=project_id,
            conversation_id="conv",
        )
        return run, [
            event
            async for event in service.subscribe(
                run.run_id,
                project_id=project_id,
                conversation_id="conv",
            )
        ]

    run, events = asyncio.run(scenario())
    durable = store.get_director_hermes_run(
        project_id=project_id,
        run_id=run.run_id,
    )
    assert durable["status"] == "interrupted"
    assert gateway.cancellations == [run.run_id]
    assert events[0].event_type == "run_started"
    terminal_events = [
        event
        for event in events
        if event.event_type in {"blocked", "run_completed"}
    ]
    assert [event.event_type for event in terminal_events] == ["blocked"]
    assert terminal_events[0].retryable is True


def test_cancel_queued_run_before_upstream_entry_and_completed_run_is_noop(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    gateway = _BlockingGateway()
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        max_active=1,
        max_queue=1,
    )

    async def scenario():
        active = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="cancel-active-slot",
            text="첫 질문",
        )
        await gateway.entered.wait()
        queued = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="cancel-before-upstream-entry",
            text="둘째 질문",
        )
        assert gateway.calls == 1
        await service.cancel(
            queued.run_id,
            project_id=project_id,
            conversation_id="conv",
        )
        gateway.release.set()
        await active.task
        await service.cancel(
            active.run_id,
            project_id=project_id,
            conversation_id="conv",
        )
        return active, queued

    active, queued = asyncio.run(scenario())
    assert gateway.calls == 1
    assert gateway.cancellations == [queued.run_id]
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=queued.run_id,
    )["status"] == "interrupted"
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=active.run_id,
    )["status"] == "completed"


def test_explicit_retry_links_new_run_and_rejects_active_or_completed_source(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    interrupted = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="retry-source",
        user_text="다시 해 줘",
        expected_session_revision=1,
        expected_asset_index_revision=0,
    )
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=interrupted["run_id"],
        owner_token=interrupted["owner_token"],
        status="interrupted",
        assistant_text="중단됐어요.",
        public_text="",
        retryable=True,
    )
    active = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="retry-active",
        user_text="진행 중",
        expected_session_revision=1,
        expected_asset_index_revision=0,
    )
    completed = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="retry-completed",
        user_text="완료됨",
        expected_session_revision=1,
        expected_asset_index_revision=0,
    )
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=completed["run_id"],
        owner_token=completed["owner_token"],
        status="completed",
        assistant_text="완료",
        public_text="",
        retryable=False,
    )
    blocked = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="retry-blocked",
        user_text="차단됨",
        expected_session_revision=1,
        expected_asset_index_revision=0,
    )
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=blocked["run_id"],
        owner_token=blocked["owner_token"],
        status="blocked",
        assistant_text="차단",
        public_text="",
        retryable=True,
    )
    gateway = _Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario():
        before_wrong_scope = store.list_director_messages(
            project_id=project_id,
            conversation_id="conv",
        )
        with pytest.raises(KeyError, match="director_hermes_run_missing"):
            await service.retry(
                interrupted["run_id"],
                project_id=project_id,
                conversation_id="wrong-conversation",
            )
        with pytest.raises(KeyError, match="director_hermes_run_missing"):
            await service.retry(
                interrupted["run_id"],
                project_id="wrong-project",
                conversation_id="conv",
            )
        assert store.list_director_messages(
            project_id=project_id,
            conversation_id="conv",
        ) == before_wrong_scope
        retried = await service.retry(
            interrupted["run_id"],
            project_id=project_id,
            conversation_id="conv",
        )
        await retried.task
        with pytest.raises(ValueError, match="hermes_run_retry_not_eligible"):
            await service.retry(
                active["run_id"],
                project_id=project_id,
                conversation_id="conv",
            )
        with pytest.raises(ValueError, match="hermes_run_retry_not_eligible"):
            await service.retry(
                completed["run_id"],
                project_id=project_id,
                conversation_id="conv",
            )
        retried_blocked = await service.retry(
            blocked["run_id"],
            project_id=project_id,
            conversation_id="conv",
        )
        await retried_blocked.task
        return retried, retried_blocked

    retried, retried_blocked = asyncio.run(scenario())
    durable = store.get_director_hermes_run(
        project_id=project_id, run_id=retried.run_id
    )
    assert durable["retry_of_run_id"] == interrupted["run_id"]
    assert durable["client_message_id"] != "retry-source"
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=retried_blocked.run_id,
    )["retry_of_run_id"] == blocked["run_id"]
    assert gateway.calls == 2


@pytest.mark.parametrize("stale_identity", ("session", "asset"))
def test_retry_rejects_stale_source_identity_without_store_mutation(
    tmp_path: Path,
    stale_identity: str,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    source = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id=f"retry-stale-{stale_identity}",
        user_text="오래된 요청",
        expected_session_revision=1,
        expected_asset_index_revision=0,
    )
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=source["run_id"],
        owner_token=source["owner_token"],
        status="interrupted",
        assistant_text="중단",
        public_text="",
        retryable=True,
    )
    context_builder = None
    if stale_identity == "session":
        current = store.get_editing_session(
            project_id=project_id,
            session_id=session_id,
        )
        store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=current,
            expected_revision=1,
        )
    else:
        store.bump_asset_index_revision(project_id)

        def context_builder(**kwargs):
            return SimpleNamespace(
                session_revision=kwargs["expected_session_revision"],
                asset_index_revision=1,
                model_dump=lambda **_: {
                    "project_id": kwargs["project_id"],
                    "session_id": kwargs["session_id"],
                    "session_revision": kwargs["expected_session_revision"],
                    "asset_index_revision": 1,
                },
            )

    gateway = _Gateway()
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        **({"context_builder": context_builder} if context_builder else {}),
    )
    before = store.list_director_messages(
        project_id=project_id,
        conversation_id="conv",
    )

    async def scenario():
        with pytest.raises(
            ValueError,
            match=(
                "creator_context_session_revision_mismatch"
                if stale_identity == "session"
                else "hermes_run_retry_identity_mismatch"
            ),
        ):
            await service.retry(
                source["run_id"],
                project_id=project_id,
                conversation_id="conv",
            )

    asyncio.run(scenario())
    assert store.list_director_messages(
        project_id=project_id,
        conversation_id="conv",
    ) == before
    assert gateway.preparations == 0
    assert gateway.calls == 0


def test_terminal_commit_between_replay_list_and_status_is_drained(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="terminal-race",
        user_text="질문",
        expected_session_revision=1,
        expected_asset_index_revision=0,
    )
    original_list = store.list_director_hermes_run_events
    first = True

    def interleaved_list(**kwargs):
        nonlocal first
        events = original_list(**kwargs)
        if first:
            first = False
            assert store.complete_director_hermes_run(
                project_id=project_id,
                run_id=durable["run_id"],
                owner_token=durable["owner_token"],
                status="completed",
                assistant_text="answer",
                public_text="",
                retryable=False,
            )
        return events

    store.list_director_hermes_run_events = interleaved_list
    service = HermesRunService(store=store, gateway_client=_Gateway())

    async def replay():
        return [
            event
            async for event in service.subscribe(
                durable["run_id"],
                project_id=project_id,
                conversation_id="conv",
            )
        ]

    events = asyncio.run(replay())
    assert [event.event_type for event in events] == [
        "run_started",
        "text_delta",
        "run_completed",
    ]


def test_draft_commit_racing_cancel_reconciles_before_terminal(
    tmp_path: Path,
) -> None:
    visible = "This committed draft is long enough to race cancellation safely."
    store, project_id, session_id = _scope(tmp_path)
    committed = threading.Event()
    release_return = threading.Event()
    original_append = store.append_director_hermes_draft_event

    def delayed_append(**kwargs):
        result = original_append(**kwargs)
        committed.set()
        assert release_return.wait(timeout=3)
        return result

    store.append_director_hermes_draft_event = delayed_append
    gateway = _Gateway(
        events=[
            AgentGatewayEvent("text_delta", visible),
            AgentGatewayEvent("run_completed", visible),
        ]
    )
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="draft-cancel-race",
            text="질문",
        )
        assert await asyncio.to_thread(committed.wait, 3)
        cancel = asyncio.create_task(service.cancel(run.run_id))
        for _ in range(100):
            if run.terminalizing:
                break
            await asyncio.sleep(0.01)
        assert run.terminalizing
        release_return.set()
        await asyncio.gather(run.task, cancel, return_exceptions=True)
        events = await asyncio.wait_for(
            _collect_events(service.subscribe(run.run_id)), timeout=2
        )
        return run, events

    async def _collect_events(events):
        return [event async for event in events]

    run, events = asyncio.run(scenario())
    durable = store.get_director_hermes_run(
        project_id=project_id, run_id=run.run_id
    )
    assert durable["status"] == "interrupted"
    assert events[-1].event_type == "blocked"
    assert sum(event.event_type == "blocked" for event in events) == 1
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text
    messages = store.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )
    assert sum(message["role"] == "assistant" for message in messages) == 1


@pytest.mark.parametrize(
    "terminal_failure", [False, RuntimeError("terminal unavailable")]
)
def test_real_store_terminal_failure_ends_without_fabricated_durable_event(
    tmp_path: Path, terminal_failure
) -> None:
    visible = "This durable suffix must survive terminal persistence failure."
    store, project_id, session_id = _scope(tmp_path)
    original_complete = store.complete_director_hermes_run

    def fail_terminal(**kwargs):
        if isinstance(terminal_failure, Exception):
            raise terminal_failure
        return terminal_failure

    store.complete_director_hermes_run = fail_terminal
    service = HermesRunService(
        store=store,
        gateway_client=_Gateway(
            events=[
                AgentGatewayEvent("text_delta", visible),
                AgentGatewayEvent("run_completed", visible),
            ]
        ),
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id=f"terminal-failure-{type(terminal_failure).__name__}",
            text="질문",
        )
        await run.task
        events = await asyncio.wait_for(
            _collect_events(service.subscribe(run.run_id)), timeout=1
        )
        return run, events

    async def _collect_events(events):
        return [event async for event in events]

    run, events = asyncio.run(scenario())
    store.complete_director_hermes_run = original_complete
    assert [event.event_type for event in events] == [
        "run_started",
        "text_delta",
    ]
    assert events[-1].text == visible
    assert sum(
        event.event_type in {"blocked", "run_completed"} for event in events
    ) == 0
    durable = store.get_director_hermes_run(
        project_id=project_id, run_id=run.run_id
    )
    assert durable["status"] in {"pending", "streaming"}
    messages = store.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )
    assert sum(message["role"] == "assistant" for message in messages) == 0


def _proposal_context(*, asset_revision: int = 0) -> YujinCreatorContext:
    return YujinCreatorContext.model_validate(
        {
            "schema_version": "videobox.yujin-context.v1",
            "project_id": "project-1",
            "session_id": "session-1",
            "session_revision": 1,
            "asset_index_revision": asset_revision,
            "timeline_id": "timeline",
            "timeline_version": "v001",
            "selected_script_id": "script-1",
            "selected_segment_id": "segment-1",
            "segment_summaries": (
                {
                    "segment_id": "segment-1",
                    "start_sec": 0.0,
                    "end_sec": 5.0,
                    "text": "첫 장면",
                },
            ),
            "media_candidates": (
                {
                    "asset_id": "asset-video",
                    "kind": "broll_video",
                    "title": "산책",
                    "duration_sec": 5.0,
                    "tags": (),
                },
            ),
            "timeline_summary": {
                "duration_sec": 5.0,
                "track_count": 1,
                "clip_count": 1,
                "gap_count": 0,
            },
            "supported_controls": (
                {"kind": "broll", "mode": "recommendation_only"},
            ),
        }
    )


def _proposal_output(context: YujinCreatorContext) -> str:
    reply = "산책 영상을 추천합니다."
    payload = {
        "schema_version": "videobox.yujin-response.v1",
        "reply_text": reply,
        "proposal": {
            "proposal_id": "proposal-yujin-service",
            "base_revision": (
                f"session:{context.session_id}:revision:{context.session_revision}:"
                f"assets:{context.asset_index_revision}"
            ),
            "title": "첫 장면 B-roll",
            "rationale": "장면을 보강합니다.",
            "operations": [
                {
                    "operation_id": "operation-1",
                    "kind": "broll",
                    "target": {
                        "segment_id": "segment-1",
                        "track_id": "video-primary",
                    },
                    "parameters": {
                        "asset_id": context.media_candidates[0].asset_id,
                        "start_sec": 0.0,
                        "duration_sec": 3.0,
                        "fit": "cover",
                    },
                    "requires_materialization": True,
                    "preview_summary": "첫 장면에 3초 산책 영상",
                }
            ],
        },
    }
    return (
        f"{reply}\n```videobox-yujin-response\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n```"
    )


def _output_check_projection(
    *,
    store: LocalProjectStore,
    project_id: str,
    session_id: str,
    run_id: str,
):
    session = store.get_editing_session(
        project_id=project_id,
        session_id=session_id,
    )
    context = build_yujin_creator_context(
        store=store,
        project_id=project_id,
        session_id=session_id,
        expected_session_revision=int(session["session_revision"]),
        selected_segment_id="segment-1",
    )
    reply = "현재 타임라인의 빈 구간을 확인했습니다."
    payload = {
        "schema_version": "videobox.yujin-response.v1",
        "reply_text": reply,
        "proposal": {
            "proposal_id": "untrusted-output-check",
            "base_revision": (
                f"session:{context.session_id}:revision:{context.session_revision}:"
                f"assets:{context.asset_index_revision}"
            ),
            "title": "빈 구간 확인",
            "rationale": "현재 편집본의 빈 구간만 읽습니다.",
            "operations": [
                {
                    "operation_id": "operation-output-check",
                    "kind": "output_check",
                    "target": {"track_id": "output-primary"},
                    "parameters": {"check": "timeline_gaps"},
                    "requires_materialization": False,
                    "preview_summary": "빈 구간 확인",
                }
            ],
        },
    }
    raw = (
        f"{reply}\n```videobox-yujin-response\n"
        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n```"
    )
    projection = parse_and_project_yujin_creator_output(
        raw,
        context,
        trusted_project_id=project_id,
        trusted_run_id=run_id,
    )
    activated = activate_yujin_media_projection(
        store=store,
        project_id=project_id,
        context=context,
        projection=projection,
    )
    assert activated.proposal is not None
    assert activated.proposal.candidates[0].controls["gap_count"] == (
        context.timeline_summary.gap_count
    )
    return context, activated


def _real_output_scope(
    tmp_path: Path,
    *,
    gap_count: int,
    remove_segment: bool = False,
):
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("output-gap-terminal")
    gap_slots = [
        {
            "gap_id": f"gap-{index + 1}",
            "segment_id": "segment-1",
            "start_sec": float(index),
            "end_sec": float(index + 1),
            "reason": "asset_gap",
        }
        for index in range(gap_count)
    ]
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [],
            "gap_slots": gap_slots,
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "segment-1",
                    "start_sec": 0.0,
                    "end_sec": 5.0,
                    "caption_text": "첫 장면",
                    **({"cut_action": "remove"} if remove_segment else {}),
                }
            ],
            "history": [],
        },
    )
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conv-output-gap",
    )
    return store, project.project_id, session["session_id"], timeline["timeline_id"]


@pytest.mark.parametrize("gap_count", (0, 1))
def test_real_store_output_check_terminal_uses_current_materialized_gap_truth(
    tmp_path: Path,
    gap_count: int,
) -> None:
    store, project_id, session_id, _timeline_id = _real_output_scope(
        tmp_path,
        gap_count=gap_count,
    )
    run_id = f"output-gap-{gap_count}"
    context, projection = _output_check_projection(
        store=store,
        project_id=project_id,
        session_id=session_id,
        run_id=run_id,
    )
    proposal = projection.proposal
    assert proposal is not None
    assert context.timeline_summary.gap_count == gap_count
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv-output-gap",
        client_message_id=run_id,
        user_text="빈 구간 확인",
        expected_session_revision=context.session_revision,
        expected_asset_index_revision=context.asset_index_revision,
    )

    result = _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text=projection.reply_text,
        retryable=False,
        proposal=proposal,
    )

    assert result is True
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )["status"] == "completed"


def test_real_store_output_check_terminal_uses_materialized_not_raw_gap_count(
    tmp_path: Path,
) -> None:
    store, project_id, session_id, _timeline_id = _real_output_scope(
        tmp_path,
        gap_count=1,
        remove_segment=True,
    )
    run_id = "output-gap-materialized"
    context, projection = _output_check_projection(
        store=store,
        project_id=project_id,
        session_id=session_id,
        run_id=run_id,
    )
    proposal = projection.proposal
    assert proposal is not None
    assert context.timeline_summary.gap_count == 0
    assert proposal.candidates[0].controls["gap_count"] == 0
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv-output-gap",
        client_message_id=run_id,
        user_text="빈 구간 확인",
        expected_session_revision=context.session_revision,
        expected_asset_index_revision=context.asset_index_revision,
    )

    result = _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text=projection.reply_text,
        retryable=False,
        proposal=proposal,
    )

    assert result is True


def test_real_store_output_check_terminal_rolls_back_when_gap_truth_changes(
    tmp_path: Path,
) -> None:
    store, project_id, session_id, timeline_id = _real_output_scope(
        tmp_path,
        gap_count=0,
    )
    run_id = "output-gap-race"
    context, projection = _output_check_projection(
        store=store,
        project_id=project_id,
        session_id=session_id,
        run_id=run_id,
    )
    proposal = projection.proposal
    assert proposal is not None
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv-output-gap",
        client_message_id=run_id,
        user_text="빈 구간 확인",
        expected_session_revision=context.session_revision,
        expected_asset_index_revision=context.asset_index_revision,
    )
    timeline = store.get_timeline_run(
        project_id=project_id,
        timeline_id=timeline_id,
    )
    timeline["gap_slots"] = [
        {
            "gap_id": "gap-after-context",
            "segment_id": "segment-1",
            "start_sec": 0.0,
            "end_sec": 1.0,
            "reason": "asset_gap",
        }
    ]
    store.update_timeline_run(
        project_id=project_id,
        timeline_id=timeline_id,
        timeline_payload=timeline,
    )

    result = _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text=projection.reply_text,
        retryable=False,
        proposal=proposal,
    )

    assert result == "proposal_stale"
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )["status"] == "pending"
    assert store.list_director_proposals(project_id) == []
    assert [
        message["role"]
        for message in store.list_director_messages(
            project_id=project_id,
            conversation_id="conv-output-gap",
        )
    ] == ["user"]


def test_real_store_output_check_terminal_rejects_file_before_summary_race(
    tmp_path: Path,
) -> None:
    store, project_id, session_id, timeline_id = _real_output_scope(
        tmp_path,
        gap_count=0,
    )
    run_id = "output-gap-file-before-db"
    context, projection = _output_check_projection(
        store=store,
        project_id=project_id,
        session_id=session_id,
        run_id=run_id,
    )
    proposal = projection.proposal
    assert proposal is not None
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv-output-gap",
        client_message_id=run_id,
        user_text="빈 구간 확인",
        expected_session_revision=context.session_revision,
        expected_asset_index_revision=context.asset_index_revision,
    )
    timeline = store.get_timeline_run(
        project_id=project_id,
        timeline_id=timeline_id,
    )
    timeline.pop("summary", None)
    timeline["gap_slots"] = [
        {
            "gap_id": "gap-file-before-db",
            "segment_id": "segment-1",
            "start_sec": 0.0,
            "end_sec": 1.0,
            "reason": "asset_gap",
        }
    ]
    timeline_path = store.resolve_storage_uri(
        project_id=project_id,
        storage_uri=str(timeline["file_uri"]),
    )
    timeline_path.write_text(
        json.dumps(timeline, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    result = _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text=projection.reply_text,
        retryable=False,
        proposal=proposal,
    )

    assert result == "proposal_stale"
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )["status"] == "pending"
    assert store.list_director_proposals(project_id) == []


def test_real_store_output_check_terminal_materializes_legacy_gap_summary(
    tmp_path: Path,
) -> None:
    store, project_id, session_id, timeline_id = _real_output_scope(
        tmp_path,
        gap_count=1,
    )
    run_id = "output-gap-legacy-summary"
    context, projection = _output_check_projection(
        store=store,
        project_id=project_id,
        session_id=session_id,
        run_id=run_id,
    )
    proposal = projection.proposal
    assert proposal is not None
    connection = store._connection(project_id)
    try:
        row = connection.execute(
            "SELECT summary_json FROM timelines "
            "WHERE project_id = ? AND timeline_id = ?",
            (project_id, timeline_id),
        ).fetchone()
        summary = json.loads(str(row["summary_json"]))
        summary.pop("gap_count")
        connection.execute(
            "UPDATE timelines SET summary_json = ? "
            "WHERE project_id = ? AND timeline_id = ?",
            (json.dumps(summary, ensure_ascii=True), project_id, timeline_id),
        )
        connection.commit()
    finally:
        connection.close()
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv-output-gap",
        client_message_id=run_id,
        user_text="빈 구간 확인",
        expected_session_revision=context.session_revision,
        expected_asset_index_revision=context.asset_index_revision,
    )

    result = _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text=projection.reply_text,
        retryable=False,
        proposal=proposal,
    )

    assert result is True
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )["status"] == "completed"


def _ready_yujin_proposal(
    store: LocalProjectStore,
    *,
    project_id: str,
    session_id: str,
    asset_id: str,
    claimed_source_kind: str = "broll_video",
) -> DirectorProposal:
    session = store.get_editing_session(
        project_id=project_id,
        session_id=session_id,
    )
    asset = store.get_asset(project_id=project_id, asset_id=asset_id)
    source = store.resolve_storage_uri(
        project_id=project_id,
        storage_uri=str(asset["storage_uri"]),
    )
    candidate = DirectorCandidate(
        candidate_id="yujin-ready-candidate",
        visible_reference_code="P00-B-01",
        media_type="broll",
        asset_id=asset_id,
        library_asset_id=None,
        reason_chips=("추천",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={"fit": "fit"},
        expected_content_sha256=sha256_file(source),
        media_revision=str(asset["created_at"]),
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "broll",
            "yujin_actionable_media": True,
            "source_media_kind": claimed_source_kind,
            "target_segment_id": "segment-1",
        },
    )
    return DirectorProposal(
        proposal_id="yujin-ready-proposal",
        revision_code="P00",
        revision=0,
        base_session_revision=int(session["session_revision"]),
        asset_index_revision=store.get_asset_index_revision(project_id),
        source_session_id=session_id,
        target_segment_ids=("segment-1",),
        source_script_segment_ids=("segment-1",),
        status="ready",
        diff={"proposal_mode": "yujin_actionable_media_v1"},
        expires_at=None,
        candidates=(candidate,),
    )


@pytest.mark.parametrize(
    "race",
    (
        "session_revision",
        "asset_index",
        "forged_type",
        "media_revision",
        "source_missing",
        "claimed_raw_actual_broll",
        "claimed_broll_actual_raw",
    ),
)
def test_ready_yujin_terminal_cas_rolls_back_stale_proposal_before_terminal_write(
    tmp_path: Path,
    race: str,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    source = tmp_path / f"{race}.bin"
    source.write_bytes(b"terminal-race-source")
    asset = store.register_asset(
        project_id=project_id,
        asset_type=(
            AssetType.IMAGE
            if race == "forged_type"
            else AssetType.RAW_VIDEO
            if race == "claimed_broll_actual_raw"
            else AssetType.BROLL_VIDEO
        ),
        source_path=source,
        metadata={},
    )
    proposal = _ready_yujin_proposal(
        store,
        project_id=project_id,
        session_id=session_id,
        asset_id=asset.asset_id,
        claimed_source_kind=(
            "raw_video" if race == "claimed_raw_actual_broll" else "broll_video"
        ),
    )
    if race == "media_revision":
        proposal = replace(
            proposal,
            candidates=(
                replace(proposal.candidates[0], media_revision="forged-r1"),
            ),
        )
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id=f"terminal-race-{race}",
        user_text="추천",
        expected_session_revision=proposal.base_session_revision,
        expected_asset_index_revision=proposal.asset_index_revision,
    )
    if race == "session_revision":
        current = store.get_editing_session(
            project_id=project_id,
            session_id=session_id,
        )
        store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=current,
            expected_revision=proposal.base_session_revision,
        )
    elif race == "asset_index":
        store.bump_asset_index_revision(project_id)
    elif race == "source_missing":
        stored_asset = store.get_asset(
            project_id=project_id,
            asset_id=asset.asset_id,
        )
        store.resolve_storage_uri(
            project_id=project_id,
            storage_uri=str(stored_asset["storage_uri"]),
        ).unlink()

    result = _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="추천 결과",
        retryable=False,
        proposal=proposal,
    )

    assert result == "proposal_stale"
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )["status"] == "pending"
    assert store.list_director_proposals(project_id) == []
    messages = store.list_director_messages(
        project_id=project_id,
        conversation_id="conv",
    )
    assert [message["role"] for message in messages] == ["user"]


@pytest.mark.parametrize(
    ("asset_type", "claimed_source_kind"),
    (
        (AssetType.BROLL_VIDEO, "broll_video"),
        (AssetType.RAW_VIDEO, "raw_video"),
    ),
)
def test_current_ready_yujin_terminal_cas_persists_atomically(
    tmp_path: Path,
    asset_type: AssetType,
    claimed_source_kind: str,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    source = tmp_path / "current-ready.bin"
    source.write_bytes(b"current-ready-source")
    asset = store.register_asset(
        project_id=project_id,
        asset_type=asset_type,
        source_path=source,
        metadata={},
    )
    proposal = _ready_yujin_proposal(
        store,
        project_id=project_id,
        session_id=session_id,
        asset_id=asset.asset_id,
        claimed_source_kind=claimed_source_kind,
    )
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="terminal-current",
        user_text="추천",
        expected_session_revision=proposal.base_session_revision,
        expected_asset_index_revision=proposal.asset_index_revision,
    )

    assert _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="추천 결과",
        retryable=False,
        proposal=proposal,
    )
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )["status"] == "completed"


def test_current_b4_caption_terminal_cas_persists_without_fake_asset_lookup(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    session = store.get_editing_session(
        project_id=project_id,
        session_id=session_id,
    )
    candidate = DirectorCandidate(
        candidate_id="yujin-caption-command",
        visible_reference_code="P00-CAPTION-01",
        media_type="caption",
        asset_id="yujin-caption-command",
        library_asset_id=None,
        reason_chips=("자막 변경",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={"text": "현재 장면 자막"},
        expected_content_sha256=None,
        media_revision="session-caption-r1",
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "caption",
            "yujin_actionable_operation": True,
            "command_kind": "set_caption_text",
            "target_segment_id": "segment-1",
            "requires_materialization": False,
        },
    )
    proposal = DirectorProposal(
        proposal_id="yujin-caption-proposal",
        revision_code="P00",
        revision=0,
        base_session_revision=int(session["session_revision"]),
        asset_index_revision=store.get_asset_index_revision(project_id),
        source_session_id=session_id,
        target_segment_ids=("segment-1",),
        source_script_segment_ids=("segment-1",),
        status="ready",
        diff={"proposal_mode": "yujin_actionable_v1"},
        expires_at=None,
        candidates=(candidate,),
    )
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="terminal-caption-current",
        user_text="자막 추천",
        expected_session_revision=proposal.base_session_revision,
        expected_asset_index_revision=proposal.asset_index_revision,
    )

    assert _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="자막 추천 결과",
        retryable=False,
        proposal=proposal,
    )
    assert store.get_director_proposal(
        project_id,
        proposal.proposal_id,
    ).diff["proposal_mode"] == "yujin_actionable_v1"
    assert [item.proposal_id for item in store.list_director_proposals(project_id)] == [
        proposal.proposal_id
    ]
    assistant = store.list_director_messages(
        project_id=project_id,
        conversation_id="conv",
    )[-1]
    assert assistant["proposal_id"] == proposal.proposal_id


@pytest.mark.parametrize(
    ("forgery", "media_type", "command_kind", "controls"),
    (
        (
            "caption-placement",
            "caption",
            "set_caption_text",
            {"text": "현재 장면 자막", "placement": "bottom"},
        ),
        (
            "caption-partial-style",
            "caption",
            "set_caption_style",
            {"scope": "current_caption", "style": {"font_family": "Arial"}},
        ),
        (
            "overlay-position",
            "overlay",
            "apply_overlay",
            {
                "overlay_kind": "explanation-card",
                "title": "핵심",
                "body": "설명",
                "text": "장면 설명",
                "x": 0.5,
                "y": 0.5,
                "opacity": 1.0,
            },
        ),
        (
            "overlay-malformed-table",
            "overlay",
            "apply_overlay",
            {
                "overlay_kind": "table",
                "columns": ["항목", "값"],
                "rows": [["한 칸뿐"]],
                "text": "잘못된 표",
            },
        ),
    ),
)
def test_b4_terminal_cas_rejects_forged_caption_and_overlay_controls(
    tmp_path: Path,
    forgery: str,
    media_type: str,
    command_kind: str,
    controls: dict[str, object],
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    session = store.get_editing_session(
        project_id=project_id,
        session_id=session_id,
    )
    candidate = DirectorCandidate(
        candidate_id=f"yujin-{forgery}",
        visible_reference_code="P00-B4-01",
        media_type=media_type,
        asset_id=f"yujin-{forgery}",
        library_asset_id=None,
        reason_chips=("위조 B4 command",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls=controls,
        expected_content_sha256=None,
        media_revision="session-b4-r1",
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": media_type,
            "yujin_actionable_operation": True,
            "command_kind": command_kind,
            "target_segment_id": "segment-1",
            "requires_materialization": False,
        },
    )
    proposal = DirectorProposal(
        proposal_id=f"yujin-{forgery}-proposal",
        revision_code="P00",
        revision=0,
        base_session_revision=int(session["session_revision"]),
        asset_index_revision=store.get_asset_index_revision(project_id),
        source_session_id=session_id,
        target_segment_ids=("segment-1",),
        source_script_segment_ids=("segment-1",),
        status="ready",
        diff={"proposal_mode": "yujin_actionable_v1"},
        expires_at=None,
        candidates=(candidate,),
    )
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id=f"terminal-{forgery}",
        user_text="위조 추천",
        expected_session_revision=proposal.base_session_revision,
        expected_asset_index_revision=proposal.asset_index_revision,
    )

    result = _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="위조 추천 결과",
        retryable=False,
        proposal=proposal,
    )

    assert result == "proposal_stale"
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )["status"] == "pending"
    assert store.list_director_proposals(project_id) == []
    assert [
        message["role"]
        for message in store.list_director_messages(
            project_id=project_id,
            conversation_id="conv",
        )
    ] == ["user"]


def test_b4_terminal_cas_rejects_voice_controls_that_disagree_with_attested_identity(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    source = tmp_path / "approved-voice.bin"
    source.write_bytes(b"approved-voice")
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.GENERATED_TTS_AUDIO,
        source_path=source,
        metadata={},
    )
    persisted = store.save_tts_candidate(
        project_id=project_id,
        segment_id="segment-1",
        asset_id=asset.asset_id,
        source_text="승인 음성",
        acceptance=SimpleNamespace(
            technical_status="accepted",
            operator_review_status="pending",
        ),
    )
    store.update_tts_candidate_listening_review(
        project_id=project_id,
        candidate_id=persisted["candidate_id"],
        decision="approved",
    )
    session = store.get_editing_session(
        project_id=project_id,
        session_id=session_id,
    )
    candidate = DirectorCandidate(
        candidate_id="yujin-forged-voice",
        visible_reference_code="P00-VOICE-01",
        media_type="voice",
        asset_id=asset.asset_id,
        library_asset_id=None,
        reason_chips=("위조 음성 command",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={
            "candidate_id": "tts_candidate_999",
            "asset_id": asset.asset_id,
        },
        expected_content_sha256=sha256_file(
            store.resolve_storage_uri(
                project_id=project_id,
                storage_uri=str(asset.storage_uri),
            )
        ),
        media_revision=asset.created_at.isoformat(),
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "voice",
            "yujin_actionable_operation": True,
            "command_kind": "apply_tts_candidate",
            "candidate_id": persisted["candidate_id"],
            "source_media_kind": "generated_tts_audio",
            "target_segment_id": "segment-1",
            "requires_materialization": False,
        },
    )
    proposal = DirectorProposal(
        proposal_id="yujin-forged-voice-proposal",
        revision_code="P00",
        revision=0,
        base_session_revision=int(session["session_revision"]),
        asset_index_revision=store.get_asset_index_revision(project_id),
        source_session_id=session_id,
        target_segment_ids=("segment-1",),
        source_script_segment_ids=("segment-1",),
        status="ready",
        diff={"proposal_mode": "yujin_actionable_v1"},
        expires_at=None,
        candidates=(candidate,),
    )
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="terminal-forged-voice",
        user_text="위조 음성 추천",
        expected_session_revision=proposal.base_session_revision,
        expected_asset_index_revision=proposal.asset_index_revision,
    )

    result = _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="위조 음성 추천 결과",
        retryable=False,
        proposal=proposal,
    )

    assert result == "proposal_stale"
    assert store.list_director_proposals(project_id) == []
    assert [
        message["role"]
        for message in store.list_director_messages(
            project_id=project_id,
            conversation_id="conv",
        )
    ] == ["user"]


def test_machine_payload_is_never_public_and_candidate_links_atomically(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="videobox_api.hermes_run_service")
    store, project_id, session_id = _scope(tmp_path)
    session = store.get_editing_session(project_id=project_id, session_id=session_id)
    context = _proposal_context()
    context = context.model_copy(
        update={"project_id": project_id, "session_id": session_id}
    )
    raw = _proposal_output(context)
    split = raw.index("```") + 2
    gateway = _Gateway(
        [
            AgentGatewayEvent("text_delta", raw[:split]),
            AgentGatewayEvent("text_delta", raw[split:]),
            AgentGatewayEvent(
                "run_completed",
                raw,
                publish_capability_token="header.publish.signature",
            ),
        ]
    )
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=lambda **_: context,
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="typed-proposal",
            text="추천해줘",
        )
        await run.task
        return run, [event async for event in service.subscribe(run.run_id)]

    run, events = asyncio.run(scenario())
    persisted_proposal_id = _persisted_proposal_id(
        project_id=project_id,
        run_id=run.run_id,
    )
    deltas = "".join(
        event.text for event in events if event.event_type == "text_delta"
    )
    terminal = events[-1]
    assert terminal.event_type == "run_completed"
    assert deltas == terminal.text == "산책 영상을 추천합니다."
    assert "```" not in "".join(event.text for event in events)
    messages = store.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )
    assert messages[-1]["text"] == terminal.text
    assert messages[-1]["proposal_id"] == persisted_proposal_id
    stored = store.get_director_proposal(project_id, persisted_proposal_id)
    assert stored.status == "candidate_only"
    assert stored.candidates[0].preview_uri is None
    unchanged = store.get_editing_session(
        project_id=project_id, session_id=session_id
    )
    assert unchanged["session_revision"] == session["session_revision"]
    assert unchanged["history"] == session["history"]
    validation_records = [
        record
        for record in caplog.records
        if record.message == "yujin_creator_proposal_validation"
    ]
    assert len(validation_records) == 1
    record = validation_records[0]
    assert record.proposal_id == persisted_proposal_id
    assert record.schema_version == "videobox.yujin-response.v1"
    assert record.operation_count == 1
    assert record.validation_outcome == "valid"
    assert "asset-video" not in caplog.text
    assert "operation-1" not in caplog.text
    assert "proposal-yujin-service" not in caplog.text
    assert "산책 영상을" not in caplog.text
    assert "header.publish.signature" not in caplog.text
    assert "header.publish.signature" not in "".join(
        event.model_dump_json() for event in events
    )
    with store._connection(project_id) as connection:
        capability_states = dict(
            connection.execute(
                """
                SELECT action, state FROM hermes_capability_ledger
                WHERE project_id = ? AND run_id = ?
                """,
                (project_id, run.run_id),
            ).fetchall()
        )
        publish_consume_audits = connection.execute(
            """
            SELECT COUNT(*) FROM hermes_capability_audit
            WHERE project_id = ? AND run_id = ?
              AND action = 'publish_proposal'
              AND outcome = 'accepted'
              AND reason = 'hermes_capability_consumed'
            """,
            (project_id, run.run_id),
        ).fetchone()[0]
    assert capability_states == {
        "publish_proposal": "consumed",
        "read_context": "consumed",
    }
    assert publish_consume_audits == 1


def test_publish_signature_failure_discards_proposal_and_terminalizes_once(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    session = store.get_editing_session(
        project_id=project_id,
        session_id=session_id,
    )
    context = _proposal_context().model_copy(
        update={"project_id": project_id, "session_id": session_id}
    )
    raw = _proposal_output(context)
    calls: list[str] = []
    gateway = _Gateway(
        [
            AgentGatewayEvent(
                "run_completed",
                raw,
                publish_capability_token="bad.publish.signature",
            )
        ]
    )
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=lambda **_: context,
        capability_verifier=_CapabilityVerifier(
            calls,
            fail_action="publish_proposal",
        ),
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="publish-signature-failure",
            text="추천해줘",
        )
        await run.task
        return run, [
            event async for event in service.subscribe(run.run_id)
        ]

    run, events = asyncio.run(scenario())

    terminal = [
        event
        for event in events
        if event.event_type in {"run_completed", "blocked"}
    ]
    assert len(terminal) == 1
    assert MANUAL_FALLBACK in terminal[0].text
    assert "bad.publish.signature" not in "".join(
        event.model_dump_json() for event in events
    )
    assert store.list_director_proposals(project_id) == []
    messages = store.list_director_messages(
        project_id=project_id,
        conversation_id="conv",
    )
    assert messages[-1]["proposal_id"] is None
    assert "bad.publish.signature" not in messages[-1]["text"]
    unchanged = store.get_editing_session(
        project_id=project_id,
        session_id=session_id,
    )
    assert unchanged["session_revision"] == session["session_revision"]
    assert unchanged["history"] == session["history"]
    with store._connection(project_id) as connection:
        publish = connection.execute(
            """
            SELECT state FROM hermes_capability_ledger
            WHERE project_id = ? AND run_id = ?
              AND action = 'publish_proposal'
            """,
            (project_id, run.run_id),
        ).fetchone()[0]
        denials = [
            str(row["reason"])
            for row in connection.execute(
                """
                SELECT reason FROM hermes_capability_audit
                WHERE project_id = ? AND run_id = ?
                  AND action = 'publish_proposal'
                  AND outcome = 'denied'
                """,
                (project_id, run.run_id),
            ).fetchall()
        ]
    assert publish == "revoked"
    assert denials == ["hermes_capability_signature_invalid"]
    assert gateway.calls == 1
    assert calls.count("verify") == 2


def test_publish_proposal_wrong_verified_scope_audits_and_revokes(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    context = _proposal_context().model_copy(
        update={"project_id": project_id, "session_id": session_id}
    )
    gateway = _Gateway(
        [
            AgentGatewayEvent(
                "run_completed",
                _proposal_output(context),
                publish_capability_token="header.publish.signature",
            )
        ]
    )
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=lambda **_: context,
        capability_verifier=_CapabilityVerifier(
            [],
            wrong_scope_action="publish_proposal",
        ),
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="publish-wrong-scope",
            text="추천해줘",
        )
        await run.task
        return run, [
            event async for event in service.subscribe(run.run_id)
        ]

    run, events = asyncio.run(scenario())

    assert len(
        [
            event
            for event in events
            if event.event_type in {"run_completed", "blocked"}
        ]
    ) == 1
    assert MANUAL_FALLBACK in events[-1].text
    assert store.list_director_proposals(project_id) == []
    with store._connection(project_id) as connection:
        publish_state = connection.execute(
            """
            SELECT state FROM hermes_capability_ledger
            WHERE project_id = ? AND run_id = ?
              AND action = 'publish_proposal'
            """,
            (project_id, run.run_id),
        ).fetchone()[0]
        reasons = [
            str(row["reason"])
            for row in connection.execute(
                """
                SELECT reason FROM hermes_capability_audit
                WHERE project_id = ? AND run_id = ?
                  AND action = 'publish_proposal'
                  AND outcome = 'denied'
                """,
                (project_id, run.run_id),
            ).fetchall()
        ]
    assert publish_state == "revoked"
    assert reasons == ["hermes_capability_scope_forbidden"]


def test_publish_proposal_transaction_fault_retries_one_safe_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    context = _proposal_context().model_copy(
        update={"project_id": project_id, "session_id": session_id}
    )
    original_append = store._append_hermes_capability_audit

    def fail_after_publish_consume(connection, **kwargs):
        event = original_append(connection, **kwargs)
        if kwargs["reason"] == "hermes_capability_consumed" and kwargs[
            "action"
        ] == "publish_proposal":
            raise OSError("publish terminal transaction fault")
        return event

    monkeypatch.setattr(
        store,
        "_append_hermes_capability_audit",
        fail_after_publish_consume,
    )
    gateway = _Gateway(
        [
            AgentGatewayEvent(
                "run_completed",
                _proposal_output(context),
                publish_capability_token="header.publish.signature",
            )
        ]
    )
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=lambda **_: context,
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="publish-transaction-fault",
            text="추천해줘",
        )
        await run.task
        return run, [
            event async for event in service.subscribe(run.run_id)
        ]

    run, events = asyncio.run(scenario())

    terminal = [
        event
        for event in events
        if event.event_type in {"run_completed", "blocked"}
    ]
    assert len(terminal) == 1
    assert MANUAL_FALLBACK in terminal[0].text
    assert store.list_director_proposals(project_id) == []
    message = store.list_director_messages(
        project_id=project_id,
        conversation_id="conv",
    )[-1]
    assert message["proposal_id"] is None
    with store._connection(project_id) as connection:
        publish_state = connection.execute(
            """
            SELECT state FROM hermes_capability_ledger
            WHERE project_id = ? AND run_id = ?
              AND action = 'publish_proposal'
            """,
            (project_id, run.run_id),
        ).fetchone()[0]
        consumed_audits = connection.execute(
            """
            SELECT COUNT(*) FROM hermes_capability_audit
            WHERE project_id = ? AND run_id = ?
              AND action = 'publish_proposal'
              AND reason = 'hermes_capability_consumed'
            """,
            (project_id, run.run_id),
        ).fetchone()[0]
    assert publish_state == "revoked"
    assert consumed_audits == 0
    assert gateway.calls == 1


def test_current_media_projection_is_attested_after_context_recheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    import videobox_api.hermes_run_service as run_module

    store, project_id, session_id = _scope(tmp_path)
    source = tmp_path / "attested-current.mp4"
    source.write_bytes(b"attested-current")
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
        metadata={},
    )
    base_context = _proposal_context(
        asset_revision=store.get_asset_index_revision(project_id)
    )
    context = base_context.model_copy(
        update={
            "project_id": project_id,
            "session_id": session_id,
            "media_candidates": (
                base_context.media_candidates[0].model_copy(
                    update={"asset_id": asset.asset_id}
                ),
            ),
        }
    )
    gateway = _Gateway(
        [
            AgentGatewayEvent(
                "run_completed",
                _proposal_output(context),
                publish_capability_token="header.publish.signature",
            )
        ]
    )
    activation_calls: list[dict[str, object]] = []

    def activate(**kwargs):
        activation_calls.append(kwargs)
        projection = kwargs["projection"]
        proposal = projection.proposal
        assert proposal is not None
        candidate = replace(
            proposal.candidates[0],
            availability="actionable",
            review_status="approved",
            expected_content_sha256=sha256_file(
                store.resolve_storage_uri(
                    project_id=project_id,
                    storage_uri=str(
                        store.get_asset(
                            project_id=project_id,
                            asset_id=asset.asset_id,
                        )["storage_uri"]
                    ),
                )
            ),
            media_revision=str(
                store.get_asset(
                    project_id=project_id,
                    asset_id=asset.asset_id,
                )["created_at"]
            ),
            canonical_metadata={
                "schema_version": "videobox.yujin-response.v1",
                "proposal_kind": "broll",
                "yujin_actionable_media": True,
                "source_media_kind": "broll_video",
                "target_segment_id": "segment-1",
            },
            asset_id=asset.asset_id,
        )
        return replace(
            projection,
            proposal=replace(
                proposal,
                status="ready",
                diff={
                    **dict(proposal.diff),
                    "proposal_mode": "yujin_actionable_media_v1",
                },
                candidates=(candidate,),
            ),
        )

    monkeypatch.setattr(
        run_module,
        "activate_yujin_media_projection",
        activate,
        raising=False,
    )
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=lambda **_: context,
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="actionable-proposal",
            text="추천해줘",
        )
        await run.task
        return run, [event async for event in service.subscribe(run.run_id)]

    run, events = asyncio.run(scenario())

    assert len(activation_calls) == 1
    assert activation_calls[0]["context"] == context
    assert events[-1].event_type == "run_completed"
    stored = store.get_director_proposal(
        project_id,
        _persisted_proposal_id(project_id=project_id, run_id=run.run_id),
    )
    assert stored.status == "ready"
    assert stored.candidates[0].availability == "actionable"


def test_changed_terminal_context_discards_only_proposal_with_manual_fallback(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    initial = _proposal_context().model_copy(
        update={"project_id": project_id, "session_id": session_id}
    )
    changed = initial.model_copy(update={"asset_index_revision": 1})
    contexts = iter((initial, changed))
    gateway = _Gateway(
        [AgentGatewayEvent("run_completed", _proposal_output(initial))]
    )
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=lambda **_: next(contexts),
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="stale-proposal",
            text="추천해줘",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    assert events[-1].event_type == "run_completed"
    assert events[-1].text.startswith("산책 영상을 추천합니다.")
    assert "수동" in events[-1].text
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text
    assert store.list_director_proposals(project_id) == []
    messages = store.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )
    assert messages[-1]["proposal_id"] is None


def test_invalid_json_fence_is_neither_streamed_nor_persisted(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    context = _proposal_context().model_copy(
        update={"project_id": project_id, "session_id": session_id}
    )
    raw = '설명입니다.\n```json\n{"password":"must-not-publish"}\n```'
    gateway = _Gateway(
        [
            AgentGatewayEvent("text_delta", raw[:12]),
            AgentGatewayEvent("text_delta", raw[12:]),
            AgentGatewayEvent("run_completed", raw),
        ]
    )
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=lambda **_: context,
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="invalid-frame",
            text="설명해줘",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    public = "".join(event.text for event in events)
    assert "```" not in public
    assert "password" not in public
    assert "수동" in events[-1].text
    message = store.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )[-1]
    assert message["text"] == events[-1].text
    assert "password" not in message["text"]
    assert message["proposal_id"] is None


def test_fence_free_json_and_array_are_buffered_at_every_split_boundary() -> None:
    class Store:
        def __init__(self) -> None:
            self.completions: list[dict] = []

        def begin_director_hermes_run(self, **kwargs):
            return {
                "run_id": kwargs["client_message_id"],
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def complete_director_hermes_run(self, **kwargs):
            self.completions.append(kwargs)
            return True

    async def exercise(raw: str, split: int, expected: str) -> None:
        store = Store()
        gateway = _Gateway(
            [
                AgentGatewayEvent("text_delta", raw[:split]),
                AgentGatewayEvent("text_delta", raw[split:]),
                AgentGatewayEvent("run_completed", ""),
            ]
        )
        service = HermesRunService(store=store, gateway_client=gateway)
        run = await service.create_run(
            project_id="project",
            session_id="session",
            conversation_id="conversation",
            client_message_id=f"json-{len(raw)}-{split}",
            text="question",
        )
        await run.task
        events = [event async for event in service.subscribe(run.run_id)]
        deltas = "".join(
            event.text for event in events if event.event_type == "text_delta"
        )
        assert events[-1].event_type == "run_completed"
        assert deltas == events[-1].text == expected
        assert store.completions[0]["assistant_text"] == expected
        public = "".join(event.text for event in events)
        assert "schema_version" not in public
        assert "password" not in public
        assert "must-not-publish" not in public

    async def scenario() -> None:
        raws = (
            (
                ' \r\n {"schema_version":"videobox.yujin-response.v1",'
                '"password":"must-not-publish"}',
                MANUAL_FALLBACK,
            ),
            (
                ' \t[{"password":"must-not-publish"}]',
                MANUAL_FALLBACK,
            ),
            (
                'Here is JSON: {"schema_version":'
                '"videobox.yujin-response.v1","password":"must-not-publish"}',
                f"Here is JSON:\n\n{MANUAL_FALLBACK}",
            ),
            (
                '추천 결과입니다.\n[\n{"password":"must-not-publish"}\n]',
                f"추천 결과입니다.\n\n{MANUAL_FALLBACK}",
            ),
            (
                '설명입니다.\n{"schema_version":"videobox.yujin-response.v1",'
                '"password":"must-not-publish"',
                f"설명입니다.\n\n{MANUAL_FALLBACK}",
            ),
        )
        for raw, expected in raws:
            for split in range(1, len(raw)):
                await exercise(raw, split, expected)

    asyncio.run(scenario())


def test_prose_json_cas_failure_publishes_zero_text_delta() -> None:
    raw = (
        'Here is JSON: {"schema_version":"videobox.yujin-response.v1",'
        '"password":"must-not-publish"}'
    )

    class Store:
        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "prose-json-cas-failure",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def complete_director_hermes_run(self, **_):
            return False

    service = HermesRunService(
        store=Store(),
        gateway_client=_Gateway(
            [
                AgentGatewayEvent("text_delta", raw[:15]),
                AgentGatewayEvent("text_delta", raw[15:]),
                AgentGatewayEvent("run_completed", ""),
            ]
        ),
    )

    async def scenario():
        run = await service.create_run(
            project_id="project",
            session_id="session",
            conversation_id="conversation",
            client_message_id="prose-json-cas-failure",
            text="question",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    assert events[-1].event_type == "blocked"
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text
    assert "schema_version" not in "".join(event.text for event in events)
    assert "password" not in "".join(event.text for event in events)


@pytest.mark.parametrize(
    ("raw", "visible_prefix"),
    (
        (
            'Visible reply\n{"reply_text":"must-not-publish"',
            "Visible reply",
        ),
        (
            'Inline reply: {"password":"must-not-publish"',
            "Inline reply:",
        ),
        (
            "Array reply\n[false",
            "Array reply",
        ),
    ),
)
def test_malformed_machine_suffix_storage_and_sse_keep_exact_visible_boundary(
    tmp_path: Path,
    raw: str,
    visible_prefix: str,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    context = _proposal_context().model_copy(
        update={"project_id": project_id, "session_id": session_id}
    )
    boundary = min(
        index for index in (raw.find("{"), raw.find("[")) if index >= 0
    )
    gateway = _Gateway(
        [
            AgentGatewayEvent("text_delta", raw[: boundary + 1]),
            AgentGatewayEvent("text_delta", raw[boundary + 1 : boundary + 4]),
            AgentGatewayEvent("text_delta", raw[boundary + 4 :]),
            AgentGatewayEvent("run_completed", ""),
        ]
    )
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=lambda **_: context,
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id=f"malformed-machine-{boundary}-{len(raw)}",
            text="설명해줘",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    expected = f"{visible_prefix}\n\n{MANUAL_FALLBACK}"
    deltas = "".join(
        event.text for event in events if event.event_type == "text_delta"
    )
    assert events[-1].event_type == "run_completed"
    assert deltas == events[-1].text == expected
    public = "".join(event.text for event in events)
    assert "reply_text" not in public
    assert "password" not in public
    assert "must-not-publish" not in public
    persisted = store.list_director_messages(
        project_id=project_id,
        conversation_id="conv",
    )[-1]
    assert persisted["text"] == expected
    assert persisted["proposal_id"] is None


def test_no_visible_delta_is_published_before_terminal_store_succeeds() -> None:
    entered = threading.Event()
    release = threading.Event()

    class Store:
        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "durable-first",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def complete_director_hermes_run(self, **_):
            entered.set()
            assert release.wait(timeout=2)
            return True

    service = HermesRunService(
        store=Store(),
        gateway_client=_Gateway(
            [
                AgentGatewayEvent("text_delta", "legacy "),
                AgentGatewayEvent("text_delta", "reply"),
                AgentGatewayEvent("run_completed", "legacy reply"),
            ]
        ),
    )

    async def scenario():
        run = await service.create_run(
            project_id="p",
            session_id="s",
            conversation_id="c",
            client_message_id="durable-first",
            text="q",
        )
        assert await asyncio.to_thread(entered.wait, 1)
        assert [event.event_type for event in run.events] == ["run_started"]
        release.set()
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    assert [event.event_type for event in events] == [
        "run_started",
        "text_delta",
        "run_completed",
    ]
    assert events[1].text == events[2].text == "legacy reply"


def test_live_subscriber_sees_only_durable_visible_draft_before_terminal(
    tmp_path: Path,
) -> None:
    visible = "This durable visible answer is long enough to stream safely."

    class Gateway(_Gateway):
        def __init__(self) -> None:
            super().__init__([])
            self.emitted = asyncio.Event()
            self.release = asyncio.Event()

        async def stream_run(self, **_):
            self.calls += 1
            yield AgentGatewayEvent("text_delta", visible)
            self.emitted.set()
            await self.release.wait()
            yield AgentGatewayEvent("run_completed", visible)

    store, project_id, session_id = _scope(tmp_path)
    gateway = Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="live-durable-draft",
            text="질문",
        )
        await gateway.emitted.wait()
        collected: list = []

        async def consume() -> None:
            async for event in service.subscribe(run.run_id):
                collected.append(event)

        subscriber = asyncio.create_task(consume())
        for _ in range(100):
            if len(collected) >= 2:
                break
            await asyncio.sleep(0.01)
        before_terminal = list(collected)
        durable_before_terminal = store.get_director_hermes_run(
            project_id=project_id,
            run_id=run.run_id,
        )
        gateway.release.set()
        await run.task
        await subscriber
        return before_terminal, durable_before_terminal, collected

    before_terminal, durable, events = asyncio.run(scenario())
    assert [event.event_type for event in before_terminal] == [
        "run_started",
        "text_delta",
    ]
    assert before_terminal[-1].text == visible
    assert durable["status"] == "streaming"
    assert durable["assistant_draft_text"] == visible
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text == visible


def test_cancellation_clears_durable_visible_draft_and_extends_it_with_failure(
    tmp_path: Path,
) -> None:
    visible = "This cancellable durable draft is long enough for live streaming."

    class Gateway(_Gateway):
        def __init__(self) -> None:
            super().__init__([])
            self.emitted = asyncio.Event()
            self.never = asyncio.Event()

        async def stream_run(self, **_):
            yield AgentGatewayEvent("text_delta", visible)
            self.emitted.set()
            await self.never.wait()

    store, project_id, session_id = _scope(tmp_path)
    gateway = Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="cancel-durable-draft",
            text="질문",
        )
        await gateway.emitted.wait()
        before = store.get_director_hermes_run(
            project_id=project_id,
            run_id=run.run_id,
        )
        await service.cancel(run.run_id)
        await asyncio.gather(run.task, return_exceptions=True)
        after = store.get_director_hermes_run(
            project_id=project_id,
            run_id=run.run_id,
        )
        assistant_text = store.list_director_messages(
            project_id=project_id,
            conversation_id="conv",
        )[-1]["text"]
        events = [event async for event in service.subscribe(run.run_id)]
        return before, after, assistant_text, events

    before, after, assistant_text, events = asyncio.run(scenario())
    assert before["assistant_draft_text"] == visible
    assert after["status"] == "interrupted"
    assert after["assistant_draft_text"] == ""
    assert [event.event_type for event in events] == [
        "run_started",
        "text_delta",
        "text_delta",
        "blocked",
    ]
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text == assistant_text
    assert events[-1].text.startswith(visible)


def test_draft_append_cas_loss_publishes_no_delta_and_blocks() -> None:
    class Store:
        def __init__(self) -> None:
            self.append_calls: list[dict] = []
            self.completions: list[dict] = []

        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "draft-cas-loser",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def append_director_hermes_draft(self, **kwargs):
            self.append_calls.append(kwargs)
            return False

        def complete_director_hermes_run(self, **kwargs):
            self.completions.append(kwargs)
            return True

    store = Store()
    service = HermesRunService(
        store=store,
        gateway_client=_Gateway(
            [
                AgentGatewayEvent(
                    "text_delta",
                    "This visible draft is long enough for live streaming.",
                ),
                AgentGatewayEvent("run_completed", "must-not-complete"),
            ]
        ),
    )

    async def scenario():
        run = await service.create_run(
            project_id="project",
            session_id="session",
            conversation_id="conversation",
            client_message_id="draft-cas-loser",
            text="question",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    assert len(store.append_calls) == 1
    assert store.completions[-1]["status"] == "blocked"
    assert events[-1].event_type == "blocked"
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text == store.completions[-1]["assistant_text"]


def test_durable_draft_append_is_owner_fenced_monotonic_and_terminally_cleared(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="draft-store-contract",
        user_text="질문",
        expected_session_revision=1,
        expected_asset_index_revision=0,
    )

    assert store.append_director_hermes_draft(
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        assistant_draft_text="visible",
    )
    assert not store.append_director_hermes_draft(
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        assistant_draft_text="short",
    )
    assert not store.append_director_hermes_draft(
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token="wrong-owner",
        assistant_draft_text="visible extension",
    )
    assert (
        store.get_director_hermes_run(
            project_id=project_id,
            run_id=durable["run_id"],
        )["assistant_draft_text"]
        == "visible"
    )
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="visible",
        retryable=False,
    )
    settled = store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )
    assert settled["assistant_draft_text"] == ""
    assert not store.append_director_hermes_draft(
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        assistant_draft_text="late",
    )


@pytest.mark.parametrize(
    ("limit", "terminal_text"),
    (
        (8, "123456789"),
        (8, "한글한"),
    ),
)
def test_terminal_text_enforces_utf8_byte_cap_before_storage_and_sse(
    tmp_path: Path,
    limit: int,
    terminal_text: str,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    service = HermesRunService(
        store=store,
        gateway_client=_Gateway(
            [AgentGatewayEvent("run_completed", terminal_text)]
        ),
        max_text_bytes=limit,
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id=f"terminal-cap-{limit}-{len(terminal_text)}",
            text="질문",
        )
        await run.task
        return run, [event async for event in service.subscribe(run.run_id)]

    run, events = asyncio.run(scenario())
    assert events[-1].event_type == "blocked"
    assert terminal_text not in "".join(event.text for event in events)
    persisted = store.get_director_hermes_run(
        project_id=project_id,
        run_id=run.run_id,
    )
    assert persisted["status"] == "blocked"
    assert all(
        terminal_text not in message["text"]
        for message in store.list_director_messages(
            project_id=project_id,
            conversation_id="conv",
        )
    )


def test_terminal_text_under_byte_cap_may_differ_from_assembled_but_stays_equal(
    tmp_path: Path,
) -> None:
    terminal_text = "final text under one hundred bytes"
    store, project_id, session_id = _scope(tmp_path)
    service = HermesRunService(
        store=store,
        gateway_client=_Gateway(
            [
                AgentGatewayEvent("text_delta", "draft"),
                AgentGatewayEvent("run_completed", terminal_text),
            ]
        ),
        max_text_bytes=100,
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="terminal-under-cap",
            text="질문",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    assert events[-1].event_type == "run_completed"
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text == terminal_text


def test_post_projection_fallback_expansion_rechecks_utf8_terminal_cap(
    tmp_path: Path,
) -> None:
    raw = 'Visible answer long\n{"reply_text":"truncated"'
    limit = len(raw.encode("utf-8"))
    store, project_id, session_id = _scope(tmp_path)
    service = HermesRunService(
        store=store,
        gateway_client=_Gateway([AgentGatewayEvent("run_completed", raw)]),
        max_text_bytes=limit,
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="post-projection-cap",
            text="question",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    persisted = store.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )[-1]["text"]
    assert events[-1].event_type == "blocked"
    assert len(events[-1].text.encode("utf-8")) <= limit
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text == persisted


@pytest.mark.parametrize(
    "limits",
    (
        {"max_events": 1},
        {"max_event_bytes": 180},
    ),
)
def test_terminal_event_budget_is_preflighted_before_durable_cas(limits: dict) -> None:
    class Store:
        def __init__(self) -> None:
            self.completions: list[dict] = []

        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "terminal-budget",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def complete_director_hermes_run(self, **kwargs):
            self.completions.append(kwargs)
            return True

    store = Store()
    service = HermesRunService(
        store=store,
        gateway_client=_Gateway(
            [AgentGatewayEvent("run_completed", "terminal answer")]
        ),
        **limits,
    )

    async def scenario():
        run = await service.create_run(
            project_id="project",
            session_id="session",
            conversation_id="conversation",
            client_message_id=f"terminal-budget-{limits}",
            text="question",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    assert store.completions[-1]["status"] == "blocked"
    assert events[-1].event_type == "blocked"
    assert events[-1].text == store.completions[-1]["assistant_text"]


def test_terminal_text_that_diverges_after_a_live_draft_fails_closed() -> None:
    class Store:
        def __init__(self) -> None:
            self.completions: list[dict] = []

        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "divergent-live-terminal",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def append_director_hermes_draft(self, **_):
            return True

        def complete_director_hermes_run(self, **kwargs):
            self.completions.append(kwargs)
            return True

    visible = "This live draft is long enough to become publicly visible."
    store = Store()
    service = HermesRunService(
        store=store,
        gateway_client=_Gateway(
            [
                AgentGatewayEvent("text_delta", visible),
                AgentGatewayEvent("run_completed", "A different terminal answer."),
            ]
        ),
    )

    async def scenario():
        run = await service.create_run(
            project_id="project",
            session_id="session",
            conversation_id="conversation",
            client_message_id="divergent-live-terminal",
            text="question",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    assert store.completions[-1]["status"] == "blocked"
    assert [event.event_type for event in events] == [
        "run_started",
        "text_delta",
        "text_delta",
        "blocked",
    ]
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text == store.completions[-1]["assistant_text"]


def test_terminal_cas_loser_cannot_save_orphan_candidate(tmp_path: Path) -> None:
    clock = [datetime(2026, 7, 27, tzinfo=UTC)]
    store, project_id, session_id = _scope(tmp_path, now=lambda: clock[0])
    identity = {
        "project_id": project_id,
        "session_id": session_id,
        "conversation_id": "conv",
        "client_message_id": "cas-proposal",
        "user_text": "추천",
        "expected_session_revision": 1,
        "expected_asset_index_revision": 0,
    }
    first = store.begin_director_hermes_run(**identity)
    clock[0] += timedelta(seconds=301)
    duplicate = store.begin_director_hermes_run(**identity)
    assert duplicate["dispatch"] is False
    assert duplicate["owner_token"] is None
    assert store.recover_interrupted_director_hermes_runs(
        project_id=project_id
    )
    context = _proposal_context().model_copy(
        update={"project_id": project_id, "session_id": session_id}
    )
    proposal = parse_and_project_yujin_creator_output(
        _proposal_output(context),
        context,
        revision=1,
        trusted_project_id=project_id,
        trusted_run_id=first["run_id"],
    ).proposal
    assert proposal is not None

    assert not _complete_director_hermes_run_with_publish(
        store,
        project_id=project_id,
        run_id=first["run_id"],
        owner_token=first["owner_token"],
        status="completed",
        assistant_text="산책 영상을 추천합니다.",
        retryable=False,
        proposal=proposal,
    )
    assert store.list_director_proposals(project_id) == []


def test_preexisting_trusted_proposal_id_discards_candidate_but_keeps_reply(
    tmp_path: Path,
) -> None:
    class Gateway(_Gateway):
        def __init__(self, raw: str) -> None:
            super().__init__()
            self.raw = raw
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def stream_run(self, **_):
            self.calls += 1
            self.entered.set()
            await self.release.wait()
            yield AgentGatewayEvent("run_completed", self.raw)

    store, project_id, session_id = _scope(tmp_path)
    context = _proposal_context().model_copy(
        update={"project_id": project_id, "session_id": session_id}
    )
    gateway = Gateway(_proposal_output(context))
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=lambda **_: context,
    )

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="preexisting-proposal",
            text="추천해줘",
        )
        await gateway.entered.wait()
        preexisting = parse_and_project_yujin_creator_output(
            gateway.raw,
            context,
            revision=1,
            trusted_project_id=project_id,
            trusted_run_id=run.run_id,
        ).proposal
        assert preexisting is not None
        store.save_director_proposal(project_id, preexisting)
        gateway.release.set()
        await run.task
        return preexisting, [
            event async for event in service.subscribe(run.run_id)
        ]

    preexisting, events = asyncio.run(scenario())
    assert events[-1].event_type == "run_completed"
    assert events[-1].text.startswith("산책 영상을 추천합니다.")
    assert MANUAL_FALLBACK in events[-1].text
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text
    proposals = store.list_director_proposals(project_id)
    assert [proposal.proposal_id for proposal in proposals] == [
        preexisting.proposal_id
    ]
    message = store.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )[-1]
    assert message["text"] == events[-1].text
    assert message["proposal_id"] is None


def test_proposal_insert_race_retries_terminal_cas_without_candidate() -> None:
    class Store:
        def __init__(self) -> None:
            self.completions: list[dict] = []

        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "race-run",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def director_proposal_exists(self, **_):
            return False

        def complete_director_hermes_run(self, **kwargs):
            self.completions.append(kwargs)
            return "proposal_conflict" if len(self.completions) == 1 else True

    context = _proposal_context()
    store = Store()
    service = HermesRunService(
        store=store,
        gateway_client=_Gateway(
            [
                AgentGatewayEvent(
                    "run_completed",
                    _proposal_output(context),
                    publish_capability_token="header.publish.signature",
                )
            ]
        ),
        context_builder=lambda **_: context,
    )

    async def scenario():
        run = await service.create_run(
            project_id=context.project_id,
            session_id=context.session_id,
            conversation_id="conversation",
            client_message_id="race",
            text="추천",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    assert len(store.completions) == 2
    assert store.completions[0]["proposal"] is not None
    assert store.completions[1]["proposal"] is None
    assert MANUAL_FALLBACK in store.completions[1]["assistant_text"]
    assert events[-1].event_type == "run_completed"
    assert events[-1].text == store.completions[1]["assistant_text"]


def test_proposal_stale_retries_terminal_cas_without_candidate() -> None:
    class Store:
        def __init__(self) -> None:
            self.completions: list[dict] = []

        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "stale-run",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def director_proposal_exists(self, **_):
            return False

        def complete_director_hermes_run(self, **kwargs):
            self.completions.append(kwargs)
            return "proposal_stale" if len(self.completions) == 1 else True

    context = _proposal_context()
    store = Store()
    service = HermesRunService(
        store=store,
        gateway_client=_Gateway(
            [
                AgentGatewayEvent(
                    "run_completed",
                    _proposal_output(context),
                    publish_capability_token="header.publish.signature",
                )
            ]
        ),
        context_builder=lambda **_: context,
    )

    async def scenario():
        run = await service.create_run(
            project_id=context.project_id,
            session_id=context.session_id,
            conversation_id="conversation",
            client_message_id="stale",
            text="추천",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    assert len(store.completions) == 2
    assert store.completions[0]["proposal"] is not None
    assert store.completions[1]["proposal"] is None
    assert MANUAL_FALLBACK in store.completions[1]["assistant_text"]
    assert events[-1].event_type == "run_completed"
    assert events[-1].text == store.completions[1]["assistant_text"]


def test_changed_text_conflicts_and_owner_token_fences_stale_finalizer(
    tmp_path: Path,
) -> None:
    clock = [datetime(2026, 7, 26, tzinfo=UTC)]
    store, project_id, session_id = _scope(tmp_path, now=lambda: clock[0])
    context_identity = {
        "expected_session_revision": store.get_editing_session(
            project_id=project_id, session_id=session_id
        )["session_revision"],
        "expected_asset_index_revision": store.get_asset_index_revision(project_id),
    }
    first = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="same",
        user_text="one",
        **context_identity,
    )
    with pytest.raises(
        ValueError, match="client_message_id_reused_with_different_content"
    ):
        store.begin_director_hermes_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="same",
            user_text="changed",
            **context_identity,
        )
    clock[0] += timedelta(seconds=301)
    restarted = LocalProjectStore(tmp_path / "projects", now=lambda: clock[0])
    duplicate = restarted.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="same",
        user_text="one",
        **context_identity,
    )
    assert duplicate["run_id"] == first["run_id"]
    assert duplicate["dispatch"] is False
    assert duplicate["owner_token"] is None
    assert restarted.recover_interrupted_director_hermes_runs(
        project_id=project_id
    )
    assert not restarted.complete_director_hermes_run(
        project_id=project_id,
        run_id=first["run_id"],
        owner_token=first["owner_token"],
        status="completed",
        assistant_text="winner",
        retryable=False,
    )
    assert [item["text"] for item in restarted.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )] == [
        "one",
        "Hermes is temporarily unavailable. Manual Director remains available.",
    ]


@pytest.mark.parametrize("store_result", [False, RuntimeError("db unavailable")])
def test_terminal_cas_failure_still_publishes_one_blocked_terminal(store_result) -> None:
    class Store:
        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "r",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def complete_director_hermes_run(self, **_):
            if isinstance(store_result, Exception):
                raise store_result
            return store_result

    service = HermesRunService(store=Store(), gateway_client=_Gateway())

    async def scenario():
        run = await service.create_run(
            project_id="p",
            session_id="s",
            conversation_id="c",
            client_message_id="m",
            text="q",
        )
        await run.task
        return [event async for event in service.subscribe(run.run_id)]

    events = asyncio.run(scenario())
    assert events[-1].event_type == "blocked"
    assert sum(event.event_type == "blocked" for event in events) == 1
    assert events[-1].retryable is True
    assert "".join(
        event.text for event in events if event.event_type == "text_delta"
    ) == events[-1].text


def test_hermes_capability_ledger_outage_discards_token_and_releases_without_retry() -> None:
    token_fragment = "ledger-outage-publish-secret"

    class Store:
        proposal_writes = 0

        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "ledger-outage-run",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def register_hermes_run_capabilities(self, **_):
            raise OSError("ledger unavailable")

        def revoke_issued_hermes_capabilities(self, **_):
            raise OSError("ledger unavailable")

        def complete_director_hermes_run(self, **_):
            raise OSError("ledger unavailable")

    class Gateway(_Gateway):
        def __init__(self):
            super().__init__()
            self.releases: list[str] = []
            self.provider_calls = 0

        async def reserve_run(self, **values):
            reservation = _gateway_reservation(str(values["run_id"]))
            return reservation.model_copy(
                update={
                    "read_capability_token": (
                        f"header.{token_fragment}.signature"
                    ),
                }
            )

        async def release_run(self, *, run_id: str):
            self.releases.append(run_id)

        async def stream_run(self, **_):
            self.provider_calls += 1
            yield AgentGatewayEvent(
                "run_completed",
                "must not dispatch",
                publish_capability_token=(
                    f"header.{token_fragment}.signature"
                ),
            )

    store = Store()
    gateway = Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario():
        with pytest.raises(
            HermesContextPreparationUnavailable,
            match="^hermes_context_preparation_unavailable$",
        ) as caught:
            await service.create_run(
                project_id="project",
                session_id="session",
                conversation_id="conversation",
                client_message_id="ledger-outage",
                text="question",
            )
        return caught.value

    error = asyncio.run(scenario())
    assert gateway.releases == ["ledger-outage-run"]
    assert gateway.provider_calls == 0
    assert store.proposal_writes == 0
    assert token_fragment not in repr(error)
    assert service.diagnostics() == {
        "closing": False,
        "active": 0,
        "waiting": 0,
        "admissions": 0,
        "dispatch": 0,
        "terminal": 0,
        "cleanup": 0,
    }


def test_hermes_capability_lifespan_reconciles_after_persistent_ledger_outage() -> None:
    recovered = asyncio.Event()

    class Store:
        def __init__(self) -> None:
            self.list_calls = 0
            self.recovery_calls = 0
            self.provider_calls = 0

        def list_projects(self):
            self.list_calls += 1
            if self.list_calls <= 3:
                raise OSError("ledger unavailable")
            return [{"project_id": "project"}]

        def recover_interrupted_director_hermes_runs(self, *, project_id: str):
            assert project_id == "project"
            self.recovery_calls += 1
            recovered.set()
            return [{"run_id": "old-key-run", "status": "interrupted"}]

        def recover_orphaned_media_analysis_jobs(self, *, project_id: str):
            return []

        def list_media_analysis(self, *, project_id: str):
            return []

        def prune_director_hermes_run_events(self, **_):
            return 0

    store = Store()
    app = SimpleNamespace(
        state=SimpleNamespace(
            store=store,
            media_analysis_dispatcher=None,
            media_analysis_poll_interval_seconds=0.01,
            hermes_run_service=None,
        )
    )

    async def scenario() -> None:
        async with _media_analysis_lifespan(app):
            await asyncio.wait_for(recovered.wait(), timeout=1)

    asyncio.run(scenario())
    assert store.recovery_calls >= 1
    assert store.provider_calls == 0


def test_gateway_release_cannot_delay_terminal_delivery() -> None:
    release_entered = asyncio.Event()
    release_allowed = asyncio.Event()

    class Gateway(_Gateway):
        async def release_run(self, **_):
            release_entered.set()
            await release_allowed.wait()

    service = HermesRunService(
        store=_ThreadBlockedStore(),
        gateway_client=Gateway(),
    )
    service.store.begin_release.set()

    async def scenario() -> list:
        run = await service.create_run(
            project_id="p",
            session_id="s",
            conversation_id="c",
            client_message_id="release-does-not-block-terminal",
            text="q",
        )
        await asyncio.wait_for(release_entered.wait(), timeout=1)
        events = await asyncio.wait_for(
            _collect(service.subscribe(run.run_id)),
            timeout=0.1,
        )
        release_allowed.set()
        await asyncio.wait_for(service.shutdown(), timeout=1)
        return events

    async def _collect(events):
        return [event async for event in events]

    events = asyncio.run(scenario())
    assert events[-1].event_type == "run_completed"
    assert sum(event.event_type == "run_completed" for event in events) == 1


def test_cancellation_during_terminal_store_cannot_leave_subscriber_hanging() -> None:
    entered = threading.Event()
    release = threading.Event()

    class Store:
        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "r",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def complete_director_hermes_run(self, **_):
            entered.set()
            assert release.wait(timeout=2)
            return True

    gateway = _Gateway(events=[AgentGatewayEvent("run_completed", "answer")])
    service = HermesRunService(store=Store(), gateway_client=gateway)

    async def scenario():
        run = await service.create_run(
            project_id="p",
            session_id="s",
            conversation_id="c",
            client_message_id="m",
            text="q",
        )
        assert await asyncio.to_thread(entered.wait, 1)
        run.task.cancel()
        release.set()
        await asyncio.gather(run.task, return_exceptions=True)
        return await asyncio.wait_for(
            _collect(service.subscribe(run.run_id)),
            timeout=1,
        )

    async def _collect(events):
        return [event async for event in events]

    events = asyncio.run(scenario())
    assert events[-1].event_type in {"run_completed", "blocked"}
    assert sum(event.event_type in {"run_completed", "blocked"} for event in events) == 1


def test_pre_entry_dispatch_cancel_releases_slot_fifty_times() -> None:
    async def scenario() -> None:
        for index in range(50):
            service = HermesRunService(
                store=_ThreadBlockedStore(),
                gateway_client=_Gateway(),
                max_active=1,
                max_queue=0,
            )
            service.store.begin_release.set()
            run = await service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id=f"pre-entry-{index}",
                text="q",
            )
            assert run.task is not None
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
            await asyncio.wait_for(service.shutdown(), timeout=1)
            assert service.diagnostics() == {
                "closing": True,
                "active": 0,
                "waiting": 0,
                "admissions": 0,
                "dispatch": 0,
                "terminal": 0,
                "cleanup": 0,
            }

    asyncio.run(scenario())


def test_shutdown_active_and_queued_runs_never_promotes_after_close_fifty_times() -> None:
    async def scenario() -> None:
        for index in range(50):
            gateway = _BlockingGateway()
            store = _ThreadBlockedStore()
            store.begin_release.set()
            service = HermesRunService(
                store=store,
                gateway_client=gateway,
                max_active=1,
                max_queue=1,
            )
            first = await service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id=f"active-{index}",
                text="q",
            )
            await asyncio.wait_for(gateway.entered.wait(), timeout=1)
            second = await service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id=f"queued-{index}",
                text="q",
            )
            await asyncio.wait_for(service.shutdown(), timeout=1)
            assert gateway.calls == 1
            assert first.terminal is True
            assert second.terminal is True
            assert service.diagnostics()["active"] == 0
            assert service.diagnostics()["waiting"] == 0

    asyncio.run(scenario())


def test_shutdown_settles_late_committed_admission_without_dispatch() -> None:
    store = _ThreadBlockedStore()
    gateway = _Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario() -> None:
        create = asyncio.create_task(
            service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id="late",
                text="q",
            )
        )
        assert await asyncio.to_thread(store.begin_entered.wait, 1)
        shutdown = asyncio.create_task(service.shutdown())
        await asyncio.sleep(0)
        store.begin_release.set()
        await asyncio.wait_for(asyncio.gather(create, shutdown), timeout=2)
        assert gateway.calls == 0
        assert len(store.completions) == 1
        assert store.completions[0]["status"] == "blocked"
        assert service.diagnostics()["active"] == 0
        assert service.diagnostics()["waiting"] == 0

    asyncio.run(scenario())


def test_cancelled_admission_cannot_leave_durable_pending_orphan() -> None:
    store = _ThreadBlockedStore()
    gateway = _Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario() -> None:
        create = asyncio.create_task(
            service.create_run(
                project_id="p",
                session_id="s",
                conversation_id="c",
                client_message_id="cancelled-admission",
                text="q",
            )
        )
        assert await asyncio.to_thread(store.begin_entered.wait, 1)
        assert await service.reconciliation_excluded_run_ids() is None
        create.cancel()
        store.begin_release.set()
        with pytest.raises(asyncio.CancelledError):
            await create
        await asyncio.wait_for(service.shutdown(), timeout=2)
        assert gateway.calls == 0
        assert len(store.completions) == 1
        assert store.completions[0]["status"] == "blocked"
        assert service.diagnostics()["admissions"] == 0

    asyncio.run(scenario())


def test_one_cancelled_duplicate_waiter_does_not_abort_the_remaining_waiter() -> None:
    store = _ThreadBlockedStore()
    gateway = _Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario():
        arguments = {
            "project_id": "p",
            "session_id": "s",
            "conversation_id": "c",
            "client_message_id": "shared-admission",
            "text": "q",
        }
        cancelled = asyncio.create_task(service.create_run(**arguments))
        remaining = asyncio.create_task(service.create_run(**arguments))
        assert await asyncio.to_thread(store.begin_entered.wait, 1)
        cancelled.cancel()
        store.begin_release.set()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        run = await asyncio.wait_for(remaining, timeout=1)
        assert run.task is not None
        await run.task
        events = [event async for event in service.subscribe(run.run_id)]
        await service.shutdown()
        return events

    events = asyncio.run(scenario())
    assert gateway.calls == 1
    assert store.completions[0]["status"] == "completed"
    assert events[-1].event_type == "run_completed"


def test_repeated_terminal_cancellation_awaits_one_owned_terminal_task() -> None:
    entered = threading.Event()
    release = threading.Event()

    class Store:
        def begin_director_hermes_run(self, **_):
            return {
                "run_id": "owned-terminal",
                "status": "pending",
                "owner_token": "owner",
                "dispatch": True,
            }

        def complete_director_hermes_run(self, **_):
            entered.set()
            assert release.wait(timeout=3)
            return True

    service = HermesRunService(
        store=Store(),
        gateway_client=_Gateway(
            events=[AgentGatewayEvent("run_completed", "answer")]
        ),
    )

    async def scenario():
        run = await service.create_run(
            project_id="p",
            session_id="s",
            conversation_id="c",
            client_message_id="owned-terminal",
            text="q",
        )
        assert await asyncio.to_thread(entered.wait, 1)
        cancellers = [
            asyncio.create_task(service.cancel(run.run_id)) for _ in range(5)
        ]
        for task in cancellers:
            task.cancel()
        release.set()
        await asyncio.gather(*cancellers, return_exceptions=True)
        await asyncio.wait_for(service.shutdown(), timeout=2)
        events = [event async for event in service.subscribe(run.run_id)]
        return run, events

    run, events = asyncio.run(scenario())
    assert run.terminalizing is False
    assert sum(
        event.event_type in {"run_completed", "blocked"} for event in events
    ) == 1


def test_postgres_translation_preserves_atomic_upsert_contract() -> None:
    statement = (
        "INSERT INTO director_hermes_runs (run_id, conversation_id, "
        "client_message_id) VALUES (?, ?, ?) "
        "ON CONFLICT (conversation_id, client_message_id) DO NOTHING"
    )
    translated = translate_sql(statement)
    assert "ON CONFLICT (conversation_id, client_message_id) DO NOTHING" in translated
    assert translated.count("%s") == 3

    cas = translate_sql(
        "UPDATE director_hermes_runs SET status = ? "
        "WHERE project_id = ? AND run_id = ? AND status = 'pending' "
        "AND owner_token = ?"
    )
    assert "status = 'pending'" in cas
    assert "owner_token = %s" in cas
    assert cas.count("%s") == 4

    proposal_exists = translate_sql(
        "SELECT 1 FROM director_proposals "
        "WHERE project_id = ? AND proposal_id = ?"
    )
    assert "project_id = %s" in proposal_exists
    assert "proposal_id = %s" in proposal_exists
    assert proposal_exists.count("%s") == 2

    draft_cas = translate_sql(
        "UPDATE director_hermes_runs SET assistant_draft_text = ? "
        "WHERE project_id = ? AND run_id = ? AND status = 'pending' "
        "AND owner_token = ? "
        "AND substr(?, 1, length(assistant_draft_text)) = assistant_draft_text"
    )
    assert "assistant_draft_text = %s" in draft_cas
    assert "owner_token = %s" in draft_cas
    assert "substr(%s, 1, length(assistant_draft_text))" in draft_cas
    assert draft_cas.count("%s") == 5


def test_completed_run_replays_durable_text_after_process_restart(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    first_gateway = _Gateway()

    async def complete_once():
        first = HermesRunService(store=store, gateway_client=first_gateway)
        run = await first.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="restart",
            text="question",
        )
        await run.task

    asyncio.run(complete_once())
    restarted_gateway = _Gateway()

    async def replay():
        restarted = HermesRunService(
            store=LocalProjectStore(tmp_path / "projects"),
            gateway_client=restarted_gateway,
        )
        run = await restarted.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="restart",
            text="question",
        )
        return [event async for event in restarted.subscribe(run.run_id)]

    events = asyncio.run(replay())
    assert [event.event_type for event in events] == [
        "run_started",
        "text_delta",
        "run_completed",
    ]
    assert events[-1].text == "안녕하세요"
    assert restarted_gateway.calls == 0


def test_reverse_exchange_uses_durable_message_links_not_adjacency(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    context_identity = {
        "expected_session_revision": store.get_editing_session(
            project_id=project_id, session_id=session_id
        )["session_revision"],
        "expected_asset_index_revision": store.get_asset_index_revision(project_id),
    }
    durable = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="linked",
        user_text="question",
        **context_identity,
    )
    store.append_director_message(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        role="user",
        text="interleaved",
        client_message_id="manual",
    )
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="linked answer",
        retryable=False,
    )

    exchange = store.get_director_exchange_by_client_message_id(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="linked",
        user_text="question",
    )
    assert exchange is not None
    assert exchange["user_message"]["text"] == "question"
    assert exchange["assistant_message"]["text"] == "linked answer"
