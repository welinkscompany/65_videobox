"""Safe lifecycle API for the owner-managed personal media library.

The pack API remains under ``/api/media-library``.  This router owns only
content-addressed user assets and never serializes an absolute filesystem
path.  A small derivative manifest is persisted for preview affordances; the
actual preview always streams a re-checked source file.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from videobox_api.models import MaterializeLibraryAssetRequest
from videobox_core_engine.library_ingest import LibraryIngestService
from videobox_core_engine.project_asset_materializer import ProjectAssetMaterializer
from videobox_domain_models.library_assets import LibraryAssetLifecycle, LibraryAssetOrigin, LibraryMediaType
from videobox_storage.library_user_asset_store import LibraryUserAssetStore
from videobox_storage.media_library_store import MediaLibraryStore


DERIVATIVE_VERSION = "v1"


def build_library_assets_router(
    *,
    project_store: object,
    media_library_store: MediaLibraryStore,
    user_asset_store: LibraryUserAssetStore,
    ingest_service: LibraryIngestService,
    managed_root: Path,
) -> APIRouter:
    router = APIRouter()
    materializer = ProjectAssetMaterializer(project_store)

    def user_asset(asset_id: str):
        return user_asset_store.get_asset(asset_id)

    def builtin_asset(asset_id: str) -> dict[str, Any] | None:
        try:
            for item in media_library_store.inspect_active_assets():
                if str(item.get("library_asset_id")) == asset_id:
                    return item
        except Exception:
            return None
        return None

    def public_user(asset: Any) -> dict[str, Any]:
        # ``to_dict`` contains a managed relative path by design.  Never add
        # the resolved root or arbitrary provenance to this response.
        value = asset.to_dict()
        value.pop("provenance", None)
        value["origin"] = LibraryAssetOrigin.USER.value
        value["preview_url"] = f"/api/library/assets/{asset.library_asset_id}/preview"
        value["thumbnail_url"] = f"/api/library/assets/{asset.library_asset_id}/thumbnail"
        value["waveform_url"] = f"/api/library/assets/{asset.library_asset_id}/waveform"
        return value

    def public_builtin(item: dict[str, Any]) -> dict[str, Any]:
        asset_id = str(item["library_asset_id"])
        return {
            "library_asset_id": asset_id,
            "asset_id": item.get("asset_id"),
            "media_type": item.get("media_type"),
            "origin": LibraryAssetOrigin.BUILTIN.value,
            "lifecycle": "ready" if item.get("available") else "needs_attention",
            "content_sha256": item.get("sha256"),
            "byte_count": None,
            "mime_type": _mime_type(Path(str(item.get("path") or ""))),
            "duration_seconds": item.get("duration_seconds"),
            "tags": item.get("tags", []),
            "verified": bool(item.get("verified")),
            "available": bool(item.get("available")),
            "preview_url": f"/api/library/assets/{asset_id}/preview",
            "thumbnail_url": f"/api/library/assets/{asset_id}/thumbnail",
            "waveform_url": f"/api/library/assets/{asset_id}/waveform",
        }

    def find_asset(asset_id: str):
        asset = user_asset(asset_id)
        if asset is not None:
            return asset, None
        builtin = builtin_asset(asset_id)
        if builtin is not None:
            return None, builtin
        raise HTTPException(status_code=404, detail="asset_missing")

    def source_for_user(asset: Any) -> Path:
        root = managed_root.resolve()
        source = (root / asset.managed_relative_path).resolve()
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="asset_path_invalid") from exc
        if not source.is_file():
            raise HTTPException(status_code=404, detail="asset_unavailable")
        digest = _sha256(source)
        if digest != asset.content_sha256:
            raise HTTPException(status_code=422, detail="asset_checksum_mismatch")
        return source

    @router.post("/api/library/ingest", status_code=status.HTTP_201_CREATED)
    def ingest_library_assets(
        files: list[UploadFile] = File(...),
        media_type: str = Form(...),
        idempotency_key: str | None = Form(None),
        provenance: str | None = Form(None),
    ) -> dict[str, Any]:
        try:
            resolved_type = LibraryMediaType(media_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="media_type_invalid") from exc
        key = (idempotency_key or "batch").strip() or "batch"
        try:
            provenance_value = json.loads(provenance) if provenance else {}
            if not isinstance(provenance_value, dict):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail="provenance_invalid") from exc
        items: list[dict[str, Any]] = []
        for index, upload in enumerate(files):
            item_key = key if len(files) == 1 else f"{key}:{index}"
            try:
                result = ingest_service.ingest(
                    media_type=resolved_type,
                    source=upload.file,
                    filename=upload.filename or "asset",
                    idempotency_key=item_key,
                    batch_idempotency_key=key,
                    provenance=provenance_value,
                )
                items.append(result)
            except Exception as exc:  # one bad file does not hide a good drop
                items.append({
                    "filename": upload.filename,
                    "idempotency_key": item_key,
                    "state": "needs_attention",
                    "error_code": type(exc).__name__,
                })
        if not items:
            raise HTTPException(status_code=422, detail="files_required")
        return {
            "ingest_batch_id": ingest_service.store.create_ingest_batch(idempotency_key=key)["ingest_batch_id"],
            "items": items,
            "partial": any(item.get("state") == "needs_attention" for item in items) and any(item.get("state") == "ready" for item in items),
        }

    @router.get("/api/library/assets")
    def list_library_assets(
        media_type: str | None = Query(None),
        q: str | None = Query(None),
        include_trashed: bool = Query(False),
        limit: int = Query(100, ge=1, le=500),
    ) -> dict[str, Any]:
        try:
            users = user_asset_store.list_assets(media_type=media_type, include_trashed=include_trashed)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="media_type_invalid") from exc
        needle = (q or "").strip().lower()
        values = [public_user(asset) for asset in users]
        if not needle:
            values.extend(public_builtin(item) for item in media_library_store.inspect_active_assets())
        else:
            values.extend(public_builtin(item) for item in media_library_store.inspect_active_assets() if needle in json.dumps(item.get("tags", []), ensure_ascii=False).lower())
        return {"assets": values[:limit], "total": len(values)}

    # Asset identities are opaque IDs (``user_<uuid>`` or ``pack:<...>``),
    # never filesystem paths.  Keeping this route non-greedy lets the more
    # specific ``/preview``/lifecycle routes below win reliably.
    @router.get("/api/library/assets/{asset_id}")
    def get_library_asset(asset_id: str) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        return {"asset": public_user(asset) if asset is not None else public_builtin(builtin)}

    @router.get("/api/library/search")
    def search_library_assets(
        request: Request,
        q: str = Query(..., min_length=1),
        media_type: str = Query(...),
        limit: int = Query(20, ge=1, le=100),
    ) -> dict[str, Any]:
        try:
            kind = LibraryMediaType(media_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="media_type_invalid") from exc
        needle = q.strip().lower()
        matches: list[dict[str, Any]] = []
        for asset in user_asset_store.list_assets(media_type=kind):
            haystack = " ".join([asset.user_metadata.get("filename", ""), json.dumps(asset.machine_metadata, ensure_ascii=False), json.dumps(asset.user_metadata, ensure_ascii=False)]).lower()
            if needle in haystack:
                result = public_user(asset)
                result["score"] = 1.0 if needle in str(asset.user_metadata.get("filename", "")).lower() else 0.5
                result["reason"] = "파일명 또는 분석 메타데이터 일치"
                matches.append(result)
        matches.sort(key=lambda value: (-float(value.get("score", 0)), value["library_asset_id"]))
        return {"matches": matches[:limit], "semantic": bool(getattr(request.app.state, "media_analysis_embedding_provider", None))}

    @router.get("/api/library/assets/{asset_id}/usage")
    def get_library_asset_usage(asset_id: str) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            return {"library_asset_id": asset_id, "locations": []}
        return {"library_asset_id": asset_id, "locations": user_asset_store.usage(asset_id)}

    @router.post("/api/library/assets/{asset_id}/trash")
    def trash_library_asset(asset_id: str) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=409, detail={"code": "builtin_asset_immutable", "library_asset_id": asset_id})
        try:
            return {"asset": public_user(user_asset_store.trash_asset(asset_id))}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "asset_referenced", "locations": user_asset_store.usage(asset_id)}) from exc

    @router.post("/api/library/assets/{asset_id}/restore")
    def restore_library_asset(asset_id: str) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=409, detail={"code": "builtin_asset_immutable"})
        try:
            return {"asset": public_user(user_asset_store.restore_asset(asset_id))}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.delete("/api/library/assets/{asset_id}/permanent", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    def permanently_delete_library_asset(asset_id: str) -> None:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=409, detail={"code": "builtin_asset_immutable"})
        try:
            user_asset_store.permanently_delete_asset(asset_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "asset_referenced", "locations": user_asset_store.usage(asset_id)}) from exc
        # The row is gone only after the guard/transaction succeeds.  Cleanup
        # is then best-effort and limited to the managed root; a stale file is
        # harmless to the authority, while a path outside this root is never
        # touched.
        if asset is not None:
            _remove_managed_file(managed_root, asset.managed_relative_path)

    @router.delete("/api/library/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    def permanently_delete_library_asset_alias(asset_id: str, permanent: bool = Query(False)) -> None:
        if not permanent:
            raise HTTPException(status_code=405, detail="permanent_query_required")
        permanently_delete_library_asset(asset_id)

    @router.get("/api/library/assets/{asset_id}/preview")
    def preview_library_asset(asset_id: str):
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            snapshot = media_library_store.snapshot_verified_asset(library_asset_id=asset_id)
            if snapshot is None:
                raise HTTPException(status_code=404, detail="asset_unavailable")
            _, path = snapshot
            return FileResponse(path, media_type=_mime_type(path), background=BackgroundTask(media_library_store.remove_verified_snapshot, path))
        source = source_for_user(asset)
        return FileResponse(source, media_type=asset.mime_type)

    @router.get("/api/library/assets/{asset_id}/{derivative_kind}")
    def get_derivative(asset_id: str, derivative_kind: str):
        if derivative_kind not in {"thumbnail", "waveform"}:
            raise HTTPException(status_code=404, detail="derivative_missing")
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            return {"library_asset_id": asset_id, "kind": derivative_kind, "source_hash": builtin.get("sha256"), "version": DERIVATIVE_VERSION}
        source = source_for_user(asset)
        derivative = _ensure_derivative(user_asset_store, managed_root, asset, derivative_kind, source)
        return {"library_asset_id": asset_id, "kind": derivative_kind, "version": DERIVATIVE_VERSION, "source_hash": asset.content_sha256, "derivative": derivative}

    @router.post("/api/library/assets/{asset_id}/materialize", status_code=status.HTTP_201_CREATED)
    def materialize_library_asset(asset_id: str, payload: MaterializeLibraryAssetRequest) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=422, detail="builtin_materialize_use_media_library_api")
        source = source_for_user(asset)
        try:
            result = materializer.materialize_user_library_asset(
                project_id=payload.project_id,
                library_asset_id=asset_id,
                library_asset=public_user(asset),
                source_path=source,
                mime_type=asset.mime_type,
            )
            reference = user_asset_store.add_project_reference(project_id=payload.project_id, library_asset_id=asset_id, materialized_asset_id=str(result.get("asset_id")), location={"project_id": payload.project_id})
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="project_missing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"asset": result, "reference": reference}

    @router.delete("/api/library/assets/{asset_id}/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    def remove_library_reference(asset_id: str, reference_id: str) -> None:
        find_asset(asset_id)
        user_asset_store.remove_project_reference(reference_id)

    return router


def _ensure_derivative(store: LibraryUserAssetStore, root: Path, asset: Any, kind: str, source: Path) -> dict[str, Any]:
    relative = Path("derivatives") / asset.content_sha256 / f"{DERIVATIVE_VERSION}-{kind}.json"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        payload = {"source_sha256": asset.content_sha256, "version": DERIVATIVE_VERSION, "kind": kind, "mime_type": asset.mime_type, "source_name": asset.user_metadata.get("filename", source.name)}
        target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    digest = _sha256(target)
    return store.upsert_derivative(library_asset_id=asset.library_asset_id, kind=kind, managed_relative_path=relative.as_posix(), content_sha256=digest, byte_count=target.stat().st_size, mime_type="application/json", metadata={"source_sha256": asset.content_sha256, "version": DERIVATIVE_VERSION})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _remove_managed_file(root: Path, relative: str) -> None:
    base = root.resolve()
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return
    candidate.unlink(missing_ok=True)


__all__ = ["build_library_assets_router"]
