"""Bounded streaming registry backed by durable Director Hermes run rows."""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import AsyncIterator, Callable, Coroutine
import uuid

from videobox_api.hermes_capabilities import (
    ExpectedCapability,
    HermesCapabilityError,
    HermesCapabilityUnavailableError as HermesVerifierUnavailableError,
)
from videobox_api.models import HermesStreamEvent
from videobox_core_engine.yujin_creator_context import (
    attach_yujin_memories,
    build_yujin_creator_context,
)
from videobox_core_engine.yujin_creator_proposal_adapter import (
    MANUAL_FALLBACK,
    YujinCreatorProjection,
    activate_yujin_media_projection,
    parse_and_project_yujin_creator_output,
    safe_yujin_stream_visible_prefix,
)
from videobox_domain_models.yujin_creator_context import YujinCreatorContext


_BLOCKED_TEXT = "Hermes is temporarily unavailable. Manual Director remains available."
_GATEWAY_RELEASE_TIMEOUT_SECONDS = 1.0
_MIN_LIVE_DRAFT_CHARS = 16
_LOGGER = logging.getLogger(__name__)
# uvicorn 이 설정한 로거만 컨테이너 로그에 나온다. 모듈 로거는 묻힌다.
_BLOCK_LOGGER = logging.getLogger("uvicorn.error")


def _log_block(reason: str) -> None:
    """차단 사유를 남긴다.

    화면 문구는 어느 경우든 똑같아서, 사유를 남기지 않으면 서로 다른 원인이
    전부 같은 증상으로 보인다. 2026-08-08 에 이것 때문에 오래 헤맸다.
    사유는 코드 문자열만 쓴다 -- 대화 내용이 로그로 새면 안 된다.
    """

    _BLOCK_LOGGER.warning("hermes run blocked: %s", reason)


class HermesCapacityUnavailable(RuntimeError):
    """The bounded process-local run registry has no admission capacity."""


class HermesContextPreparationUnavailable(RuntimeError):
    """Capability admission failed without exposing internal authority state."""


class _Lifecycle(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    ACTIVE = "active"
    TERMINALIZING = "terminalizing"
    TERMINAL = "terminal"


@dataclass
class _Run:
    run_id: str
    project_id: str
    session_id: str
    conversation_id: str
    client_message_id: str
    user_text: str
    expected_session_revision: int
    selected_segment_id: str | None
    retry_of_run_id: str | None
    owner_token: str | None
    creator_context: YujinCreatorContext | object | None = None
    gateway_prepared: bool = False
    events: list[HermesStreamEvent] = field(default_factory=list)
    event_bytes: int = 0
    assembled: str = ""
    public_text: str = ""
    lifecycle: _Lifecycle = _Lifecycle.QUEUED
    signal: asyncio.Event = field(default_factory=asyncio.Event)
    dispatch_task: asyncio.Task | None = None
    terminal_task: asyncio.Task | None = None
    cancellation_task: asyncio.Task | None = None
    cancel_requested: bool = False
    active_slot: bool = False
    terminal_at: float | None = None
    persistence_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def terminal(self) -> bool:
        return self.lifecycle is _Lifecycle.TERMINAL

    @property
    def terminalizing(self) -> bool:
        return self.lifecycle is _Lifecycle.TERMINALIZING

    @property
    def task(self) -> asyncio.Task | None:
        """Compatibility alias for callers that await the dispatch task."""

        return self.dispatch_task


@dataclass
class _Admission:
    waiters: int = 0
    abandoned: bool = False
    task: asyncio.Task | None = None
    durable_run_id: str | None = None


class HermesRunService:
    def __init__(
        self,
        *,
        store,
        gateway_client,
        max_active: int = 2,
        max_queue: int = 8,
        max_total: int = 64,
        # 유진의 두뇌는 이 컴퓨터의 로컬 모델이라 글자 단위로 흘려보낸다.
        # 256 이면 답 하나가 몇백 글자에서 잘린다(2026-08-08 실기 확인).
        # 실제 분량은 아래 max_text_bytes 가 막으므로 개수만 넉넉히 둔다.
        max_events: int = 4_096,
        max_event_bytes: int = 256_000,
        max_text_bytes: int = 200_000,
        # 게이트웨이가 한 대화에 쓰는 시간과 맞춘다. 이쪽이 짧으면 먼저 끊는다.
        timeout_seconds: float = 300.0,
        terminal_ttl_seconds: float = 300.0,
        monotonic: Callable[[], float] = time.monotonic,
        context_builder: Callable | None = None,
        capability_verifier=None,
        memory_service=None,
    ) -> None:
        if min(max_active, max_total, max_events, max_event_bytes, max_text_bytes) < 1:
            raise ValueError("hermes_run_limits_invalid")
        if max_queue < 0 or max_active + max_queue > max_total:
            raise ValueError("hermes_run_limits_invalid")
        self.store = store
        self.gateway_client = gateway_client
        self.max_active = max_active
        self.max_queue = max_queue
        self.max_total = max_total
        self.max_events = max_events
        self.max_event_bytes = max_event_bytes
        self.max_text_bytes = max_text_bytes
        self.timeout_seconds = timeout_seconds
        self.terminal_ttl_seconds = terminal_ttl_seconds
        self._clock = monotonic
        self._context_builder = context_builder or build_yujin_creator_context
        self.capability_verifier = capability_verifier
        self.memory_service = memory_service
        self._runs: dict[str, _Run] = {}
        self._keys: dict[tuple[str, str, str], str] = {}
        self._admissions: dict[tuple[str, str, str], _Admission] = {}
        self._waiting: deque[str] = deque()
        self._active = 0
        self._lock = asyncio.Lock()
        self._reconciliation_lock = asyncio.Lock()
        self._closing = False
        self._admission_tasks: set[asyncio.Task] = set()
        self._dispatch_tasks: set[asyncio.Task] = set()
        self._terminal_tasks: set[asyncio.Task] = set()
        self._cleanup_tasks: set[asyncio.Task] = set()

    async def create_run(
        self,
        *,
        project_id: str,
        session_id: str,
        conversation_id: str,
        client_message_id: str,
        text: str,
        expected_session_revision: int = 1,
        selected_segment_id: str | None = None,
        retry_of_run_id: str | None = None,
    ) -> _Run:
        key = (project_id, conversation_id, client_message_id)
        async with self._lock:
            self._cleanup_locked()
            if self._closing:
                raise HermesCapacityUnavailable("hermes_run_service_closing")
            existing_id = self._keys.get(key)
            if existing_id is not None:
                existing = self._runs[existing_id]
                self._validate_duplicate(
                    existing,
                    session_id=session_id,
                    text=text,
                    expected_session_revision=expected_session_revision,
                    selected_segment_id=selected_segment_id,
                )
                return existing
            admission = self._admissions.get(key)
            if admission is None:
                live_count = sum(not run.terminal for run in self._runs.values())
                if (
                    len(self._runs) + len(self._admissions) >= self.max_total
                    or live_count + len(self._admissions)
                    >= self.max_active + self.max_queue
                ):
                    raise HermesCapacityUnavailable("hermes_run_capacity_exhausted")
                admission = _Admission()
                self._admissions[key] = admission
                admission.task = self._spawn_task(
                    self._admit(
                        admission=admission,
                        key=key,
                        project_id=project_id,
                        session_id=session_id,
                        conversation_id=conversation_id,
                        client_message_id=client_message_id,
                        text=text,
                        expected_session_revision=expected_session_revision,
                        selected_segment_id=selected_segment_id,
                        retry_of_run_id=retry_of_run_id,
                    ),
                    self._admission_tasks,
                    name=f"videobox-admit-{client_message_id}",
                )
            admission.waiters += 1
            task = admission.task
            assert task is not None

        cancelled = False
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
            async with self._lock:
                admission.waiters -= 1
                abandon_run = admission.waiters == 0
                if abandon_run:
                    admission.abandoned = True
            # A durable begin cannot be safely cancelled.  Wait until the owned
            # admission either fails or finalizes any committed row as blocked.
            admitted_run: _Run | None = None
            try:
                admitted_run = await asyncio.shield(task)
            except Exception:
                pass
            if (
                abandon_run
                and admitted_run is not None
                and not admitted_run.terminal
            ):
                dispatch = admitted_run.dispatch_task
                if dispatch is not None:
                    dispatch.cancel()
                await self._terminal(
                    admitted_run,
                    "blocked",
                    _BLOCKED_TEXT,
                    retryable=True,
                )
            raise
        finally:
            if not cancelled:
                async with self._lock:
                    admission.waiters -= 1

    async def subscribe(
        self,
        run_id: str,
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
        after_event_id: int = 0,
    ) -> AsyncIterator[HermesStreamEvent]:
        list_events = getattr(
            self.store, "list_director_hermes_run_events", None
        )
        run = self._runs.get(run_id)
        if list_events is not None:
            if project_id is None or conversation_id is None:
                if run is None:
                    raise KeyError("director_hermes_run_missing")
                project_id = run.project_id
                conversation_id = run.conversation_id
            cursor = after_event_id
            while True:
                rows = await asyncio.to_thread(
                    list_events,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    after_event_id=cursor,
                )
                for item in rows:
                    event = HermesStreamEvent.model_validate(item)
                    cursor = event.event_id
                    yield event
                durable = await asyncio.to_thread(
                    self.store.get_director_hermes_run,
                    project_id=project_id,
                    run_id=run_id,
                )
                if str(durable.get("status") or "") in {
                    "completed",
                    "blocked",
                    "interrupted",
                }:
                    if cursor >= int(durable.get("next_event_id") or 1) - 1:
                        return
                    continue
                if run is None:
                    return
                if run.terminal:
                    return
                run.signal.clear()
                try:
                    await asyncio.wait_for(run.signal.wait(), timeout=0.25)
                except TimeoutError:
                    pass
            return
        if run is None:
            raise KeyError("director_hermes_run_missing")
        index = 0
        while True:
            async with self._lock:
                batch = run.events[index:]
                index = len(run.events)
                terminal = run.terminal
                if not batch and not terminal:
                    run.signal.clear()
            for event in batch:
                yield event
            if terminal:
                return
            await run.signal.wait()

    async def cancel(
        self,
        run_id: str,
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        run = self._runs.get(run_id)
        if run is None:
            if project_id is None:
                return
            projects = await asyncio.to_thread(self.store.list_projects)
            if not any(
                str(project.get("project_id") or "") == project_id
                for project in projects
            ):
                raise KeyError("director_hermes_run_missing")
            try:
                durable = await asyncio.to_thread(
                    self.store.get_director_hermes_run,
                    project_id=project_id,
                    run_id=run_id,
                )
            except (KeyError, OSError) as error:
                raise KeyError("director_hermes_run_missing") from error
            if (
                conversation_id is not None
                and str(durable.get("conversation_id") or "") != conversation_id
            ):
                raise KeyError("director_hermes_run_missing")
            return
        if (
            (project_id is not None and run.project_id != project_id)
            or (
                conversation_id is not None
                and run.conversation_id != conversation_id
            )
        ):
            raise KeyError("director_hermes_run_missing")
        async with self._lock:
            if run.terminal:
                return
            task = run.cancellation_task
            if task is None:
                if run.terminalizing:
                    return
                run.cancel_requested = True
                task = self._spawn_task(
                    self._cancel_owned(run),
                    self._cleanup_tasks,
                    name=f"videobox-cancel-{run.run_id}",
                )
                run.cancellation_task = task
        await asyncio.shield(task)

    async def _cancel_owned(self, run: _Run) -> None:
        if run.gateway_prepared:
            try:
                await self.gateway_client.cancel_run(run_id=run.run_id)
            except Exception:
                pass
        await self._terminal(
            run,
            "blocked",
            _BLOCKED_TEXT,
            retryable=True,
            durable_status="interrupted",
        )
        task = run.dispatch_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def retry(
        self,
        run_id: str,
        *,
        project_id: str,
        conversation_id: str,
    ) -> _Run:
        projects = await asyncio.to_thread(self.store.list_projects)
        if not any(
            str(project.get("project_id") or "") == project_id
            for project in projects
        ):
            raise KeyError("director_hermes_run_missing")
        try:
            durable = await asyncio.to_thread(
                self.store.get_director_hermes_run,
                project_id=project_id,
                run_id=run_id,
            )
        except (KeyError, OSError) as error:
            raise KeyError("director_hermes_run_missing") from error
        if str(durable.get("conversation_id") or "") != conversation_id:
            raise KeyError("director_hermes_run_missing")
        if str(durable.get("status") or "") not in {"blocked", "interrupted"}:
            raise ValueError("hermes_run_retry_not_eligible")
        return await self.create_run(
            project_id=project_id,
            session_id=str(durable["session_id"]),
            conversation_id=conversation_id,
            client_message_id=f"retry-{uuid.uuid4().hex}",
            text=str(durable["user_text"]),
            expected_session_revision=int(
                durable["expected_session_revision"]
            ),
            selected_segment_id=durable.get("selected_segment_id"),
            retry_of_run_id=run_id,
        )

    async def shutdown(self) -> None:
        async with self._lock:
            self._closing = True
            admissions = tuple(self._admission_tasks)

        if admissions:
            await asyncio.gather(
                *(asyncio.shield(task) for task in admissions),
                return_exceptions=True,
            )

        while True:
            async with self._lock:
                dispatches = tuple(
                    task for task in self._dispatch_tasks if not task.done()
                )
                unfinished = tuple(
                    run for run in self._runs.values() if not run.terminal
                )
            for task in dispatches:
                task.cancel()
            if dispatches:
                await asyncio.gather(*dispatches, return_exceptions=True)
            if unfinished:
                await asyncio.gather(
                    *(
                        self._terminal(
                            run, "blocked", _BLOCKED_TEXT, retryable=True
                        )
                        for run in unfinished
                    ),
                    return_exceptions=True,
                )
            await self._await_owned_fixed_point()
            async with self._lock:
                remaining = (
                    any(not run.terminal for run in self._runs.values())
                    or any(not task.done() for task in self._admission_tasks)
                    or any(not task.done() for task in self._dispatch_tasks)
                    or any(not task.done() for task in self._terminal_tasks)
                    or any(not task.done() for task in self._cleanup_tasks)
                )
                if not remaining:
                    for run in self._runs.values():
                        self._release_slot_and_promote_locked(run)
                    self._waiting.clear()
                    self._active = 0
                    return

    def diagnostics(self) -> dict[str, int | bool]:
        """Return bounded process-local lifecycle counts without run content."""

        return {
            "closing": self._closing,
            "active": self._active,
            "waiting": len(self._waiting),
            "admissions": sum(
                not task.done() for task in self._admission_tasks
            ),
            "dispatch": sum(not task.done() for task in self._dispatch_tasks),
            "terminal": sum(not task.done() for task in self._terminal_tasks),
            "cleanup": sum(not task.done() for task in self._cleanup_tasks),
        }

    async def reconciliation_excluded_run_ids(
        self,
    ) -> dict[str, tuple[str, ...]] | None:
        async with self._lock:
            if any(
                admission.durable_run_id is None
                for admission in self._admissions.values()
            ):
                return None
            excluded_by_project: dict[str, set[str]] = {}
            for run_id, run in self._runs.items():
                if not run.terminal:
                    excluded_by_project.setdefault(
                        run.project_id, set()
                    ).add(run_id)
            for key, admission in self._admissions.items():
                if admission.durable_run_id is not None:
                    excluded_by_project.setdefault(key[0], set()).add(
                        admission.durable_run_id
                    )
            return {
                project_id: tuple(sorted(run_ids))
                for project_id, run_ids in excluded_by_project.items()
            }

    @asynccontextmanager
    async def reconciliation_scope(self):
        """Fence only durable begin while startup reconciliation owns the DB."""

        async with self._reconciliation_lock:
            yield await self.reconciliation_excluded_run_ids()

    def get_run(self, run_id: str) -> _Run:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError("director_hermes_run_missing")
        return run

    async def _admit(
        self,
        *,
        admission: _Admission,
        key: tuple[str, str, str],
        project_id: str,
        session_id: str,
        conversation_id: str,
        client_message_id: str,
        text: str,
        expected_session_revision: int,
        selected_segment_id: str | None,
        retry_of_run_id: str | None,
    ) -> _Run:
        try:
            context = await asyncio.to_thread(
                self._context_builder,
                store=self.store,
                project_id=project_id,
                session_id=session_id,
                expected_session_revision=expected_session_revision,
                selected_segment_id=selected_segment_id,
            )
            async with self._reconciliation_lock:
                durable = await asyncio.to_thread(
                    self.store.begin_director_hermes_run,
                    project_id=project_id,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    client_message_id=client_message_id,
                    user_text=text,
                    expected_session_revision=expected_session_revision,
                    expected_asset_index_revision=(
                        context.asset_index_revision
                    ),
                    selected_segment_id=selected_segment_id,
                    retry_of_run_id=retry_of_run_id,
                )
                async with self._lock:
                    admission.durable_run_id = str(durable["run_id"])
            if (
                str(durable.get("status") or "") in {"pending", "streaming"}
                and not bool(durable.get("dispatch"))
            ):
                raise HermesCapacityUnavailable("hermes_run_in_progress")
            if (
                str(durable.get("status") or "") in {"pending", "streaming"}
                and bool(durable.get("dispatch"))
                and durable.get("owner_token") is not None
            ):
                run_id = str(durable["run_id"])
                if self.memory_service is not None:
                    memories = (
                        await self.memory_service.retrieve_for_new_owned_dispatch(
                            dispatch=bool(durable.get("dispatch")),
                            owner_token=str(durable["owner_token"]),
                            project_id=project_id,
                            conversation_id=conversation_id,
                            query=text,
                        )
                    )
                    if memories:
                        context = attach_yujin_memories(context, memories)
                gateway_reservation_attempted = False
                try:
                    gateway_reservation_attempted = True
                    reservation = await self.gateway_client.reserve_run(
                        project_id=project_id,
                        conversation_id=conversation_id,
                        run_id=run_id,
                        session_id=session_id,
                        session_revision=context.session_revision,
                        asset_index_revision=context.asset_index_revision,
                    )
                    self._raise_if_admission_abandoned(admission)
                    if self.capability_verifier is None:
                        await asyncio.to_thread(
                            self.store.record_hermes_capability_denial,
                            project_id=project_id,
                            conversation_id=conversation_id,
                            run_id=run_id,
                            action="read_context",
                            reason="hermes_capability_unavailable",
                            use_registered_capability_id=False,
                        )
                        raise RuntimeError(
                            "hermes_capability_verifier_unavailable"
                        )
                    await asyncio.to_thread(
                        self.store.register_hermes_run_capabilities,
                        project_id=project_id,
                        conversation_id=conversation_id,
                        run_id=run_id,
                        session_id=session_id,
                        session_revision=context.session_revision,
                        asset_index_revision=context.asset_index_revision,
                        capabilities=tuple(
                            item.model_dump(mode="python")
                            for item in reservation.capabilities
                        ),
                    )
                    self._raise_if_admission_abandoned(admission)
                    expected_payload = await asyncio.to_thread(
                        self.store.get_expected_hermes_capability,
                        project_id=project_id,
                        conversation_id=conversation_id,
                        run_id=run_id,
                        action="read_context",
                    )
                    if expected_payload is None:
                        await asyncio.to_thread(
                            self.store.record_hermes_capability_denial,
                            project_id=project_id,
                            conversation_id=conversation_id,
                            run_id=run_id,
                            action="read_context",
                            reason="hermes_capability_scope_forbidden",
                            use_registered_capability_id=False,
                        )
                        raise RuntimeError(
                            "hermes_capability_expected_missing"
                        )
                    expected = ExpectedCapability(
                        capability_id=str(
                            expected_payload["capability_id"]
                        ),
                        project_id=str(expected_payload["project_id"]),
                        conversation_id=str(
                            expected_payload["conversation_id"]
                        ),
                        run_id=str(expected_payload["run_id"]),
                        session_id=str(expected_payload["session_id"]),
                        session_revision=int(
                            expected_payload["session_revision"]
                        ),
                        asset_index_revision=int(
                            expected_payload["asset_index_revision"]
                        ),
                        action=str(expected_payload["action"]),
                    )
                    try:
                        self.capability_verifier.verify(
                            reservation.read_capability_token,
                            expected=expected,
                        )
                    except HermesVerifierUnavailableError:
                        await asyncio.to_thread(
                            self.store.record_hermes_capability_denial,
                            project_id=project_id,
                            conversation_id=conversation_id,
                            run_id=run_id,
                            action="read_context",
                            reason="hermes_capability_unavailable",
                        )
                        raise
                    except HermesCapabilityError as error:
                        await asyncio.to_thread(
                            self.store.record_hermes_capability_denial,
                            project_id=project_id,
                            conversation_id=conversation_id,
                            run_id=run_id,
                            action="read_context",
                            reason=str(error),
                        )
                        raise
                    self._raise_if_admission_abandoned(admission)
                    consume_result = await asyncio.to_thread(
                        self.store.consume_registered_hermes_capability,
                        project_id=project_id,
                        capability_id=expected.capability_id,
                        conversation_id=conversation_id,
                        run_id=run_id,
                        session_id=session_id,
                        session_revision=context.session_revision,
                        asset_index_revision=context.asset_index_revision,
                        action="read_context",
                    )
                    if consume_result != "accepted":
                        raise RuntimeError(str(consume_result))
                    self._raise_if_admission_abandoned(admission)
                    await self.gateway_client.attach_run_context(
                        project_id=project_id,
                        conversation_id=conversation_id,
                        run_id=run_id,
                        session_id=session_id,
                        session_revision=context.session_revision,
                        asset_index_revision=context.asset_index_revision,
                        reservation=reservation,
                        context=context.model_dump(mode="json"),
                    )
                    self._raise_if_admission_abandoned(admission)
                except BaseException as error:
                    cleanup_error: BaseException | None = None
                    try:
                        if gateway_reservation_attempted:
                            await self._release_gateway_run(run_id)
                    except BaseException as release_error:
                        cleanup_error = release_error
                    try:
                        await asyncio.to_thread(
                            self.store.complete_director_hermes_run,
                            project_id=project_id,
                            run_id=run_id,
                            owner_token=str(
                                durable["owner_token"]
                            ),
                            status="blocked",
                            assistant_text=_BLOCKED_TEXT,
                            retryable=True,
                        )
                    except BaseException as terminal_error:
                        if cleanup_error is None:
                            cleanup_error = terminal_error
                    if isinstance(error, asyncio.CancelledError):
                        raise
                    if not isinstance(error, Exception):
                        raise
                    raise HermesContextPreparationUnavailable(
                        "hermes_context_preparation_unavailable"
                    ) from (cleanup_error or error)
            run = _Run(
                run_id=str(durable["run_id"]),
                project_id=project_id,
                session_id=session_id,
                conversation_id=conversation_id,
                client_message_id=client_message_id,
                user_text=text,
                expected_session_revision=expected_session_revision,
                selected_segment_id=selected_segment_id,
                retry_of_run_id=retry_of_run_id,
                owner_token=durable.get("owner_token"),
                creator_context=context,
                gateway_prepared=bool(durable.get("dispatch")),
            )
            terminal: tuple[str, str, bool] | None = None
            async with self._lock:
                self._runs[run.run_id] = run
                self._keys[key] = run.run_id
                self._publish_locked(run, "run_started")
                status = str(durable.get("status") or "")
                if status not in {"pending", "streaming"}:
                    terminal_text = str(durable.get("assistant_text") or "")
                    self._publish_locked(
                        run,
                        "run_completed" if status == "completed" else "blocked",
                        text=(
                            terminal_text
                            if status == "completed"
                            else _BLOCKED_TEXT
                        ),
                        retryable=status != "completed",
                        terminal=True,
                    )
                elif not durable.get("dispatch") or run.owner_token is None:
                    self._publish_locked(
                        run,
                        "blocked",
                        text=_BLOCKED_TEXT,
                        retryable=True,
                        terminal=True,
                    )
                elif self._closing or admission.abandoned:
                    terminal = ("blocked", _BLOCKED_TEXT, True)
                elif self._active < self.max_active:
                    self._activate_locked(run)
                elif len(self._waiting) < self.max_queue:
                    run.lifecycle = _Lifecycle.QUEUED
                    self._waiting.append(run.run_id)
                else:
                    terminal = ("blocked", _BLOCKED_TEXT, True)
                self._admissions.pop(key, None)
            if terminal is not None:
                await self._terminal(
                    run,
                    terminal[0],
                    terminal[1],
                    retryable=terminal[2],
                )
            return run
        except BaseException:
            async with self._lock:
                self._admissions.pop(key, None)
            raise

    @staticmethod
    def _validate_duplicate(
        run: _Run,
        *,
        session_id: str,
        text: str,
        expected_session_revision: int,
        selected_segment_id: str | None,
    ) -> None:
        if (
            run.user_text != text
            or run.session_id != session_id
            or run.expected_session_revision != expected_session_revision
            or run.selected_segment_id != selected_segment_id
        ):
            raise ValueError("client_message_id_reused_with_different_content")

    def _activate_locked(self, run: _Run) -> None:
        if self._closing or run.terminal or run.active_slot:
            return
        self._active += 1
        run.active_slot = True
        run.lifecycle = _Lifecycle.STARTING
        task = self._spawn_task(
            self._dispatch(run),
            self._dispatch_tasks,
            name=f"videobox-dispatch-{run.run_id}",
            cleanup=lambda completed: self._dispatch_done(run, completed),
        )
        run.dispatch_task = task

    async def _dispatch(self, run: _Run) -> None:
        # Admission must return only after the durable user row exists, while
        # leaving gateway dispatch for the next loop turn.
        await asyncio.sleep(0)
        async with self._lock:
            if self._closing or run.terminal:
                return
            run.lifecycle = _Lifecycle.ACTIVE
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async for upstream in self.gateway_client.stream_run(
                    run_id=run.run_id,
                    client_message_id=run.client_message_id,
                    text=run.user_text,
                ):
                    if run.terminal:
                        return
                    if upstream.event_type == "text_delta":
                        if not upstream.text:
                            continue
                        overflow = False
                        chunk_bytes = len(upstream.text.encode("utf-8"))
                        async with self._lock:
                            if run.terminal:
                                return
                            if (
                                len(run.assembled.encode("utf-8")) + chunk_bytes
                                > self.max_text_bytes
                            ):
                                overflow = True
                            else:
                                run.assembled += upstream.text
                        if overflow:
                            _log_block("assembled_text_over_limit")
                            await self._terminal(
                                run, "blocked", _BLOCKED_TEXT, retryable=True
                            )
                            return
                        if not await self._persist_visible_draft(run):
                            _log_block("visible_draft_not_monotonic")
                            await self._terminal(
                                run, "blocked", _BLOCKED_TEXT, retryable=True
                            )
                            return
                    elif upstream.event_type == "blocked":
                        _log_block("gateway_sent_blocked")
                        await self._terminal(
                            run, "blocked", _BLOCKED_TEXT, retryable=True
                        )
                        return
                    elif upstream.event_type == "run_completed":
                        completed_text = upstream.text or run.assembled
                        if (
                            len(completed_text.encode("utf-8"))
                            > self.max_text_bytes
                            or not completed_text.strip()
                        ):
                            _log_block("completed_text_rejected")
                            await self._terminal(
                                run, "blocked", _BLOCKED_TEXT, retryable=True
                            )
                        else:
                            await self._terminal(
                                run,
                                "run_completed",
                                completed_text,
                                retryable=False,
                                publish_capability_token=(
                                    upstream.publish_capability_token
                                ),
                            )
                        return
                    else:
                        _log_block("unknown_upstream_event")
                        await self._terminal(
                            run, "blocked", _BLOCKED_TEXT, retryable=True
                        )
                        return
            _log_block("stream_ended_without_completion")
            await self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)
        except asyncio.CancelledError:
            _log_block("cancelled")
            await self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)
            raise
        except Exception as error:
            _log_block("unexpected:" + type(error).__name__)
            await self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)

    async def _persist_visible_draft(self, run: _Run) -> bool:
        async with run.persistence_lock:
            return await self._persist_visible_draft_serialized(run)

    async def _persist_visible_draft_serialized(self, run: _Run) -> bool:
        append_event = getattr(
            self.store, "append_director_hermes_draft_event", None
        )
        append_draft = getattr(self.store, "append_director_hermes_draft", None)
        if append_draft is None or run.owner_token is None:
            return True
        async with self._lock:
            if run.terminal or run.terminalizing:
                return False
            target = safe_yujin_stream_visible_prefix(run.assembled)
            target = self._truncate_utf8(
                target,
                max(0, self.max_text_bytes - len("\n\n!".encode("utf-8"))),
            ).rstrip()
            if len(target) < _MIN_LIVE_DRAFT_CHARS:
                return True
            if len(target) <= len(run.public_text):
                return True
            if not target.startswith(run.public_text):
                return False
            future_failure = target + self._truncate_utf8(
                f"\n\n{_BLOCKED_TEXT}",
                self.max_text_bytes - len(target.encode("utf-8")),
            )
            if not self._sequence_fits_locked(
                run,
                target=target,
                terminal_event_type="blocked",
                terminal_text=future_failure,
                include_initial_delta=True,
            ):
                return True
        try:
            kwargs = {
                "project_id": run.project_id,
                "run_id": run.run_id,
                "owner_token": run.owner_token,
                "assistant_draft_text": target,
            }
            if append_event is not None:
                kwargs.update(
                    {
                        "event_text": target[len(run.public_text) :],
                        "expected_event_id": len(run.events) + 1,
                    }
                )
                append_task = asyncio.create_task(
                    asyncio.to_thread(append_event, **kwargs),
                    name=f"videobox-draft-persist-{run.run_id}",
                )
            else:
                append_task = asyncio.create_task(
                    asyncio.to_thread(append_draft, **kwargs),
                    name=f"videobox-draft-persist-{run.run_id}",
                )
            cancelled = False
            try:
                stored = await asyncio.shield(append_task)
            except asyncio.CancelledError:
                cancelled = True
                stored = await asyncio.shield(append_task)
        except Exception:
            # 초안이 남지 않는다. owner에게는 그냥 아무 일도 없던 것처럼 보인다.
            _LOGGER.warning("유진 초안을 저장하지 못했습니다.", exc_info=True)
            return False
        if stored is not True:
            return False
        async with self._lock:
            if run.terminal:
                return False
            try:
                self._publish_public_delta_locked(run, target)
            except OverflowError:
                return False
        if cancelled:
            raise asyncio.CancelledError
        return True

    async def _dispatch_done(
        self, run: _Run, _completed: asyncio.Task
    ) -> None:
        if not run.terminal and not run.terminalizing:
            await self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)
        async with self._lock:
            self._release_slot_and_promote_locked(run)

    async def _terminal(
        self,
        run: _Run,
        event_type: str,
        text: str,
        *,
        retryable: bool,
        durable_status: str | None = None,
        publish_capability_token: str | None = None,
    ) -> None:
        async with self._lock:
            if run.terminal:
                return
            task = run.terminal_task
            if task is None:
                if run.cancel_requested:
                    event_type = "blocked"
                    text = _BLOCKED_TEXT
                    retryable = True
                    durable_status = "interrupted"
                run.lifecycle = _Lifecycle.TERMINALIZING
                task = self._spawn_task(
                    self._finish_terminal(
                        run,
                        event_type=event_type,
                        text=text,
                        retryable=retryable,
                        durable_status=durable_status,
                        publish_capability_token=(
                            publish_capability_token
                        ),
                    ),
                    self._terminal_tasks,
                    name=f"videobox-terminal-{run.run_id}",
                    cleanup=lambda completed: self._terminal_done(run, completed),
                )
                run.terminal_task = task
        await asyncio.shield(task)

    async def _finish_terminal(
        self,
        run: _Run,
        *,
        event_type: str,
        text: str,
        retryable: bool,
        durable_status: str | None,
        publish_capability_token: str | None,
    ) -> None:
        async with run.persistence_lock:
            await self._finish_terminal_serialized(
                run,
                event_type=event_type,
                text=text,
                retryable=retryable,
                durable_status=durable_status,
                publish_capability_token=publish_capability_token,
            )

    async def _finish_terminal_serialized(
        self,
        run: _Run,
        *,
        event_type: str,
        text: str,
        retryable: bool,
        durable_status: str | None,
        publish_capability_token: str | None,
    ) -> None:
        proposal = None
        verified_publish_capability: dict[str, Any] | None = None
        projection: YujinCreatorProjection | None = None
        preflight_failed = False
        if event_type == "run_completed" and run.creator_context is not None:
            projection = parse_and_project_yujin_creator_output(
                text,
                run.creator_context,  # type: ignore[arg-type]
                trusted_project_id=run.project_id,
                trusted_run_id=run.run_id,
            )
            if projection.proposal is not None:
                projection = await self._recheck_projection(run, projection)
            if projection.proposal is not None:
                exists = getattr(self.store, "director_proposal_exists", None)
                if exists is not None:
                    try:
                        collision = await asyncio.to_thread(
                            exists,
                            project_id=run.project_id,
                            proposal_id=projection.proposal.proposal_id,
                        )
                    except Exception:
                        # 여기서 멈추면 제안이 통째로 저장되지 않는데, 화면에는
                        # 평범한 답변이 그대로 뜬다. owner는 눌러도 아무 일이
                        # 없는 이유를 알 방법이 없다. 저장을 건너뛰는 동작은
                        # 그대로 두고 이유만 남긴다.
                        _LOGGER.warning(
                            "제안 중복 확인이 실패해 저장을 건너뜁니다. "
                            "화면의 답변은 그대로 뜨지만 제안은 남지 않습니다 "
                            "(project=%s, run=%s).",
                            run.project_id,
                            run.run_id,
                            exc_info=True,
                        )
                        preflight_failed = True
                    else:
                        if collision:
                            projection = self._discard_projection_for_collision(
                                projection
                            )
            text = projection.reply_text
            proposal = projection.proposal
            if proposal is not None:
                verified_publish_capability = (
                    await self._verify_terminal_publish_capability(
                        run,
                        publish_capability_token,
                    )
                )
                if verified_publish_capability is None:
                    projection = self._discard_capability_denied_projection(
                        projection
                    )
                    text = projection.reply_text
                    proposal = None
        event_type, text, retryable, proposal = self._normalize_terminal(
            run, event_type, text, retryable, proposal
        )
        async with self._lock:
            publish_remainder = self._sequence_fits_locked(
                run,
                target=run.public_text,
                terminal_event_type=event_type,
                terminal_text=text,
            )
        if not publish_remainder:
            event_type = "blocked"
            text = self._bounded_failure_text(run)
            retryable = True
            proposal = None
            async with self._lock:
                publish_remainder = self._sequence_fits_locked(
                    run,
                    target=run.public_text,
                    terminal_event_type=event_type,
                    terminal_text=text,
                )
        stored: bool | str = not preflight_failed
        if run.owner_token is not None and stored:
            try:
                completion_kwargs = {
                    "project_id": run.project_id,
                    "run_id": run.run_id,
                    "owner_token": run.owner_token,
                    "status": (
                        durable_status
                        or (
                            "completed"
                            if event_type == "run_completed"
                            else "blocked"
                        )
                    ),
                    "assistant_text": text or _BLOCKED_TEXT,
                    "retryable": retryable,
                    "proposal": proposal,
                    "verified_publish_capability": (
                        verified_publish_capability
                        if proposal is not None
                        else None
                    ),
                }
                if hasattr(self.store, "list_director_hermes_run_events"):
                    completion_kwargs["public_text"] = run.public_text
                stored = await asyncio.to_thread(
                    self.store.complete_director_hermes_run,
                    **completion_kwargs,
                )
            except Exception:
                # 아래 고정 코드는 무엇이 터졌든 하나로 뭉갠다. 뒤이어 제안
                # 없이 한 번 더 저장하므로 owner에게는 정상 답변으로 보이고,
                # 진짜 이유는 여기서 남기지 않으면 사라진다.
                _LOGGER.warning(
                    "유진 실행 결과를 저장하지 못했습니다. "
                    "제안이 남지 않습니다 (project=%s, run=%s).",
                    run.project_id,
                    run.run_id,
                    exc_info=True,
                )
                stored = (
                    "publish_transaction_fault"
                    if proposal is not None
                    else False
                )
            if stored in {
                "proposal_conflict",
                "proposal_stale",
                "publish_capability_denied",
                "publish_transaction_fault",
            } and projection is not None:
                if stored == "proposal_conflict":
                    projection = self._discard_projection_for_collision(
                        projection
                    )
                elif stored == "proposal_stale":
                    projection = self._discard_stale_projection(projection)
                elif stored == "publish_capability_denied":
                    projection = (
                        self._discard_capability_denied_projection(
                            projection
                        )
                    )
                else:
                    projection = self._discard_stale_projection(
                        projection
                    )
                text = projection.reply_text
                proposal = None
                event_type, text, retryable, proposal = self._normalize_terminal(
                    run, "run_completed", text, False, proposal
                )
                async with self._lock:
                    publish_remainder = self._sequence_fits_locked(
                        run,
                        target=run.public_text,
                        terminal_event_type=event_type,
                        terminal_text=text,
                    )
                if not publish_remainder:
                    event_type = "blocked"
                    text = self._bounded_failure_text(run)
                    retryable = True
                try:
                    completion_kwargs = {
                        "project_id": run.project_id,
                        "run_id": run.run_id,
                        "owner_token": run.owner_token,
                        "status": (
                            "completed"
                            if event_type == "run_completed"
                            else "blocked"
                        ),
                        "assistant_text": text,
                        "retryable": retryable,
                        "proposal": None,
                        "verified_publish_capability": None,
                    }
                    if hasattr(self.store, "list_director_hermes_run_events"):
                        completion_kwargs["public_text"] = run.public_text
                    stored = await asyncio.to_thread(
                        self.store.complete_director_hermes_run,
                        **completion_kwargs,
                    )
                except Exception:
                    # 유진과 나눈 대화가 사라진다. 실행 자체는 계속 진행하되
                    # 무엇을 못 남겼는지는 기록한다.
                    _LOGGER.warning(
                        "유진 실행 결과를 저장하지 못했습니다. 대화가 남지 않습니다.",
                        exc_info=True,
                    )
                    stored = False
        persist_succeeded = stored is True
        if projection is not None:
            _LOGGER.info(
                "yujin_creator_proposal_validation",
                extra={
                    "proposal_id": (
                        proposal.proposal_id
                        if persist_succeeded and proposal is not None
                        else None
                    ),
                    "schema_version": projection.schema_version,
                    "operation_count": projection.operation_count,
                    "validation_outcome": projection.validation_outcome,
                },
            )
        async with self._lock:
            if not run.terminal:
                if not persist_succeeded:
                    if hasattr(
                        self.store, "list_director_hermes_run_events"
                    ):
                        self._mark_terminal_without_event_locked(run)
                    else:
                        event_type = "blocked"
                        text = self._bounded_failure_text(run)
                        retryable = True
                        publish_remainder = self._sequence_fits_locked(
                            run,
                            target=run.public_text,
                            terminal_event_type=event_type,
                            terminal_text=text,
                        )
                if not run.terminal:
                    if publish_remainder:
                        self._publish_terminal_remainder_locked(run, text)
                    self._publish_locked(
                        run,
                        event_type,
                        text=text,
                        retryable=retryable,
                        terminal=True,
                    )
            self._release_slot_and_promote_locked(run)
        if run.gateway_prepared:
            self._spawn_cleanup(
                self._release_gateway_run(run.run_id),
                name=f"videobox-gateway-release-{run.run_id}",
            )

    async def _verify_terminal_publish_capability(
        self,
        run: _Run,
        token: str | None,
    ) -> dict[str, Any] | None:
        reason = "hermes_capability_unavailable"
        try:
            expected_payload = await asyncio.to_thread(
                self.store.get_expected_hermes_capability,
                project_id=run.project_id,
                conversation_id=run.conversation_id,
                run_id=run.run_id,
                action="publish_proposal",
            )
            if expected_payload is None:
                reason = "hermes_capability_scope_forbidden"
                raise HermesCapabilityError(reason)
            expected = ExpectedCapability(
                capability_id=str(expected_payload["capability_id"]),
                project_id=str(expected_payload["project_id"]),
                conversation_id=str(
                    expected_payload["conversation_id"]
                ),
                run_id=str(expected_payload["run_id"]),
                session_id=str(expected_payload["session_id"]),
                session_revision=int(
                    expected_payload["session_revision"]
                ),
                asset_index_revision=int(
                    expected_payload["asset_index_revision"]
                ),
                action=str(expected_payload["action"]),
            )
            if token is None or self.capability_verifier is None:
                raise HermesCapabilityError(reason)
            verified = self.capability_verifier.verify(
                token,
                expected=expected,
            )
            return {
                field: getattr(verified, field)
                for field in (
                    "capability_id",
                    "project_id",
                    "conversation_id",
                    "run_id",
                    "session_id",
                    "session_revision",
                    "asset_index_revision",
                    "action",
                    "issued_at",
                    "not_before",
                    "expires_at",
                )
            }
        except HermesCapabilityError as error:
            reason = str(error)
        except Exception:
            # 아래 사유는 고정 문자열이라 무엇이 터졌든 똑같이 기록된다.
            # 제안이 저장되지 않는 결과는 같으므로 진짜 원인은 여기에만 남는다.
            _LOGGER.warning(
                "제안 권한을 확인하지 못했습니다 (project=%s, run=%s).",
                run.project_id,
                run.run_id,
                exc_info=True,
            )
            reason = "hermes_capability_unavailable"
        try:
            await asyncio.to_thread(
                self.store.record_hermes_capability_denial,
                project_id=run.project_id,
                conversation_id=run.conversation_id,
                run_id=run.run_id,
                action="publish_proposal",
                reason=reason,
            )
        except Exception:
            # 거절 사유를 남기는 것마저 실패하면 감사 화면에도 흔적이 없다.
            # 실행은 그대로 진행한다.
            _LOGGER.warning(
                "제안 권한 거절 사유를 남기지 못했습니다 (project=%s, run=%s, 사유=%s).",
                run.project_id,
                run.run_id,
                reason,
                exc_info=True,
            )
        return None

    async def _recheck_projection(
        self,
        run: _Run,
        projection: YujinCreatorProjection,
    ) -> YujinCreatorProjection:
        try:
            current = await asyncio.to_thread(
                self._context_builder,
                store=self.store,
                project_id=run.project_id,
                session_id=run.session_id,
                expected_session_revision=run.expected_session_revision,
                selected_segment_id=run.selected_segment_id,
            )
            original = run.creator_context
            if (
                not isinstance(current, YujinCreatorContext)
                or not isinstance(original, YujinCreatorContext)
                or current.model_dump(mode="json")
                != original.model_dump(mode="json")
            ):
                raise ValueError("creator_context_changed")
            projection = await asyncio.to_thread(
                activate_yujin_media_projection,
                store=self.store,
                project_id=run.project_id,
                context=current,
                projection=projection,
            )
        except Exception:
            # 화면에는 "직접 해 주세요" 한 문장만 남고 제안은 버려진다.
            # 편집 중에 실제로 바뀐 것과 되짚기가 못 돈 것이 화면에서
            # 구분되지 않으므로, 어느 쪽이었는지는 여기서만 알 수 있다.
            _LOGGER.warning(
                "제안 되짚기가 실패해 수동 안내로 넘어갑니다 "
                "(project=%s, run=%s).",
                run.project_id,
                run.run_id,
                exc_info=True,
            )
            visible = projection.reply_text.strip()
            return YujinCreatorProjection(
                reply_text=(
                    f"{visible}\n\n{MANUAL_FALLBACK}"
                    if visible
                    else MANUAL_FALLBACK
                ),
                proposal=None,
                schema_version=projection.schema_version,
                operation_count=projection.operation_count,
                validation_outcome="stale_context",
                manual_fallback=True,
            )
        return projection

    @staticmethod
    def _discard_projection_for_collision(
        projection: YujinCreatorProjection,
    ) -> YujinCreatorProjection:
        visible = projection.reply_text.strip()
        return YujinCreatorProjection(
            reply_text=(
                f"{visible}\n\n{MANUAL_FALLBACK}"
                if visible
                else MANUAL_FALLBACK
            ),
            proposal=None,
            schema_version=projection.schema_version,
            operation_count=projection.operation_count,
            validation_outcome="proposal_conflict",
            manual_fallback=True,
        )

    @staticmethod
    def _discard_stale_projection(
        projection: YujinCreatorProjection,
    ) -> YujinCreatorProjection:
        visible = projection.reply_text.strip()
        return YujinCreatorProjection(
            reply_text=(
                f"{visible}\n\n{MANUAL_FALLBACK}"
                if visible
                else MANUAL_FALLBACK
            ),
            proposal=None,
            schema_version=projection.schema_version,
            operation_count=projection.operation_count,
            validation_outcome="stale_context",
            manual_fallback=True,
        )

    @staticmethod
    def _discard_capability_denied_projection(
        projection: YujinCreatorProjection,
    ) -> YujinCreatorProjection:
        visible = projection.reply_text.strip()
        return YujinCreatorProjection(
            reply_text=(
                f"{visible}\n\n{MANUAL_FALLBACK}"
                if visible
                else MANUAL_FALLBACK
            ),
            proposal=None,
            schema_version=projection.schema_version,
            operation_count=projection.operation_count,
            validation_outcome="capability_denied",
            manual_fallback=True,
        )

    def _publish_terminal_remainder_locked(self, run: _Run, text: str) -> None:
        if not text.startswith(run.public_text):
            return
        self._publish_public_delta_locked(run, text)

    def _normalize_terminal(self, run: _Run, event_type, text, retryable, proposal):
        if (
            event_type != "run_completed"
            or len(text.encode("utf-8")) > self.max_text_bytes
            or not text.startswith(run.public_text)
        ):
            return "blocked", self._bounded_failure_text(run), True, None
        return event_type, text, retryable, proposal

    def _bounded_failure_text(self, run: _Run) -> str:
        if run.public_text:
            suffix = self._truncate_utf8(
                f"\n\n{_BLOCKED_TEXT}",
                self.max_text_bytes - len(run.public_text.encode("utf-8")),
            )
            if not suffix:
                suffix = self._truncate_utf8("!", self.max_text_bytes - len(run.public_text.encode("utf-8")))
            return f"{run.public_text}{suffix}"
        return self._truncate_utf8(_BLOCKED_TEXT, self.max_text_bytes) or "!"

    @staticmethod
    def _truncate_utf8(text: str, limit: int) -> str:
        if limit <= 0:
            return ""
        encoded = text.encode("utf-8")
        if len(encoded) <= limit:
            return text
        return encoded[:limit].decode("utf-8", errors="ignore")

    def _sequence_fits_locked(
        self,
        run: _Run,
        *,
        target: str,
        terminal_event_type: str,
        terminal_text: str,
        include_initial_delta: bool = False,
    ) -> bool:
        texts: list[tuple[str, str, bool]] = []
        simulated_public = run.public_text
        if include_initial_delta and len(target) > len(simulated_public):
            texts.append(("text_delta", target[len(simulated_public):], False))
            simulated_public = target
        if not terminal_text.startswith(simulated_public):
            return False
        remainder = terminal_text[len(simulated_public):]
        if remainder:
            texts.append(("text_delta", remainder, False))
        texts.append((terminal_event_type, terminal_text, True))
        projected_bytes = run.event_bytes
        projected_count = len(run.events)
        for offset, (event_type, text, retryable) in enumerate(texts, start=1):
            event = HermesStreamEvent(
                event_id=projected_count + offset,
                event_type=event_type,
                text=text,
                retryable=retryable,
            )
            projected_bytes += len(event.model_dump_json().encode("utf-8"))
        return (
            projected_count + len(texts) <= self.max_events
            and projected_bytes <= self.max_event_bytes
        )

    def _publish_public_delta_locked(self, run: _Run, target: str) -> None:
        if len(target) <= len(run.public_text):
            return
        if not target.startswith(run.public_text):
            raise OverflowError("hermes_public_text_mismatch")
        delta = target[len(run.public_text) :]
        self._publish_locked(run, "text_delta", text=delta)
        run.public_text = target

    async def _release_gateway_run(self, run_id: str) -> None:
        release_run = getattr(self.gateway_client, "release_run", None)
        if release_run is None:
            return
        try:
            await asyncio.wait_for(
                release_run(run_id=run_id),
                timeout=_GATEWAY_RELEASE_TIMEOUT_SECONDS,
            )
        except Exception:
            # The gateway ledger is bounded and independently expires attached
            # context. Cleanup must never delay a durable terminal response.
            return

    @staticmethod
    def _raise_if_admission_abandoned(admission: _Admission) -> None:
        if admission.abandoned:
            raise HermesCapacityUnavailable(
                "hermes_run_admission_abandoned"
            )

    async def _terminal_done(
        self, run: _Run, completed: asyncio.Task
    ) -> None:
        if completed.cancelled() or completed.exception() is not None:
            async with self._lock:
                if not run.terminal:
                    if hasattr(
                        self.store, "list_director_hermes_run_events"
                    ):
                        self._mark_terminal_without_event_locked(run)
                    else:
                        self._publish_locked(
                            run,
                            "blocked",
                            text=_BLOCKED_TEXT,
                            retryable=True,
                            terminal=True,
                        )
                self._release_slot_and_promote_locked(run)

    def _mark_terminal_without_event_locked(self, run: _Run) -> None:
        """Close only process-local lifecycle when durable terminal CAS failed."""
        if run.terminal:
            return
        run.lifecycle = _Lifecycle.TERMINAL
        run.terminal_at = self._clock()
        run.signal.set()

    def _release_slot_and_promote_locked(self, run: _Run) -> None:
        if run.active_slot:
            run.active_slot = False
            self._active = max(0, self._active - 1)
        if self._waiting:
            self._waiting = deque(
                run_id for run_id in self._waiting if run_id != run.run_id
            )
        if self._closing:
            return
        while self._waiting and self._active < self.max_active:
            next_run = self._runs.get(self._waiting.popleft())
            if (
                next_run is not None
                and next_run.lifecycle is _Lifecycle.QUEUED
                and not next_run.terminal
            ):
                self._activate_locked(next_run)

    def _publish_locked(
        self,
        run: _Run,
        event_type: str,
        text: str = "",
        retryable: bool = False,
        terminal: bool = False,
    ) -> None:
        if run.terminal:
            return
        event = HermesStreamEvent(
            event_id=len(run.events) + 1,
            event_type=event_type,
            text=text,
            retryable=retryable,
        )
        projected_bytes = run.event_bytes + len(
            event.model_dump_json().encode("utf-8")
        )
        if not terminal and (
            len(run.events) >= self.max_events
            or projected_bytes > self.max_event_bytes
        ):
            raise OverflowError("hermes_run_event_limit")
        run.events.append(event)
        run.event_bytes = projected_bytes
        if terminal:
            run.lifecycle = _Lifecycle.TERMINAL
            run.terminal_at = self._clock()
        run.signal.set()

    def _spawn_task(
        self,
        coroutine: Coroutine,
        bucket: set[asyncio.Task],
        *,
        name: str,
        cleanup: Callable[[asyncio.Task], Coroutine] | None = None,
    ) -> asyncio.Task:
        task = asyncio.create_task(coroutine, name=name)
        bucket.add(task)

        def done(completed: asyncio.Task) -> None:
            bucket.discard(completed)
            if cleanup is not None:
                self._spawn_cleanup(cleanup(completed), name=f"{name}-cleanup")

        task.add_done_callback(done)
        return task

    def _spawn_cleanup(self, coroutine: Coroutine, *, name: str) -> None:
        task = asyncio.create_task(coroutine, name=name)
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)

    async def _await_owned_fixed_point(self) -> None:
        while True:
            tasks = tuple(
                task
                for bucket in (
                    self._admission_tasks,
                    self._dispatch_tasks,
                    self._terminal_tasks,
                    self._cleanup_tasks,
                )
                for task in bucket
                if not task.done()
            )
            if not tasks:
                # Done callbacks are scheduled with call_soon.
                await asyncio.sleep(0)
                tasks = tuple(
                    task
                    for bucket in (
                        self._admission_tasks,
                        self._dispatch_tasks,
                        self._terminal_tasks,
                        self._cleanup_tasks,
                    )
                    for task in bucket
                    if not task.done()
                )
                if not tasks:
                    return
            await asyncio.gather(*tasks, return_exceptions=True)

    def _cleanup_locked(self) -> None:
        cutoff = self._clock() - self.terminal_ttl_seconds
        for run_id, run in list(self._runs.items()):
            if run.terminal_at is not None and run.terminal_at <= cutoff:
                self._runs.pop(run_id, None)
                self._keys.pop(
                    (run.project_id, run.conversation_id, run.client_message_id),
                    None,
                )
