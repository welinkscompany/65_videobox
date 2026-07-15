from __future__ import annotations

import threading
import shutil
import os
from pathlib import Path
from typing import Any

from videobox_storage.local_project_store import sha256_file
from videobox_domain_models.assets import AssetType


class ProjectAssetMaterializer:
    """Validate an immutable proposal candidate before exposing its project-local bytes.

    Director candidates already point at assets owned by the target project.  This
    boundary deliberately does not apply a proposal or alter an editing session;
    it serializes same-SHA checks and proves that the registered bytes still have
    the identity captured in the proposal.
    """

    def __init__(self, store: object) -> None:
        self.store = store
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def validate_candidate(self, *, project_id: str, candidate: object) -> tuple[dict[str, Any], Path]:
        asset = self.store.get_asset(project_id=project_id, asset_id=candidate.asset_id)  # type: ignore[attr-defined]
        source = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))  # type: ignore[attr-defined]
        if not source.exists() or sha256_file(source) != candidate.expected_content_sha256:
            raise ValueError("candidate_source_changed")
        if candidate.media_revision != str(asset.get("created_at") or ""):
            raise ValueError("candidate_media_revision_changed")
        self._validate_eligibility(project_id=project_id, asset=asset, candidate=candidate)
        return asset, source

    def materialize(self, *, project_id: str, candidate: object) -> dict[str, Any]:
        digest = str(candidate.expected_content_sha256 or "")
        if not digest:
            raise ValueError("candidate_sha_missing")
        with self._lock_for(digest):
            asset, source = self.validate_candidate(project_id=project_id, candidate=candidate)
            for existing in self.store.list_assets(project_id=project_id):  # type: ignore[attr-defined]
                metadata = dict(existing.get("metadata") or {})
                existing_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(existing["storage_uri"]))  # type: ignore[attr-defined]
                if (metadata.get("director_materialized_sha256") == digest and metadata.get("source_asset_id") == candidate.asset_id
                        and metadata.get("license_policy") == candidate.license_policy
                        and list(metadata.get("warning_provenance") or []) == list(candidate.warning_provenance)
                        and existing_path.exists() and sha256_file(existing_path) == digest):
                    return self._candidate_result(existing, candidate, digest)
            stage_dir = self.store.project_root(project_id) / ".materializing"  # type: ignore[attr-defined]
            stage_dir.mkdir(parents=True, exist_ok=True)
            staged = stage_dir / f"{digest}-{source.name}"
            registered = None
            try:
                if sha256_file(source) != digest:
                    raise ValueError("candidate_source_changed")
                shutil.copy2(source, staged)
                if sha256_file(source) != digest or sha256_file(staged) != digest:
                    raise ValueError("candidate_staging_sha_mismatch")
                asset_type = {"broll": AssetType.BROLL_VIDEO, "bgm": AssetType.BGM, "sfx": AssetType.SFX}.get(candidate.media_type)
                if asset_type is None:
                    raise ValueError("candidate_media_type_invalid")
                registered = self.store.register_asset(  # type: ignore[attr-defined]
                    project_id=project_id, asset_type=asset_type, source_path=staged,
                    source_kind="director_materialized", mime_type=None,
                    metadata={"director_materialized_sha256": digest, "director_proposal_candidate_id": candidate.candidate_id,
                              "source_asset_id": candidate.asset_id, "license_policy": candidate.license_policy,
                              "warning_provenance": list(candidate.warning_provenance)},
                )
                result = self.store.get_asset(project_id=project_id, asset_id=registered.asset_id)  # type: ignore[attr-defined]
                project_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(result["storage_uri"]))  # type: ignore[attr-defined]
                if sha256_file(staged) != digest or not project_path.exists() or sha256_file(project_path) != digest:
                    raise ValueError("candidate_project_sha_mismatch")
                return self._candidate_result(result, candidate, digest)
            except Exception:
                if registered is not None:
                    self._compensate_registered_asset(project_id=project_id, asset_id=registered.asset_id)
                raise
            finally:
                if staged.exists():
                    os.remove(staged)
                if stage_dir.exists() and not any(stage_dir.iterdir()):
                    os.rmdir(stage_dir)

    @staticmethod
    def _candidate_result(asset: dict[str, Any], candidate: object, digest: str) -> dict[str, Any]:
        return {**asset, "content_sha256": digest, "media_revision": candidate.media_revision,
                "controls": dict(candidate.controls), "warning_provenance": list(candidate.warning_provenance)}

    def preview_snapshot(self, *, project_id: str, candidate: object) -> Path:
        """Return a rehashed immutable preview copy, never a mutable source path."""
        digest = str(candidate.expected_content_sha256 or "")
        with self._lock_for(f"preview:{project_id}:{digest}"):
            _, source = self.validate_candidate(project_id=project_id, candidate=candidate)
            previews = self.store.project_root(project_id) / ".preview-snapshots"  # type: ignore[attr-defined]
            previews.mkdir(parents=True, exist_ok=True)
            snapshot = previews / f"{digest}-{threading.get_ident()}-{source.name}"
            try:
                if sha256_file(source) != digest:
                    raise ValueError("candidate_source_changed")
                shutil.copy2(source, snapshot)
                if sha256_file(source) != digest or sha256_file(snapshot) != digest:
                    raise ValueError("candidate_preview_sha_mismatch")
                return snapshot
            except Exception:
                if snapshot.exists(): os.remove(snapshot)
                if previews.exists() and not any(previews.iterdir()): os.rmdir(previews)
                raise

    def materialize_verified_library_snapshot(
        self, *, project_id: str, library_asset_id: str, library_asset: dict[str, Any], snapshot_path: Path,
        mime_type: str | None,
    ) -> dict[str, Any]:
        """Copy a verified immutable snapshot once per project/SHA.

        The input is a MediaLibraryStore controlled snapshot, rather than its
        mutable pack source.  Hash it before and after registration; if a store
        failure leaves an asset record behind, remove it and its copied bytes.
        """
        expected = str(library_asset.get("sha256") or "")
        if not expected or not snapshot_path.exists() or sha256_file(snapshot_path) != expected:
            raise ValueError("library_snapshot_changed")
        with self._lock_for(f"{project_id}:{expected}"):
            for asset in self.store.list_assets(project_id=project_id):  # type: ignore[attr-defined]
                metadata = dict(asset.get("metadata") or {})
                source = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))  # type: ignore[attr-defined]
                if (metadata.get("source_library_asset_id") == library_asset_id
                        and metadata.get("license_snapshot") == {"official_url": str(library_asset["official_license_url"]), "evidence_timestamp": str(library_asset["evidence_timestamp"]), "evidence_sha256": str(library_asset["evidence_sha256"]), "source": str(library_asset["source"]), "creator": str(library_asset["creator"]), "attribution_required": bool(library_asset["attribution_required"]), "attribution_text": str(library_asset["attribution_text"])}
                        and source.exists() and sha256_file(source) == expected and str(asset.get("asset_type")) == ("bgm" if str(library_asset.get("media_type")) == "music" else "sfx")):
                    return asset
            media_type = str(library_asset.get("media_type") or "")
            asset_type = AssetType.BGM if media_type == "music" else AssetType.SFX if media_type == "sfx" else None
            if asset_type is None:
                raise ValueError("unsupported_media_type")
            source_pack_id = library_asset_id.split(":", 2)[1] if library_asset_id.startswith("pack:") else ""
            metadata = {
                "source_library_asset_id": library_asset_id, "source_pack_id": source_pack_id,
                "source_pack_version": str(library_asset["version"]),
                "license_snapshot": {"official_url": str(library_asset["official_license_url"]), "evidence_timestamp": str(library_asset["evidence_timestamp"]), "evidence_sha256": str(library_asset["evidence_sha256"]), "source": str(library_asset["source"]), "creator": str(library_asset["creator"]), "attribution_required": bool(library_asset["attribution_required"]), "attribution_text": str(library_asset["attribution_text"])},
            }
            registered = None
            try:
                registered = self.store.register_asset(project_id=project_id, asset_type=asset_type, source_path=snapshot_path, source_kind="media_library", mime_type=mime_type, metadata=metadata)  # type: ignore[attr-defined]
                result = self.store.get_asset(project_id=project_id, asset_id=registered.asset_id)  # type: ignore[attr-defined]
                project_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(result["storage_uri"]))  # type: ignore[attr-defined]
                if sha256_file(snapshot_path) != expected or not project_path.exists() or sha256_file(project_path) != expected:
                    raise ValueError("materialized_sha_mismatch")
                return result
            except Exception:
                if registered is not None:
                    self._compensate_registered_asset(project_id=project_id, asset_id=registered.asset_id)
                raise

    def _compensate_registered_asset(self, *, project_id: str, asset_id: str) -> None:
        """Leave neither asset row nor bytes when post-register verification fails.

        `delete_asset` normally owns this, but it commits its row deletion before
        unlinking.  If that unlink failed, remove the known project file using
        the OS primitive and retry the durable delete; never silently accept an
        orphan from a failed materialization.
        """
        path = None
        try:
            asset = self.store.get_asset(project_id=project_id, asset_id=asset_id)  # type: ignore[attr-defined]
            path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))  # type: ignore[attr-defined]
            self.store.delete_asset(project_id=project_id, asset_id=asset_id)  # type: ignore[attr-defined]
        except Exception:
            if path is not None and path.exists():
                os.remove(path)
            try:
                self.store.delete_asset(project_id=project_id, asset_id=asset_id)  # type: ignore[attr-defined]
            except KeyError:
                pass
        if path is not None and path.exists():
            os.remove(path)

    def _validate_eligibility(self, *, project_id: str, asset: dict[str, Any], candidate: object) -> None:
        metadata = dict(asset.get("metadata") or {})
        if candidate.media_type in {"bgm", "sfx"}:
            required = ("mood", "energy", "genre", "recommended_use") if candidate.media_type == "bgm" else ("action_event", "intensity", "recommended_use")
            if metadata.get("canonical_metadata_indexed") is not True or any(metadata.get(key) in (None, "") for key in required):
                raise ValueError("candidate_not_indexed")
            return
        analyses = self.store.list_media_analysis(project_id=project_id)  # type: ignore[attr-defined]
        matching = [item for item in analyses if str(item.get("asset_id")) == candidate.asset_id]
        if not any(self.store.can_apply_media_analysis(project_id=project_id, analysis_id=str(item["analysis_id"])) and bool(item.get("result")) for item in matching):  # type: ignore[attr-defined]
            raise ValueError("candidate_analysis_unavailable")

    def _lock_for(self, digest: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(digest, threading.Lock())
