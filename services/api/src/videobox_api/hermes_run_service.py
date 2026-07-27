"""Bounded streaming registry backed by durable Director Hermes run rows."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import AsyncIterator, Callable, Coroutine

from videobox_api.models import HermesStreamEvent
from videobox_core_engine.yujin_creator_context import (
    build_yujin_creator_context,
)
from videobox_core_engine.yujin_creator_proposal_adapter import (
    MANUAL_FALLBACK,
    YujinCreatorProjection,
    parse_and_project_yujin_creator_output,
    safe_yujin_stream_visible_prefix,
)
from videobox_domain_models.yujin_creator_context import YujinCreatorContext


_BLOCKED_TEXT = "Hermes is temporarily unavailable. Manual Director remains available."
_GATEWAY_RELEASE_TIMEOUT_SECONDS = 1.0
_MIN_LIVE_DRAFT_CHARS = 16
_LOGGER = logging.getLogger(__name__)


class HermesCapacityUnavailable(RuntimeError):
    """The bounded process-local run registry has no admission capacity."""


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
    owner_token: str | None
    creator_context: YujinCreatorContext | object | None = None
    gateway_prepared: bool = False
    events: list[HermesStreamEvent] = field(default_factory=list)
    event_bytes: int = 0
    assembled: str = ""
    public_text: str = ""
    lifecycle: _Lifecycle = _Lifecycle.QUEUED
    subscriber_claimed: bool = False
    signal: asyncio.Event = field(default_factory=asyncio.Event)
    dispatch_task: asyncio.Task | None = None
    terminal_task: asyncio.Task | None = None
    active_slot: bool = False
    terminal_at: float | None = None

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


class HermesRunService:
    def __init__(
        self,
        *,
        store,
        gateway_client,
        max_active: int = 2,
        max_queue: int = 8,
        max_total: int = 64,
        max_events: int = 256,
        max_event_bytes: int = 256_000,
        max_text_bytes: int = 200_000,
        timeout_seconds: float = 35.0,
        terminal_ttl_seconds: float = 300.0,
        monotonic: Callable[[], float] = time.monotonic,
        context_builder: Callable | None = None,
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
        self._runs: dict[str, _Run] = {}
        self._keys: dict[tuple[str, str, str], str] = {}
        self._admissions: dict[tuple[str, str, str], _Admission] = {}
        self._waiting: deque[str] = deque()
        self._active = 0
        self._lock = asyncio.Lock()
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

    async def reserve_subscriber(self, run_id: str) -> None:
        async with self._lock:
            run = self.get_run(run_id)
            if run.subscriber_claimed:
                raise ValueError("hermes_run_single_subscriber")
            run.subscriber_claimed = True

    async def subscribe(
        self, run_id: str, *, reserved: bool = False
    ) -> AsyncIterator[HermesStreamEvent]:
        if not reserved:
            await self.reserve_subscriber(run_id)
        run = self.get_run(run_id)
        index = 0
        try:
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
        finally:
            if not run.terminal:
                await self.cancel(run_id)

    async def cancel(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run is None or run.terminal:
            return
        task = run.dispatch_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        await self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)

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
            durable = await asyncio.to_thread(
                self.store.begin_director_hermes_run,
                project_id=project_id,
                session_id=session_id,
                conversation_id=conversation_id,
                client_message_id=client_message_id,
                user_text=text,
                expected_session_revision=expected_session_revision,
                expected_asset_index_revision=context.asset_index_revision,
                selected_segment_id=selected_segment_id,
            )
            if (
                str(durable.get("status") or "") == "pending"
                and not bool(durable.get("dispatch"))
            ):
                raise HermesCapacityUnavailable("hermes_run_in_progress")
            if (
                str(durable.get("status") or "") == "pending"
                and bool(durable.get("dispatch"))
                and durable.get("owner_token") is not None
            ):
                try:
                    await self.gateway_client.prepare_run(
                        project_id=project_id,
                        conversation_id=conversation_id,
                        run_id=str(durable["run_id"]),
                        session_id=session_id,
                        session_revision=context.session_revision,
                        asset_index_revision=context.asset_index_revision,
                        context=context.model_dump(mode="json"),
                    )
                except BaseException:
                    try:
                        await asyncio.to_thread(
                            self.store.complete_director_hermes_run,
                            project_id=project_id,
                            run_id=str(durable["run_id"]),
                            owner_token=str(durable["owner_token"]),
                            status="blocked",
                            assistant_text=_BLOCKED_TEXT,
                            retryable=True,
                        )
                    finally:
                        raise
            run = _Run(
                run_id=str(durable["run_id"]),
                project_id=project_id,
                session_id=session_id,
                conversation_id=conversation_id,
                client_message_id=client_message_id,
                user_text=text,
                expected_session_revision=expected_session_revision,
                selected_segment_id=selected_segment_id,
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
                if status != "pending":
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
                            await self._terminal(
                                run, "blocked", _BLOCKED_TEXT, retryable=True
                            )
                            return
                        if not await self._persist_visible_draft(run):
                            await self._terminal(
                                run, "blocked", _BLOCKED_TEXT, retryable=True
                            )
                            return
                    elif upstream.event_type == "blocked":
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
                            await self._terminal(
                                run, "blocked", _BLOCKED_TEXT, retryable=True
                            )
                        else:
                            await self._terminal(
                                run,
                                "run_completed",
                                completed_text,
                                retryable=False,
                            )
                        return
                    else:
                        await self._terminal(
                            run, "blocked", _BLOCKED_TEXT, retryable=True
                        )
                        return
            await self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)
        except asyncio.CancelledError:
            await self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)
            raise
        except Exception:
            await self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)

    async def _persist_visible_draft(self, run: _Run) -> bool:
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
            stored = await asyncio.to_thread(
                append_draft,
                project_id=run.project_id,
                run_id=run.run_id,
                owner_token=run.owner_token,
                assistant_draft_text=target,
            )
        except Exception:
            return False
        if stored is not True:
            return False
        async with self._lock:
            if run.terminal or run.terminalizing:
                return False
            try:
                self._publish_public_delta_locked(run, target)
            except OverflowError:
                return False
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
    ) -> None:
        async with self._lock:
            if run.terminal:
                return
            task = run.terminal_task
            if task is None:
                run.lifecycle = _Lifecycle.TERMINALIZING
                task = self._spawn_task(
                    self._finish_terminal(
                        run,
                        event_type=event_type,
                        text=text,
                        retryable=retryable,
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
    ) -> None:
        proposal = None
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
                        preflight_failed = True
                    else:
                        if collision:
                            projection = self._discard_projection_for_collision(
                                projection
                            )
            text = projection.reply_text
            proposal = projection.proposal
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
                stored = await asyncio.to_thread(
                    self.store.complete_director_hermes_run,
                    project_id=run.project_id,
                    run_id=run.run_id,
                    owner_token=run.owner_token,
                    status=(
                        "completed"
                        if event_type == "run_completed"
                        else "blocked"
                    ),
                    assistant_text=text or _BLOCKED_TEXT,
                    retryable=retryable,
                    proposal=proposal,
                )
            except Exception:
                stored = False
            if stored == "proposal_conflict" and projection is not None:
                projection = self._discard_projection_for_collision(projection)
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
                    stored = await asyncio.to_thread(
                        self.store.complete_director_hermes_run,
                        project_id=run.project_id,
                        run_id=run.run_id,
                        owner_token=run.owner_token,
                        status=(
                            "completed"
                            if event_type == "run_completed"
                            else "blocked"
                        ),
                        assistant_text=text,
                        retryable=retryable,
                        proposal=None,
                    )
                except Exception:
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
                    event_type = "blocked"
                    text = self._bounded_failure_text(run)
                    retryable = True
                    publish_remainder = self._sequence_fits_locked(
                        run,
                        target=run.public_text,
                        terminal_event_type=event_type,
                        terminal_text=text,
                    )
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
        except Exception:
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

    async def _terminal_done(
        self, run: _Run, completed: asyncio.Task
    ) -> None:
        if completed.cancelled() or completed.exception() is not None:
            async with self._lock:
                if not run.terminal:
                    self._publish_locked(
                        run,
                        "blocked",
                        text=_BLOCKED_TEXT,
                        retryable=True,
                        terminal=True,
                    )
                self._release_slot_and_promote_locked(run)

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
