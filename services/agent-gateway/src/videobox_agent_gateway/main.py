"""Narrow authenticated VideoBox-to-Hermes stream gateway."""

from __future__ import annotations

from collections.abc import AsyncIterator
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
    r"(?i)(?:password|passwd|token|secret|api[_-]?key|provider)\s*[:=]"
    r"|/opt/data(?:/|\\|\b)|(?:^|\s)[a-z]:[\\/]|/home/",
)
_MAX_PUBLIC_TEXT_BYTES = 200_000
_MAX_PUBLIC_EVENTS = 512


def _valid_service_token(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        len(value.encode("utf-8")) >= 32
        and "changeme" not in lowered
        and "replace_me" not in lowered
        and "placeholder" not in lowered
    )


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

            async def lines() -> AsyncIterator[bytes]:
                try:
                    pending: list[dict[str, str]] = []
                    total = 0
                    aggregate = ""
                    event_count = 0
                    async for event in hermes_client.stream_prompt(text=body.text):
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
                        total += len(event.text.encode("utf-8"))
                        aggregate += event.text
                        if (
                            total > _MAX_PUBLIC_TEXT_BYTES
                            or _UNSAFE_OUTPUT.search(aggregate)
                        ):
                            raise ValueError("gateway_output_unsafe")
                        pending.append(
                            {
                                "event_type": (
                                    "text_delta"
                                    if event.event_type == "message.delta"
                                    else "run_completed"
                                ),
                                "text": event.text,
                            }
                        )
                    if not pending or pending[-1]["event_type"] != "run_completed":
                        raise ValueError("gateway_completion_missing")
                    for public in pending:
                        yield (
                            json.dumps(
                                public, ensure_ascii=True, separators=(",", ":")
                            )
                            + "\n"
                        ).encode()
                except Exception:
                    yield b'{"event_type":"blocked","text":"","retryable":true}\n'

            return StreamingResponse(lines(), media_type="application/x-ndjson")

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
