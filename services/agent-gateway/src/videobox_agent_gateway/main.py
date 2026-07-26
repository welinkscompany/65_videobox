"""Narrow authenticated VideoBox-to-Hermes stream gateway."""

from __future__ import annotations

from collections.abc import AsyncIterator
import hmac
import json
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from videobox_agent_gateway.hermes_rpc_client import HermesRpcClient


class GatewayRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    client_message_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=20_000)


def create_app(*, hermes_client=None, service_token: str | None = None) -> FastAPI:
    app = FastAPI(
        title="VideoBox Agent Gateway",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
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
                    async for event in hermes_client.stream_prompt(text=body.text):
                        if event.event_type == "gateway.ready":
                            continue
                        event_type = (
                            "text_delta"
                            if event.event_type == "message.delta"
                            else "run_completed"
                        )
                        public = {"event_type": event_type, "text": event.text}
                        yield (json.dumps(public, ensure_ascii=True) + "\n").encode()
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
