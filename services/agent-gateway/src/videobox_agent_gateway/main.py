"""Narrow authenticated VideoBox-to-Hermes stream gateway."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
import hmac
import json
import os
import re

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from videobox_agent_gateway.hermes_rpc_client import HermesRpcClient


class GatewayRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    client_message_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=20_000)


_UNSAFE_OUTPUT = re.compile(
    r"(?i)(?:authorization|proxy-authorization|cookie|set-cookie)\s*:"
    r"|\bbearer\s+[^\s]+"
    r"|(?:password|passwd|token|secret|api[_-]?key|provider)\s*[:=]"
    r"|/(?:opt/data|videobox-data|etc)(?:/|\\|\b)"
    r"|(?:^|\s)[a-z]:[\\/]|/home/",
)
_MAX_PUBLIC_TEXT_BYTES = 200_000
_MAX_PUBLIC_EVENTS = 512
_QUARANTINE_CHARS = 256
_MAX_PUBLIC_DELTA_BYTES = 32_000


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


async def _stream_public_lines(hermes_client, *, text: str) -> AsyncIterator[bytes]:
    """Translate the strict Hermes stream into public NDJSON frames."""

    try:
        assembled = ""
        assembled_bytes = 0
        emitted = ""
        quarantine = ""
        event_count = 0
        async for event in hermes_client.stream_prompt(text=text):
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
                safe_count = max(0, len(candidate) - _QUARANTINE_CHARS)
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
            yield _encode_public("run_completed", final_text)
            return
        else:
            raise ValueError("gateway_completion_missing")
    except Exception:
        yield b'{"event_type":"blocked","text":"","retryable":true}\n'


def _encode_public(event_type: str, text: str) -> bytes:
    return (
        json.dumps(
            {"event_type": event_type, "text": text},
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


def create_app(*, hermes_client=None, service_token: str | None = None) -> FastAPI:
    if hermes_client is not None and service_token is not None:
        if not _valid_service_token(service_token):
            raise ValueError("gateway_service_token_invalid")
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

        @app.post("/internal/hermes/stream")
        async def stream(
            body: GatewayRunRequest, authorization: str | None = Header(default=None)
        ) -> StreamingResponse:
            expected = f"Bearer {service_token}"
            if authorization is None or not hmac.compare_digest(
                authorization, expected
            ):
                raise HTTPException(status_code=401, detail="gateway_auth_required")

            return StreamingResponse(
                _stream_public_lines(hermes_client, text=body.text),
                media_type="application/x-ndjson",
            )

    return app


def _app_from_environment() -> FastAPI:
    url = os.environ.get("HERMES_YUJIN_URL", "")
    username = os.environ.get("HERMES_YUJIN_GATEWAY_USERNAME", "")
    password = os.environ.get("HERMES_YUJIN_GATEWAY_PASSWORD", "")
    token = os.environ.get("VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN", "")
    if not all((url, username, password, token)):
        return create_app()
    return create_app(
        hermes_client=HermesRpcClient(
            base_url=url, username=username, password=password
        ),
        service_token=token,
    )


app = _app_from_environment()
