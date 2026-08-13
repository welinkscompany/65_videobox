from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from videobox_api.models import (
    OutputVariantCreateRequest,
    OutputVariantMaterializeRequest,
    OutputVariantPatchRequest,
    OutputVariantRebaseRequest,
)
from videobox_core_engine.output_variants import (
    VariantInvariantError,
    apply_variant_patch,
    materialize_variant,
    rebase_variant,
)
from videobox_domain_models.output_variants import OutputVariant
from videobox_storage.local_project_store import (
    EditingSessionRevisionConflict,
    LocalProjectStore,
)


def _domain_variant(row: dict[str, Any]) -> OutputVariant:
    return OutputVariant.model_validate(
        {
            key: value
            for key, value in row.items()
            if key not in {"project_id", "created_at", "updated_at"}
        }
    )


def _raise_variant_error(error: Exception) -> None:
    if isinstance(error, KeyError):
        raise HTTPException(status_code=404, detail="output_variant_missing") from error
    if isinstance(error, EditingSessionRevisionConflict):
        raise HTTPException(status_code=409, detail="output_variant_revision_conflict") from error
    if isinstance(error, (VariantInvariantError, ValueError)):
        detail = str(error)
        if "stale_variant_revision" in detail:
            detail = "stale_variant_revision"
            raise HTTPException(status_code=409, detail=detail) from error
        if "stale_master_revision" in detail:
            detail = "stale_master_revision"
            raise HTTPException(status_code=409, detail=detail) from error
        raise HTTPException(status_code=422, detail=detail) from error
    raise error


def build_output_variants_router(store: LocalProjectStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/output-variants")
    def list_variants(
        project_id: str,
        session_id: str | None = Query(default=None, min_length=1),
    ) -> dict[str, object]:
        try:
            return {"variants": store.ensure_output_variants(project_id=project_id, session_id=session_id)}
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

    @router.post(
        "/api/projects/{project_id}/output-variants",
        status_code=status.HTTP_201_CREATED,
    )
    def create_variant(project_id: str, request: OutputVariantCreateRequest) -> dict[str, object]:
        try:
            return {
                "variant": store.create_output_variant(
                    project_id=project_id,
                    source_session_id=request.source_session_id,
                    kind=request.kind,
                    variant_id=request.variant_id,
                )
            }
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

    @router.patch("/api/projects/{project_id}/output-variants/{variant_id}")
    def patch_variant(
        project_id: str, variant_id: str, request: OutputVariantPatchRequest
    ) -> dict[str, object]:
        try:
            current = store.get_output_variant(project_id=project_id, variant_id=variant_id)
            updated = apply_variant_patch(
                _domain_variant(current),
                request.patch,
                expected_variant_revision=request.expected_variant_revision,
            )
            return {
                "variant": store.update_output_variant(
                    project_id=project_id,
                    variant_id=variant_id,
                    expected_variant_revision=request.expected_variant_revision,
                    variant=updated,
                )
            }
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

    @router.post("/api/projects/{project_id}/output-variants/{variant_id}/rebase")
    def rebase_variant_route(
        project_id: str, variant_id: str, request: OutputVariantRebaseRequest
    ) -> dict[str, object]:
        try:
            current = store.get_output_variant(project_id=project_id, variant_id=variant_id)
            rebased = rebase_variant(
                _domain_variant(current),
                new_master_revision=request.new_master_revision,
                changed_fields=tuple(request.changed_fields),
            )
            return {
                "variant": store.update_output_variant(
                    project_id=project_id,
                    variant_id=variant_id,
                    expected_variant_revision=int(current["variant_revision"]),
                    variant=rebased,
                )
            }
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

    @router.post(
        "/api/projects/{project_id}/output-variants/{variant_id}/materialize",
        status_code=status.HTTP_201_CREATED,
    )
    def materialize_variant_route(
        project_id: str,
        variant_id: str,
        request: OutputVariantMaterializeRequest,
    ) -> dict[str, object]:
        try:
            current = store.get_output_variant(project_id=project_id, variant_id=variant_id)
            variant = _domain_variant(current)
            session = store.get_editing_session(
                project_id=project_id, session_id=variant.source_session_id
            )
            current_master_revision = int(session.get("session_revision") or 0)
            if request.expected_master_session_revision is not None and (
                current_master_revision != request.expected_master_session_revision
            ):
                raise VariantInvariantError("stale_master_revision")
            if current_master_revision != variant.source_session_revision:
                raise VariantInvariantError("stale_master_revision")
            derived = materialize_variant(
                variant,
                session.get("segments", []),
                master_session_revision=current_master_revision,
            )
            try:
                existing = store.get_variant_materialization(
                    project_id=project_id,
                    variant_id=variant_id,
                    source_variant_revision=derived.source_variant_revision,
                )
            except KeyError:
                existing = None
            if existing is not None:
                return {"materialization": {
                    **existing,
                    "source_variant_id": derived.source_variant_id,
                    "source_variant_revision": derived.source_variant_revision,
                }}
            try:
                master_timeline = store.get_timeline_run(
                    project_id=project_id,
                    timeline_id=str(session.get("timeline_id") or ""),
                )
            except KeyError:
                master_timeline = {}
            timeline_payload = {
                key: value
                for key, value in master_timeline.items()
                if key not in {"timeline_id", "project_id", "file_uri", "created_at", "summary"}
            }
            timeline_payload.update({
                "source_variant_id": derived.source_variant_id,
                "source_variant_revision": derived.source_variant_revision,
                "segments": list(derived.segments),
                "tracks": list(master_timeline.get("tracks", [])),
                "review_flags": list(master_timeline.get("review_flags", [])),
                "pending_recommendations": list(master_timeline.get("pending_recommendations", [])),
                "applied_recommendations": list(master_timeline.get("applied_recommendations", [])),
            })
            timeline = store.save_timeline_run(
                project_id=project_id,
                output_mode=variant.kind,
                source_session_id=derived.source_session_id,
                source_session_revision=derived.source_session_revision,
                timeline_payload=timeline_payload,
            )
            materialization = store.save_variant_materialization(
                project_id=project_id,
                variant_id=variant_id,
                source_session_id=derived.source_session_id,
                source_session_revision=derived.source_session_revision,
                source_variant_revision=derived.source_variant_revision,
                timeline_id=timeline["timeline_id"],
                segments=derived.segments,
            )
            return {"materialization": {**materialization, **{
                "timeline_id": timeline["timeline_id"],
                "source_session_id": derived.source_session_id,
                "source_session_revision": derived.source_session_revision,
                "source_variant_id": derived.source_variant_id,
                "source_variant_revision": derived.source_variant_revision,
            }}}
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

    return router
