"""Narrow authenticated VideoBox-to-Hermes stream gateway."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator, Iterator
import hmac
import json
import os
import re
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
) -> AsyncIterator[bytes]:
    """Translate the strict Hermes stream into public NDJSON frames."""

    stream = None
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
                for public_chunk in _bounded_text_chunks(
                    final_suffix, _MAX_PUBLIC_DELTA_BYTES
                ):
                    yield _encode_public("text_delta", public_chunk)
            yield _encode_public(
                "run_completed",
                final_text,
                publish_capability_token=publish_capability_token,
            )
            return
        else:
            raise ValueError("gateway_completion_missing")
    except Exception:
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
) -> FastAPI:
    if hermes_client is not None and service_token is not None:
        if not _valid_service_token(service_token):
            raise ValueError("gateway_service_token_invalid")
        if context_ledger is None and capability_issuer is None:
            raise ValueError("gateway_capability_issuer_required")
    app = FastAPI(
        title="VideoBox Agent Gateway",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
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
    def health() -> dict[str, bool | str]:
        return {
            "status": "ready",
            "scope": "gateway_http_process",
            "hermes_http_ready": False,
            "provider_ready": False,
            "chat_ready": False,
        }

    if hermes_client is not None and service_token:
        ledger = context_ledger or CreatorContextLedger(
            capability_issuer=capability_issuer,
        )

        def require_service_token(authorization: str | None) -> None:
            expected = f"Bearer {service_token}"
            if authorization is None or not hmac.compare_digest(
                authorization, expected
            ):
                raise HTTPException(status_code=401, detail="gateway_auth_required")

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
        return create_app()
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
    return create_app(
        hermes_client=HermesRpcClient(
            base_url=url, username=username, password=password
        ),
        service_token=token,
        capability_issuer=capability_issuer,
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
