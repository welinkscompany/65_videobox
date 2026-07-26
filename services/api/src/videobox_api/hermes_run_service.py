"""Process-local bounded streaming registry backed by durable Director run rows."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
import time
from typing import AsyncIterator, Callable

from videobox_api.agent_gateway_client import AgentGatewayUnavailable
from videobox_api.models import HermesStreamEvent


_BLOCKED_TEXT = "Hermes is temporarily unavailable. Manual Director remains available."


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
    subscriber_claimed: bool = False
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task | None = None
    terminal_at: float | None = None


class HermesRunService:
    def __init__(
        self,
        *,
        store,
        gateway_client,
        max_active: int = 2,
        max_queue: int = 8,
        max_events: int = 256,
        max_event_bytes: int = 256_000,
        max_text_bytes: int = 200_000,
        timeout_seconds: float = 35.0,
        terminal_ttl_seconds: float = 300.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.gateway_client = gateway_client
        self.max_active = max_active
        self.max_queue = max_queue
        self.max_events = max_events
        self.max_event_bytes = max_event_bytes
        self.max_text_bytes = max_text_bytes
        self.timeout_seconds = timeout_seconds
        self.terminal_ttl_seconds = terminal_ttl_seconds
        self._clock = monotonic
        self._runs: dict[str, _Run] = {}
        self._keys: dict[tuple[str, str, str], str] = {}
        self._waiting: deque[str] = deque()
        self._active = 0
        self._lock = asyncio.Lock()

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
        async with self._lock:
            self._cleanup_locked()
            existing_id = self._keys.get(key)
            if existing_id is not None:
                existing = self._runs[existing_id]
                if existing.user_text != text or existing.session_id != session_id:
                    raise ValueError(
                        "client_message_id_reused_with_different_content"
                    )
                return existing
            durable = self.store.begin_director_hermes_run(
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
            self._runs[run.run_id] = run
            self._keys[key] = run.run_id
            await self._publish_locked(run, "run_started")
            if durable.get("status") != "pending":
                await self._publish_locked(
                    run,
                    "run_completed"
                    if durable.get("status") == "completed"
                    else "blocked",
                    retryable=durable.get("status") != "completed",
                    terminal=True,
                )
            elif not durable.get("dispatch"):
                await self._publish_locked(
                    run, "blocked", text=_BLOCKED_TEXT, retryable=True, terminal=True
                )
            elif self._active < self.max_active:
                self._start_locked(run)
            elif len(self._waiting) < self.max_queue:
                self._waiting.append(run.run_id)
            else:
                await self._terminal_locked(
                    run, "blocked", _BLOCKED_TEXT, retryable=True
                )
            return run

    async def subscribe(self, run_id: str) -> AsyncIterator[HermesStreamEvent]:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError("director_hermes_run_missing")
        async with run.condition:
            if run.subscriber_claimed:
                raise ValueError("hermes_run_single_subscriber")
            run.subscriber_claimed = True
        index = 0
        try:
            while True:
                async with run.condition:
                    await run.condition.wait_for(
                        lambda: index < len(run.events) or run.terminal
                    )
                    while index < len(run.events):
                        event = run.events[index]
                        index += 1
                        yield event
                    if run.terminal:
                        return
        finally:
            if not run.terminal:
                await self.cancel(run_id)

    async def cancel(self, run_id: str) -> None:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.terminal:
                return
            if run.task is not None:
                run.task.cancel()
            await self._terminal_locked(
                run, "blocked", _BLOCKED_TEXT, retryable=True
            )

    def get_run(self, run_id: str) -> _Run:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError("director_hermes_run_missing")
        return run

    def _start_locked(self, run: _Run) -> None:
        self._active += 1
        run.task = asyncio.create_task(
            self._dispatch(run), name=f"videobox-{run.run_id}"
        )

    async def _dispatch(self, run: _Run) -> None:
        completed_text = ""
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async for upstream in self.gateway_client.stream_run(
                    session_id=run.session_id,
                    client_message_id=run.client_message_id,
                    text=run.user_text,
                ):
                    async with self._lock:
                        if run.terminal:
                            return
                        if upstream.event_type == "text_delta":
                            if not upstream.text:
                                continue
                            if (
                                len(run.assembled.encode()) + len(upstream.text.encode())
                                > self.max_text_bytes
                            ):
                                await self._terminal_locked(
                                    run, "blocked", _BLOCKED_TEXT, retryable=True
                                )
                                return
                            run.assembled += upstream.text
                            await self._publish_locked(
                                run, "text_delta", text=upstream.text
                            )
                        elif upstream.event_type == "blocked":
                            await self._terminal_locked(
                                run, "blocked", _BLOCKED_TEXT, retryable=True
                            )
                            return
                        elif upstream.event_type == "run_completed":
                            completed_text = upstream.text or run.assembled
                            await self._terminal_locked(
                                run,
                                "run_completed",
                                completed_text,
                                retryable=False,
                            )
                            return
            async with self._lock:
                if not run.terminal:
                    await self._terminal_locked(
                        run, "blocked", _BLOCKED_TEXT, retryable=True
                    )
        except (TimeoutError, AgentGatewayUnavailable, Exception):
            async with self._lock:
                if not run.terminal:
                    await self._terminal_locked(
                        run, "blocked", _BLOCKED_TEXT, retryable=True
                    )
        finally:
            async with self._lock:
                if self._active:
                    self._active -= 1
                while self._waiting and self._active < self.max_active:
                    next_run = self._runs.get(self._waiting.popleft())
                    if next_run is not None and not next_run.terminal:
                        self._start_locked(next_run)

    async def _terminal_locked(
        self,
        run: _Run,
        event_type: str,
        text: str,
        *,
        retryable: bool,
    ) -> None:
        if run.terminal:
            return
        if run.owner_token is not None:
            stored = self.store.complete_director_hermes_run(
                project_id=run.project_id,
                run_id=run.run_id,
                owner_token=run.owner_token,
                status="completed" if event_type == "run_completed" else "blocked",
                assistant_text=text or _BLOCKED_TEXT,
                retryable=retryable,
            )
            if not stored:
                return
        await self._publish_locked(
            run,
            event_type,
            text=text,
            retryable=retryable,
            terminal=True,
        )

    async def _publish_locked(
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
        projected_bytes = run.event_bytes + len(event.model_dump_json().encode())
        if not terminal and (
            len(run.events) >= self.max_events
            or projected_bytes > self.max_event_bytes
        ):
            await self._terminal_locked(
                run, "blocked", _BLOCKED_TEXT, retryable=True
            )
            return
        run.events.append(event)
        run.event_bytes = projected_bytes
        if terminal:
            run.terminal = True
            run.terminal_at = self._clock()
        async with run.condition:
            run.condition.notify_all()

    def _cleanup_locked(self) -> None:
        cutoff = self._clock() - self.terminal_ttl_seconds
        for run_id, run in list(self._runs.items()):
            if run.terminal_at is not None and run.terminal_at <= cutoff:
                self._runs.pop(run_id, None)
                self._keys.pop(
                    (run.project_id, run.conversation_id, run.client_message_id),
                    None,
                )
