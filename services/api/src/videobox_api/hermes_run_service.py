"""Bounded streaming registry backed by durable Director Hermes run rows."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
import time
from typing import AsyncIterator, Callable

from videobox_api.models import HermesStreamEvent


_BLOCKED_TEXT = "Hermes is temporarily unavailable. Manual Director remains available."


class HermesCapacityUnavailable(RuntimeError):
    """The bounded process-local run registry has no admission capacity."""


@dataclass
class _Run:
    run_id: str
    project_id: str
    session_id: str
    conversation_id: str
    client_message_id: str
    user_text: str
    owner_token: str | None
    events: list[HermesStreamEvent] = field(default_factory=list)
    event_bytes: int = 0
    assembled: str = ""
    terminal: bool = False
    terminalizing: bool = False
    subscriber_claimed: bool = False
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task | None = None
    active_slot: bool = False
    terminal_at: float | None = None


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
        self._runs: dict[str, _Run] = {}
        self._keys: dict[tuple[str, str, str], str] = {}
        self._admissions: dict[
            tuple[str, str, str], asyncio.Future[None]
        ] = {}
        self._waiting: deque[str] = deque()
        self._active = 0
        self._lock = asyncio.Lock()
        self._closing = False

    async def create_run(
        self,
        *,
        project_id: str,
        session_id: str,
        conversation_id: str,
        client_message_id: str,
        text: str,
    ) -> _Run:
        key = (project_id, conversation_id, client_message_id)
        wait_for: asyncio.Future[None] | None = None
        admission: asyncio.Future[None] | None = None
        async with self._lock:
            self._cleanup_locked()
            if self._closing:
                raise HermesCapacityUnavailable("hermes_run_service_closing")
            existing_id = self._keys.get(key)
            if existing_id is not None:
                existing = self._runs[existing_id]
                self._validate_duplicate(existing, session_id=session_id, text=text)
                return existing
            wait_for = self._admissions.get(key)
            if wait_for is None:
                live_count = sum(not run.terminal for run in self._runs.values())
                if (
                    len(self._runs) + len(self._admissions) >= self.max_total
                    or live_count + len(self._admissions)
                    >= self.max_active + self.max_queue
                ):
                    raise HermesCapacityUnavailable("hermes_run_capacity_exhausted")
                admission = asyncio.get_running_loop().create_future()
                self._admissions[key] = admission

        if wait_for is not None:
            await asyncio.shield(wait_for)
            return await self.create_run(
                project_id=project_id,
                session_id=session_id,
                conversation_id=conversation_id,
                client_message_id=client_message_id,
                text=text,
            )

        try:
            durable = await asyncio.to_thread(
                self.store.begin_director_hermes_run,
                project_id=project_id,
                session_id=session_id,
                conversation_id=conversation_id,
                client_message_id=client_message_id,
                user_text=text,
            )
            run = _Run(
                run_id=str(durable["run_id"]),
                project_id=project_id,
                session_id=session_id,
                conversation_id=conversation_id,
                client_message_id=client_message_id,
                user_text=text,
                owner_token=durable.get("owner_token"),
            )
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
                        text=terminal_text if status == "completed" else _BLOCKED_TEXT,
                        retryable=status != "completed",
                        terminal=True,
                    )
                elif not durable.get("dispatch"):
                    self._publish_locked(
                        run,
                        "blocked",
                        text=_BLOCKED_TEXT,
                        retryable=True,
                        terminal=True,
                    )
                elif self._active < self.max_active:
                    self._start_locked(run)
                elif len(self._waiting) < self.max_queue:
                    self._waiting.append(run.run_id)
                else:
                    self._publish_locked(
                        run,
                        "blocked",
                        text=_BLOCKED_TEXT,
                        retryable=True,
                        terminal=True,
                    )
                self._admissions.pop(key, None)
                assert admission is not None
                admission.set_result(None)
            return run
        except BaseException as error:
            async with self._lock:
                self._admissions.pop(key, None)
                if admission is not None and not admission.done():
                    admission.set_exception(error)
                    # Consume the exception when no duplicate caller was waiting.
                    admission.exception()
            raise

    async def reserve_subscriber(self, run_id: str) -> None:
        run = self.get_run(run_id)
        async with run.condition:
            if run.subscriber_claimed:
                raise ValueError("hermes_run_single_subscriber")
            run.subscriber_claimed = True

    async def subscribe(
        self, run_id: str, *, reserved: bool = False
    ) -> AsyncIterator[HermesStreamEvent]:
        run = self.get_run(run_id)
        if not reserved:
            await self.reserve_subscriber(run_id)
        index = 0
        try:
            while True:
                async with run.condition:
                    await run.condition.wait_for(
                        lambda: index < len(run.events) or run.terminal
                    )
                    batch = run.events[index:]
                    index = len(run.events)
                    terminal = run.terminal
                for event in batch:
                    yield event
                if terminal:
                    return
        finally:
            if not run.terminal:
                await self.cancel(run_id)

    async def cancel(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run is None or run.terminal:
            return
        task = run.task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        await self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)

    async def shutdown(self) -> None:
        async with self._lock:
            self._closing = True
            tasks = [
                run.task
                for run in self._runs.values()
                if run.task is not None and not run.task.done()
            ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for run in list(self._runs.values()):
            if not run.terminal:
                await self._terminal(
                    run, "blocked", _BLOCKED_TEXT, retryable=True
                )

    def get_run(self, run_id: str) -> _Run:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError("director_hermes_run_missing")
        return run

    @staticmethod
    def _validate_duplicate(run: _Run, *, session_id: str, text: str) -> None:
        if run.user_text != text or run.session_id != session_id:
            raise ValueError("client_message_id_reused_with_different_content")

    def _start_locked(self, run: _Run) -> None:
        self._active += 1
        run.active_slot = True
        run.task = asyncio.create_task(
            self._dispatch(run), name=f"videobox-{run.run_id}"
        )

    async def _dispatch(self, run: _Run) -> None:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async for upstream in self.gateway_client.stream_run(
                    session_id=run.session_id,
                    client_message_id=run.client_message_id,
                    text=run.user_text,
                ):
                    if run.terminal:
                        return
                    if upstream.event_type == "text_delta":
                        if not upstream.text:
                            continue
                        overflow = False
                        async with self._lock:
                            if run.terminal:
                                return
                            if (
                                len(run.assembled.encode("utf-8"))
                                + len(upstream.text.encode("utf-8"))
                                > self.max_text_bytes
                            ):
                                overflow = True
                            else:
                                run.assembled += upstream.text
                                try:
                                    self._publish_locked(
                                        run, "text_delta", text=upstream.text
                                    )
                                except OverflowError:
                                    overflow = True
                        if overflow:
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
                        if not completed_text.strip():
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
            await asyncio.shield(
                self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)
            )
            raise
        except Exception:
            await self._terminal(run, "blocked", _BLOCKED_TEXT, retryable=True)
        finally:
            async with self._lock:
                if run.active_slot:
                    run.active_slot = False
                    self._active -= 1
                while self._waiting and self._active < self.max_active:
                    next_run = self._runs.get(self._waiting.popleft())
                    if next_run is not None and not next_run.terminal:
                        self._start_locked(next_run)

    async def _terminal(
        self,
        run: _Run,
        event_type: str,
        text: str,
        *,
        retryable: bool,
    ) -> None:
        async with run.condition:
            if run.terminal or run.terminalizing:
                return
            run.terminalizing = True

        stored = True
        cancellation_requested = False
        if run.owner_token is not None:
            store_task = asyncio.create_task(
                asyncio.to_thread(
                    self.store.complete_director_hermes_run,
                    project_id=run.project_id,
                    run_id=run.run_id,
                    owner_token=run.owner_token,
                    status=(
                        "completed" if event_type == "run_completed" else "blocked"
                    ),
                    assistant_text=text or _BLOCKED_TEXT,
                    retryable=retryable,
                )
            )
            try:
                stored = await asyncio.shield(store_task)
            except asyncio.CancelledError:
                cancellation_requested = True
                try:
                    stored = await store_task
                except Exception:
                    stored = False
            except Exception:
                stored = False

        async with self._lock:
            if run.terminal:
                return
            if not stored:
                event_type = "blocked"
                text = _BLOCKED_TEXT
                retryable = True
            self._publish_locked(
                run,
                event_type,
                text=text,
                retryable=retryable,
                terminal=True,
            )
        if cancellation_requested:
            raise asyncio.CancelledError

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
            run.terminal = True
            run.terminalizing = False
            run.terminal_at = self._clock()

        async def notify() -> None:
            async with run.condition:
                run.condition.notify_all()

        asyncio.create_task(notify())

    def _cleanup_locked(self) -> None:
        cutoff = self._clock() - self.terminal_ttl_seconds
        for run_id, run in list(self._runs.items()):
            if run.terminal_at is not None and run.terminal_at <= cutoff:
                self._runs.pop(run_id, None)
                self._keys.pop(
                    (run.project_id, run.conversation_id, run.client_message_id),
                    None,
                )
