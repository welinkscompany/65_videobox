"""Strict internal transport for explicitly approved Yujin memories."""

from __future__ import annotations

import asyncio
import math
from typing import Callable, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


MemoryCategory = Literal["pacing", "caption", "audio", "tone", "workflow"]
MemoryWriteStatus = Literal[
    "stored", "event_pending", "failed_retryable", "ambiguous"
]


class ApprovedMemoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    text: str = Field(min_length=1, max_length=280)
    category: MemoryCategory
    external_ref: str = Field(pattern=r"^ext-[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^op-[0-9a-f]{64}$")


class AdapterMemoryWrite(ApprovedMemoryWrite):
    user_id: Literal["videobox-owner-v1"] = "videobox-owner-v1"
    agent_id: Literal["videobox-yujin-v1"] = "videobox-yujin-v1"
    infer: Literal[False] = False
    metadata: dict[str, str]

    @model_validator(mode="after")
    def metadata_is_exact(self) -> "AdapterMemoryWrite":
        if self.metadata != {
            "source": "videobox_yujin_approved_v1",
            "category": self.category,
            "external_ref": self.external_ref,
        }:
            raise ValueError("memory_metadata_invalid")
        return self


class MemoryReconcile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    text: str = Field(min_length=1, max_length=280)
    category: MemoryCategory
    external_ref: str = Field(pattern=r"^ext-[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^op-[0-9a-f]{64}$")
    event_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )


class AdapterMemoryReconcile(MemoryReconcile):
    user_id: Literal["videobox-owner-v1"] = "videobox-owner-v1"
    agent_id: Literal["videobox-yujin-v1"] = "videobox-yujin-v1"


class MemorySearch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    query: str = Field(min_length=1, max_length=280)
    limit: int = Field(ge=1, le=5, strict=True)


class AdapterMemorySearch(MemorySearch):
    user_id: Literal["videobox-owner-v1"] = "videobox-owner-v1"
    agent_id: Literal["videobox-yujin-v1"] = "videobox-yujin-v1"


class RetrievedMemory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    memory_ref: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=280)
    category: MemoryCategory
    external_ref: str = Field(pattern=r"^ext-[0-9a-f]{64}$")


class MemorySearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    memories: tuple[RetrievedMemory, ...] = Field(max_length=5)


class MemoryDelete(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    memory_ref: str = Field(min_length=1, max_length=256)
    external_ref: str = Field(pattern=r"^ext-[0-9a-f]{64}$")
    allow_absent: bool


class AdapterMemoryDelete(MemoryDelete):
    user_id: Literal["videobox-owner-v1"] = "videobox-owner-v1"
    agent_id: Literal["videobox-yujin-v1"] = "videobox-yujin-v1"


class MemoryDeleteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    deleted: Literal[True]


class MemoryWriteOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: MemoryWriteStatus
    memory_ref: str | None = Field(default=None, min_length=1, max_length=256)
    event_ref: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def reference_matches_status(self) -> "MemoryWriteOutcome":
        if (
            self.status == "stored"
            and (self.memory_ref is None or self.event_ref is not None)
        ) or (
            self.status == "event_pending"
            and (self.event_ref is None or self.memory_ref is not None)
        ) or (
            self.status in {"failed_retryable", "ambiguous"}
            and self.memory_ref is not None
        ):
            raise ValueError("memory_write_outcome_invalid")
        return self


class HermesMemoryGateway(Protocol):
    async def add_approved(
        self, request: AdapterMemoryWrite
    ) -> MemoryWriteOutcome: ...

    async def reconcile(
        self, request: AdapterMemoryReconcile
    ) -> MemoryWriteOutcome: ...

    async def search(
        self, request: AdapterMemorySearch
    ) -> MemorySearchResult: ...

    async def delete(
        self, request: AdapterMemoryDelete
    ) -> MemoryDeleteResult: ...


def adapter_write(request: ApprovedMemoryWrite) -> AdapterMemoryWrite:
    return AdapterMemoryWrite(
        **request.model_dump(),
        metadata={
            "source": "videobox_yujin_approved_v1",
            "category": request.category,
            "external_ref": request.external_ref,
        },
    )


def adapter_reconcile(request: MemoryReconcile) -> AdapterMemoryReconcile:
    return AdapterMemoryReconcile(**request.model_dump())


def adapter_search(request: MemorySearch) -> AdapterMemorySearch:
    return AdapterMemorySearch(**request.model_dump())


def adapter_delete(request: MemoryDelete) -> AdapterMemoryDelete:
    return AdapterMemoryDelete(**request.model_dump())


def _default_http_client_factory(*, base_url: str, timeout: float):
    import httpx

    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
    )


class HermesMemoryAdapterClient:
    """Gateway-owned client; it can reach only the isolated adapter."""

    def __init__(
        self,
        *,
        base_url: str,
        service_token: str,
        http_client_factory: Callable = _default_http_client_factory,
        timeout_seconds: float = 8.0,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "videobox-hermes-memory-adapter"
            or parsed.port != 8082
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("memory_adapter_url_must_be_internal")
        lowered_token = service_token.strip().lower()
        if (
            len(service_token.encode("utf-8")) < 32
            or service_token != service_token.strip()
            or len(set(service_token)) < 8
            or "changeme" in lowered_token
            or "replace_me" in lowered_token
            or "placeholder" in lowered_token
        ):
            raise ValueError("memory_adapter_service_token_invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or not 0 < float(timeout_seconds) <= 10
        ):
            raise ValueError("memory_adapter_timeout_invalid")
        self._base_url = base_url.rstrip("/")
        self._token = service_token
        self._factory = http_client_factory
        self._timeout = timeout_seconds

    async def _post(self, path: str, payload: dict) -> MemoryWriteOutcome:
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                response = await client.post(
                    path,
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=payload,
                )
                if bool(getattr(response, "is_redirect", False)):
                    return MemoryWriteOutcome(status="ambiguous")
                if response.status_code == 503:
                    return MemoryWriteOutcome(status="failed_retryable")
                response.raise_for_status()
                content = getattr(response, "content", b"")
                if isinstance(content, (bytes, bytearray)) and len(content) > 16_384:
                    return MemoryWriteOutcome(status="ambiguous")
                return MemoryWriteOutcome.model_validate(response.json())
        except asyncio.CancelledError:
            raise
        except Exception:
            return MemoryWriteOutcome(status="ambiguous")

    async def add_approved(
        self, request: AdapterMemoryWrite
    ) -> MemoryWriteOutcome:
        return await self._post("/internal/memory/add", request.model_dump())

    async def reconcile(
        self, request: AdapterMemoryReconcile
    ) -> MemoryWriteOutcome:
        return await self._post(
            "/internal/memory/reconcile", request.model_dump()
        )

    async def search(
        self, request: AdapterMemorySearch
    ) -> MemorySearchResult:
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                response = await client.post(
                    "/internal/memory/search",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=request.model_dump(),
                )
                if bool(getattr(response, "is_redirect", False)):
                    raise ValueError("memory_adapter_response_invalid")
                response.raise_for_status()
                content = getattr(response, "content", b"")
                if isinstance(content, (bytes, bytearray)) and len(content) > 16_384:
                    raise ValueError("memory_adapter_response_invalid")
                # Decode the wire bytes, not `.json()`.  The model is strict and
                # `memories` is a tuple, and strict Python-mode validation
                # rejects the list every JSON decoder produces.
                return MemorySearchResult.model_validate_json(content)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise RuntimeError("memory_adapter_unavailable") from error

    async def delete(
        self, request: AdapterMemoryDelete
    ) -> MemoryDeleteResult:
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                response = await client.post(
                    "/internal/memory/delete",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=request.model_dump(),
                )
                if bool(getattr(response, "is_redirect", False)):
                    raise ValueError("memory_adapter_response_invalid")
                response.raise_for_status()
                content = getattr(response, "content", b"")
                if isinstance(content, (bytes, bytearray)) and len(content) > 16_384:
                    raise ValueError("memory_adapter_response_invalid")
                return MemoryDeleteResult.model_validate(response.json())
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise RuntimeError("memory_adapter_unavailable") from error


__all__ = [
    "AdapterMemoryReconcile",
    "AdapterMemoryDelete",
    "AdapterMemorySearch",
    "AdapterMemoryWrite",
    "ApprovedMemoryWrite",
    "HermesMemoryAdapterClient",
    "HermesMemoryGateway",
    "MemoryReconcile",
    "MemoryDelete",
    "MemoryDeleteResult",
    "MemorySearch",
    "MemorySearchResult",
    "RetrievedMemory",
    "MemoryWriteOutcome",
    "adapter_reconcile",
    "adapter_delete",
    "adapter_search",
    "adapter_write",
]
