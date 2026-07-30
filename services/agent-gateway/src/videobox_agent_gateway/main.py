"""Narrow authenticated VideoBox-to-Hermes stream gateway."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
import hmac
import json
import os
import re
import threading
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from videobox_agent_gateway.context_capabilities import YujinCapabilityIssuer
from videobox_agent_gateway.creator_context import (
    CreatorContextLedger,
    GatewayContextAttachRequest,
    GatewayRunIdentity,
    GatewayStreamRequest,
    prompt_envelope,
)
from videobox_agent_gateway.hermes_rpc_client import HermesRpcClient
from videobox_agent_gateway.memory_gateway import (
    ApprovedMemoryWrite,
    HermesMemoryAdapterClient,
    MemoryReconcile,
    MemoryDelete,
    MemoryDeleteResult,
    MemorySearch,
    MemorySearchResult,
    MemoryWriteOutcome,
    adapter_reconcile,
    adapter_delete,
    adapter_search,
    adapter_write,
)


class GatewayReservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=256)
    conversation_id: str = Field(min_length=1, max_length=256)
    run_id: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    session_revision: int = Field(ge=1, strict=True)
    asset_index_revision: int = Field(ge=0, strict=True)


_ASSIGNMENT_LABEL = (
    r"(?:authorization|proxy-authorization|cookie|set-cookie"
    r"|password|passwd|token|secret|provider"
    r"|api(?:[\s_-]*key)"
    r"|oauth(?:[\s_-]+token)?"
    r"|(?:access|refresh)[\s_-]+token"
    r"|client[\s_-]+secret"
    r"|mem0(?:[\s_-]+api[\s_-]*key)?)"
)
_UNSAFE_OUTPUT = re.compile(
    rf"(?i){_ASSIGNMENT_LABEL}\s*[:=]"
    r"|\bbearer\s+[^\s]+"
    r"|/(?:opt/data|videobox-data|etc)(?:/|\\|\b)"
    r"|(?:^|\s)[a-z]:[\\/]|/home/",
)
_SENSITIVE_START = re.compile(
    r"(?i)(?:proxy-authorization|authorization|set-cookie|cookie|bearer"
    r"|password|passwd|provider|token|secret"
    r"|api[_-]?key|api"
    r"|oauth[_-]token|oauth"
    r"|access[_-]token|access"
    r"|refresh[_-]token|refresh"
    r"|client[_-]secret|client"
    r"|mem0[_-]api[_-]?key|mem0)"
    r"(?![a-z0-9_])"
)
_MAX_PUBLIC_TEXT_BYTES = 200_000
_MAX_PUBLIC_EVENTS = 512
_QUARANTINE_CHARS = 256
_MAX_UNRESOLVED_QUARANTINE_BYTES = 4_096
_MAX_PUBLIC_DELTA_BYTES = 32_000
_CAPABILITY_PRIVATE_KEY_B64 = re.compile(r"[A-Za-z0-9_-]{43}\Z", re.ASCII)
_CAPABILITY_KEY_ID = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:-]{0,254}\Z",
    re.ASCII,
)
_OBSERVATION_EPOCH = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z",
    re.ASCII,
)
_OPERATIONAL_EVIDENCE_TTL = timedelta(minutes=10)
_HEALTH_PROBE_TIMEOUT_SECONDS = 3.0
_DEGRADING_FAILURE_CODES = frozenset(
    {
        "hermes_timeout",
        "hermes_unavailable",
        "hermes_ticket_expired",
    }
)


def _strict_utc_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError("gateway_operational_clock_must_be_utc")
    return value.astimezone(UTC)


def _utc_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


class _GatewayRunObservation:
    def __init__(
        self,
        *,
        observer: "_GatewayOperationalObserver",
        generation: int,
    ) -> None:
        self._observer = observer
        self._generation = generation
        self._sequence = 0

    def _next_order(self) -> tuple[int, int]:
        self._sequence += 1
        return (self._generation, self._sequence)

    def public_delta(self) -> None:
        self._observer._record_public_delta(self._next_order())

    def public_completion(self) -> None:
        self._observer._record_public_completion(self._next_order())

    def final_failure(self, reason: str) -> None:
        self._observer._record_final_failure(
            self._next_order(),
            reason=reason,
        )


class _GatewayOperationalObserver:
    """Process-local, redacted readiness evidence with monotonic ordering."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        observation_epoch: str | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        epoch = observation_epoch or f"gateway-{uuid.uuid4().hex}"
        if _OBSERVATION_EPOCH.fullmatch(epoch) is None:
            raise ValueError("gateway_observation_epoch_invalid")
        self._epoch = epoch
        self._process_started_at = _strict_utc_now(self._clock)
        self._lock = threading.Lock()
        self._generation = 0
        self._version = 0
        self._last_order = (0, 0)
        self._provider_ready = False
        self._chat_ready = False
        self._degraded = False
        self._provider_observed_at: datetime | None = None
        self._last_chat_verified_at: datetime | None = None
        self._evidence_valid_until: datetime | None = None

    def begin_run(self) -> _GatewayRunObservation:
        with self._lock:
            self._generation += 1
            generation = self._generation
        return _GatewayRunObservation(
            observer=self,
            generation=generation,
        )

    def _record_public_delta(self, order: tuple[int, int]) -> None:
        now = _strict_utc_now(self._clock)
        with self._lock:
            if order <= self._last_order:
                return
            self._last_order = order
            self._version += 1
            self._provider_observed_at = now
            self._evidence_valid_until = (
                now + _OPERATIONAL_EVIDENCE_TTL
            )
            if not self._degraded:
                self._provider_ready = True

    def _record_public_completion(self, order: tuple[int, int]) -> None:
        now = _strict_utc_now(self._clock)
        with self._lock:
            if order <= self._last_order:
                return
            self._last_order = order
            self._version += 1
            self._provider_ready = True
            self._chat_ready = True
            self._degraded = False
            self._provider_observed_at = now
            self._last_chat_verified_at = now
            self._evidence_valid_until = (
                now + _OPERATIONAL_EVIDENCE_TTL
            )

    def _record_final_failure(
        self,
        order: tuple[int, int],
        *,
        reason: str,
    ) -> None:
        if reason not in _DEGRADING_FAILURE_CODES:
            return
        now = _strict_utc_now(self._clock)
        with self._lock:
            if (
                order <= self._last_order
                or self._last_chat_verified_at is None
            ):
                return
            self._last_order = order
            self._version += 1
            self._provider_ready = False
            self._chat_ready = False
            self._degraded = True
            self._evidence_valid_until = (
                now + _OPERATIONAL_EVIDENCE_TTL
            )

    def snapshot(self) -> dict[str, object]:
        now = _strict_utc_now(self._clock)
        with self._lock:
            evidence_current = (
                self._evidence_valid_until is not None
                and now < self._evidence_valid_until
            )
            return {
                "provider_ready": (
                    self._provider_ready if evidence_current else False
                ),
                "chat_ready": (
                    self._chat_ready if evidence_current else False
                ),
                "degraded": (
                    self._degraded if evidence_current else False
                ),
                "observation_epoch": self._epoch,
                "process_started_at": _utc_text(
                    self._process_started_at
                ),
                "provider_observed_at": _utc_text(
                    self._provider_observed_at
                ),
                "last_chat_verified_at": _utc_text(
                    self._last_chat_verified_at
                ),
                "evidence_valid_until": _utc_text(
                    self._evidence_valid_until
                ),
            }

    def version(self) -> int:
        with self._lock:
            return self._version


def _valid_service_token(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        len(value.encode("utf-8")) >= 32
        and value == value.strip()
        and len(set(value)) >= 8
        and "changeme" not in lowered
        and "replace_me" not in lowered
        and "placeholder" not in lowered
    )


async def _stream_public_lines(
    hermes_client,
    *,
    text: str,
    run_id: str | None = None,
    publish_capability_token: str | None = None,
    operational_observer: _GatewayOperationalObserver | None = None,
) -> AsyncIterator[bytes]:
    """Translate the strict Hermes stream into public NDJSON frames."""

    stream = None
    run_observation = (
        operational_observer.begin_run()
        if operational_observer is not None
        else None
    )
    try:
        assembled = ""
        assembled_bytes = 0
        emitted = ""
        quarantine = ""
        event_count = 0
        stream = (
            hermes_client.stream_prompt(text=text, run_id=run_id)
            if run_id is not None
            else hermes_client.stream_prompt(text=text)
        )
        async for event in stream:
            event_count += 1
            if event_count > _MAX_PUBLIC_EVENTS:
                raise ValueError("gateway_event_limit")
            if event.event_type == "gateway.ready":
                continue
            if event.event_type not in {
                "message.delta",
                "message.complete",
            }:
                raise ValueError("gateway_event_invalid")
            chunk_bytes = len(event.text.encode("utf-8"))
            if chunk_bytes > _MAX_PUBLIC_TEXT_BYTES:
                raise ValueError("gateway_output_limit")
            if event.event_type == "message.delta":
                if assembled_bytes + chunk_bytes > _MAX_PUBLIC_TEXT_BYTES:
                    raise ValueError("gateway_output_limit")
                candidate = quarantine + event.text
                if _UNSAFE_OUTPUT.search(candidate):
                    raise ValueError("gateway_output_unsafe")
                assembled += event.text
                assembled_bytes += chunk_bytes
                unresolved_at = _earliest_unresolved_sensitive_start(candidate)
                if unresolved_at is None:
                    safe_count = max(0, len(candidate) - _QUARANTINE_CHARS)
                else:
                    safe_count = unresolved_at
                    if (
                        len(candidate[unresolved_at:].encode("utf-8"))
                        > _MAX_UNRESOLVED_QUARANTINE_BYTES
                    ):
                        raise ValueError("gateway_output_unsafe")
                safe_prefix = candidate[:safe_count]
                quarantine = candidate[safe_count:]
                if safe_prefix:
                    if run_observation is not None:
                        run_observation.public_delta()
                    emitted += safe_prefix
                    for public_chunk in _bounded_text_chunks(
                        safe_prefix, _MAX_PUBLIC_DELTA_BYTES
                    ):
                        yield _encode_public("text_delta", public_chunk)
                continue

            final_text = event.text
            if (
                not final_text.strip()
                or _UNSAFE_OUTPUT.search(final_text)
                or not final_text.startswith(emitted)
            ):
                raise ValueError("gateway_output_unsafe")
            final_suffix = final_text[len(emitted):]
            if final_suffix:
                if run_observation is not None:
                    run_observation.public_delta()
                for public_chunk in _bounded_text_chunks(
                    final_suffix, _MAX_PUBLIC_DELTA_BYTES
                ):
                    yield _encode_public("text_delta", public_chunk)
            if run_observation is not None:
                run_observation.public_completion()
            yield _encode_public(
                "run_completed",
                final_text,
                publish_capability_token=publish_capability_token,
            )
            return
        else:
            raise ValueError("gateway_completion_missing")
    except Exception as error:
        if run_observation is not None:
            run_observation.final_failure(str(error))
        yield b'{"event_type":"blocked","text":"","retryable":true}\n'
    finally:
        if stream is not None:
            close = getattr(stream, "aclose", None)
            if callable(close):
                try:
                    await close()
                except Exception:
                    pass


def _earliest_unresolved_sensitive_start(text: str) -> int | None:
    """Find content that must stay private until its syntax is resolved."""

    for match in _SENSITIVE_START.finditer(text):
        label = match.group(0).lower()
        label_end = match.end()

        if label == "bearer":
            if label_end == len(text):
                return match.start()
            if text[label_end].isspace():
                next_nonspace = _skip_whitespace(text, label_end)
                if next_nonspace == len(text):
                    return match.start()
            continue

        if label == "api":
            state, label_end = _scan_label_extension(
                text,
                label_end,
                expected="key",
            )
            if state == "unresolved":
                return match.start()
            if state == "resolved":
                continue
        elif label in {"access", "refresh"}:
            state, label_end = _scan_label_extension(
                text,
                label_end,
                expected="token",
            )
            if state == "unresolved":
                return match.start()
            if state == "resolved":
                continue
        elif label == "client":
            state, label_end = _scan_label_extension(
                text,
                label_end,
                expected="secret",
            )
            if state == "unresolved":
                return match.start()
            if state == "resolved":
                continue
        elif label == "oauth":
            state, extension_end = _scan_label_extension(
                text,
                label_end,
                expected="token",
            )
            if state == "unresolved":
                return match.start()
            if state == "complete":
                label_end = extension_end
        elif label == "mem0":
            state, extension_end = _scan_mem0_extension(text, label_end)
            if state == "unresolved":
                return match.start()
            if state == "complete":
                label_end = extension_end

        delimiter_at = _skip_whitespace(text, label_end)
        if delimiter_at == len(text):
            return match.start()
    return None


def _scan_label_extension(
    text: str,
    start: int,
    *,
    expected: str,
) -> tuple[str, int]:
    if start == len(text):
        return ("unresolved", start)
    if text[start] in ":=":
        return ("resolved", start)
    if not (text[start].isspace() or text[start] in "_-"):
        return ("resolved", start)

    word_at = start
    while word_at < len(text) and (
        text[word_at].isspace() or text[word_at] in "_-"
    ):
        word_at += 1
    if word_at == len(text):
        return ("unresolved", word_at)

    available = text[word_at : word_at + len(expected)].lower()
    if expected.startswith(available) and len(available) < len(expected):
        return ("unresolved", len(text))
    if available != expected:
        return ("resolved", start)
    word_end = word_at + len(expected)
    if word_end < len(text) and (
        text[word_end].isalnum() or text[word_end] == "_"
    ):
        return ("resolved", start)
    return ("complete", word_end)


def _scan_mem0_extension(text: str, start: int) -> tuple[str, int]:
    state, api_end = _scan_label_extension(
        text,
        start,
        expected="api",
    )
    if state != "complete":
        return (state, api_end)
    return _scan_label_extension(
        text,
        api_end,
        expected="key",
    )


def _skip_whitespace(text: str, start: int) -> int:
    while start < len(text) and text[start].isspace():
        start += 1
    return start


def _encode_public(
    event_type: str,
    text: str,
    *,
    publish_capability_token: str | None = None,
) -> bytes:
    payload: dict[str, str] = {"event_type": event_type, "text": text}
    if publish_capability_token is not None:
        if event_type != "run_completed":
            raise ValueError("gateway_capability_frame_invalid")
        payload["publish_capability_token"] = publish_capability_token
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _bounded_text_chunks(text: str, max_bytes: int) -> Iterator[str]:
    start = 0
    size = 0
    for index, character in enumerate(text):
        character_bytes = len(character.encode("utf-8"))
        if size + character_bytes > max_bytes:
            yield text[start:index]
            start = index
            size = 0
        size += character_bytes
    if start < len(text):
        yield text[start:]


def create_app(
    *,
    hermes_client=None,
    service_token: str | None = None,
    context_ledger: CreatorContextLedger | None = None,
    capability_issuer: YujinCapabilityIssuer | None = None,
    hermes_http_probe: Callable[[], Awaitable[bool]] | None = None,
    operational_clock: Callable[[], datetime] | None = None,
    observation_epoch: str | None = None,
    memory_gateway=None,
) -> FastAPI:
    if hermes_client is not None and service_token is not None:
        if not _valid_service_token(service_token):
            raise ValueError("gateway_service_token_invalid")
        if context_ledger is None and capability_issuer is None:
            raise ValueError("gateway_capability_issuer_required")
    if memory_gateway is not None and (
        service_token is None or not _valid_service_token(service_token)
    ):
        raise ValueError("gateway_service_token_invalid")
    app = FastAPI(
        title="VideoBox Agent Gateway",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    gateway_configured = hermes_client is not None and bool(service_token)
    observer = _GatewayOperationalObserver(
        clock=operational_clock,
        observation_epoch=observation_epoch,
    )

    def require_service_token(authorization: str | None) -> None:
        if service_token is None:
            raise HTTPException(
                status_code=401, detail="gateway_auth_required"
            )
        expected = f"Bearer {service_token}"
        if authorization is None or not hmac.compare_digest(
            authorization, expected
        ):
            raise HTTPException(
                status_code=401, detail="gateway_auth_required"
            )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "gateway_request_invalid"},
        )

    @app.get("/health")
    async def health() -> dict[str, object]:
        observation_version_before_probe = observer.version()
        hermes_http_ready = False
        if gateway_configured and hermes_http_probe is not None:
            try:
                hermes_http_ready = bool(
                    await asyncio.wait_for(
                        hermes_http_probe(),
                        timeout=_HEALTH_PROBE_TIMEOUT_SECONDS,
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                hermes_http_ready = False
        observation = observer.snapshot()
        if (
            not hermes_http_ready
            and observer.version() != observation_version_before_probe
            and (
                bool(observation["provider_ready"])
                or bool(observation["chat_ready"])
            )
        ):
            hermes_http_ready = True
        elif not hermes_http_ready:
            observation = {
                **observation,
                "provider_ready": False,
                "chat_ready": False,
            }
        return {
            "status": "ready",
            "scope": "gateway_http_process",
            "gateway_configured": gateway_configured,
            "capability_routes_ready": gateway_configured,
            "hermes_http_ready": hermes_http_ready,
            **observation,
            "status_basis": "gateway_observation",
        }

    if hermes_client is not None and service_token:
        ledger = context_ledger or CreatorContextLedger(
            capability_issuer=capability_issuer,
        )

        @app.post("/internal/hermes/runs")
        async def reserve_run(
            body: GatewayReservationRequest,
            authorization: str | None = Header(default=None),
        ) -> dict[str, object]:
            require_service_token(authorization)
            identity = GatewayRunIdentity.model_validate(body.model_dump())
            try:
                reservation = ledger.reserve(identity)
            except OverflowError as error:
                raise HTTPException(
                    status_code=503, detail="gateway_reservation_unavailable"
                ) from error
            except ValueError as error:
                raise HTTPException(
                    status_code=409, detail="gateway_reservation_rejected"
                ) from error
            return {
                "run_id": identity.run_id,
                "attach_context": reservation.attach_context,
                "expires_in_seconds": reservation.expires_in_seconds,
                "read_capability_token": (
                    reservation.read_capability_token
                ),
                "capabilities": [
                    item.as_dict() for item in reservation.capabilities
                ],
            }

        @app.post(
            "/internal/hermes/runs/{run_id}/context",
            status_code=204,
            response_class=Response,
        )
        async def attach_context(
            run_id: str,
            body: GatewayContextAttachRequest,
            authorization: str | None = Header(default=None),
            attach_ticket: str | None = Header(
                default=None, alias="X-VideoBox-Attach-Ticket"
            ),
        ) -> Response:
            require_service_token(authorization)
            if not attach_ticket:
                raise HTTPException(
                    status_code=401, detail="gateway_attach_ticket_required"
                )
            try:
                ledger.attach(
                    run_id=run_id,
                    ticket=attach_ticket,
                    identity=body.identity,
                    context=body.context,
                )
            except ValueError as error:
                raise HTTPException(
                    status_code=409, detail="gateway_context_rejected"
                ) from error
            return Response(status_code=204)

        @app.post("/internal/hermes/runs/{run_id}/stream")
        async def stream(
            run_id: str,
            body: GatewayStreamRequest,
            authorization: str | None = Header(default=None),
        ) -> StreamingResponse:
            require_service_token(authorization)
            try:
                (
                    _identity,
                    context_json,
                    publish_capability_token,
                ) = ledger.consume(run_id=run_id)
            except ValueError as error:
                raise HTTPException(
                    status_code=409, detail="gateway_stream_rejected"
                ) from error
            return StreamingResponse(
                _stream_public_lines(
                    hermes_client,
                    run_id=run_id,
                    text=prompt_envelope(
                        user_text=body.text,
                        context_json=context_json,
                    ),
                    publish_capability_token=publish_capability_token,
                    operational_observer=observer,
                ),
                media_type="application/x-ndjson",
            )

        @app.post(
            "/internal/hermes/runs/{run_id}/cancel",
            status_code=204,
            response_class=Response,
        )
        async def cancel_run(
            run_id: str,
            authorization: str | None = Header(default=None),
        ) -> Response:
            require_service_token(authorization)
            await hermes_client.interrupt(run_id=run_id)
            return Response(status_code=204)

        @app.delete(
            "/internal/hermes/runs/{run_id}",
            status_code=204,
            response_class=Response,
        )
        async def release_run(
            run_id: str,
            authorization: str | None = Header(default=None),
        ) -> Response:
            require_service_token(authorization)
            ledger.release(run_id=run_id)
            return Response(status_code=204)

    if memory_gateway is not None:

        @app.post(
            "/internal/hermes/memory/add",
            response_model=MemoryWriteOutcome,
        )
        async def add_approved_memory(
            body: ApprovedMemoryWrite,
            authorization: str | None = Header(default=None),
        ) -> MemoryWriteOutcome:
            require_service_token(authorization)
            try:
                return await memory_gateway.add_approved(
                    adapter_write(body)
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                raise HTTPException(
                    status_code=503,
                    detail="gateway_memory_unavailable",
                ) from None

        @app.post(
            "/internal/hermes/memory/reconcile",
            response_model=MemoryWriteOutcome,
        )
        async def reconcile_memory(
            body: MemoryReconcile,
            authorization: str | None = Header(default=None),
        ) -> MemoryWriteOutcome:
            require_service_token(authorization)
            try:
                return await memory_gateway.reconcile(
                    adapter_reconcile(body)
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                raise HTTPException(
                    status_code=503,
                    detail="gateway_memory_unavailable",
                ) from None

        @app.post(
            "/internal/hermes/memory/search",
            response_model=MemorySearchResult,
        )
        async def search_memory(
            body: MemorySearch,
            authorization: str | None = Header(default=None),
        ) -> MemorySearchResult:
            require_service_token(authorization)
            try:
                return await memory_gateway.search(
                    adapter_search(body)
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                raise HTTPException(
                    status_code=503,
                    detail="gateway_memory_unavailable",
                ) from None

        @app.post(
            "/internal/hermes/memory/delete",
            response_model=MemoryDeleteResult,
        )
        async def delete_memory(
            body: MemoryDelete,
            authorization: str | None = Header(default=None),
        ) -> MemoryDeleteResult:
            require_service_token(authorization)
            try:
                return await memory_gateway.delete(
                    adapter_delete(body)
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                raise HTTPException(
                    status_code=503,
                    detail="gateway_memory_unavailable",
                ) from None

    return app


def _app_from_environment() -> FastAPI:
    url = os.environ.get("HERMES_YUJIN_URL", "")
    username = os.environ.get("HERMES_YUJIN_GATEWAY_USERNAME", "")
    password = os.environ.get("HERMES_YUJIN_GATEWAY_PASSWORD", "")
    token = os.environ.get("VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN", "")
    private_key_b64 = os.environ.get(
        "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64",
        "",
    )
    key_id = os.environ.get("VIDEOBOX_HERMES_CAPABILITY_KEY_ID", "")
    memory_url = os.environ.get("HERMES_MEMORY_ADAPTER_URL", "")
    memory_token = os.environ.get(
        "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN", ""
    )
    memory_gateway = None
    if memory_url and memory_token:
        try:
            memory_gateway = HermesMemoryAdapterClient(
                base_url=memory_url,
                service_token=memory_token,
            )
        except ValueError:
            memory_gateway = None
    if not all(
        (
            url,
            username,
            password,
            token,
            private_key_b64,
            key_id,
        )
    ):
        return create_app(
            service_token=token if memory_gateway is not None else None,
            memory_gateway=memory_gateway,
        )
    try:
        private_key = _parse_capability_private_key(private_key_b64)
        _validate_capability_key_id(key_id)
        capability_issuer = YujinCapabilityIssuer(
            key_id=key_id,
            private_key=private_key,
            capability_id_factory=(
                lambda: f"capability-{uuid.uuid4().hex}"
            ),
        )
    except (TypeError, ValueError):
        return create_app()
    hermes_client = HermesRpcClient(
        base_url=url, username=username, password=password
    )
    return create_app(
        hermes_client=hermes_client,
        service_token=token,
        capability_issuer=capability_issuer,
        hermes_http_probe=hermes_client.probe_http_ready,
        memory_gateway=memory_gateway,
    )


def _parse_capability_private_key(value: object) -> bytes:
    if (
        type(value) is not str
        or _CAPABILITY_PRIVATE_KEY_B64.fullmatch(value) is None
    ):
        raise ValueError("gateway_capability_private_key_invalid")
    try:
        decoded = base64.b64decode(
            value + "=",
            altchars=b"-_",
            validate=True,
        )
    except Exception as error:
        raise ValueError(
            "gateway_capability_private_key_invalid"
        ) from error
    canonical = (
        base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    )
    if len(decoded) != 32 or canonical != value:
        raise ValueError("gateway_capability_private_key_invalid")
    return decoded


def _validate_capability_key_id(value: object) -> str:
    if (
        type(value) is not str
        or _CAPABILITY_KEY_ID.fullmatch(value) is None
        or any(
            marker in value.lower()
            for marker in ("changeme", "replace_me", "placeholder")
        )
    ):
        raise ValueError("gateway_capability_key_id_invalid")
    return value


app = _app_from_environment()
