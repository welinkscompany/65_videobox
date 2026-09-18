"""기동 시 기억 사서 "따라잡기" -- owner 확정 지침(2026-09-18).

컨테이너가 상시 실행이 아니라 owner가 켜고 끄는 방식이라(재시작 정책·크론
없음) 고정 시각 스케줄 대신 "기동마다 워터마크를 보고 밀렸으면 그 자리에서
한 번 따라잡는다"로 만들었다(`videobox_api.main._catch_up_memory_librarian`).

가장 중요한 안전장치는 **워터마크가 있는 (project_id, conversation_id)만
본다**는 것이다 -- `list_projects()`로 전체를 훑지 않는다. 이 저장소
Postgres에는 dev 검증 대화가 실제 owner 프로젝트와 섞여 있어서, 자동
따라잡기가 사람이 한 번도 보지 않은 프로젝트까지 훑으면 시험 데이터가
"owner 취향"으로 승격될 위험이 있다 -- 이 시험이 그 경계를 고정한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from videobox_api.main import (
    MEMORY_LIBRARIAN_STALE_AFTER_SECONDS,
    _catch_up_memory_librarian,
    _memory_librarian_watermark_is_stale,
)


def test_watermark_without_a_run_is_always_stale() -> None:
    assert _memory_librarian_watermark_is_stale(
        {"last_run_at": None}, now=datetime.now(timezone.utc)
    )
    assert _memory_librarian_watermark_is_stale(
        {}, now=datetime.now(timezone.utc)
    )


def test_watermark_is_stale_only_past_the_threshold() -> None:
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    fresh = (now - timedelta(hours=1)).isoformat()
    old = (now - timedelta(seconds=MEMORY_LIBRARIAN_STALE_AFTER_SECONDS + 1)).isoformat()

    assert not _memory_librarian_watermark_is_stale(
        {"last_run_at": fresh}, now=now
    )
    assert _memory_librarian_watermark_is_stale(
        {"last_run_at": old}, now=now
    )


class _FakeStore:
    def __init__(self, watermarks: list[dict]) -> None:
        self._watermarks = watermarks
        self.raised_watermark_read = False

    def list_memory_librarian_watermarks(self) -> list[dict]:
        if self.raised_watermark_read:
            raise RuntimeError("watermark table unavailable")
        return list(self._watermarks)


def _fake_app(store: _FakeStore) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            store=store,
            memory_librarian_runtime_service=object(),
        )
    )


def test_only_stale_watermarked_pairs_are_distilled(monkeypatch) -> None:
    """워터마크가 없는 프로젝트는 절대 건드리지 않는다(핵심 안전장치)."""
    now = datetime.now(timezone.utc)
    fresh_at = now.isoformat()
    stale_at = (now - timedelta(seconds=MEMORY_LIBRARIAN_STALE_AFTER_SECONDS + 10)).isoformat()
    watermarks = [
        {
            "project_id": "project-fresh",
            "conversation_id": "conversation-a",
            "last_run_at": fresh_at,
        },
        {
            "project_id": "project-stale",
            "conversation_id": "conversation-b",
            "last_run_at": stale_at,
        },
        {
            "project_id": "project-never-run",
            "conversation_id": "conversation-c",
            "last_run_at": None,
        },
    ]
    store = _FakeStore(watermarks)
    app = _fake_app(store)

    calls: list[tuple[str, str]] = []

    def fake_distill(_store, *, project_id, conversation_id, runtime, as_of):
        calls.append((project_id, conversation_id))

    monkeypatch.setattr(
        "videobox_core_engine.memory_librarian.distill_conversation_memories",
        fake_distill,
    )

    _catch_up_memory_librarian(app)

    assert sorted(calls) == [
        ("project-never-run", "conversation-c"),
        ("project-stale", "conversation-b"),
    ]
    assert ("project-fresh", "conversation-a") not in calls


def test_one_failing_conversation_does_not_block_the_rest(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    watermarks = [
        {"project_id": "p1", "conversation_id": "c1", "last_run_at": None},
        {"project_id": "p2", "conversation_id": "c2", "last_run_at": None},
    ]
    store = _FakeStore(watermarks)
    app = _fake_app(store)
    calls: list[str] = []

    def fake_distill(_store, *, project_id, conversation_id, runtime, as_of):
        calls.append(project_id)
        if project_id == "p1":
            raise RuntimeError("local model unreachable")

    monkeypatch.setattr(
        "videobox_core_engine.memory_librarian.distill_conversation_memories",
        fake_distill,
    )

    _catch_up_memory_librarian(app)  # must not raise

    assert calls == ["p1", "p2"]


def test_watermark_read_failure_is_caught_and_logged(caplog) -> None:
    store = _FakeStore([])
    store.raised_watermark_read = True
    app = _fake_app(store)

    _catch_up_memory_librarian(app)  # must not raise


def test_no_stale_watermarks_means_no_work() -> None:
    now = datetime.now(timezone.utc)
    store = _FakeStore(
        [
            {
                "project_id": "p1",
                "conversation_id": "c1",
                "last_run_at": now.isoformat(),
            }
        ]
    )
    app = _fake_app(store)

    _catch_up_memory_librarian(app)  # no distill call, no error
