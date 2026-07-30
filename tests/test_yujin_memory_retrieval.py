from __future__ import annotations

import asyncio
import pytest

from videobox_api.yujin_memory_service import YujinMemoryService
from videobox_core_engine.yujin_creator_context import (
    _fit_context,
    attach_yujin_memories,
    canonical_creator_context_json,
)
from videobox_domain_models.yujin_creator_context import (
    UserApprovedPreference,
    YujinCreatorContext,
)
from videobox_storage.local_project_store import LocalProjectStore


def _stored(
    *,
    candidate_id: str,
    memory_ref: str,
    external_ref: str,
    text: str,
    category: str = "pacing",
    project_id: str = "project-a",
    conversation_id: str = "conversation-a",
    status: str = "approved",
    storage_status: str = "stored",
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "project_id": project_id,
        "conversation_id": conversation_id,
        "status": status,
        "storage_status": storage_status,
        "memory_ref": memory_ref,
        "external_ref": external_ref,
        "text": text,
        "category": category,
    }


class _Store:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, str]] = []

    def list_yujin_memory_retrieval_rows(
        self, *, project_id: str, conversation_id: str
    ) -> list[dict[str, object]]:
        self.calls.append((project_id, conversation_id))
        return list(self.rows)


class _Gateway:
    def __init__(self, memories: object, *, delay: float = 0) -> None:
        self.memories = memories
        self.delay = delay
        self.requests = []

    async def search_memory(self, request):
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        return {"memories": self.memories}


def test_retrieval_cross_checks_exact_current_private_stored_rows() -> None:
    external_a = "ext-" + "a" * 64
    external_b = "ext-" + "b" * 64
    rows = [
        _stored(
            candidate_id="candidate-a",
            memory_ref="memory-a",
            external_ref=external_a,
            text="빠른 컷 편집을 선호합니다.",
        ),
        _stored(
            candidate_id="candidate-b",
            memory_ref="memory-b",
            external_ref=external_b,
            text="자막은 두 줄 이내를 선호합니다.",
            category="caption",
        ),
        _stored(
            candidate_id="candidate-pending",
            memory_ref="memory-pending",
            external_ref="ext-" + "c" * 64,
            text="대기 중 후보",
            status="pending",
            storage_status="not_requested",
        ),
        _stored(
            candidate_id="candidate-rejected",
            memory_ref="memory-rejected",
            external_ref="ext-" + "d" * 64,
            text="거절 후보",
            status="rejected",
            storage_status="not_requested",
        ),
        _stored(
            candidate_id="candidate-failed",
            memory_ref="memory-failed",
            external_ref="ext-" + "e" * 64,
            text="저장 실패 후보",
            storage_status="failed_retryable",
        ),
        _stored(
            candidate_id="candidate-deleted",
            memory_ref="memory-deleted",
            external_ref="ext-" + "f" * 64,
            text="삭제 후보",
            storage_status="deleted",
        ),
    ]
    gateway = _Gateway(
        [
            {
                "memory_ref": "memory-b",
                "external_ref": external_b,
                "text": "자막은 두 줄 이내를 선호합니다.",
                "category": "caption",
            },
            {
                "memory_ref": "memory-a",
                "external_ref": external_a,
                "text": "빠른 컷 편집을 선호합니다.",
                "category": "pacing",
            },
            # Exact duplicate must collapse.
            {
                "memory_ref": "memory-a",
                "external_ref": external_a,
                "text": "빠른 컷 편집을 선호합니다.",
                "category": "pacing",
            },
            # Provider/local mismatches and unrelated rows must not enter.
            {
                "memory_ref": "memory-a",
                "external_ref": external_a,
                "text": "위조된 텍스트",
                "category": "pacing",
            },
            {
                "memory_ref": "memory-other",
                "external_ref": "ext-" + "9" * 64,
                "text": "다른 프로젝트 기억",
                "category": "tone",
            },
        ]
    )
    service = YujinMemoryService(store=_Store(rows), gateway=gateway)

    memories = asyncio.run(
        service.retrieve_approved_memories(
            project_id="project-a",
            conversation_id="conversation-a",
            query="편집 템포와 자막",
        )
    )

    assert [item.model_dump() for item in memories] == [
        {
            "kind": "user_approved_preference",
            "category": "caption",
            "text": "자막은 두 줄 이내를 선호합니다.",
        },
        {
            "kind": "user_approved_preference",
            "category": "pacing",
            "text": "빠른 컷 편집을 선호합니다.",
        },
    ]
    assert len(gateway.requests) == 1
    assert gateway.requests[0].limit == 5
    assert not hasattr(memories[0], "memory_ref")
    assert not hasattr(memories[0], "external_ref")


def test_provider_cannot_revive_non_approved_or_non_stored_local_rows() -> None:
    rows = [
        _stored(
            candidate_id=f"candidate-{index}",
            memory_ref=f"memory-{index}",
            external_ref="ext-" + str(index) * 64,
            text=f"제외 대상 {index}",
            status=status,
            storage_status=storage_status,
        )
        for index, (status, storage_status) in enumerate(
            (
                ("pending", "not_requested"),
                ("rejected", "not_requested"),
                ("approved", "failed_retryable"),
                ("approved", "deleted"),
            ),
            start=1,
        )
    ]
    rows.append(
        _stored(
            candidate_id="candidate-valid",
            memory_ref="memory-valid",
            external_ref="ext-" + "a" * 64,
            text="검증된 취향",
        )
    )
    gateway = _Gateway(
        [
            {
                "memory_ref": row["memory_ref"],
                "external_ref": row["external_ref"],
                "text": row["text"],
                "category": row["category"],
            }
            for row in rows
        ]
    )
    service = YujinMemoryService(store=_Store(rows), gateway=gateway)

    memories = asyncio.run(
        service.retrieve_approved_memories(
            project_id="project-a",
            conversation_id="conversation-a",
            query="이전 편집 취향",
        )
    )
    assert [item.text for item in memories] == ["검증된 취향"]
    assert len(gateway.requests) == 1


def test_retrieval_bounds_five_items_and_total_text_to_1400() -> None:
    rows = []
    provider = []
    for index in range(7):
        external_ref = "ext-" + f"{index + 1:x}" * 64
        text = chr(ord("가") + index) * 280
        rows.append(
            _stored(
                candidate_id=f"candidate-{index}",
                memory_ref=f"memory-{index}",
                external_ref=external_ref,
                text=text,
                category="workflow",
            )
        )
        provider.append(
            {
                "memory_ref": f"memory-{index}",
                "external_ref": external_ref,
                "text": text,
                "category": "workflow",
            }
        )
    service = YujinMemoryService(
        store=_Store(rows), gateway=_Gateway(provider[:5])
    )

    memories = asyncio.run(
        service.retrieve_approved_memories(
            project_id="project-a",
            conversation_id="conversation-a",
            query="작업 방식",
        )
    )

    assert len(memories) == 5
    assert sum(len(item.text) for item in memories) <= 1400
    assert tuple(item.text for item in memories) == tuple(
        sorted(item.text for item in memories)
    )


def test_retrieval_timeout_outage_and_malformed_fall_back_without_retry() -> None:
    row = _stored(
        candidate_id="candidate-a",
        memory_ref="memory-a",
        external_ref="ext-" + "a" * 64,
        text="빠른 컷 편집을 선호합니다.",
    )

    timeout_gateway = _Gateway([], delay=1)
    timeout_service = YujinMemoryService(
        store=_Store([row]), gateway=timeout_gateway
    )
    async def exercise_timeout():
        loop = asyncio.get_running_loop()
        started = loop.time()
        result = await timeout_service.retrieve_approved_memories(
            project_id="project-a",
            conversation_id="conversation-a",
            query="편집 템포",
        )
        return result, loop.time() - started

    timeout_result, elapsed = asyncio.run(exercise_timeout())
    assert timeout_result == ()
    assert elapsed < 0.9
    assert len(timeout_gateway.requests) == 1

    malformed_gateway = _Gateway([{"raw_provider_body": "unsafe"}])
    malformed_service = YujinMemoryService(
        store=_Store([row]), gateway=malformed_gateway
    )
    assert asyncio.run(
        malformed_service.retrieve_approved_memories(
            project_id="project-a",
            conversation_id="conversation-a",
            query="편집 템포",
        )
    ) == ()
    assert len(malformed_gateway.requests) == 1

    oversized_gateway = _Gateway(
        [
            {
                "memory_ref": "memory-a",
                "external_ref": "ext-" + "a" * 64,
                "text": "가" * 281,
                "category": "pacing",
            }
        ]
    )
    oversized_service = YujinMemoryService(
        store=_Store([row]), gateway=oversized_gateway
    )
    assert asyncio.run(
        oversized_service.retrieve_approved_memories(
            project_id="project-a",
            conversation_id="conversation-a",
            query="편집 템포",
        )
    ) == ()
    assert len(oversized_gateway.requests) == 1

    unavailable_service = YujinMemoryService(
        store=_Store([row]), gateway=None
    )
    assert asyncio.run(
        unavailable_service.retrieve_approved_memories(
            project_id="project-a",
            conversation_id="conversation-a",
            query="편집 템포",
        )
    ) == ()


@pytest.mark.parametrize(
    "unsafe_suffix",
    [
        " API_KEY=sk-live-secret-value-123456",
        r" C:\Users\owner\private.txt",
        " https://private.example.invalid/token",
        " bearer credential-value",
    ],
)
def test_retrieval_scans_full_original_prompt_before_truncation(
    unsafe_suffix: str,
) -> None:
    row = _stored(
        candidate_id="candidate-a",
        memory_ref="memory-a",
        external_ref="ext-" + "a" * 64,
        text="빠른 컷 편집을 선호합니다.",
    )
    gateway = _Gateway([])
    service = YujinMemoryService(store=_Store([row]), gateway=gateway)

    assert asyncio.run(
        service.retrieve_approved_memories(
            project_id="project-a",
            conversation_id="conversation-a",
            query=("안전한 편집 요청 " + "가" * 280 + unsafe_suffix),
        )
    ) == ()
    assert gateway.requests == []


def test_creator_context_accepts_only_id_free_user_approved_advisory_memories() -> None:
    context = YujinCreatorContext.model_validate(
        {
            "schema_version": "videobox.yujin-context.v1",
            "project_id": "project-a",
            "session_id": "session-a",
            "session_revision": 1,
            "asset_index_revision": 0,
            "timeline_id": "timeline-a",
            "timeline_version": "v1",
            "selected_script_id": None,
            "selected_segment_id": None,
            "segment_summaries": (),
            "media_candidates": (),
            "approved_tts_candidates": (),
            "timeline_summary": {
                "duration_sec": 0.0,
                "track_count": 0,
                "clip_count": 0,
                "gap_count": 0,
            },
            "supported_controls": (),
            "memories": (
                {
                    "kind": "user_approved_preference",
                    "category": "tone",
                    "text": "차분한 분위기를 선호합니다.",
                },
            ),
        }
    )

    dumped = context.model_dump(mode="json")
    assert dumped["memories"] == [
        {
            "kind": "user_approved_preference",
            "category": "tone",
            "text": "차분한 분위기를 선호합니다.",
        }
    ]
    assert "memory_ref" not in str(dumped["memories"])
    with pytest.raises(ValueError):
        YujinCreatorContext.model_validate(
            {
                **dumped,
                "memories": (
                    {
                        "kind": "system_instruction",
                        "category": "tone",
                        "text": "반드시 적용",
                    },
                ),
            }
        )


def test_creator_context_drops_memory_first_at_48kb_boundary() -> None:
    oversized = YujinCreatorContext.model_validate(
        {
            "schema_version": "videobox.yujin-context.v1",
            "project_id": "project-a",
            "session_id": "session-a",
            "session_revision": 1,
            "asset_index_revision": 0,
            "timeline_id": "timeline-a",
            "timeline_version": "v1",
            "selected_script_id": None,
            "selected_segment_id": None,
            "segment_summaries": tuple(
                {
                    "segment_id": f"segment-{index}-" + "s" * 230,
                    "start_sec": float(index),
                    "end_sec": float(index + 1),
                    "text": "가" * 80,
                }
                for index in range(32)
            ),
            "media_candidates": tuple(
                {
                    "asset_id": f"asset-{index}-" + "a" * 230,
                    "kind": "image",
                    "title": "t" * 128,
                    "duration_sec": None,
                    "tags": tuple("z" * 64 for _ in range(8)),
                }
                for index in range(48)
            ),
            "approved_tts_candidates": (),
            "memories": (),
            "timeline_summary": {
                "duration_sec": 32.0,
                "track_count": 1,
                "clip_count": 32,
                "gap_count": 0,
            },
            "supported_controls": (),
        }
    )
    fitted = _fit_context(oversized)
    original_candidates = fitted.media_candidates
    memories = tuple(
        UserApprovedPreference(
            kind="user_approved_preference",
            category="workflow",
            text=chr(ord("가") + index) * 280,
        )
        for index in range(5)
    )

    attached = attach_yujin_memories(fitted, memories)

    assert len(canonical_creator_context_json(attached).encode("utf-8")) <= 48_000
    assert attached.memories == ()
    assert attached.media_candidates == original_candidates


def test_new_owned_dispatch_searches_once_but_replay_and_unsafe_do_not() -> None:
    """The integration hook must be explicit and fail-open for manual editing."""
    gateway = _Gateway([])
    service = YujinMemoryService(
        store=_Store([
            _stored(
                candidate_id="candidate-a",
                memory_ref="memory-a",
                external_ref="ext-" + "a" * 64,
                text="빠른 컷 편집을 선호합니다.",
            )
        ]),
        gateway=gateway,
    )

    # This desired helper is called only from the durable dispatch-owned branch.
    async def exercise():
        owned = await service.retrieve_for_new_owned_dispatch(
            dispatch=True,
            owner_token="owner",
            project_id="project-a",
            conversation_id="conversation-a",
            query="새 요청",
        )
        replay = await service.retrieve_for_new_owned_dispatch(
            dispatch=False,
            owner_token=None,
            project_id="project-a",
            conversation_id="conversation-a",
            query="재생",
        )
        unsafe = await service.retrieve_for_new_owned_dispatch(
            dispatch=True,
            owner_token=None,
            project_id="project-a",
            conversation_id="conversation-a",
            query="기억 후보 만들기",
        )
        return owned, replay, unsafe

    owned, replay, unsafe = asyncio.run(exercise())

    assert owned == ()
    assert replay == ()
    assert unsafe == ()
    assert len(gateway.requests) == 1
    assert gateway.requests[0].query == "새 요청"


def test_local_store_projects_only_current_approved_stored_private_rows(
    tmp_path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("retrieval")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    conversation = store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conversation-a",
    )
    source = store.append_director_message(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation["conversation_id"],
        role="user",
        text="빠른 편집을 원해요.",
    )
    candidate = store.create_yujin_memory_candidate(
        project_id=project.project_id,
        conversation_id=conversation["conversation_id"],
        client_request_id="request-stored",
        source_message_ids=(source["message_id"],),
        memory_scope="creator",
        category="pacing",
        proposed_text="빠른 컷 편집을 선호합니다.",
    )
    store.create_yujin_memory_candidate(
        project_id=project.project_id,
        conversation_id=conversation["conversation_id"],
        client_request_id="request-pending",
        source_message_ids=(source["message_id"],),
        memory_scope="creator",
        category="caption",
        proposed_text="자막은 두 줄 이내를 선호합니다.",
    )
    candidate_id = candidate["candidate_id"]
    store.transition_yujin_memory_candidate(
        project_id=project.project_id,
        candidate_id=candidate_id,
        action="approve",
    )
    claim_token = "claim-" + "a" * 64
    store.claim_yujin_memory_store(
        project_id=project.project_id,
        candidate_id=candidate_id,
        client_request_id="request-store",
        claim_token=claim_token,
    )
    store.mark_yujin_memory_store_call_started(
        project_id=project.project_id,
        candidate_id=candidate_id,
        claim_token=claim_token,
    )
    store.record_yujin_memory_provider_outcome(
        project_id=project.project_id,
        candidate_id=candidate_id,
        claim_token=claim_token,
        status="stored",
        memory_ref="memory-private",
        event_ref=None,
    )
    store.finalize_yujin_memory_store(
        project_id=project.project_id,
        candidate_id=candidate_id,
    )

    rows = store.list_yujin_memory_retrieval_rows(
        project_id=project.project_id,
        conversation_id=conversation["conversation_id"],
    )

    assert len(rows) == 1
    assert rows[0] == {
        "candidate_id": candidate_id,
        "project_id": project.project_id,
        "conversation_id": conversation["conversation_id"],
        "status": "approved",
        "storage_status": "stored",
        "memory_ref": "memory-private",
        "external_ref": rows[0]["external_ref"],
        "text": "빠른 컷 편집을 선호합니다.",
        "category": "pacing",
    }
    assert str(rows[0]["external_ref"]).startswith("ext-")
    assert store.list_yujin_memory_retrieval_rows(
        project_id=project.project_id,
        conversation_id="missing",
    ) == []
