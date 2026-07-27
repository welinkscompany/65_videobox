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

from videobox_api.agent_gateway_client import AgentGatewayEvent
from videobox_api.hermes_run_service import HermesRunService
from videobox_domain_models.assets import AssetType
from videobox_domain_models.director_proposals import DirectorCandidate, DirectorProposal
from videobox_core_engine.yujin_creator_proposal_adapter import (
    MANUAL_FALLBACK,
    parse_and_project_yujin_creator_output,
)
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


def _scope(tmp_path: Path, *, now=None):
    store = LocalProjectStore(tmp_path / "projects", now=now)
    project = store.bootstrap_project("hermes")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": []},
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


class _BlockingGateway:
    def __init__(self) -> None:
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.preparations = 0

    async def prepare_run(self, **_):
        self.preparations += 1

    async def stream_run(self, **_):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        yield AgentGatewayEvent("run_completed", "answer")


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

    result = store.complete_director_hermes_run(
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

    assert store.complete_director_hermes_run(
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
    assert [item.proposal_id for item in store.list_director_proposals(project_id)] == [
        proposal.proposal_id
    ]
    assistant = store.list_director_messages(
        project_id=project_id,
        conversation_id="conv",
    )[-1]
    assert assistant["proposal_id"] == proposal.proposal_id


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
        [AgentGatewayEvent("run_completed", _proposal_output(context))]
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
        await asyncio.sleep(0)
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
    assert durable["status"] == "pending"
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
    assert after["status"] == "blocked"
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
    winner = store.begin_director_hermes_run(**identity)
    context = _proposal_context().model_copy(
        update={"project_id": project_id, "session_id": session_id}
    )
    proposal = parse_and_project_yujin_creator_output(
        _proposal_output(context),
        context,
        revision=1,
        trusted_project_id=project_id,
        trusted_run_id=winner["run_id"],
    ).proposal
    assert proposal is not None

    assert not store.complete_director_hermes_run(
        project_id=project_id,
        run_id=first["run_id"],
        owner_token=first["owner_token"],
        status="completed",
        assistant_text="산책 영상을 추천합니다.",
        retryable=False,
        proposal=proposal,
    )
    assert store.list_director_proposals(project_id) == []
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=winner["run_id"],
        owner_token=winner["owner_token"],
        status="completed",
        assistant_text="산책 영상을 추천합니다.",
        retryable=False,
        proposal=proposal,
    )
    assert [item.proposal_id for item in store.list_director_proposals(project_id)] == [
        proposal.proposal_id
    ]


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
            [AgentGatewayEvent("run_completed", _proposal_output(context))]
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
            [AgentGatewayEvent("run_completed", _proposal_output(context))]
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
    reclaimed = restarted.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="same",
        user_text="one",
        **context_identity,
    )
    assert reclaimed["run_id"] == first["run_id"]
    assert reclaimed["dispatch"] is True
    assert reclaimed["owner_token"] != first["owner_token"]
    assert not restarted.complete_director_hermes_run(
        project_id=project_id,
        run_id=first["run_id"],
        owner_token=first["owner_token"],
        status="completed",
        assistant_text="winner",
        retryable=False,
    )
    assert restarted.complete_director_hermes_run(
        project_id=project_id,
        run_id=first["run_id"],
        owner_token=reclaimed["owner_token"],
        status="completed",
        assistant_text="winner",
        retryable=False,
    )
    assert [item["text"] for item in restarted.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )] == ["one", "winner"]


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
