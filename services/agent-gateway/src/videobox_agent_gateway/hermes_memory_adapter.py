"""Isolated Mem0 adapter that never starts the Hermes agent loop."""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import threading
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from videobox_agent_gateway.fault_reporting import FaultReporter
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


# uvicorn 이 설정한 로거를 쓴다. 모듈 로거는 컨테이너 로그에 나오지 않는다.
_LOGGER = logging.getLogger("uvicorn.error")


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
    # 위층이 유보를 나중에 다시 맞춰 보기 때문에 같은 고장이 반복해서
    # 들어온다. 사유가 달라질 때만 남긴다.
    _add_faults = FaultReporter(_LOGGER)
    _reconcile_faults = FaultReporter(_LOGGER)

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
        except Exception as exc:  # noqa: BLE001 - 저장 판정은 유보로 떨어진다
            # 유보로 떨어지면 위층은 나중에 다시 맞춰 보려 한다. 그 사이
            # 원인이 무엇이었는지는 여기 말고 어디에도 없다.
            _add_faults.report_once(
                exc, "기억을 저장하지 못해 유보로 처리합니다."
            )
            return MemoryWriteOutcome(status="ambiguous")
        _add_faults.clear()
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
        except Exception as exc:  # noqa: BLE001 - 맞춰 보기는 유보로 떨어진다
            # 맞춰 보기가 실패하면 저장이 됐는지 영영 확정되지 않는다.
            _reconcile_faults.report_once(
                exc, "기억을 맞춰 보지 못해 유보로 처리합니다."
            )
            return MemoryWriteOutcome(
                status="ambiguous", event_ref=body.event_ref
            )
        _reconcile_faults.clear()
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


# 이 컴퓨터에서만 도는 기억 저장소의 기본값. 전부 로컬을 가리킨다.
_LOCAL_MEM0_BASE_URL = "http://host.docker.internal:1234/v1"
_LOCAL_MEM0_LLM_MODEL = "qwen/qwen3.6-35b-a3b"
_LOCAL_MEM0_EMBEDDER_MODEL = "text-embedding-bge-m3"
_LOCAL_MEM0_EMBEDDING_DIMS = 1024
_LOCAL_MEM0_STORE_PATH = "/var/lib/videobox-mem0/qdrant"


def local_mem0_config_from_environment(values) -> dict:
    """이 컴퓨터 안에서만 도는 Mem0 설정을 만든다.

    기억 생성과 검색을 로컬 모델이 처리하고, 벡터 저장소는 파일 경로 방식이라
    서버가 따로 필요 없다. 열쇠 값은 LM Studio 가 확인하지 않으므로 비밀이
    아니라 자리를 채우는 값이다.
    """

    base_url = (
        values.get("VIDEOBOX_MEM0_LOCAL_BASE_URL") or _LOCAL_MEM0_BASE_URL
    )
    api_key = values.get("VIDEOBOX_MEM0_LOCAL_API_KEY") or "lm-studio"
    dims_text = values.get("VIDEOBOX_MEM0_EMBEDDING_DIMS") or ""
    try:
        dims = int(dims_text)
    except ValueError:
        dims = _LOCAL_MEM0_EMBEDDING_DIMS
    return {
        "llm": {
            "provider": "openai",
            "config": {
                "model": (
                    values.get("VIDEOBOX_MEM0_LLM_MODEL")
                    or _LOCAL_MEM0_LLM_MODEL
                ),
                "openai_base_url": base_url,
                "api_key": api_key,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": (
                    values.get("VIDEOBOX_MEM0_EMBEDDER_MODEL")
                    or _LOCAL_MEM0_EMBEDDER_MODEL
                ),
                "openai_base_url": base_url,
                "api_key": api_key,
                "embedding_dims": dims,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "path": (
                    values.get("VIDEOBOX_MEM0_STORE_PATH")
                    or _LOCAL_MEM0_STORE_PATH
                ),
            },
        },
    }


class _LocalMem0Provider:
    """Hermes 의 OSS 백엔드를 어댑터가 기대하는 모양으로 감싼다."""

    def __init__(self, oss_config: dict) -> None:
        from plugins.memory.mem0._backend import OSSBackend

        self._backend = OSSBackend(oss_config)

    def add(self, **kwargs):
        return self._backend.add(**kwargs)

    _OWNER_KEYS = ("user_id", "agent_id", "run_id")

    @classmethod
    def _split_filters(cls, filters) -> tuple[dict, dict]:
        """호스팅 문법의 필터를 소유자 조건과 metadata 조건으로 가른다.

        자체 호스팅 Mem0 는 {"AND": [...]} 를 모르고, 소유자 키 중 최소 하나를
        평평한 형태로 요구한다. metadata 조건은 받아 주지 않으므로 따로 떼어
        두었다가 결과에 직접 적용한다.
        """

        owner: dict = {}
        metadata: dict = {}

        def absorb(block) -> None:
            if type(block) is not dict:
                return
            for key, value in block.items():
                if key in cls._OWNER_KEYS:
                    owner[key] = value
                elif key == "metadata" and type(value) is dict:
                    metadata.update(value)
                elif key in {"AND", "OR"} and type(value) is list:
                    for item in value:
                        absorb(item)

        absorb(filters)
        return owner, metadata

    def search(self, query, *, filters, top_k=10, rerank=False):
        owner, metadata = self._split_filters(filters)
        rows = self._backend.search(
            query, filters=owner, top_k=top_k, rerank=rerank
        )
        if not metadata:
            return rows
        # 저장소는 소유자 단위로만 걸러 준다. 승인 표시와 external_ref 는
        # 여기서 다시 확인하지 않으면 엉뚱한 기억이 섞여 나온다.
        kept = []
        for row in rows:
            found = row.get("metadata") if type(row) is dict else None
            if type(found) is not dict:
                continue
            if all(found.get(key) == value for key, value in metadata.items()):
                kept.append(row)
        return kept

    def delete(self, memory_id: str):
        return self._backend.delete(memory_id)

    def get_event(self, *, event_id: str):
        # 호스팅 Mem0 의 비동기 이벤트 조회 API 다. 자체 호스팅에는 없고,
        # 저장이 즉시 끝나므로 필요하지도 않다.
        raise RuntimeError("memory_event_unsupported_in_local_mode")


def _default_local_provider_factory(oss_config: dict):
    os.environ["MEM0_TELEMETRY"] = "false"
    return _LocalMem0Provider(oss_config)


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
    local_provider_factory=_default_local_provider_factory,
) -> FastAPI:
    values = os.environ if environ is None else environ
    token = values.get("VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN", "")
    api_key = values.get("MEM0_API_KEY", "")
    if not _valid_token(token):
        return create_memory_adapter_app(
            provider=None,
            service_token=secrets.token_urlsafe(32),
        )
    if api_key:
        # 호스팅 열쇠가 들어 있으면 기존 설정을 그대로 존중한다.
        provider = _LazyProvider(lambda: provider_factory(api_key))
    elif (values.get("VIDEOBOX_MEM0_MODE") or "").strip().lower() == "local":
        oss_config = local_mem0_config_from_environment(values)
        provider = _LazyProvider(
            lambda: local_provider_factory(oss_config)
        )
    else:
        provider = None
    return create_memory_adapter_app(
        provider=provider,
        service_token=token,
    )


app = build_memory_adapter_from_environment()


__all__ = [
    "build_memory_adapter_from_environment",
    "create_memory_adapter_app",
]
