"""Isolated Mem0 adapter that never starts the Hermes agent loop."""

from __future__ import annotations

import hmac
import os
import secrets
import threading
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from videobox_agent_gateway.memory_gateway import (
    AdapterMemoryReconcile,
    AdapterMemoryDelete,
    AdapterMemorySearch,
    MemoryDeleteResult,
    MemorySearchResult,
    AdapterMemoryWrite,
    MemoryWriteOutcome,
    RetrievedMemory,
)


def _valid_token(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        len(value.encode("utf-8")) >= 32
        and value == value.strip()
        and len(set(value)) >= 8
        and "changeme" not in lowered
        and "replace_me" not in lowered
        and "placeholder" not in lowered
    )


def _bounded_ref(value: object) -> str | None:
    if type(value) is not str or not 1 <= len(value) <= 256:
        return None
    if not all(character.isalnum() or character in "._:-" for character in value):
        return None
    return value


def _direct_memory_ref(result: object) -> str | None:
    if type(result) is not dict:
        return None
    direct = _bounded_ref(result.get("memory_id"))
    if direct is not None:
        return direct
    results = result.get("results")
    if type(results) is not list or len(results) != 1:
        return None
    item = results[0]
    if type(item) is not dict:
        return None
    return _bounded_ref(item.get("id") or item.get("memory_id"))


def _event_ref(result: object) -> str | None:
    if type(result) is not dict:
        return None
    return _bounded_ref(result.get("event_id"))


def _outcome_from_add(result: object) -> MemoryWriteOutcome:
    memory_ref = _direct_memory_ref(result)
    if memory_ref is not None:
        return MemoryWriteOutcome(status="stored", memory_ref=memory_ref)
    event_ref = _event_ref(result)
    if event_ref is not None:
        return MemoryWriteOutcome(
            status="event_pending", event_ref=event_ref
        )
    return MemoryWriteOutcome(status="ambiguous")


def _outcome_from_event(
    result: object, request: AdapterMemoryReconcile
) -> MemoryWriteOutcome:
    if type(result) is not dict:
        return MemoryWriteOutcome(status="ambiguous")
    state = str(result.get("status", "")).upper()
    if state in {"PENDING", "RUNNING"}:
        return MemoryWriteOutcome(
            status="event_pending", event_ref=request.event_ref
        )
    if state == "FAILED":
        return MemoryWriteOutcome(status="failed_retryable")
    if state != "SUCCEEDED":
        return MemoryWriteOutcome(status="ambiguous")
    results = result.get("results")
    if type(results) is not list or len(results) != 1:
        return MemoryWriteOutcome(status="ambiguous")
    item = results[0]
    if type(item) is not dict:
        return MemoryWriteOutcome(status="ambiguous")
    memory_ref = _bounded_ref(item.get("id") or item.get("memory_id"))
    text = item.get("memory")
    metadata = item.get("metadata")
    if (
        memory_ref is None
        or text != request.text
        or metadata
        != {
            "source": "videobox_yujin_approved_v1",
            "category": request.category,
            "external_ref": request.external_ref,
        }
    ):
        return MemoryWriteOutcome(status="ambiguous")
    return MemoryWriteOutcome(status="stored", memory_ref=memory_ref)


def _outcome_from_search(
    result: object, request: AdapterMemoryReconcile
) -> MemoryWriteOutcome:
    if type(result) is dict:
        results = result.get("results")
    else:
        results = result
    if type(results) is not list:
        return MemoryWriteOutcome(status="ambiguous")
    if len(results) == 0:
        return MemoryWriteOutcome(status="failed_retryable")
    matches = []
    expected_metadata = {
        "source": "videobox_yujin_approved_v1",
        "category": request.category,
        "external_ref": request.external_ref,
    }
    for item in results:
        if (
            type(item) is dict
            and item.get("memory") == request.text
            and item.get("metadata") == expected_metadata
            and _bounded_ref(item.get("id") or item.get("memory_id"))
            is not None
        ):
            matches.append(item)
    if len(results) != 1 or len(matches) != 1:
        return MemoryWriteOutcome(status="ambiguous")
    memory_ref = _bounded_ref(
        matches[0].get("id") or matches[0].get("memory_id")
    )
    return MemoryWriteOutcome(status="stored", memory_ref=memory_ref)


def create_memory_adapter_app(*, provider, service_token: str) -> FastAPI:
    if not _valid_token(service_token):
        raise ValueError("memory_adapter_service_token_invalid")
    app = FastAPI(
        title="VideoBox Hermes Memory Adapter",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "memory_adapter_request_invalid"},
        )

    def require_token(authorization: str | None) -> None:
        expected = f"Bearer {service_token}"
        if authorization is None or not hmac.compare_digest(
            authorization, expected
        ):
            raise HTTPException(
                status_code=401, detail="memory_adapter_auth_required"
            )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ready", "configured": provider is not None}

    @app.post(
        "/internal/memory/add", response_model=MemoryWriteOutcome
    )
    def add(
        body: AdapterMemoryWrite,
        authorization: str | None = Header(default=None),
    ) -> MemoryWriteOutcome:
        require_token(authorization)
        if provider is None:
            raise HTTPException(
                status_code=503, detail="memory_adapter_unavailable"
            )
        try:
            result = provider.add(
                messages=[{"role": "user", "content": body.text}],
                user_id=body.user_id,
                agent_id=body.agent_id,
                infer=False,
                metadata=body.metadata,
            )
        except Exception:
            return MemoryWriteOutcome(status="ambiguous")
        return _outcome_from_add(result)

    @app.post(
        "/internal/memory/reconcile", response_model=MemoryWriteOutcome
    )
    def reconcile(
        body: AdapterMemoryReconcile,
        authorization: str | None = Header(default=None),
    ) -> MemoryWriteOutcome:
        require_token(authorization)
        if provider is None:
            raise HTTPException(
                status_code=503, detail="memory_adapter_unavailable"
            )
        try:
            if body.event_ref is not None:
                result = provider.get_event(event_id=body.event_ref)
                event_outcome = _outcome_from_event(result, body)
                if event_outcome.status in {
                    "stored",
                    "event_pending",
                }:
                    return event_outcome
            result = provider.search(
                body.text,
                filters={
                    "AND": [
                        {"user_id": body.user_id},
                        {
                            "metadata": {
                                "external_ref": body.external_ref
                            }
                        },
                    ]
                },
                top_k=2,
                rerank=False,
            )
        except Exception:
            return MemoryWriteOutcome(
                status="ambiguous", event_ref=body.event_ref
            )
        return _outcome_from_search(result, body)

    @app.post(
        "/internal/memory/search", response_model=MemorySearchResult
    )
    def search(
        body: AdapterMemorySearch,
        authorization: str | None = Header(default=None),
    ) -> MemorySearchResult:
        require_token(authorization)
        if provider is None:
            raise HTTPException(
                status_code=503, detail="memory_adapter_unavailable"
            )
        try:
            result = provider.search(
                body.query,
                filters={
                    "AND": [
                        {"user_id": body.user_id},
                        {
                            "metadata": {
                                "source": (
                                    "videobox_yujin_approved_v1"
                                )
                            }
                        },
                    ]
                },
                top_k=body.limit,
                rerank=False,
            )
        except Exception as error:
            raise HTTPException(
                status_code=503, detail="memory_adapter_unavailable"
            ) from error
        rows = result.get("results") if type(result) is dict else result
        if type(rows) is not list or len(rows) > body.limit:
            raise HTTPException(
                status_code=502, detail="memory_adapter_response_invalid"
            )
        memories = []
        for row in rows:
            if type(row) is not dict or type(row.get("metadata")) is not dict:
                raise HTTPException(
                    status_code=502,
                    detail="memory_adapter_response_invalid",
                )
            metadata = row["metadata"]
            if (
                metadata.get("source")
                != "videobox_yujin_approved_v1"
                or set(metadata) != {"source", "category", "external_ref"}
            ):
                raise HTTPException(
                    status_code=502,
                    detail="memory_adapter_response_invalid",
                )
            try:
                memories.append(
                    RetrievedMemory(
                        memory_ref=row.get("id") or row.get("memory_id"),
                        text=row.get("memory"),
                        category=metadata.get("category"),
                        external_ref=metadata.get("external_ref"),
                    )
                )
            except Exception as error:
                raise HTTPException(
                    status_code=502,
                    detail="memory_adapter_response_invalid",
                ) from error
        return MemorySearchResult(memories=tuple(memories))

    @app.post(
        "/internal/memory/delete", response_model=MemoryDeleteResult
    )
    def delete(
        body: AdapterMemoryDelete,
        authorization: str | None = Header(default=None),
    ) -> MemoryDeleteResult:
        require_token(authorization)
        if provider is None:
            raise HTTPException(
                status_code=503, detail="memory_adapter_unavailable"
            )
        try:
            result = provider.search(
                body.external_ref,
                filters={
                    "AND": [
                        {"user_id": body.user_id},
                        {
                            "metadata": {
                                "external_ref": body.external_ref
                            }
                        },
                    ]
                },
                top_k=2,
                rerank=False,
            )
            rows = (
                result.get("results")
                if type(result) is dict
                else result
            )
            if type(rows) is not list:
                raise ValueError("memory_ownership_mismatch")
            if len(rows) == 0:
                if body.allow_absent:
                    return MemoryDeleteResult(deleted=True)
                raise ValueError("memory_ownership_mismatch")
            if len(rows) != 1:
                raise ValueError("memory_ownership_mismatch")
            row = rows[0]
            metadata = row.get("metadata") if type(row) is dict else None
            if (
                type(metadata) is not dict
                or set(metadata)
                != {"source", "category", "external_ref"}
                or metadata.get("source")
                != "videobox_yujin_approved_v1"
                or metadata.get("external_ref") != body.external_ref
                or (row.get("id") or row.get("memory_id"))
                != body.memory_ref
            ):
                raise ValueError("memory_ownership_mismatch")
            provider.delete(body.memory_ref)
        except ValueError as error:
            raise HTTPException(
                status_code=409, detail="memory_adapter_ownership_mismatch"
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=503, detail="memory_adapter_unavailable"
            ) from error
        return MemoryDeleteResult(deleted=True)

    return app


class _PinnedHermesMem0Provider:
    """Narrow wrapper over the exact pinned Hermes PlatformBackend."""

    def __init__(
        self, api_key: str, *, event_http_client_factory=None
    ) -> None:
        from plugins.memory.mem0._backend import PlatformBackend

        self._backend = PlatformBackend(api_key)
        self._api_key = api_key
        self._event_http_client_factory = (
            event_http_client_factory
            or self._default_event_http_client_factory
        )

    @staticmethod
    def _default_event_http_client_factory(**kwargs):
        import httpx

        return httpx.Client(**kwargs)

    def add(self, **kwargs):
        return self._backend.add(**kwargs)

    def search(self, query, **kwargs):
        return self._backend.search(query, **kwargs)

    def delete(self, memory_id: str):
        return self._backend.delete(memory_id)

    def get_event(self, *, event_id: str):
        if _bounded_ref(event_id) is None:
            raise RuntimeError("memory_event_ref_invalid")
        with self._event_http_client_factory(
            base_url="https://api.mem0.ai",
            headers={"Authorization": f"Token {self._api_key}"},
            timeout=5.0,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = client.get(f"/v1/event/{event_id}/")
            if (
                response.status_code != 200
                or bool(getattr(response, "is_redirect", False))
                or len(response.content) > 16_384
            ):
                raise RuntimeError("memory_event_response_invalid")
            payload = response.json()
        if type(payload) is not dict:
            raise RuntimeError("memory_event_response_invalid")
        return payload


def _default_provider_factory(api_key: str):
    os.environ["MEM0_TELEMETRY"] = "false"
    return _PinnedHermesMem0Provider(api_key)


class _LazyProvider:
    def __init__(self, factory) -> None:
        self._factory = factory
        self._provider = None
        self._lock = threading.Lock()

    def _get(self):
        if self._provider is None:
            with self._lock:
                if self._provider is None:
                    self._provider = self._factory()
        return self._provider

    def add(self, **kwargs):
        return self._get().add(**kwargs)

    def search(self, query, **kwargs):
        return self._get().search(query, **kwargs)

    def delete(self, memory_id):
        return self._get().delete(memory_id)

    def get_event(self, *, event_id):
        return self._get().get_event(event_id=event_id)


def build_memory_adapter_from_environment(
    *,
    environ=None,
    provider_factory=_default_provider_factory,
) -> FastAPI:
    values = os.environ if environ is None else environ
    token = values.get("VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN", "")
    api_key = values.get("MEM0_API_KEY", "")
    if not _valid_token(token):
        return create_memory_adapter_app(
            provider=None,
            service_token=secrets.token_urlsafe(32),
        )
    provider = (
        _LazyProvider(lambda: provider_factory(api_key))
        if api_key
        else None
    )
    return create_memory_adapter_app(
        provider=provider,
        service_token=token,
    )


app = build_memory_adapter_from_environment()


__all__ = [
    "build_memory_adapter_from_environment",
    "create_memory_adapter_app",
]
