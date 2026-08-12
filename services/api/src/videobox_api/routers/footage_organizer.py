"""Non-destructive footage organization HTTP API.

The router deliberately owns only proposal/sequence state.  It never calls an
editing-session mutation and previews are read-only range deliveries from the
canonical library source.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from typing import Any, Callable, Mapping
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status

from videobox_api.content_delivery import deliver_file
from videobox_api.models import (
    FootageApprovalRequest,
    FootageDerivativeRenderRequest,
    FootageProposalCreateRequest,
    FootageProposalEditRequest,
    FootageRevisionRequest,
    VirtualSequenceApprovalRequest,
    VirtualSequenceCreateRequest,
    VirtualSequenceReorderRequest,
)
from videobox_core_engine.footage_organizer import FootageOrganizerService
from videobox_domain_models.footage_organizer import VirtualSequenceItem
from videobox_storage.footage_organizer_store import (
    FootageOrganizerStore,
    OptimisticRevisionConflict,
)
from videobox_storage.media_library_store import MediaLibraryStore


class _LibraryAssetAdapter:
    """Expose verified user assets in the shape used by the core service."""

    def __init__(self, store: MediaLibraryStore) -> None:
        self.store = store

    def get_verified_asset(self, *, library_asset_id: str) -> dict[str, Any] | None:
        asset = self.store.user_asset_store.get_asset(library_asset_id)
        if asset is None or asset.lifecycle.value != "ready":
            return None
        path = (self.store.root / asset.managed_relative_path).resolve()
        try:
            path.relative_to(self.store.root.resolve())
        except ValueError:
            return None
        if not path.is_file() or _sha256(path) != asset.content_sha256:
            return None
        return {
            "library_asset_id": asset.library_asset_id,
            "content_sha256": asset.content_sha256,
            "filename": path.name,
            "path": str(path),
            "duration_seconds": asset.technical_metadata.get("duration_seconds"),
        }


def build_footage_organizer_router(
    *,
    media_library_store: MediaLibraryStore,
    detector: Any | None = None,
    derivative_renderer: Callable[[Path, Path, list[tuple[float, float]]], None] | None = None,
) -> APIRouter:
    router = APIRouter()
    footage_store = media_library_store.footage_organizer_store
    asset_adapter = _LibraryAssetAdapter(media_library_store)
    _ensure_derivative_jobs_schema(footage_store.database_path)

    def service(analysis: Mapping[str, Any] | None = None) -> FootageOrganizerService:
        def detect(asset: Mapping[str, Any]) -> Mapping[str, Any]:
            if analysis is not None:
                return analysis
            duration = asset.get("duration_seconds") or 1.0
            return {"total_duration": float(duration)}

        return FootageOrganizerService(
            store=footage_store,
            # A request-supplied deterministic analysis is an explicit owner
            # proposal and takes precedence over the runtime detector.
            detector=detect if analysis is not None else (detector or detect),
            asset_store=asset_adapter,
        )

    @router.post("/api/footage/proposals", status_code=status.HTTP_201_CREATED)
    def propose(payload: FootageProposalCreateRequest) -> dict[str, Any]:
        try:
            result = service(payload.analysis).propose_segments(
                payload.library_asset_id, payload.idempotency_key
            )
        except Exception as exc:  # noqa: BLE001 - API boundary normalization
            raise _footage_error(exc) from exc
        return _proposal_payload(result)

    @router.get("/api/footage/proposals/{proposal_id}")
    def get_proposal(proposal_id: str) -> dict[str, Any]:
        result = footage_store.get_proposal(proposal_id)
        if result is None:
            raise HTTPException(status_code=404, detail="footage_proposal_missing")
        return _proposal_payload(result)

    @router.patch("/api/footage/proposals/{proposal_id}")
    def edit_proposal(proposal_id: str, payload: FootageProposalEditRequest) -> dict[str, Any]:
        try:
            worker = service()
            if payload.operation == "move_boundary":
                if payload.segment_id is None or payload.boundary_sec is None:
                    raise ValueError("segment_id and boundary_sec are required")
                result = worker.move_boundary(
                    proposal_id=proposal_id,
                    segment_id=payload.segment_id,
                    boundary_sec=payload.boundary_sec,
                    expected_revision=payload.expected_revision,
                )
            elif payload.operation == "split":
                if payload.segment_id is None or payload.split_sec is None:
                    raise ValueError("segment_id and split_sec are required")
                result = worker.split_draft(
                    proposal_id=proposal_id,
                    segment_id=payload.segment_id,
                    split_sec=payload.split_sec,
                    expected_revision=payload.expected_revision,
                )
            elif payload.operation == "merge":
                result = worker.merge_drafts(
                    proposal_id=proposal_id,
                    segment_ids=payload.segment_ids,
                    expected_revision=payload.expected_revision,
                )
            elif payload.operation == "exclude":
                if payload.segment_id is None:
                    raise ValueError("segment_id is required")
                result = worker.exclude_draft(
                    proposal_id=proposal_id,
                    segment_id=payload.segment_id,
                    expected_revision=payload.expected_revision,
                )
            else:
                current = footage_store.get_proposal(proposal_id)
                if current is None:
                    raise KeyError(proposal_id)
                if current.status.value != "draft":
                    raise ValueError("only draft proposals can be edited")
                result = footage_store.confirm_proposal_fields(
                    proposal_id=proposal_id,
                    expected_revision=payload.expected_revision,
                    fields=payload.fields,
                )
        except Exception as exc:  # noqa: BLE001
            raise _footage_error(exc) from exc
        return _proposal_payload(result)

    @router.post("/api/footage/proposals/{proposal_id}/preview")
    def preview_proposal(proposal_id: str, payload: FootageRevisionRequest) -> dict[str, Any]:
        proposal = footage_store.get_proposal(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="footage_proposal_missing")
        if proposal.revision != payload.expected_revision:
            raise HTTPException(status_code=409, detail="footage_proposal_revision_conflict")
        source = footage_store.get_source(proposal.source_id)
        if source is None or asset_adapter.get_verified_asset(library_asset_id=source.library_asset_id) is None:
            raise HTTPException(status_code=422, detail="footage_source_stale")
        return {
            "status": "ready",
            "proposal_id": proposal_id,
            "revision": proposal.revision,
            "source_id": source.source_id,
            "preview_url": f"/api/footage/sources/{source.source_id}/preview",
            "segments": [_segment_payload(segment) for segment in proposal.segments],
        }

    @router.post("/api/footage/proposals/{proposal_id}/cancel")
    def cancel_proposal(proposal_id: str) -> dict[str, Any]:
        # Cancellation is a UI intent, not a persistence transition.  This is
        # intentionally a pure read so a preview/cancel pair cannot create a
        # library row or revision.
        proposal = footage_store.get_proposal(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="footage_proposal_missing")
        return {"status": "cancelled", "proposal_id": proposal_id, "revision": proposal.revision}

    @router.post("/api/footage/proposals/{proposal_id}/approve")
    def approve_proposal(proposal_id: str, payload: FootageApprovalRequest) -> dict[str, Any]:
        current = footage_store.get_proposal(proposal_id)
        if current is None:
            raise HTTPException(status_code=404, detail="footage_proposal_missing")
        if current.status.value == "approved":
            return _proposal_payload(current)
        if current.status.value != "draft":
            raise HTTPException(status_code=409, detail="footage_proposal_not_approvable")
        try:
            result = footage_store.set_proposal_status(
                proposal_id=proposal_id,
                status="approved",
                expected_revision=payload.expected_revision,
            )
        except Exception as exc:  # noqa: BLE001
            raise _footage_error(exc) from exc
        return _proposal_payload(result)

    @router.post("/api/footage/sequences", status_code=status.HTTP_201_CREATED)
    def create_sequence(payload: VirtualSequenceCreateRequest) -> dict[str, Any]:
        sequence_id = (
            "vseq_" + hashlib.sha256(
                json.dumps(payload.model_dump(exclude={"idempotency_key"}), sort_keys=True).encode()
            ).hexdigest()[:32]
            if payload.idempotency_key
            else None
        )
        try:
            result = footage_store.create_virtual_sequence(
                source_id=payload.source_id,
                name=payload.name,
                items=[VirtualSequenceItem.create(**item.model_dump()) for item in payload.items],
                sequence_id=sequence_id,
            )
        except sqlite3.IntegrityError:
            if sequence_id is None:
                raise
            result = footage_store.get_virtual_sequence(sequence_id)
            if result is None:
                raise
        except Exception as exc:  # noqa: BLE001
            raise _footage_error(exc) from exc
        return _sequence_payload(result)

    @router.get("/api/footage/sequences/{sequence_id}")
    def get_sequence(sequence_id: str) -> dict[str, Any]:
        result = footage_store.get_virtual_sequence(sequence_id)
        if result is None:
            raise HTTPException(status_code=404, detail="footage_sequence_missing")
        return _sequence_payload(result)

    @router.patch("/api/footage/sequences/{sequence_id}/reorder")
    def reorder_sequence(sequence_id: str, payload: VirtualSequenceReorderRequest) -> dict[str, Any]:
        try:
            result = _reorder_sequence(footage_store, sequence_id, payload.expected_revision, payload.item_ids)
        except Exception as exc:  # noqa: BLE001
            raise _footage_error(exc) from exc
        return _sequence_payload(result)

    @router.post("/api/footage/sequences/{sequence_id}/preview")
    def preview_sequence(sequence_id: str) -> dict[str, Any]:
        result = footage_store.get_virtual_sequence(sequence_id)
        if result is None:
            raise HTTPException(status_code=404, detail="footage_sequence_missing")
        source = footage_store.get_source(result.source_id)
        if source is None or asset_adapter.get_verified_asset(library_asset_id=source.library_asset_id) is None:
            raise HTTPException(status_code=422, detail="footage_source_stale")
        return {"status": "ready", "sequence_id": sequence_id, "revision": result.revision, "preview_url": f"/api/footage/sources/{source.source_id}/preview", "items": [_item_payload(item) for item in result.items]}

    @router.post("/api/footage/sequences/{sequence_id}/cancel")
    def cancel_sequence(sequence_id: str) -> dict[str, Any]:
        result = footage_store.get_virtual_sequence(sequence_id)
        if result is None:
            raise HTTPException(status_code=404, detail="footage_sequence_missing")
        return {"status": "cancelled", "sequence_id": sequence_id, "revision": result.revision}

    @router.post("/api/footage/sequences/{sequence_id}/approve")
    def approve_sequence(sequence_id: str, payload: VirtualSequenceApprovalRequest) -> dict[str, Any]:
        result = footage_store.get_virtual_sequence(sequence_id)
        if result is None:
            raise HTTPException(status_code=404, detail="footage_sequence_missing")
        connection = sqlite3.connect(footage_store.database_path)
        try:
            prior = connection.execute(
                "SELECT idempotency_key FROM footage_sequence_approvals WHERE sequence_id = ?", (sequence_id,)
            ).fetchone()
            if prior is not None and str(prior[0]) != payload.idempotency_key:
                raise HTTPException(status_code=409, detail="footage_sequence_idempotency_conflict")
            connection.execute(
                "INSERT OR IGNORE INTO footage_sequence_approvals (sequence_id, idempotency_key, created_at) VALUES (?, ?, datetime('now'))",
                (sequence_id, payload.idempotency_key),
            )
            connection.commit()
        finally:
            connection.close()
        # Sequence rows are created atomically with their ordered items; this
        # small approval ledger makes the explicit transition durable/replayable.
        response = _sequence_payload(result)
        response["status"] = "approved"
        return response

    @router.get("/api/footage/sources/{source_id}/preview")
    def source_preview(source_id: str, request: Request):
        source = footage_store.get_source(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="footage_source_missing")
        asset = asset_adapter.get_verified_asset(library_asset_id=source.library_asset_id)
        if asset is None:
            raise HTTPException(status_code=422, detail="footage_source_stale")
        path = Path(str(asset["path"]))
        return deliver_file(request=request, path=path, media_type="video/mp4")

    @router.post("/api/footage/derivatives/render", status_code=status.HTTP_202_ACCEPTED)
    def render_derivative(payload: FootageDerivativeRenderRequest) -> dict[str, Any]:
        return _render_derivative(
            footage_store,
            media_library_store,
            asset_adapter,
            payload,
            derivative_renderer,
        )

    return router


def _proposal_payload(value: Any) -> dict[str, Any]:
    return {"proposal_id": value.proposal_id, "source_id": value.source_id, "source_sha256": value.source_sha256, "status": value.status.value, "revision": value.revision, "confirmed_fields": value.confirmed_fields, "machine_fields": value.machine_fields, "segments": [_segment_payload(segment) for segment in value.segments]}


def _segment_payload(value: Any) -> dict[str, Any]:
    return {"segment_id": value.segment_id, "source_segment_id": value.source_segment_id, "source_sha256": value.source_sha256, "start_sec": value.start_sec, "end_sec": value.end_sec, "machine_fields": value.machine_fields, "confirmed_fields": value.confirmed_fields}


def _item_payload(value: Any) -> dict[str, Any]:
    return {"item_id": value.item_id, "source_segment_id": value.source_segment_id, "item_order": value.item_order, "start_sec": value.start_sec, "end_sec": value.end_sec}


def _sequence_payload(value: Any) -> dict[str, Any]:
    return {"sequence_id": value.sequence_id, "source_id": value.source_id, "source_sha256": value.source_sha256, "name": value.name, "revision": value.revision, "items": [_item_payload(item) for item in value.items]}


def _ensure_derivative_jobs_schema(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS footage_derivative_jobs (job_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, source_kind TEXT NOT NULL, source_id TEXT NOT NULL, status TEXT NOT NULL, derived_asset_id TEXT, error_message TEXT, created_at TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS footage_sequence_approvals (sequence_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL, created_at TEXT NOT NULL)")
        connection.commit()
    finally:
        connection.close()


def _reorder_sequence(store: FootageOrganizerStore, sequence_id: str, expected_revision: int, item_ids: list[str]) -> Any:
    connection = store._connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT revision FROM library_virtual_sequences WHERE sequence_id = ?", (sequence_id,)).fetchone()
        if row is None:
            raise KeyError(sequence_id)
        if int(row["revision"]) != expected_revision:
            raise OptimisticRevisionConflict("sequence revision conflict")
        approved = connection.execute(
            "SELECT 1 FROM footage_sequence_approvals WHERE sequence_id = ?", (sequence_id,)
        ).fetchone()
        if approved is not None:
            raise ValueError("approved sequence cannot be reordered")
        existing = [str(item[0]) for item in connection.execute("SELECT item_id FROM library_virtual_sequence_items WHERE sequence_id = ? ORDER BY item_order", (sequence_id,)).fetchall()]
        if sorted(existing) != sorted(item_ids) or len(set(item_ids)) != len(item_ids):
            raise ValueError("item_ids must contain exactly the sequence items")
        # The schema requires positive orders, so use a disjoint positive
        # range while swapping instead of a temporary zero/negative value.
        for position, item_id in enumerate(item_ids, 1):
            connection.execute("UPDATE library_virtual_sequence_items SET item_order = ? WHERE item_id = ?", (1000000 + position, item_id))
        for position, item_id in enumerate(item_ids, 1):
            connection.execute("UPDATE library_virtual_sequence_items SET item_order = ? WHERE item_id = ?", (position, item_id))
        connection.execute("UPDATE library_virtual_sequences SET revision = revision + 1 WHERE sequence_id = ?", (sequence_id,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return store.get_virtual_sequence(sequence_id)


def _render_derivative(store: FootageOrganizerStore, library: MediaLibraryStore, adapter: _LibraryAssetAdapter, payload: FootageDerivativeRenderRequest, renderer: Callable[[Path, Path, list[tuple[float, float]]], None] | None) -> dict[str, Any]:
    connection = sqlite3.connect(store.database_path)
    connection.row_factory = sqlite3.Row
    try:
        existing = connection.execute("SELECT * FROM footage_derivative_jobs WHERE idempotency_key = ?", (payload.idempotency_key,)).fetchone()
        if existing is not None:
            if str(existing["source_kind"]) != payload.source_kind or str(existing["source_id"]) != payload.source_id:
                raise HTTPException(status_code=409, detail="footage_derivative_idempotency_conflict")
            return dict(existing)
        job_id = f"footage_render_job_{uuid4().hex}"
        try:
            connection.execute("INSERT INTO footage_derivative_jobs (job_id, idempotency_key, source_kind, source_id, status, created_at) VALUES (?, ?, ?, ?, 'running', datetime('now'))", (job_id, payload.idempotency_key, payload.source_kind, payload.source_id))
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            replay = connection.execute("SELECT * FROM footage_derivative_jobs WHERE idempotency_key = ?", (payload.idempotency_key,)).fetchone()
            if replay is None or str(replay["source_kind"]) != payload.source_kind or str(replay["source_id"]) != payload.source_id:
                raise HTTPException(status_code=409, detail="footage_derivative_idempotency_conflict")
            return dict(replay)
    finally:
        connection.close()
    if payload.source_kind == "proposal":
        source_record = store.get_proposal(payload.source_id)
        if source_record is None or source_record.status.value != "approved":
            return _finish_job(store.database_path, job_id, "failed", error="footage_proposal_not_approved")
        source = store.get_source(source_record.source_id)
        ranges = [(segment.start_sec, segment.end_sec) for segment in source_record.segments]
    else:
        source_record = store.get_virtual_sequence(payload.source_id)
        if source_record is None:
            return _finish_job(store.database_path, job_id, "failed", error="footage_sequence_missing")
        approval = sqlite3.connect(store.database_path)
        try:
            approved = approval.execute(
                "SELECT 1 FROM footage_sequence_approvals WHERE sequence_id = ?", (payload.source_id,)
            ).fetchone()
        finally:
            approval.close()
        if approved is None:
            return _finish_job(store.database_path, job_id, "failed", error="footage_sequence_not_approved")
        source = store.get_source(source_record.source_id)
        ranges = [(item.start_sec or 0.0, item.end_sec or 0.0) for item in source_record.items]
    if source is None:
        return _finish_job(store.database_path, job_id, "failed", error="footage_source_stale")
    asset = adapter.get_verified_asset(library_asset_id=source.library_asset_id)
    if asset is None:
        return _finish_job(store.database_path, job_id, "failed", error="footage_source_stale")
    output_relative = f"derived/footage/{job_id}.mp4"
    output_path = library.root / output_relative
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if renderer is not None:
            renderer(Path(str(asset["path"])), output_path, ranges)
        else:
            _default_render(Path(str(asset["path"])), output_path, ranges)
        digest = _sha256(output_path)
        derived = library.user_asset_store.register_asset(
            library_asset_id=f"derived:{job_id}", media_type="broll", origin="user", lifecycle="ready",
            content_sha256=digest, managed_relative_path=output_relative, byte_count=output_path.stat().st_size,
            mime_type="video/mp4", machine_metadata={"semantic_index_status": "queued", "source_kind": payload.source_kind, "source_id": payload.source_id},
        )
        # The existing maintenance indexer discovers user footage by this
        # durable asset/path identity.  Touch the same pending queue after the
        # derived row commits so a response cannot claim indexing without an
        # actual pending item.
        pending = library.list_footage_needing_analysis(
            paths=[output_path], description_version=2
        )
        if not any(str(item.get("library_asset_id")) == derived.library_asset_id for item in pending):
            raise RuntimeError("derived_asset_not_queued_for_semantic_index")
    except Exception as exc:  # noqa: BLE001
        return _finish_job(store.database_path, job_id, "failed", error=str(exc))
    return _finish_job(store.database_path, job_id, "succeeded", derived_asset_id=derived.library_asset_id)


def _finish_job(database_path: Path, job_id: str, status_value: str, *, derived_asset_id: str | None = None, error: str | None = None) -> dict[str, Any]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("UPDATE footage_derivative_jobs SET status = ?, derived_asset_id = ?, error_message = ? WHERE job_id = ?", (status_value, derived_asset_id, error, job_id))
        row = connection.execute("SELECT * FROM footage_derivative_jobs WHERE job_id = ?", (job_id,)).fetchone()
        connection.commit()
        assert row is not None
        return dict(row)
    finally:
        connection.close()


def _default_render(source: Path, output: Path, ranges: list[tuple[float, float]]) -> None:
    # Rendering remains explicit and independent.  The source is never opened
    # for writing; ffmpeg writes a new managed path.
    if len(ranges) == 1 and ranges[0][0] <= 0 and ranges[0][1] <= 0:
        shutil.copy2(source, output)
        return
    if not ranges:
        raise RuntimeError("footage_derivative_render_failed")
    with tempfile.TemporaryDirectory(prefix="footage-render-", dir=str(output.parent)) as temp:
        parts: list[Path] = []
        for index, (start, end) in enumerate(ranges):
            part = Path(temp) / f"part-{index:04d}.mp4"
            command = ["ffmpeg", "-y", "-v", "error", "-ss", str(max(0.0, start)), "-i", str(source)]
            if end > start:
                command.extend(["-t", str(end - start)])
            command.extend(["-c", "copy", str(part)])
            result = subprocess.run(command, capture_output=True, check=False, timeout=120)
            if result.returncode != 0 or not part.is_file():
                raise RuntimeError("footage_derivative_render_failed")
            parts.append(part)
        concat_file = Path(temp) / "concat.txt"
        concat_file.write_text("\n".join(f"file '{part.as_posix()}'" for part in parts), encoding="utf-8")
        result = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output)],
            capture_output=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0 or not output.is_file():
            raise RuntimeError("footage_derivative_render_failed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _footage_error(exc: Exception) -> HTTPException:
    if isinstance(exc, OptimisticRevisionConflict):
        if "sequence" in str(exc):
            return HTTPException(status_code=409, detail="footage_sequence_revision_conflict")
        return HTTPException(status_code=409, detail="footage_proposal_revision_conflict")
    if isinstance(exc, (KeyError, LookupError)):
        return HTTPException(status_code=404, detail="footage_source_missing")
    if isinstance(exc, ValueError) and "stale" in str(exc):
        return HTTPException(status_code=422, detail="footage_source_stale")
    if isinstance(exc, ValueError) and "approved" in str(exc):
        return HTTPException(status_code=409, detail="footage_already_approved")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


__all__ = ["build_footage_organizer_router"]
