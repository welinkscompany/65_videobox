"""Explicit-store coordinator for approved Yujin memory candidates."""

from __future__ import annotations

import hashlib
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MemoryStoreUnavailable(RuntimeError):
    pass


class ApprovedMemoryStoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    text: str = Field(min_length=1, max_length=280)
    category: Literal["pacing", "caption", "audio", "tone", "workflow"]
    external_ref: str = Field(pattern=r"^ext-[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^op-[0-9a-f]{64}$")


class MemoryReconcileRequest(ApprovedMemoryStoreRequest):
    event_ref: str | None = Field(default=None, min_length=1, max_length=256)


class GatewayMemoryWriteOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[
        "stored", "event_pending", "failed_retryable", "ambiguous"
    ]
    memory_ref: str | None = None
    event_ref: str | None = None


class GatewayMemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    query: str = Field(min_length=1, max_length=280)
    limit: int = Field(ge=1, le=5, strict=True)


class GatewayRetrievedMemory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    memory_ref: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=280)
    category: Literal["pacing", "caption", "audio", "tone", "workflow"]
    external_ref: str = Field(pattern=r"^ext-[0-9a-f]{64}$")


class GatewayMemorySearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    memories: tuple[GatewayRetrievedMemory, ...] = Field(max_length=5)


class GatewayMemoryDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    memory_ref: str = Field(min_length=1, max_length=256)
    external_ref: str = Field(pattern=r"^ext-[0-9a-f]{64}$")
    allow_absent: bool


class GatewayMemoryDeleteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    deleted: Literal[True]


class YujinMemoryService:
    def __init__(self, *, store, gateway) -> None:
        self._store = store
        self._gateway = gateway

    def _public(self, *, project_id: str, candidate_id: str) -> dict:
        return self._store.get_yujin_memory_store_state(
            project_id=project_id,
            candidate_id=candidate_id,
        )

    async def store_candidate(
        self,
        *,
        project_id: str,
        candidate_id: str,
        client_request_id: str,
    ) -> dict:
        current = self._public(
            project_id=project_id, candidate_id=candidate_id
        )
        if current["status"] != "approved":
            raise ValueError("memory_candidate_not_approved")
        if current["storage_status"] == "stored":
            return current
        if current["storage_status"] == "deleted":
            raise ValueError("memory_candidate_deleted")
        if self._gateway is None:
            raise MemoryStoreUnavailable("memory_store_unavailable")
        claim_token = "claim-" + hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        claim = self._store.claim_yujin_memory_store(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id=client_request_id,
            claim_token=claim_token,
        )
        if claim["action"] in {"stored", "replay"}:
            return self._public(
                project_id=project_id, candidate_id=candidate_id
            )
        if claim["action"] == "finalize":
            self._store.finalize_yujin_memory_store(
                project_id=project_id,
                candidate_id=candidate_id,
            )
            return self._public(
                project_id=project_id, candidate_id=candidate_id
            )

        request_data = {
            "text": claim["text"],
            "category": claim["category"],
            "external_ref": claim["external_ref"],
            "operation_id": claim["operation_id"],
        }
        parsed = None
        try:
            self._store.mark_yujin_memory_store_call_started(
                project_id=project_id,
                candidate_id=candidate_id,
                claim_token=claim_token,
            )
            if claim["action"] == "reconcile":
                outcome = await self._gateway.reconcile_memory(
                    MemoryReconcileRequest(
                        **request_data,
                        event_ref=claim["event_ref"],
                    )
                )
            else:
                outcome = await self._gateway.add_approved_memory(
                    ApprovedMemoryStoreRequest(**request_data)
                )
            parsed = GatewayMemoryWriteOutcome.model_validate(
                outcome.model_dump()
                if hasattr(outcome, "model_dump")
                else outcome
            )
            self._store.record_yujin_memory_provider_outcome(
                project_id=project_id,
                candidate_id=candidate_id,
                claim_token=claim_token,
                status=parsed.status,
                memory_ref=parsed.memory_ref,
                event_ref=parsed.event_ref,
            )
        except Exception as error:
            self._store.release_yujin_memory_store_claim(
                project_id=project_id,
                candidate_id=candidate_id,
                claim_token=claim_token,
                storage_status="ambiguous",
                event_ref=(
                    parsed.event_ref if parsed is not None else None
                ),
            )
            raise MemoryStoreUnavailable(
                "memory_store_unavailable"
            ) from error

        if parsed.status == "stored":
            self._store.finalize_yujin_memory_store(
                project_id=project_id,
                candidate_id=candidate_id,
            )
        return self._public(
            project_id=project_id, candidate_id=candidate_id
        )

    async def delete_candidate_memory(
        self, *, project_id: str, candidate_id: str
    ) -> dict:
        current = self._public(
            project_id=project_id, candidate_id=candidate_id
        )
        if current["storage_status"] == "deleted":
            return current
        mapping = self._store.get_yujin_memory_private_mapping(
            project_id=project_id,
            candidate_id=candidate_id,
        )
        if self._gateway is None:
            raise MemoryStoreUnavailable("memory_delete_unavailable")
        try:
            delete_state = (
                self._store.mark_yujin_memory_delete_call_started(
                    project_id=project_id,
                    candidate_id=candidate_id,
                )
            )
        except (KeyError, ValueError):
            raise
        except Exception as error:
            raise MemoryStoreUnavailable(
                "memory_delete_unavailable"
            ) from error
        try:
            result = await self._gateway.delete_memory(
                GatewayMemoryDeleteRequest(
                    memory_ref=delete_state["memory_ref"],
                    external_ref=delete_state["external_ref"],
                    allow_absent=delete_state["allow_absent"],
                )
            )
            GatewayMemoryDeleteResult.model_validate(
                result.model_dump()
                if hasattr(result, "model_dump")
                else result
            )
        except Exception as error:
            raise MemoryStoreUnavailable(
                "memory_delete_unavailable"
            ) from error
        try:
            return self._store.mark_yujin_memory_deleted(
                project_id=project_id,
                candidate_id=candidate_id,
            )
        except Exception as error:
            raise MemoryStoreUnavailable(
                "memory_delete_unavailable"
            ) from error


__all__ = [
    "ApprovedMemoryStoreRequest",
    "GatewayMemoryWriteOutcome",
    "GatewayMemoryDeleteRequest",
    "GatewayMemoryDeleteResult",
    "GatewayMemorySearchRequest",
    "GatewayMemorySearchResult",
    "GatewayRetrievedMemory",
    "MemoryReconcileRequest",
    "MemoryStoreUnavailable",
    "YujinMemoryService",
]
