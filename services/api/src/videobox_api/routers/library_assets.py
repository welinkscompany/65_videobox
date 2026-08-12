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
import subprocess
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from videobox_api.models import MaterializeLibraryAssetRequest
from videobox_core_engine.library_ingest import LibraryIngestIdempotencyConflict, LibraryIngestService
from videobox_core_engine.project_asset_materializer import ProjectAssetMaterializer
from videobox_domain_models.library_assets import LibraryAssetLifecycle, LibraryAssetOrigin, LibraryMediaType
from videobox_storage.library_user_asset_store import LibraryUserAssetStore
from videobox_storage.media_library_store import MediaLibraryStore
from videobox_provider_interfaces.embeddings import EmbeddingRequest


DERIVATIVE_VERSION = "v2"


class _DerivativeToolUnavailable(RuntimeError):
    pass


def build_library_assets_router(
    *,
    project_store: object,
    media_library_store: MediaLibraryStore,
    user_asset_store: LibraryUserAssetStore,
    ingest_service: LibraryIngestService,
    managed_root: Path,
    managed_roots: tuple[Path, ...] | None = None,
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

    roots = tuple(dict.fromkeys(Path(value).resolve() for value in (managed_roots or (managed_root,))))

    def source_for_user(asset: Any) -> Path:
        # Watcher imports may use a dedicated inbox/audio root while sharing
        # the same user-asset DB. Resolve only within configured roots and
        # require the content hash before serving bytes.
        invalid = False
        for root in roots:
            source = (root / asset.managed_relative_path).resolve()
            try:
                source.relative_to(root)
            except ValueError:
                invalid = True
                continue
            if source.is_file() and _sha256(source) == asset.content_sha256:
                return source
        if invalid:
            raise HTTPException(status_code=422, detail="asset_path_invalid")
        raise HTTPException(status_code=404, detail="asset_unavailable")

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
        # Missing keys must never collapse unrelated uploads into one durable
        # retry row. Explicit keys remain the caller's retry contract.
        key = (idempotency_key or "").strip() or f"upload_{uuid4().hex}"
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
            except LibraryIngestIdempotencyConflict as exc:
                raise HTTPException(status_code=409, detail="idempotency_key_conflict") from exc
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
        values = [public_user(asset) for asset in users if not needle or needle in json.dumps(asset.to_dict(), ensure_ascii=False).lower()]
        builtin_values = []
        for item in media_library_store.inspect_active_assets():
            item_type = str(item.get("media_type") or "")
            if media_type and item_type != media_type:
                continue
            public = public_builtin(item)
            if not needle or needle in json.dumps(public, ensure_ascii=False).lower():
                builtin_values.append(public)
        values.extend(builtin_values)
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
        orientation: str | None = Query(None),
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
        # Reuse the verified pack indexer's semantic contract whenever the
        # local embedding model is available.  User assets are merged here as
        # lexical fallbacks until Wave1 Task4 writes their descriptors.
        provider = getattr(request.app.state, "media_analysis_embedding_provider", None)
        model_name = (getattr(request.app.state, "media_analysis_profile", None) or {}).get("embedding_model_name")
        semantic = False
        if provider is not None and model_name:
            try:
                vector = [float(value) for value in provider.embed(EmbeddingRequest(model_name=model_name, inputs=(q.strip(),))).vectors[0]]
                if kind is LibraryMediaType.BROLL:
                    semantic_matches = media_library_store.find_footage_matches(query_embedding=vector, orientation=orientation, limit=limit)
                else:
                    semantic_matches = media_library_store.find_audio_matches(query_embedding=vector, media_type=kind.value, limit=limit)
                for value in semantic_matches:
                    value["reason"] = "의미 기반 색인 일치"
                matches.extend(semantic_matches)
                semantic = True
            except Exception:
                # Search remains useful with filename/metadata matches when
                # LM Studio is unavailable; never fabricate semantic scores.
                semantic = False
        matches.sort(key=lambda value: (-float(value.get("score", 0)), str(value.get("library_asset_id", value.get("content_sha256", "")))))
        return {"matches": matches[:limit], "semantic": semantic}

    @router.get("/api/library/assets/{asset_id}/usage")
    def get_library_asset_usage(asset_id: str) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            return {"library_asset_id": asset_id, "locations": []}
        locations = user_asset_store.usage(asset_id)
        # Defensive reverse scan catches older projects/timelines created
        # before explicit global references were introduced.
        for project in getattr(project_store, "list_projects", lambda **_: [])(include_archived=True):
            project_id = str(project.get("project_id", ""))
            try:
                for candidate in project_store.list_assets(project_id=project_id):
                    metadata = dict(candidate.get("metadata") or {})
                    if metadata.get("source_library_asset_id") == asset_id and not any(loc.get("materialized_asset_id") == candidate.get("asset_id") for loc in locations):
                        locations.append({"project_id": project_id, "materialized_asset_id": candidate.get("asset_id"), "location": {"kind": "project_asset"}})
            except Exception:
                continue
        return {"library_asset_id": asset_id, "locations": locations}

    @router.post("/api/library/assets/{asset_id}/trash")
    def trash_library_asset(asset_id: str) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=409, detail={"code": "builtin_asset_immutable", "library_asset_id": asset_id})
        if get_library_asset_usage(asset_id)["locations"]:
            raise HTTPException(status_code=409, detail={"code": "asset_referenced", "locations": get_library_asset_usage(asset_id)["locations"]})
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
        locations = get_library_asset_usage(asset_id)["locations"]
        if locations:
            raise HTTPException(status_code=409, detail={"code": "asset_referenced", "locations": locations})
        if asset.lifecycle is not LibraryAssetLifecycle.TRASHED:
            raise HTTPException(status_code=409, detail={"code": "asset_must_be_trashed"})
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
        try:
            derivative = _ensure_derivative(user_asset_store, managed_root, asset, derivative_kind, source)
        except _DerivativeToolUnavailable as exc:
            user_asset_store.update_lifecycle(asset.library_asset_id, LibraryAssetLifecycle.NEEDS_ATTENTION)
            raise HTTPException(status_code=503, detail={"state": "needs_attention", "code": "MEDIA_DERIVATIVE_TOOL_UNAVAILABLE"}) from exc
        derivative_path = managed_root / str(derivative["managed_relative_path"])
        return FileResponse(derivative_path, media_type=str(derivative["mime_type"]))

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
            try:
                reference = user_asset_store.add_project_reference(project_id=payload.project_id, library_asset_id=asset_id, materialized_asset_id=str(result.get("asset_id")), location={"project_id": payload.project_id})
            except Exception:
                # Cross-database atomicity is impossible here; compensate the
                # project copy immediately so a failed reference can never
                # leave an unguarded materialized asset behind.
                materializer._compensate_registered_asset(project_id=payload.project_id, asset_id=str(result.get("asset_id")))
                raise
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="project_missing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"asset": result, "reference": reference}

    @router.delete("/api/library/assets/{asset_id}/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    def remove_library_reference(asset_id: str, reference_id: str) -> None:
        find_asset(asset_id)
        if not any(str(item.get("reference_id")) == reference_id for item in user_asset_store.list_project_references(library_asset_id=asset_id)):
            raise HTTPException(status_code=404, detail="reference_missing")
        user_asset_store.remove_project_reference(reference_id)

    return router


def _ensure_derivative(store: LibraryUserAssetStore, root: Path, asset: Any, kind: str, source: Path) -> dict[str, Any]:
    extension = ".png"
    relative = Path("derivatives") / asset.content_sha256 / f"{DERIVATIVE_VERSION}-{kind}{extension}"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        try:
            rendered = _render_derivative(source=source, media_type=asset.media_type.value, kind=kind)
        except FileNotFoundError as exc:
            raise _DerivativeToolUnavailable("ffmpeg_unavailable") from exc
        if rendered is None:
            # A corrupt/unsupported file must remain inspectable, but never
            # receive the old fixed-label SVG. The hash-derived bars make the
            # fallback visibly tied to the uploaded bytes and are deterministic.
            bars = "".join(
                f'<rect x="{index * 20}" y="{20 + (int(char, 16) * 8)}" width="12" height="{180 - int(char, 16) * 6}" fill="#e85d04"/>'
                for index, char in enumerate(asset.content_sha256[:32])
            )
            extension = ".svg"
            relative = relative.with_suffix(extension)
            target = root / relative
            target.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="220" viewBox="0 0 640 220"><rect width="640" height="220" fill="#fff7ed"/>{bars}</svg>', encoding="utf-8")
        else:
            target.write_bytes(rendered)
    mime_type = "image/svg+xml" if target.suffix == ".svg" else "image/png"
    digest = _sha256(target)
    return store.upsert_derivative(library_asset_id=asset.library_asset_id, kind=kind, managed_relative_path=relative.as_posix(), content_sha256=digest, byte_count=target.stat().st_size, mime_type=mime_type, metadata={"source_sha256": asset.content_sha256, "version": DERIVATIVE_VERSION, "generator": "ffmpeg" if target.suffix != ".svg" else "hash-fallback"})


def _render_derivative(*, source: Path, media_type: str, kind: str) -> bytes | None:
    if media_type == "broll":
        command = ["ffmpeg", "-y", "-v", "error", "-ss", "0", "-i", str(source), "-frames:v", "1", "-vf", "scale=640:360:force_original_aspect_ratio=decrease", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    else:
        height = "220" if kind == "waveform" else "360"
        command = ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-filter_complex", f"aformat=channel_layouts=mono,showwavespic=s=640x{height}:colors=orangered", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    if result.returncode != 0 or not result.stdout:
        return None
    return bytes(result.stdout)


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
