from __future__ import annotations

import json
import hashlib
import logging
import math
from copy import deepcopy
from dataclasses import replace
import re
import shutil
import sqlite3
import subprocess
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal

from videobox_domain_models.assets import AssetRecord, AssetType
from videobox_storage.broll_source_window import choose_broll_source_window
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.media_analysis import MediaAnalysisStatus
from videobox_domain_models.projects import ProjectRecord, ProjectStatus
from videobox_domain_models.recommendations import RecommendationRecord, RecommendationType
from videobox_domain_models.transcripts import TranscriptRecord
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_core_engine.exact_preview import ExactPreviewRequest
from videobox_core_engine.composition_plan import materialize_editing_session_timeline
from videobox_core_engine.editor_playback_manifest import (
    build_editor_playback_manifest,
)
from videobox_storage.sqlite_schema import (
    ARTIFACT_SOURCE_SESSION_BACKFILL_STATEMENTS,
    HERMES_CAPABILITY_LEDGER_SCHEMA_STATEMENT,
    PROJECT_SCHEMA_STATEMENTS,
)
from videobox_domain_models.caption_style import CaptionStyle
from videobox_domain_models.director_proposals import DirectorProposal
from videobox_domain_models.yujin_creator_proposals import (
    CaptionTextParameters,
    EditorCaptionStyle,
    ExplanationCardParameters,
    ImageOverlayParameters,
    TableOverlayParameters,
    VoiceParameters,
)
from videobox_core_engine.director_proposals import proposal_from_payload, proposal_to_payload
from videobox_storage._store_hermes_capability import (
    HERMES_AUTHORITY_ID_MAX_LENGTH,
    HERMES_AUTHORITY_ID_PATTERN,
    HERMES_CAPABILITY_DENIAL_REASONS,
    HermesCapabilityMixin,
)
from videobox_storage._store_media_analysis import MediaAnalysisMixin, sha256_file
from videobox_storage._store_yujin_memory import (
    YUJIN_MEMORY_STORE_CLAIM_LEASE_SECONDS,
    YujinMemoryMixin,
)
from videobox_storage._store_output_variants import OutputVariantMixin
from videobox_storage._store_preview_shares import PreviewShareMixin

_LOGGER = logging.getLogger(__name__)
from videobox_core_engine.creation_interview import (
    CreationInterviewRuntime,
    DeterministicCreationInterviewRuntime,
    MAX_CREATION_INTERVIEW_QUESTIONS,
)

# Heavy exports (rendered mp4s, CapCut drafts) can be large; keep only the most
# recent N per export_type per project so disk usage does not grow unbounded.
DEFAULT_EXPORT_RETENTION_COUNT = 5
CAPCUT_DRAFT_HANDOFF_CLAIM_LEASE_SECONDS = 300
RETIRED_CREDENTIAL_TABLE = "g" + "emini_provider_keys"


class EditingSessionRevisionConflict(RuntimeError):
    """The persisted editing-session revision did not match the requested CAS revision."""


class EditingSessionPostCommitFileWriteError(OSError):
    """SQLite committed an editing session, but its convenience JSON mirror did not.

    The SQLite ``session_json`` column is authoritative and will recreate the
    mirror on the next read.  Callers that own files registered in the same
    transaction must therefore *not* compensate those files.
    """


def _normalize_boolish(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _is_actionable_yujin_media_proposal(proposal: DirectorProposal) -> bool:
    if (
        proposal.status != "ready"
        or proposal.diff.get("proposal_mode")
        not in {"yujin_actionable_media_v1", "yujin_actionable_v1"}
    ):
        return False
    actionable = [
        candidate
        for candidate in proposal.candidates
        if candidate.availability == "actionable"
    ]
    def valid(candidate: DirectorCandidate) -> bool:
        metadata = candidate.canonical_metadata
        if candidate.review_status != "approved" or not metadata.get(
            "target_segment_id"
        ):
            return False
        if candidate.media_type in {"broll", "bgm", "sfx"}:
            return bool(
                (
                    metadata.get("source_media_kind")
                    in {"raw_video", "broll_video"}
                    if candidate.media_type == "broll"
                    else metadata.get("source_media_kind") == candidate.media_type
                )
                and candidate.expected_content_sha256 is not None
                and len(candidate.expected_content_sha256) == 64
                and metadata.get("yujin_actionable_media") is True
            )
        return bool(
            candidate.media_type in {"caption", "voice", "overlay"}
            and metadata.get("yujin_actionable_operation") is True
            and metadata.get("command_kind")
            in {
                "set_caption_text",
                "set_caption_style",
                "apply_tts_candidate",
                "apply_overlay",
            }
        )

    return bool(actionable) and all(valid(candidate) for candidate in actionable)


def _has_exact_keys(value: object, expected: set[str]) -> bool:
    return isinstance(value, Mapping) and set(value) == expected


def _json_plain_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _json_plain_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_plain_value(item) for item in value]
    return value


def _valid_b4_candidate_controls(candidate: DirectorCandidate) -> bool:
    controls = candidate.controls
    metadata = candidate.canonical_metadata
    command_kind = metadata.get("command_kind")
    try:
        if candidate.media_type == "caption" and command_kind == "set_caption_text":
            if not _has_exact_keys(controls, {"text"}):
                return False
            CaptionTextParameters.model_validate(
                {"action": "set_text", "text": controls["text"]}
            )
            return True
        if candidate.media_type == "caption" and command_kind == "set_caption_style":
            if (
                not _has_exact_keys(controls, {"scope", "style"})
                or controls.get("scope") != "current_caption"
            ):
                return False
            EditorCaptionStyle.model_validate(dict(controls["style"]))
            return True
        if candidate.media_type == "voice" and command_kind == "apply_tts_candidate":
            if not _has_exact_keys(controls, {"candidate_id", "asset_id"}):
                return False
            voice = VoiceParameters.model_validate(dict(controls))
            return bool(
                voice.candidate_id == metadata.get("candidate_id")
                and voice.asset_id == candidate.asset_id
            )
        if candidate.media_type != "overlay" or command_kind != "apply_overlay":
            return False
        overlay_kind = controls.get("overlay_kind")
        if overlay_kind == "explanation-card":
            if not _has_exact_keys(
                controls,
                {"overlay_kind", "title", "body", "text"},
            ):
                return False
            ExplanationCardParameters.model_validate(
                {**dict(controls), "overlay_kind": "explanation_card"}
            )
            return True
        if overlay_kind == "image":
            if not _has_exact_keys(controls, {"overlay_kind", "asset_id", "text"}):
                return False
            image = ImageOverlayParameters.model_validate(dict(controls))
            return image.asset_id == candidate.asset_id
        if overlay_kind == "table":
            if not _has_exact_keys(
                controls,
                {"overlay_kind", "columns", "rows", "text"},
            ):
                return False
            TableOverlayParameters.model_validate_json(
                json.dumps(dict(controls), ensure_ascii=False)
            )
            return True
    except (KeyError, TypeError, ValueError):
        return False
    return False


def _session_image_overlay_matches_identity(
    *,
    session_payload: dict[str, Any],
    segment_id: str,
    asset_id: str,
    text: str,
    asset_uri: str,
    expected_content_sha256: str,
    media_revision: str,
) -> bool:
    has_direct_match = any(
        isinstance(segment, dict)
        and str(segment.get("segment_id") or "") == segment_id
        for segment in session_payload.get("segments", [])
    )
    matched: list[dict[str, Any]] = []
    for segment in session_payload.get("segments", []):
        if not isinstance(segment, dict):
            continue
        containing_segment_id = str(segment.get("segment_id") or "")
        direct_match = containing_segment_id == segment_id
        overlay_lists: list[list[Any]] = []
        if direct_match and isinstance(segment.get("visual_overlays"), list):
            overlay_lists.append(segment["visual_overlays"])
        content_windows = segment.get("content_windows")
        if isinstance(content_windows, list):
            for window in content_windows:
                if not isinstance(window, dict):
                    continue
                source_segment_id = str(
                    window.get("source_segment_id") or containing_segment_id
                )
                visible_match = (
                    direct_match
                    if has_direct_match
                    else source_segment_id == segment_id
                )
                if visible_match and isinstance(
                    window.get("visual_overlays"), list
                ):
                    overlay_lists.append(window["visual_overlays"])
        for overlays in overlay_lists:
            matched.extend(
                overlay
                for overlay in overlays
                if isinstance(overlay, dict)
                and overlay.get("overlay_type") == "image_overlay"
            )
    return bool(matched) and all(
        overlay.get("asset_id") == asset_id
        and overlay.get("text") == text
        and overlay.get("asset_uri") == asset_uri
        and overlay.get("expected_content_sha256") == expected_content_sha256
        and overlay.get("media_revision") == media_revision
        for overlay in matched
    )


def _session_matches_yujin_b4_command(
    *,
    session_payload: dict[str, Any],
    segment_id: str,
    command_kind: str,
    controls: dict[str, Any],
) -> bool:
    targets: list[dict[str, Any]] = []
    for segment in session_payload.get("segments", []):
        if not isinstance(segment, dict):
            continue
        containing_id = str(segment.get("segment_id") or "")
        if containing_id == segment_id:
            targets.append(segment)
        for window in segment.get("content_windows", []):
            if not isinstance(window, dict):
                continue
            source_id = str(window.get("source_segment_id") or containing_id)
            if source_id == segment_id:
                targets.append(window)
    if command_kind == "set_caption_text":
        return any(
            item.get("caption_text") == str(controls.get("text") or "").strip()
            for item in targets
        )
    if command_kind == "set_caption_style":
        # 유진이 보낸 칸(11개, `yujin_creator_proposals.EditorCaptionStyle`
        # 고정 스키마)과 세션에 저장된 칸을 그냥 비교하면 안 맞는다 -- 저장은
        # `CaptionStyle.from_dict(...).to_dict()`를 거쳐 굵게·기울임·자간
        # 기본값(2026-09-03 추가)까지 채워서 14개가 되기 때문이다. 원문
        # 그대로 대조하면 유진이 자막 모양을 바꿀 때마다 매번 증명 불일치로
        # 막힌다 -- 나중에 칸이 늘 때마다 반복될 함정이라 **양쪽 다 같은
        # 정규화를 거쳐** 비교한다.
        try:
            expected_style = CaptionStyle.from_dict(controls.get("style")).to_dict()
        except (TypeError, ValueError):
            return False
        return any(
            _json_plain_value(item.get("caption_style")) == _json_plain_value(expected_style)
            for item in targets
        )
    if command_kind == "apply_tts_candidate":
        expected = {
            "recommendation_id": controls.get("candidate_id"),
            "asset_id": controls.get("asset_id"),
        }
        return any(item.get("tts_replacement") == expected for item in targets)
    if command_kind != "apply_overlay":
        return False
    expected_type = {
        "explanation-card": "explanation_card",
        "table": "table_overlay",
    }.get(controls.get("overlay_kind"))
    if expected_type is None:
        return False
    expected_payload = {
        "overlay_type": expected_type,
        **{
            key: value
            for key, value in controls.items()
            if key != "overlay_kind"
        },
    }
    return any(
        _json_plain_value(overlay) == _json_plain_value(expected_payload)
        for item in targets
        for overlay in item.get("visual_overlays", [])
        if isinstance(overlay, dict)
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _canonical_recommendation_type(value: object) -> str:
    return str(value or "").strip().lower()


def _canonical_review_flag_code(value: object) -> str:
    return str(value or "").strip().lower()


def _canonical_track_type(value: object) -> str:
    return str(value or "").strip().lower()


VALID_STORE_BLOCKING_REVIEW_FLAG_CODES = {
    "segment_review_required",
    "broll_review_required",
    "sfx_review_required",
    "tts_replacement_review_required",
}
VALID_STORE_TRACK_TYPES = {"narration", "broll", "bgm", "sfx"}
VALID_STORE_BLOCKING_RECOMMENDATION_TYPES = {
    RecommendationType.TTS_REPLACEMENT.value,
    RecommendationType.BROLL.value,
    RecommendationType.BGM.value,
    RecommendationType.SFX.value,
    RecommendationType.OVERLAY.value,
}


def _is_store_supported_recommendation_type(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    return _canonical_recommendation_type(item.get("recommendation_type")) in VALID_STORE_BLOCKING_RECOMMENDATION_TYPES


def _is_store_supported_track(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    return _canonical_track_type(item.get("track_type")) in VALID_STORE_TRACK_TYPES


def _is_store_supported_track_summary(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    return _canonical_track_type(item.get("track_type")) in VALID_STORE_TRACK_TYPES


def _is_store_blocking_review_flag(flag: object) -> bool:
    if not isinstance(flag, dict):
        return False
    code = flag.get("code")
    segment_id = flag.get("segment_id")
    return (
        isinstance(code, str)
        and _canonical_review_flag_code(code) in VALID_STORE_BLOCKING_REVIEW_FLAG_CODES
        and isinstance(segment_id, str)
        and bool(segment_id.strip())
    )


def _is_store_blocking_pending_recommendation(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    recommendation_id = item.get("recommendation_id")
    target_segment_id = item.get("target_segment_id")
    recommendation_type = item.get("recommendation_type")
    decision_state = str(item.get("decision_state") or "").strip().lower()
    if decision_state and decision_state != "pending":
        return False
    if _normalize_boolish(item.get("auto_apply_allowed", False)) and not _normalize_boolish(
        item.get("review_required", False)
    ):
        return False
    return (
        isinstance(recommendation_id, str)
        and bool(recommendation_id.strip())
        and isinstance(target_segment_id, str)
        and bool(target_segment_id.strip())
        and _canonical_recommendation_type(recommendation_type) in VALID_STORE_BLOCKING_RECOMMENDATION_TYPES
    )


def _normalize_review_flag_payloads(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        code = _canonical_review_flag_code(item.get("code"))
        segment_id = str(item.get("segment_id") or "").strip()
        if not code or not segment_id:
            continue
        message = str(item.get("message") or "").strip()
        normalized.append(
            {
                "code": code,
                "segment_id": segment_id,
                "message": message or "Operator review required before approval or output.",
            }
        )
    return normalized


def _timeline_summary_json(payload: dict[str, Any]) -> str:
    tracks = payload.get("tracks", [])
    gap_slots = payload.get("gap_slots", [])
    review_flags = payload.get("review_flags", [])
    applied_recommendations = payload.get("applied_recommendations", [])
    pending_recommendations = payload.get("pending_recommendations", [])
    return json.dumps(
        {
            "track_count": sum(1 for track in tracks if _is_store_supported_track(track))
            if isinstance(tracks, list)
            else 0,
            "gap_count": sum(1 for gap in gap_slots if isinstance(gap, dict))
            if isinstance(gap_slots, list)
            else 0,
            "review_flag_count": sum(
                1 for flag in review_flags if _is_store_blocking_review_flag(flag)
            )
            if isinstance(review_flags, list)
            else 0,
            "applied_recommendation_count": sum(
                1
                for item in applied_recommendations
                if _is_store_supported_recommendation_type(item)
            )
            if isinstance(applied_recommendations, list)
            else 0,
            "pending_recommendation_count": sum(
                1
                for item in pending_recommendations
                if _is_store_blocking_pending_recommendation(item)
            )
            if isinstance(pending_recommendations, list)
            else 0,
        },
        ensure_ascii=True,
    )


class LocalProjectStore(OutputVariantMixin, PreviewShareMixin, YujinMemoryMixin, MediaAnalysisMixin, HermesCapabilityMixin):
    def __init__(
        self,
        projects_root: Path,
        now: Callable[[], datetime] | None = None,
        *,
        atomic_bundle_fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.projects_root = Path(projects_root)
        self._clock = now or (lambda: datetime.now(UTC))
        # A new store instance is a new local API process.  Exact-preview
        # workers lease this epoch, which lets startup reclaim a recent dead
        # process without weakening the generation/owner publish fence.
        self.exact_preview_process_epoch = uuid.uuid4().hex
        self.proposal_preview_process_epoch = uuid.uuid4().hex
        # Deliberately injectable only for deterministic failure-contract tests.
        # Production callers leave this unset; it is never a runtime provider hook.
        self._atomic_bundle_fault_hook = atomic_bundle_fault_hook
        self._reconcile_batch_director_operations()
        self._reconcile_atomic_draft_bundle_operations()

    def _reconcile_atomic_draft_bundle_operations(self) -> None:
        """Discard uncommitted draft-bundle stages left by a crash.

        The SQLite bundle row is authoritative.  A stage with no matching
        committed bundle is disposable and must never become a later draft.
        """
        projects = self.projects_root / "projects"
        if not projects.exists(): return
        for project_root in projects.iterdir():
            staging = project_root / "staging"
            if not staging.is_dir(): continue
            for candidate in staging.glob("draft-bundle-*"):
                manifest = candidate / "operation.json"
                if candidate.is_dir() and manifest.exists(): shutil.rmtree(candidate, ignore_errors=True)

    def _write_atomic_bundle_manifest(self, stage: Path, manifest: dict[str, Any]) -> None:
        """Durably publish the stage inventory before any mirror is made visible."""
        target = stage / "operation.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        temporary.replace(target)

    def _atomic_bundle_fault(self, event: str) -> None:
        if self._atomic_bundle_fault_hook is not None:
            self._atomic_bundle_fault_hook(event)

    def bootstrap_project(self, name: str) -> ProjectRecord:
        project = ProjectRecord.create(name=name)
        project_root = self.project_root(project.project_id)
        self._create_project_layout(project_root)
        self._bootstrap_database(project_root / "db" / "project.sqlite", project)
        return project

    def list_projects(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        projects_directory = self.projects_root / "projects"
        if not projects_directory.exists():
            return []
        items: list[dict[str, Any]] = []
        for project_directory in sorted(projects_directory.iterdir()):
            if not project_directory.is_dir():
                continue
            database_path = project_directory / "db" / "project.sqlite"
            if not database_path.exists():
                continue
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            try:
                schema_ready = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'projects'"
                ).fetchone()
                if schema_ready is None:
                    # bootstrap_project creates the file before its schema is
                    # committed. Background catalog polling may observe that
                    # short window; it should retry on the next poll rather
                    # than treating an initializing project as corruption.
                    continue
                row = connection.execute(
                    """
                    SELECT project_id, name, status, root_storage_uri, created_at, updated_at
                    FROM projects
                    LIMIT 1
                    """
                ).fetchone()
            finally:
                connection.close()
            if row is not None and (include_archived or str(row["status"]) != ProjectStatus.ARCHIVED.value):
                items.append(dict(row))
        return items

    def archive_project(self, *, project_id: str) -> dict[str, Any]:
        """Hide a project from the default list without touching its data
        (F-5). Reversible via restore_project -- §10.12.3's
        preserve-evidence intent makes archive the safe default; permanent
        deletion is a separate, not-yet-built decision."""
        return self._set_project_status(project_id=project_id, status=ProjectStatus.ARCHIVED)

    def restore_project(self, *, project_id: str) -> dict[str, Any]:
        return self._set_project_status(project_id=project_id, status=ProjectStatus.DRAFT)

    def rename_project(self, *, project_id: str, name: str) -> dict[str, Any]:
        """Change only what the owner reads: the display name.

        `project_id` and `root_storage_uri` deliberately stay put. They are
        the on-disk directory and the address every already-made asset and
        finished video points at -- moving them each time a title is edited
        would orphan the work that was already done. So a title stays
        editable forever while the storage layout stays stable.
        """
        display_name = name.strip()
        if not display_name:
            raise ValueError("project_name_required")
        self.get_project(project_id=project_id)  # raises KeyError if missing, on either backend
        self._execute(
            project_id,
            "UPDATE projects SET name = ?, updated_at = ? WHERE project_id = ?",
            (display_name, self._now_iso(), project_id),
        )
        return self.get_project(project_id=project_id)

    def delete_project_permanently(self, *, project_id: str) -> None:
        """Irreversibly remove a project's directory (its DB, assets,
        exports -- everything). Owner decision (2026-08-06): archive alone
        wasn't enough; a real delete path is needed, gated by explicit
        confirmation at the API/UI layer (see routers/projects.py and
        ProductShell.tsx's two-step confirm). Works on both active and
        archived projects."""
        project_dir = self.project_root(project_id)
        if not project_dir.is_dir():
            raise KeyError(f"Project not found: {project_id}")
        shutil.rmtree(project_dir)

    def _set_project_status(self, *, project_id: str, status: ProjectStatus) -> dict[str, Any]:
        self.get_project(project_id=project_id)  # raises KeyError if missing, on either backend
        self._execute(
            project_id,
            "UPDATE projects SET status = ?, updated_at = ? WHERE project_id = ?",
            (status.value, self._now_iso(), project_id),
        )
        return self.get_project(project_id=project_id)

    def list_all_jobs(self) -> list[dict[str, Any]]:
        # Jobs live in one SQLite file per project (see database_path) with no
        # shared/global jobs table, so a cross-project view has to iterate
        # every project directory and merge — the same approach list_projects
        # already uses. Fine at the project counts a local-first single-user
        # tool expects; would need a real index if that ever changes.
        all_jobs: list[dict[str, Any]] = []
        for project in self.list_projects():
            project_id = str(project["project_id"])
            for job in self.list_jobs(project_id=project_id):
                all_jobs.append({"project_name": project["name"], **job})
        return all_jobs

    def project_root(self, project_id: str) -> Path:
        return self.projects_root / "projects" / project_id

    def _reconcile_batch_director_operations(self) -> None:
        """Recover only disposable batch-apply files left around a process crash.

        A manifest is deliberately filesystem-durable before bytes leave staging.
        On restart, a destination is preserved only when SQLite owns the exact
        URI and hash; every other staged/destination file is compensation work.
        """
        projects = self.projects_root / "projects"
        if not projects.exists():
            return
        for project_root in projects.iterdir():
            if not project_root.is_dir() or not (project_root / "db" / "project.sqlite").is_file():
                continue
            operations = project_root / ".batch-director-operations"
            if not operations.exists():
                continue
            project_id = project_root.name
            for manifest in operations.glob("*.json"):
                try:
                    payload = json.loads(manifest.read_text(encoding="utf-8"))
                    if not self._batch_manifest_paths_are_safe(
                        project_root=project_root,
                        operations=operations,
                        manifest=manifest,
                        payload=payload,
                    ):
                        # A manifest can be hand-edited or partially corrupt.
                        # Retain it for inspection rather than using its paths
                        # as deletion authority.
                        continue
                    entries = list(payload.get("entries") or []) if isinstance(payload, dict) else []
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        destination = Path(str(entry.get("destination_path") or ""))
                        staged = Path(str(entry.get("staged_path") or ""))
                        digest = str(entry.get("sha256") or "")
                        if destination.exists() and not self._batch_destination_is_registered(project_id, destination, digest):
                            destination.unlink()
                        if staged.exists():
                            staged.unlink()
                        if staged.parent != operations and staged.parent.exists() and not any(staged.parent.iterdir()):
                            staged.parent.rmdir()
                except (OSError, ValueError, json.JSONDecodeError):
                    # A corrupt manifest must not make startup unavailable;
                    # it is retained for operator inspection rather than
                    # guessing which files it owns.
                    continue
                manifest.unlink(missing_ok=True)
            # ``.tmp`` is only the atomically-written manifest sidecar.  It is
            # safe to remove from the operation root even when no final JSON
            # was written; do not infer ownership from arbitrary nested files.
            for temporary in operations.glob("*.tmp"):
                if temporary.is_file():
                    temporary.unlink(missing_ok=True)
            for operation_dir in operations.iterdir():
                if operation_dir.is_dir() and not any(operation_dir.iterdir()):
                    operation_dir.rmdir()
            if operations.exists() and not any(operations.iterdir()):
                operations.rmdir()

    @staticmethod
    def _batch_manifest_paths_are_safe(*, project_root: Path, operations: Path, manifest: Path, payload: object) -> bool:
        """Return true only when every cleanup path is one this batch owns."""
        if not isinstance(payload, dict):
            return False
        operation_id = payload.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id or manifest.stem != operation_id:
            return False
        operation_root = (operations / operation_id).resolve()
        # Current batch materialization uses assets/imported.  The media roots
        # remain accepted solely for pre-existing project layouts that used the
        # same crash-recovery manifest contract.
        destination_roots = tuple(
            (project_root / relative).resolve()
            for relative in (Path("assets") / "imported", Path("media") / "broll", Path("media") / "bgm", Path("media") / "sfx")
        )
        try:
            operation_root.relative_to(operations.resolve())
            for destination_root in destination_roots:
                destination_root.relative_to(project_root.resolve())
        except ValueError:
            return False
        entries = payload.get("entries")
        if not isinstance(entries, list):
            return False
        for entry in entries:
            if not isinstance(entry, dict):
                return False
            staged_value = entry.get("staged_path")
            destination_value = entry.get("destination_path")
            digest = entry.get("sha256")
            if not isinstance(staged_value, str) or not isinstance(destination_value, str) or not isinstance(digest, str) or not digest:
                return False
            try:
                resolved_staged = Path(staged_value).resolve()
                # Older manifests used a one-file stage directly under the
                # operations root.  Keep recovery compatible, but never allow
                # another operation directory to be claimed.
                if not _is_relative_to(resolved_staged, operation_root) and resolved_staged.parent != operations.resolve():
                    return False
                resolved_destination = Path(destination_value).resolve()
                if not any(_is_relative_to(resolved_destination, root) for root in destination_roots):
                    return False
            except ValueError:
                return False
        return True

    def _batch_destination_is_registered(self, project_id: str, destination: Path, digest: str) -> bool:
        try:
            root = self.project_root(project_id).resolve()
            resolved = destination.resolve()
            if root not in resolved.parents or not digest or not resolved.is_file() or sha256_file(resolved) != digest:
                return False
            uri = self._path_to_uri(project_id, resolved)
            connection = sqlite3.connect(self.database_path(project_id))
            try:
                row = connection.execute("SELECT asset_id FROM assets WHERE project_id = ? AND storage_uri = ?", (project_id, uri)).fetchone()
                return row is not None
            finally:
                connection.close()
        except (OSError, ValueError, sqlite3.Error):
            return False

    def database_path(self, project_id: str) -> Path:
        return self.project_root(project_id) / "db" / "project.sqlite"

    def begin_exact_preview(
        self, *, project_id: str, request: Any, fingerprint: str, duration_sec: float | None = None,
        source_duration_sec: float | None = None,
    ) -> dict[str, Any]:
        """Create or coalesce a durable exact-preview generation.

        This is deliberately storage-only: ffmpeg workers claim and publish a
        generation separately, so a late worker cannot turn an obsolete record
        back into the current artifact.
        """
        session_id = str(request.session_id)
        expected_revision = int(request.expected_revision)
        profile = str(request.profile)
        cache_key = str(request.cache_key(source_fingerprint=fingerprint))
        if request.end_sec is not None and duration_sec is None:
            raise ValueError("exact_preview_duration_required")
        if source_duration_sec is not None:
            request.validate_duration(float(source_duration_sec))
        elif duration_sec is not None:
            request.validate_duration(float(duration_sec))
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute(
                "SELECT session_revision FROM editing_sessions WHERE project_id = ? AND session_id = ?",
                (project_id, session_id),
            ).fetchone()
            if session is None:
                raise KeyError(f"Editing session not found: {session_id}")
            if int(session["session_revision"]) != expected_revision:
                raise EditingSessionRevisionConflict("exact preview session revision is stale")
            existing = connection.execute(
                """SELECT * FROM exact_preview_renders WHERE project_id = ? AND session_id = ?
                   AND cache_key = ? AND state IN ('pending', 'running', 'succeeded')
                   ORDER BY created_at DESC LIMIT 1""",
                (project_id, session_id, cache_key),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._exact_preview_row(dict(existing))
            connection.execute(
                """UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?,
                   invalidated_reason = 'superseded', updated_at = ?
                   WHERE project_id = ? AND session_id = ? AND state IN ('pending', 'running', 'succeeded')""",
                (now, now, project_id, session_id),
            )
            generation_id = f"exact_preview_{uuid.uuid4().hex}"
            connection.execute(
                """INSERT INTO exact_preview_renders (
                    generation_id, project_id, session_id, expected_revision, cache_key, fingerprint,
                    start_sec, end_sec, duration_sec, profile, state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (generation_id, project_id, session_id, expected_revision, cache_key, fingerprint,
                 request.start_sec, request.end_sec, duration_sec, profile, now, now),
            )
            row = connection.execute("SELECT * FROM exact_preview_renders WHERE generation_id = ?", (generation_id,)).fetchone()
            connection.commit()
            return self._exact_preview_row(dict(row))
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def claim_exact_preview(self, *, project_id: str, generation_id: str, owner_token: str) -> bool:
        if not owner_token:
            raise ValueError("exact_preview_claim_token_required")
        connection = self._connection(project_id)
        try:
            now = self._now_iso()
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'running', claim_token = ?, claimed_at = ?, updated_at = ?
                   WHERE project_id = ? AND generation_id = ? AND state = 'pending'""",
                (owner_token, now, now, project_id, generation_id),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def finish_exact_preview(
        self, *, project_id: str, generation_id: str, fingerprint: str, artifact_path: Path, owner_token: str,
        source_fence: Callable[[sqlite3.Connection], bool] | None = None,
        source_fence_result: bool | None = None,
    ) -> bool:
        """Atomically copy/rename then publish only a still-current generation."""
        artifact_path = Path(artifact_path)
        if not owner_token:
            raise ValueError("exact_preview_claim_token_required")
        if not artifact_path.is_file():
            raise FileNotFoundError(artifact_path)
        destination_dir = self.project_root(project_id) / "derived" / "exact_previews"
        destination_dir.mkdir(parents=True, exist_ok=True)
        # Copying a completed proxy can take much longer than a SQLite writer
        # budget.  Stage it under the active generation before BEGIN IMMEDIATE;
        # the transaction below still owns all authoritative CAS/fence checks
        # and the atomic rename which makes the bytes eligible for a pointer.
        generation_token = generation_id.rsplit("_", 1)[-1][-8:]
        temporary = destination_dir / f".ep-{generation_token}-{uuid.uuid4().hex[:6]}.tmp"
        try:
            shutil.copyfile(artifact_path, temporary)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        try:
            connection = self._connection(project_id)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        published: Path | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM exact_preview_renders WHERE project_id = ? AND generation_id = ?", (project_id, generation_id)).fetchone()
            if (
                row is None
                or str(row["fingerprint"]) != fingerprint
                or str(row["state"]) != "running"
                or str(row["claim_token"] or "") != owner_token
            ):
                connection.rollback()
                return False
            current = connection.execute(
                "SELECT session_revision FROM editing_sessions WHERE project_id = ? AND session_id = ?",
                (project_id, str(row["session_id"])),
            ).fetchone()
            if current is None or int(current["session_revision"]) != int(row["expected_revision"]):
                connection.execute("UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?, invalidated_reason = 'session_revision_changed', updated_at = ? WHERE generation_id = ?", (self._now_iso(), self._now_iso(), generation_id))
                connection.commit()
                return False
            published = destination_dir / f"{generation_id}.mp4"
            temporary.replace(published)
            # Revalidate inside the same durable claim transaction after the
            # artifact is staged.  This closes the render->publish handoff:
            # a source changed after the pipeline's first check can never gain
            # an observable succeeded pointer.
            # 울타리가 "소스가 바뀌었다"고 답한 것과 울타리 자체가 터진 것은 다르다.
            # 둘 다 발행하지 않는 것은 같지만 -- 확인하지 못한 것을 현재라고 발행할
            # 수는 없다 -- 남기는 이유는 달라야 한다. 예전에는 터진 경우에도
            # `publish_source_fence_failed`를 적어서, 멀쩡한 소스를 두고 "소스가
            # 바뀌었다"는 기록만 남았고 진짜 원인은 어디에도 없었다.
            invalidated_reason = "publish_source_fence_failed"
            try:
                source_is_current = (
                    (source_fence_result is None or bool(source_fence_result))
                    and (source_fence is None or bool(source_fence(connection)))
                )
            except Exception:
                source_is_current = False
                invalidated_reason = "publish_source_fence_errored"
                _LOGGER.warning(
                    "미리보기를 낼 때 소스 확인이 실패했습니다 (project=%s, generation=%s). "
                    "만들어 둔 영상을 버리고 다시 만들어야 합니다.",
                    project_id,
                    generation_id,
                    exc_info=True,
                )
            if not source_is_current:
                published.unlink(missing_ok=True)
                connection.execute(
                    """UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?,
                       invalidated_reason = ?, updated_at = ?
                       WHERE project_id = ? AND generation_id = ? AND state = 'running' AND claim_token = ?""",
                    (self._now_iso(), invalidated_reason, self._now_iso(), project_id, generation_id, owner_token),
                )
                connection.commit()
                return False
            uri = self._path_to_uri(project_id, published)
            # Fence again after the filesystem publication but before the DB pointer.
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'succeeded', artifact_uri = ?, updated_at = ?
                   WHERE project_id = ? AND generation_id = ? AND fingerprint = ?
                   AND state = 'running' AND claim_token = ?""",
                (uri, self._now_iso(), project_id, generation_id, fingerprint, owner_token),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                published.unlink(missing_ok=True)
                return False
            connection.commit()
            return True
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            if published is not None:
                published.unlink(missing_ok=True)
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            connection.close()

    def get_exact_preview(self, *, project_id: str, generation_id: str) -> dict[str, Any]:
        row = self._fetchone(project_id, "SELECT * FROM exact_preview_renders WHERE project_id = ? AND generation_id = ?", (project_id, generation_id))
        if row is None:
            raise KeyError(f"Exact preview not found: {generation_id}")
        return self._exact_preview_row(dict(row))

    def begin_proposal_preview(self, *, project_id: str, session_id: str, proposal_id: str, expected_revision: int, fingerprint: str) -> dict[str, Any]:
        """Create/coalesce a proposal-result preview in its own durable namespace."""
        cache_key = "proposal-preview:" + hashlib.sha256(
            f"{proposal_id}:{session_id}:{expected_revision}:{fingerprint}".encode()
        ).hexdigest()
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute("SELECT session_revision FROM editing_sessions WHERE project_id = ? AND session_id = ?", (project_id, session_id)).fetchone()
            if session is None:
                raise KeyError(f"Editing session not found: {session_id}")
            if int(session["session_revision"]) != expected_revision:
                raise EditingSessionRevisionConflict("proposal preview session revision is stale")
            existing = connection.execute("""SELECT * FROM proposal_preview_renders WHERE project_id = ? AND session_id = ? AND proposal_id = ? AND cache_key = ? AND state IN ('pending', 'running', 'succeeded') ORDER BY created_at DESC LIMIT 1""", (project_id, session_id, proposal_id, cache_key)).fetchone()
            if existing is not None:
                connection.commit(); return self._exact_preview_row(dict(existing))
            now = self._now_iso()
            generation_id = f"proposal_preview_{uuid.uuid4().hex}"
            connection.execute("""INSERT INTO proposal_preview_renders (generation_id, project_id, session_id, proposal_id, expected_revision, cache_key, fingerprint, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""", (generation_id, project_id, session_id, proposal_id, expected_revision, cache_key, fingerprint, now, now))
            row = connection.execute("SELECT * FROM proposal_preview_renders WHERE generation_id = ?", (generation_id,)).fetchone()
            connection.commit(); return self._exact_preview_row(dict(row))
        except Exception:
            if connection.in_transaction: connection.rollback()
            raise
        finally:
            connection.close()

    def claim_proposal_preview(self, *, project_id: str, generation_id: str, owner_token: str) -> bool:
        return self._proposal_preview_update(project_id=project_id, generation_id=generation_id, owner_token=owner_token, state="running")

    def fail_proposal_preview(self, *, project_id: str, generation_id: str, owner_token: str, error_message: str) -> bool:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("UPDATE proposal_preview_renders SET state = 'failed', error_message = ?, updated_at = ? WHERE project_id = ? AND generation_id = ? AND state = 'running' AND claim_token = ?", (error_message[:1000], self._now_iso(), project_id, generation_id, owner_token)); connection.commit(); return cursor.rowcount == 1
        finally: connection.close()

    def mark_proposal_preview_stale(self, *, project_id: str, generation_id: str, reason: str) -> bool:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("UPDATE proposal_preview_renders SET state = 'obsolete', invalidated_reason = ?, updated_at = ? WHERE project_id = ? AND generation_id = ? AND state IN ('pending', 'running', 'succeeded')", (reason, self._now_iso(), project_id, generation_id)); connection.commit(); return cursor.rowcount == 1
        finally: connection.close()

    def _proposal_preview_update(self, *, project_id: str, generation_id: str, owner_token: str, state: str) -> bool:
        if not owner_token: raise ValueError("proposal_preview_claim_token_required")
        connection = self._connection(project_id)
        try:
            now = self._now_iso()
            cursor = connection.execute("UPDATE proposal_preview_renders SET state = ?, claim_token = ?, claimed_at = ?, updated_at = ? WHERE project_id = ? AND generation_id = ? AND state = 'pending'", (state, owner_token, now, now, project_id, generation_id)); connection.commit(); return cursor.rowcount == 1
        finally: connection.close()

    def finish_proposal_preview(self, *, project_id: str, generation_id: str, fingerprint: str, artifact_path: Path, owner_token: str, source_fence: Callable[[sqlite3.Connection], bool] | None = None, source_fence_result: bool | None = None) -> bool:
        """Stage bytes first, then atomically publish only through the durable fence."""
        if not owner_token: raise ValueError("proposal_preview_claim_token_required")
        if not artifact_path.is_file(): raise FileNotFoundError(artifact_path)
        destination = self.project_root(project_id) / "derived" / "proposal_previews"; destination.mkdir(parents=True, exist_ok=True)
        temporary = destination / f".pp-{generation_id.rsplit('_', 1)[-1][-8:]}-{uuid.uuid4().hex[:6]}.tmp"
        shutil.copyfile(artifact_path, temporary)
        published: Path | None = None
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connection(project_id)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM proposal_preview_renders WHERE project_id = ? AND generation_id = ?", (project_id, generation_id)).fetchone()
            current = connection.execute("SELECT session_revision FROM editing_sessions WHERE project_id = ? AND session_id = ?", (project_id, str(row["session_id"]))).fetchone() if row else None
            source_current = (source_fence_result is None or bool(source_fence_result)) and (source_fence is None or bool(source_fence(connection)))
            if row is not None and not source_current:
                connection.execute("UPDATE proposal_preview_renders SET state = 'obsolete', invalidated_reason = 'publish_source_fence_failed', updated_at = ? WHERE project_id = ? AND generation_id = ? AND state = 'running' AND claim_token = ?", (self._now_iso(), project_id, generation_id, owner_token)); connection.commit(); return False
            if row is None or str(row["state"]) != "running" or str(row["claim_token"] or "") != owner_token or str(row["fingerprint"]) != fingerprint or current is None or int(current["session_revision"]) != int(row["expected_revision"]) or not source_current:
                if row is not None and current is not None and int(current["session_revision"]) != int(row["expected_revision"]):
                    connection.execute("UPDATE proposal_preview_renders SET state = 'obsolete', invalidated_reason = 'session_revision_changed', updated_at = ? WHERE project_id = ? AND generation_id = ?", (self._now_iso(), project_id, generation_id))
                    connection.commit()
                else:
                    connection.rollback()
                return False
            published = destination / f"{generation_id}.mp4"
            temporary.replace(published)
            cursor = connection.execute("UPDATE proposal_preview_renders SET state = 'succeeded', artifact_uri = ?, updated_at = ? WHERE project_id = ? AND generation_id = ? AND state = 'running' AND claim_token = ?", (self._path_to_uri(project_id, published), self._now_iso(), project_id, generation_id, owner_token))
            if cursor.rowcount != 1:
                connection.rollback(); published.unlink(missing_ok=True); return False
            connection.commit(); return True
        except Exception:
            if connection is not None and connection.in_transaction: connection.rollback()
            if published is not None: published.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)
            if connection is not None: connection.close()

    def get_proposal_preview(self, *, project_id: str, generation_id: str) -> dict[str, Any]:
        row = self._fetchone(project_id, "SELECT * FROM proposal_preview_renders WHERE project_id = ? AND generation_id = ?", (project_id, generation_id))
        if row is None: raise KeyError(f"Proposal preview not found: {generation_id}")
        return self._exact_preview_row(dict(row))

    def recover_stale_proposal_preview_claims(self, *, project_id: str, older_than_seconds: float = 900) -> int:
        """Retire both a worker that died mid-render and a row whose worker
        thread never even started (the process died right after ``pending``
        was written, before any claim). Neither is reachable through the
        restart-epoch fence, since that only rewrites ``running`` rows owned
        by a stale process token -- an unclaimed ``pending`` row has none."""
        cutoff = (self._clock() - timedelta(seconds=older_than_seconds)).isoformat()
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("""UPDATE proposal_preview_renders SET state = 'failed', error_message = 'stale_running_claim', updated_at = ? WHERE project_id = ? AND state = 'running' AND claimed_at < ?""", (self._now_iso(), project_id, cutoff))
            pending_cursor = connection.execute("""UPDATE proposal_preview_renders SET state = 'failed', error_message = 'stale_pending_claim', updated_at = ? WHERE project_id = ? AND state = 'pending' AND created_at < ?""", (self._now_iso(), project_id, cutoff))
            connection.commit()
            return cursor.rowcount + pending_cursor.rowcount
        finally:
            connection.close()

    def recover_inherited_proposal_preview_claims(self, *, project_id: str, process_epoch: str) -> int:
        if not process_epoch:
            raise ValueError("proposal_preview_process_epoch_required")
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("""UPDATE proposal_preview_renders SET state = 'failed', error_message = 'process_restarted', updated_at = ? WHERE project_id = ? AND state = 'running' AND (claim_token IS NULL OR claim_token NOT LIKE ?)""", (self._now_iso(), project_id, f"proposal-preview-worker:{process_epoch}:%"))
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def cleanup_proposal_preview_artifacts(self, *, project_id: str, keep_last: int = 5, orphan_older_than_seconds: float = 300) -> int:
        """Prune proposal-preview terminal rows and renderer-owned orphans only."""
        rows = self._fetchall(project_id, "SELECT generation_id, artifact_uri FROM proposal_preview_renders WHERE project_id = ? AND state IN ('obsolete', 'failed') ORDER BY updated_at DESC", (project_id,))
        removed = 0
        for row in rows[max(keep_last, 0):]:
            uri = row["artifact_uri"]
            if uri:
                self.resolve_storage_uri(project_id=project_id, storage_uri=str(uri)).unlink(missing_ok=True)
            self._execute(project_id, "DELETE FROM proposal_preview_renders WHERE project_id = ? AND generation_id = ?", (project_id, str(row["generation_id"])))
            removed += 1
        preview_root = self.project_root(project_id) / "derived" / "proposal_previews"
        if not preview_root.is_dir():
            return removed
        referenced = {self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["artifact_uri"])).resolve() for row in self._fetchall(project_id, "SELECT artifact_uri FROM proposal_preview_renders WHERE project_id = ? AND artifact_uri IS NOT NULL", (project_id,))}
        active_generation_ids = {str(row["generation_id"]) for row in self._fetchall(project_id, "SELECT generation_id FROM proposal_preview_renders WHERE project_id = ? AND state IN ('pending', 'running')", (project_id,))}
        root = preview_root.resolve()
        cutoff = self._clock().timestamp() - orphan_older_than_seconds
        for candidate in preview_root.iterdir():
            try:
                resolved = candidate.resolve()
                if not _is_relative_to(resolved, root) or resolved in referenced or not candidate.is_file():
                    continue
                if not ((candidate.name.startswith("proposal_preview_") and candidate.suffix == ".mp4") or candidate.name.startswith(".proposal_preview_") or candidate.name.startswith(".pp-")):
                    continue
                if any(candidate.name == f"{generation_id}.mp4" or candidate.name.startswith(f".{generation_id}.") or candidate.name.startswith(f".pp-{generation_id.rsplit('_', 1)[-1][-8:]}-") for generation_id in active_generation_ids):
                    continue
                if candidate.stat().st_mtime > cutoff:
                    continue
                candidate.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    def get_latest_exact_preview(self, *, project_id: str, session_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            project_id,
            """SELECT * FROM exact_preview_renders WHERE project_id = ? AND session_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (project_id, session_id),
        )
        return self._exact_preview_row(dict(row)) if row is not None else None

    def mark_exact_preview_stale(self, *, project_id: str, generation_id: str, reason: str) -> bool:
        """Invalidate a durable preview after read-time source/revision validation."""
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?,
                   invalidated_reason = ?, updated_at = ?
                   WHERE project_id = ? AND generation_id = ?
                   AND state IN ('pending', 'running', 'succeeded')""",
                (self._now_iso(), reason, self._now_iso(), project_id, generation_id),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def fail_exact_preview(self, *, project_id: str, generation_id: str, owner_token: str, error_message: str) -> bool:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'failed', error_message = ?, updated_at = ?
                   WHERE project_id = ? AND generation_id = ? AND state = 'running' AND claim_token = ?""",
                (error_message[:1000], self._now_iso(), project_id, generation_id, owner_token),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def recover_stale_exact_preview_claims(self, *, project_id: str, older_than_seconds: float = 900) -> int:
        cutoff = (self._clock() - timedelta(seconds=older_than_seconds)).isoformat()
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'failed', error_message = 'stale_running_claim',
                   updated_at = ? WHERE project_id = ? AND state = 'running' AND claimed_at < ?""",
                (self._now_iso(), project_id, cutoff),
            )
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def recover_inherited_exact_preview_claims(self, *, project_id: str, process_epoch: str) -> int:
        """Fence off running claims owned by a previous local API process."""
        if not process_epoch:
            raise ValueError("exact_preview_process_epoch_required")
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'failed', error_message = 'process_restarted',
                   updated_at = ?
                   WHERE project_id = ? AND state = 'running'
                   AND (claim_token IS NULL OR claim_token NOT LIKE ?)""",
                (self._now_iso(), project_id, f"exact-preview-worker:{process_epoch}:%"),
            )
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def retry_exact_preview(self, *, project_id: str, generation_id: str) -> dict[str, Any]:
        row = self.get_exact_preview(project_id=project_id, generation_id=generation_id)
        if str(row["state"]) != "failed":
            raise ValueError("exact_preview_retry_not_failed")
        request = ExactPreviewRequest(
            session_id=str(row["session_id"]), expected_revision=int(row["expected_revision"]),
            start_sec=row["start_sec"], end_sec=row["end_sec"], profile=str(row["profile"]),
        )
        duration_sec = row.get("duration_sec")
        if request.end_sec is not None and duration_sec is None:
            raise ValueError("exact_preview_duration_required")
        if duration_sec is not None:
            request.validate_duration(float(duration_sec))
        # Failed rows must not coalesce with a retry; a distinct cache identity
        # makes generation ownership explicit while preserving the source fence.
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?,
                   invalidated_reason = 'retry', updated_at = ?
                   WHERE project_id = ? AND generation_id = ? AND state = 'failed'""",
                (self._now_iso(), self._now_iso(), project_id, generation_id),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise ValueError("exact_preview_retry_not_failed")
            connection.commit()
        finally:
            connection.close()
        return self.begin_exact_preview(
            project_id=project_id, request=request, fingerprint=str(row["fingerprint"]), duration_sec=duration_sec
        )

    def cleanup_exact_preview_artifacts(
        self, *, project_id: str, keep_last: int = 5, orphan_older_than_seconds: float = 300
    ) -> int:
        """Prune retained stale rows and crash-orphaned files inside this project only."""
        rows = self._fetchall(project_id, "SELECT generation_id, artifact_uri FROM exact_preview_renders WHERE project_id = ? AND state IN ('obsolete', 'failed') ORDER BY updated_at DESC", (project_id,))
        removed = 0
        for row in rows[max(keep_last, 0):]:
            uri = row["artifact_uri"]
            if uri:
                self.resolve_storage_uri(project_id=project_id, storage_uri=str(uri)).unlink(missing_ok=True)
            self._execute(project_id, "DELETE FROM exact_preview_renders WHERE project_id = ? AND generation_id = ?", (project_id, str(row["generation_id"])))
            removed += 1
        preview_root = self.project_root(project_id) / "derived" / "exact_previews"
        if not preview_root.is_dir():
            return removed
        referenced = {
            self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["artifact_uri"])).resolve()
            for row in self._fetchall(
                project_id,
                "SELECT artifact_uri FROM exact_preview_renders WHERE project_id = ? AND artifact_uri IS NOT NULL",
                (project_id,),
            )
        }
        active_generation_ids = {
            str(row["generation_id"])
            for row in self._fetchall(
                project_id,
                "SELECT generation_id FROM exact_preview_renders WHERE project_id = ? AND state IN ('pending', 'running')",
                (project_id,),
            )
        }
        root = preview_root.resolve()
        cutoff = self._clock().timestamp() - orphan_older_than_seconds
        for candidate in preview_root.iterdir():
            try:
                resolved = candidate.resolve()
                if not _is_relative_to(resolved, root) or resolved in referenced or not candidate.is_file():
                    continue
                # Only this renderer's published names and atomic temporary
                # names are eligible; unrelated derived files are untouched.
                if (
                    not (candidate.name.startswith("exact_preview_") and candidate.suffix == ".mp4")
                    and not candidate.name.startswith(".exact_preview_")
                    and not candidate.name.startswith(".ep-")
                ):
                    continue
                # finish_exact_preview publishes `.ep-<short-generation>-<nonce>.tmp`
                # then `<generation>.mp4` before its fenced DB pointer update.
                # Those files are deliberately unreferenced during that small
                # window, so an active claim is an ownership fence for cleanup.
                if any(
                    candidate.name == f"{generation_id}.mp4"
                    or candidate.name.startswith(f".{generation_id}.")
                    or candidate.name.startswith(f".ep-{generation_id.rsplit('_', 1)[-1][-8:]}-")
                    for generation_id in active_generation_ids
                ):
                    continue
                if candidate.stat().st_mtime > cutoff:
                    continue
                candidate.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    @staticmethod
    def _exact_preview_row(row: dict[str, Any]) -> dict[str, Any]:
        row["start_sec"] = float(row["start_sec"]) if row.get("start_sec") is not None else None
        row["end_sec"] = float(row["end_sec"]) if row.get("end_sec") is not None else None
        row["duration_sec"] = float(row["duration_sec"]) if row.get("duration_sec") is not None else None
        row["expected_revision"] = int(row["expected_revision"])
        return row

    def thumbnail_storage_path(self, *, project_id: str, asset_id: str) -> Path:
        return self.project_root(project_id) / "derived" / "thumbnails" / f"{asset_id}.jpg"

    def waveform_storage_path(self, *, project_id: str, asset_id: str) -> Path:
        # 썸네일 옆에 둔다. 둘 다 원본에서 다시 만들 수 있는 파생물이라 같은
        # `derived/` 아래에 있어야 정리 규칙(§10.16)이 함께 적용된다.
        return self.project_root(project_id) / "derived" / "waveforms" / f"{asset_id}.png"

    def thumbnail_storage_uri(self, *, project_id: str, asset_id: str) -> str:
        return self._path_to_uri(project_id, self.thumbnail_storage_path(project_id=project_id, asset_id=asset_id))

    def get_project(self, *, project_id: str) -> dict[str, Any]:
        # A deleted/never-existing project's per-project sqlite file has no
        # parent directory, so sqlite3.connect() itself raises
        # OperationalError here (LocalProjectStore only) rather than the
        # query simply returning no row (which is all that happens on
        # Postgres's single shared database). Normalize both to KeyError.
        try:
            row = self._fetchone(
                project_id,
                """
                SELECT project_id, name, status, root_storage_uri, created_at, updated_at
                FROM projects
                WHERE project_id = ?
                """,
                (project_id,),
            )
        except sqlite3.OperationalError:
            raise KeyError(f"Project not found: {project_id}") from None
        if row is None:
            raise KeyError(f"Project not found: {project_id}")
        return dict(row)

    def create_creation_brief(
        self,
        *,
        project_id: str,
        script_filename: str,
        script_text: str,
        idempotency_key: str,
        capability_profile: dict[str, Any],
        script_asset_id: str | None = None,
        runtime: CreationInterviewRuntime | None = None,
    ) -> dict[str, Any]:
        """Persist a local-only interview before any optional provider exists."""
        self._validate_creation_brief_input(
            script_filename=script_filename, script_text=script_text, idempotency_key=idempotency_key
        )
        existing = self._fetchone(
            project_id, "SELECT * FROM creation_briefs WHERE project_id = ? AND idempotency_key = ?", (project_id, idempotency_key)
        )
        if existing is not None:
            return self._creation_brief_payload(existing)
        owned_script_asset = script_asset_id is None
        if script_asset_id is None:
            script_asset_id = self._materialize_creation_brief_script(
                project_id=project_id, script_filename=script_filename, script_text=script_text
            )
        else:
            asset = self.get_asset(project_id=project_id, asset_id=script_asset_id)
            if asset["asset_type"] != AssetType.SCRIPT_DOCUMENT.value:
                raise ValueError("creation_brief_script_asset_invalid")
        planner = runtime or DeterministicCreationInterviewRuntime()
        try:
            questions = self._normalize_creation_interview_questions(
                planner.plan_questions(script_text=script_text)
            )
        except Exception:
            if owned_script_asset and script_asset_id:
                self.delete_asset(project_id=project_id, asset_id=script_asset_id)
            raise
        now = self._clock().isoformat()
        brief_id = f"brief-{uuid.uuid4().hex}"
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM creation_briefs WHERE project_id = ? AND idempotency_key = ?",
                (project_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                connection.commit()
                payload = self._creation_brief_payload(existing)
                # A competing request may have materialized its retained
                # input while waiting for the idempotency-row lock. It never
                # became part of the winning brief, so remove it before
                # returning the durable winner.
                if owned_script_asset and script_asset_id:
                    connection.close()
                    self.delete_asset(project_id=project_id, asset_id=script_asset_id)
                return payload
            connection.execute(
                """
                INSERT INTO creation_briefs (
                    brief_id, project_id, idempotency_key, script_filename, script_text,
                    script_asset_id, script_asset_owned, capability_profile_json, questions_json, answers_json,
                    current_step, status, revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', 0, 'interviewing', 1, ?, ?)
                """,
                (
                    brief_id, project_id, idempotency_key, script_filename, script_text,
                    script_asset_id, int(owned_script_asset), json.dumps(capability_profile, ensure_ascii=False, sort_keys=True),
                    json.dumps(questions, ensure_ascii=False), now, now,
                ),
            )
            row = connection.execute("SELECT * FROM creation_briefs WHERE brief_id = ?", (brief_id,)).fetchone()
            connection.commit()
            return self._creation_brief_payload(row)
        except sqlite3.IntegrityError:
            connection.rollback()
            existing = self._fetchone(
                project_id, "SELECT * FROM creation_briefs WHERE project_id = ? AND idempotency_key = ?", (project_id, idempotency_key)
            )
            if owned_script_asset and script_asset_id:
                self.delete_asset(project_id=project_id, asset_id=script_asset_id)
            if existing is None:
                raise
            return self._creation_brief_payload(existing)
        except Exception:
            connection.rollback()
            if owned_script_asset and script_asset_id:
                self.delete_asset(project_id=project_id, asset_id=script_asset_id)
            raise
        finally:
            connection.close()

    def get_creation_brief(self, *, project_id: str, brief_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            "SELECT * FROM creation_briefs WHERE project_id = ? AND brief_id = ?",
            (project_id, brief_id),
        )
        if row is None:
            raise KeyError(f"Creation brief not found: {brief_id}")
        return self._creation_brief_payload(row)

    def list_creation_briefs(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                "SELECT * FROM creation_briefs WHERE project_id = ? ORDER BY created_at DESC, brief_id DESC",
                (project_id,),
            ).fetchall()
            return [self._creation_brief_payload(row) for row in rows]
        finally:
            connection.close()

    def answer_creation_brief_question(
        self, *, project_id: str, brief_id: str, question_id: str, answer: str, expected_revision: int
    ) -> dict[str, Any]:
        normalized = answer.strip()
        if not normalized:
            raise ValueError("creation_brief_answer_required")
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM creation_briefs WHERE project_id = ? AND brief_id = ?", (project_id, brief_id)
            ).fetchone()
            if row is None:
                raise KeyError(f"Creation brief not found: {brief_id}")
            self._assert_creation_brief_mutable(row)
            if int(row["revision"]) != expected_revision:
                raise ValueError("creation_brief_revision_conflict")
            if row["status"] != "interviewing":
                raise ValueError("creation_brief_not_interviewing")
            questions = json.loads(row["questions_json"])
            question = next((item for item in questions if item["question_id"] == question_id), None)
            if question is None:
                raise ValueError("creation_brief_question_not_found")
            if questions[int(row["current_step"])]["question_id"] != question_id:
                raise ValueError("creation_brief_question_not_current")
            answers = json.loads(row["answers_json"])
            answers[question["field"]] = normalized
            # The cursor advances from the question just answered.  Counting all
            # saved answers would skip a question after the creator returns to
            # revise an earlier answer.
            current_step = questions.index(question) + 1
            status = "ready_for_approval" if current_step == len(questions) else "interviewing"
            connection.execute(
                """UPDATE creation_briefs
                   SET answers_json = ?, current_step = ?, status = ?, revision = revision + 1, updated_at = ?
                   WHERE project_id = ? AND brief_id = ?""",
                (json.dumps(answers, ensure_ascii=False, sort_keys=True), current_step, status, self._clock().isoformat(), project_id, brief_id),
            )
            updated = connection.execute("SELECT * FROM creation_briefs WHERE brief_id = ?", (brief_id,)).fetchone()
            connection.commit()
            return self._creation_brief_payload(updated)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def bypass_creation_interview(
        self, *, project_id: str, brief_id: str, expected_revision: int | None = None
    ) -> dict[str, Any]:
        """Make the explicit manual choice durable; approval remains separate."""
        return self._mutate_creation_brief(
            project_id=project_id, brief_id=brief_id, expected_revision=expected_revision,
            mutation=lambda row: (
                {item["field"]: json.loads(row["answers_json"]).get(item["field"], "건너뛰기") for item in json.loads(row["questions_json"])},
                len(json.loads(row["questions_json"])), "ready_for_approval", row["summary_text"],
            ),
        )

    def previous_creation_brief_question(
        self, *, project_id: str, brief_id: str, expected_revision: int
    ) -> dict[str, Any]:
        """Return to the prior durable question without discarding saved answers.

        A changed answer can alter the generated summary, so any earlier summary is
        cleared and must be reviewed again before approval.
        """
        def previous(row: sqlite3.Row) -> tuple[dict[str, str], int, str, str]:
            questions = json.loads(row["questions_json"])
            current_step = int(row["current_step"])
            if current_step <= 0 or not questions:
                raise ValueError("creation_brief_previous_question_unavailable")
            return (
                json.loads(row["answers_json"]),
                min(current_step - 1, len(questions) - 1),
                "interviewing",
                "",
            )

        return self._mutate_creation_brief(
            project_id=project_id,
            brief_id=brief_id,
            expected_revision=expected_revision,
            mutation=previous,
        )

    def update_creation_brief_summary(
        self, *, project_id: str, brief_id: str, summary: str, expected_revision: int
    ) -> dict[str, Any]:
        if not summary.strip():
            raise ValueError("creation_brief_summary_required")
        return self._mutate_creation_brief(
            project_id=project_id, brief_id=brief_id, expected_revision=expected_revision,
            mutation=lambda row: (json.loads(row["answers_json"]), row["current_step"], "ready_for_approval", summary.strip()),
        )

    def approve_creation_brief(self, *, project_id: str, brief_id: str, expected_revision: int) -> dict[str, Any]:
        return self._mutate_creation_brief(
            project_id=project_id, brief_id=brief_id, expected_revision=expected_revision,
            mutation=lambda row: self._creation_brief_approval_mutation(row),
        )

    @staticmethod
    def _creation_brief_approval_mutation(row: sqlite3.Row) -> tuple[dict[str, str], int, str, str]:
        if str(row["status"]) != "ready_for_approval":
            raise ValueError("creation_brief_not_ready_for_approval")
        if not str(row["summary_text"]).strip():
            raise ValueError("creation_brief_summary_required")
        return json.loads(row["answers_json"]), int(row["current_step"]), "approved", str(row["summary_text"])

    def _mutate_creation_brief(
        self, *, project_id: str, brief_id: str, expected_revision: int | None,
        mutation: Callable[[sqlite3.Row], tuple[dict[str, str], int, str, str]],
    ) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM creation_briefs WHERE project_id = ? AND brief_id = ?", (project_id, brief_id)).fetchone()
            if row is None:
                raise KeyError(f"Creation brief not found: {brief_id}")
            self._assert_creation_brief_mutable(row)
            if expected_revision is not None and int(row["revision"]) != expected_revision:
                raise ValueError("creation_brief_revision_conflict")
            answers, current_step, status, summary = mutation(row)
            connection.execute(
                """UPDATE creation_briefs SET answers_json = ?, current_step = ?, status = ?, summary_text = ?,
                   revision = revision + 1, updated_at = ? WHERE project_id = ? AND brief_id = ?""",
                (json.dumps(answers, ensure_ascii=False, sort_keys=True), current_step, status, summary, self._clock().isoformat(), project_id, brief_id),
            )
            updated = connection.execute("SELECT * FROM creation_briefs WHERE brief_id = ?", (brief_id,)).fetchone()
            connection.commit()
            return self._creation_brief_payload(updated)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _assert_creation_brief_mutable(row: sqlite3.Row) -> None:
        if row["status"] == "approved":
            raise ValueError("creation_brief_immutable")

    def delete_creation_brief(self, *, project_id: str, brief_id: str) -> None:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT script_asset_id, script_asset_owned FROM creation_briefs WHERE project_id = ? AND brief_id = ?", (project_id, brief_id)
            ).fetchone()
            cursor = connection.execute(
                "DELETE FROM creation_briefs WHERE project_id = ? AND brief_id = ?", (project_id, brief_id)
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Creation brief not found: {brief_id}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if row is not None and bool(row["script_asset_owned"]) and row["script_asset_id"]:
            self.delete_asset(project_id=project_id, asset_id=str(row["script_asset_id"]))

    def _materialize_creation_brief_script(self, *, project_id: str, script_filename: str, script_text: str) -> str:
        directory = self.project_root(project_id) / "staging" / "creation_briefs"
        directory.mkdir(parents=True, exist_ok=True)
        staging = directory / f"{uuid.uuid4().hex}{Path(script_filename).suffix.lower()}"
        try:
            staging.write_text(script_text, encoding="utf-8")
            asset = self.register_asset(
                project_id=project_id, asset_type=AssetType.SCRIPT_DOCUMENT, source_path=staging,
                source_kind="creation_brief_retained_input", mime_type="text/plain",
            )
            return asset.asset_id
        finally:
            staging.unlink(missing_ok=True)

    @staticmethod
    def _validate_creation_brief_input(*, script_filename: str, script_text: str, idempotency_key: str) -> None:
        if Path(script_filename).suffix.lower() not in {".txt", ".md", ".srt"}:
            raise ValueError("creation_brief_script_extension_invalid")
        if not idempotency_key.strip():
            raise ValueError("creation_brief_idempotency_key_required")
        if not script_text.strip():
            raise ValueError("creation_brief_script_empty")
        try:
            size = len(script_text.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValueError("creation_brief_script_not_utf8") from exc
        if size > 1024 * 1024:
            raise ValueError("creation_brief_script_too_large")

    @staticmethod
    def _normalize_creation_interview_questions(items: object) -> list[dict[str, str]]:
        if not isinstance(items, list):
            raise ValueError("creation_brief_questions_invalid")
        if len(items) > MAX_CREATION_INTERVIEW_QUESTIONS:
            raise ValueError("creation_brief_questions_too_many")
        normalized: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        seen_fields: set[str] = set()
        for index, item in enumerate(items):
            field = str(getattr(item, "field", "")).strip()
            prompt = str(getattr(item, "prompt", "")).strip()
            provided_id = getattr(item, "question_id", None)
            question_id = f"question-{index + 1}" if provided_id is None else str(provided_id).strip()
            if not field or not prompt:
                raise ValueError("creation_brief_question_invalid")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", question_id):
                raise ValueError("creation_brief_question_id_invalid")
            if question_id in seen_ids:
                raise ValueError("creation_brief_question_id_duplicate")
            if field in seen_fields:
                raise ValueError("creation_brief_question_field_duplicate")
            seen_ids.add(question_id)
            seen_fields.add(field)
            normalized.append({"question_id": question_id, "field": field, "prompt": prompt})
        return normalized

    @staticmethod
    def _creation_brief_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "brief_id": row["brief_id"], "project_id": row["project_id"],
            "idempotency_key": row["idempotency_key"], "script_filename": row["script_filename"],
            "script_text": row["script_text"], "script_asset_id": row["script_asset_id"], "script_asset_owned": bool(row["script_asset_owned"]),
            "capability_profile": json.loads(row["capability_profile_json"]),
            "questions": json.loads(row["questions_json"]), "answers": json.loads(row["answers_json"]),
            "current_step": row["current_step"], "status": row["status"], "summary": row["summary_text"], "revision": row["revision"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    @staticmethod
    def _draft_readiness_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "readiness_id": row["readiness_id"], "project_id": row["project_id"], "brief_id": row["brief_id"],
            "approved_brief_revision": row["approved_brief_revision"], "input_fingerprint": row["input_fingerprint"],
            "narration": json.loads(row["narration_json"]), "capability": json.loads(row["capability_json"]),
            "idempotency_key": row["idempotency_key"], "status": row["status"], "revision": row["revision"],
            "cancel_requested": bool(row["cancel_requested"]), "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error_code": row["error_code"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def _probe_playable_broll_duration(self, *, project_id: str, asset: dict[str, Any]) -> float | None:
        path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
        if not path.is_file() or shutil.which("ffprobe") is None:
            return None
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            probe = json.loads(result.stdout) if result.returncode == 0 else {}
            duration_sec = float((probe.get("format") or {}).get("duration"))
            has_video = any(stream.get("codec_type") == "video" for stream in probe.get("streams") or [])
            return duration_sec if has_video and math.isfinite(duration_sec) and duration_sec > 0 else None
        except (OSError, subprocess.SubprocessError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _pair_broll_with_segments(
        *,
        segments: list[dict[str, Any]],
        playable_broll: list[tuple[dict[str, Any], float]],
    ) -> list[tuple[dict[str, Any], tuple[dict[str, Any], float]]]:
        """어느 장면에 무엇을 붙일지 정한다.

        촬영본은 어느 장면 것인지 아무도 적어 두지 않았으므로 **순서**가 유일한
        규칙이었고, 그래서 오래도록 `zip(segments, playable_broll)` 한 줄이었다.

        만든 그림은 다르다 -- 3번째 장면을 보고 만든 그림은 3번째 장면 것이다
        (`scene_image_service.py`가 `scene_segment_id`를 적어 둔다). 짝이 정해진
        것이 먼저 자리를 잡고, 나머지가 남은 자리를 앞에서부터 채운다.

        짝이 있다고 적혀 있는데 그 장면이 사라졌으면(대본을 고치면 그렇게 된다)
        **버리지 않고** 짝 없는 것과 똑같이 취급한다. 만든 것이 조용히 없어지면
        owner는 어디로 갔는지 알 수 없다.
        """
        segment_index = {str(segment["segment_id"]): index for index, segment in enumerate(segments)}
        pinned: dict[int, tuple[dict[str, Any], float]] = {}
        unpinned: list[tuple[dict[str, Any], float]] = []
        for item, duration_sec in playable_broll:
            wanted = str((item.get("metadata") or {}).get("scene_segment_id") or "")
            index = segment_index.get(wanted)
            if index is None or index in pinned:
                unpinned.append((item, duration_sec))
                continue
            pinned[index] = (item, duration_sec)
        remaining = iter(unpinned)
        paired: list[tuple[dict[str, Any], tuple[dict[str, Any], float]]] = []
        for index, segment in enumerate(segments):
            chosen = pinned.get(index) or next(remaining, None)
            if chosen is not None:
                paired.append((segment, chosen))
        return paired

    @staticmethod
    def _candidate_range_is_usable(candidate: dict[str, Any], duration_sec: float) -> bool:
        target_range = candidate.get("target_range") or {}
        try:
            start_sec, end_sec = float(target_range.get("start_sec")), float(target_range.get("end_sec"))
        except (TypeError, ValueError):
            return False
        return math.isfinite(start_sec) and math.isfinite(end_sec) and 0 <= start_sec < end_sec <= duration_sec

    def _draft_readiness_sources_match(self, *, project_id: str, result: dict[str, Any]) -> bool:
        try:
            for item in result.get("source_snapshot") or []:
                asset = self.get_asset(project_id=project_id, asset_id=str(item["asset_id"]))
                path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
                if not path.is_file() or sha256_file(path) != item.get("sha256"):
                    return False
        except (KeyError, TypeError, ValueError, OSError):
            return False
        return True

    def _normalize_draft_readiness_result(self, *, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._draft_readiness_sources_match(project_id=project_id, result=payload["result"]):
            return payload["result"]
        try:
            brief = self.get_creation_brief(project_id=project_id, brief_id=str(payload["brief_id"]))
            planned = self._draft_readiness_plan(project_id=project_id, brief=brief, narration=dict(payload["narration"]))
        except (KeyError, ValueError, TypeError):
            return payload["result"]
        existing = {str(item.get("asset_id")): item for item in payload["result"].get("broll_candidates", []) if isinstance(item, dict)}
        candidates = []
        for item in planned["broll_candidates"]:
            restored = deepcopy(item)
            previous = existing.get(str(item["asset_id"]))
            if previous and self._candidate_range_is_usable(previous, float(item["media_duration_sec"])):
                restored["target_range"] = deepcopy(previous["target_range"])
                restored["skipped"] = bool(previous.get("skipped"))
            candidates.append(restored)
        result = deepcopy(payload["result"])
        result["broll_candidates"] = candidates
        if candidates != payload["result"].get("broll_candidates", []) or (not result.get("gap_slots") and planned["gap_slots"]):
            result["gap_slots"] = planned["gap_slots"]
        result["source_snapshot"] = planned["source_snapshot"]
        return result

    def script_segments_for_narration(
        self,
        *,
        project_id: str,
        narration_asset_id: str | None,
        sentences: list[str],
    ) -> list[dict[str, Any]]:
        """Time each script sentence, following the recording when there is one.

        Every sentence used to get exactly five seconds whether or not the
        owner had recorded anything, so the captions in a narrated draft never
        landed where the words did. When a transcript exists for the chosen
        narration, its spoken stretches supply the bounds; a sentence the
        recording does not reach keeps its place on the provisional grid.
        """
        spoken: list[dict[str, Any]] = []
        if narration_asset_id:
            row = self._fetchone(
                project_id,
                "SELECT segments_json FROM transcripts WHERE project_id = ? AND source_asset_id = ? "
                "ORDER BY created_at DESC, transcript_id DESC LIMIT 1",
                (project_id, narration_asset_id),
            )
            if row is not None:
                try:
                    parsed = json.loads(str(row["segments_json"]))
                except (TypeError, ValueError):
                    parsed = []
                spoken = [item for item in parsed if isinstance(item, dict)]
        segments: list[dict[str, Any]] = []
        for index, text in enumerate(sentences):
            if index < len(spoken):
                start = float(spoken[index].get("start_sec") or 0.0)
                end = float(spoken[index].get("end_sec") or 0.0)
                if end > start:
                    segments.append({"segment_id": f"script-{index + 1}", "text": text, "start_sec": start, "end_sec": end})
                    continue
            segments.append({"segment_id": f"script-{index + 1}", "text": text, "start_sec": index * 5, "end_sec": (index + 1) * 5})
        return segments

    def _scene_windows_for_asset(self, *, project_id: str, asset_id: str) -> list[dict[str, Any]]:
        """Scene windows from this asset's most recent analysis that has any.

        Re-analysis writes a fresh set, so the newest non-empty run wins; an
        asset that was never analyzed simply yields none and the caller falls
        back to the head of the clip.
        """
        analyses = [
            analysis
            for analysis in self.list_media_analysis(project_id=project_id)
            if str(analysis["asset_id"]) == asset_id
        ]
        for analysis in reversed(analyses):
            windows = self.list_media_scene_windows(
                project_id=project_id, analysis_id=str(analysis["analysis_id"])
            )
            if windows:
                return windows
        return []

    def _draft_readiness_plan(self, *, project_id: str, brief: dict[str, Any], narration: dict[str, Any]) -> dict[str, Any]:
        sentences = [value.strip() for value in re.split(r"[.!?\n]+", str(brief["script_text"])) if value.strip()]
        segments = self.script_segments_for_narration(
            project_id=project_id,
            narration_asset_id=str(narration.get("asset_id") or "") or None,
            sentences=sentences or [str(brief["script_text"]).strip()],
        )
        assets = self.list_assets(project_id=project_id)
        playable_broll = [(item, self._probe_playable_broll_duration(project_id=project_id, asset=item)) for item in assets if item["asset_type"] == AssetType.BROLL_VIDEO.value]
        playable_broll = [(item, duration_sec) for item, duration_sec in playable_broll if duration_sec is not None]
        broll = []
        for index, (segment, (item, duration_sec)) in enumerate(
            self._pair_broll_with_segments(segments=segments, playable_broll=playable_broll)
        ):
            # Task 23: a ten-minute take is not usable from its first five
            # seconds, so pick a settled scene window when analysis found one.
            # Falls back to the head of the clip for unanalyzed footage.
            target_range = choose_broll_source_window(
                duration_sec=duration_sec,
                needed_sec=float(segment["end_sec"]) - float(segment["start_sec"]),
                scene_windows=self._scene_windows_for_asset(project_id=project_id, asset_id=str(item["asset_id"])),
            )
            broll.append({"asset_id": item["asset_id"], "rank": index + 1, "label": item["metadata"].get("title") or f"장면 영상 {index + 1}", "segment_id": segment["segment_id"], "target_range": target_range, "media_duration_sec": duration_sec, "media_type": "broll_video", "selection": item["asset_id"], "skipped": False})
        def choice(asset_type: AssetType, label: str) -> dict[str, Any]:
            item = next((asset for asset in assets if asset["asset_type"] == asset_type.value), None)
            return {"selection": item["asset_id"], "reason": "프로젝트 자산에서 골랐어요."} if item else {"selection": None, "reason": f"프로젝트에 사용할 {label}이 없어요."}
        covered_segment_ids = {str(item["segment_id"]) for item in broll}
        gaps = [
            {"gap_slot_id": f"gap-broll-{index + 1}", "segment_id": segment["segment_id"], "reason": "장면을 보여 줄 영상이 없어요.", "target_range": {"start_sec": segment["start_sec"], "end_sec": segment["end_sec"]}, "media_type": "broll_video"}
            for index, segment in enumerate(segments)
            if str(segment["segment_id"]) not in covered_segment_ids
        ]
        selected_ids = [brief.get("script_asset_id"), narration.get("asset_id")] + [item["asset_id"] for item in broll]
        snapshots = []
        for asset_id in dict.fromkeys(str(item) for item in selected_ids if item):
            asset = self.get_asset(project_id=project_id, asset_id=asset_id)
            path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
            if not path.is_file(): raise ValueError("draft_readiness_source_missing")
            snapshots.append({"asset_id": asset_id, "sha256": sha256_file(path), "media_revision": asset["created_at"], "asset_type": asset["asset_type"]})
        return {"script_segments": segments, "caption_texts": [item["text"] for item in segments], "narration": narration,
                "broll_candidates": broll, "bgm": choice(AssetType.BGM, "배경음"), "sfx": choice(AssetType.SFX, "효과음"), "gap_slots": gaps, "source_snapshot": snapshots}

    def start_draft_readiness(self, *, project_id: str, brief_id: str, narration_choice: dict[str, Any], idempotency_key: str, expected_brief_revision: int, capability: dict[str, Any] | None = None, defer: bool = True) -> dict[str, Any]:
        brief = self.get_creation_brief(project_id=project_id, brief_id=brief_id)
        if brief["status"] != "approved": raise ValueError("draft_readiness_brief_not_approved")
        if brief["revision"] != expected_brief_revision: raise ValueError("draft_readiness_brief_revision_conflict")
        kind = str(narration_choice.get("kind") or "")
        if kind not in {"silent", "existing", "source_video"}: raise ValueError("draft_readiness_narration_invalid")
        if kind in {"existing", "source_video"}:
            asset = self.get_asset(project_id=project_id, asset_id=str(narration_choice.get("asset_id") or ""))
            if asset["asset_type"] == AssetType.VOICE_SAMPLE_AUDIO.value: raise ValueError("draft_readiness_narration_voice_sample_invalid")
            required = AssetType.NARRATION_AUDIO.value if kind == "existing" else AssetType.RAW_VIDEO.value
            if asset["asset_type"] != required: raise ValueError("draft_readiness_narration_asset_invalid")
        fingerprint = hashlib.sha256(f"{brief_id}:{brief['revision']}:{brief['script_asset_id']}".encode()).hexdigest()
        # Asset reads use their own store connection; snapshot them before the
        # readiness write transaction so SQLite never nests writers.
        prepared_result = None if defer else self._draft_readiness_plan(project_id=project_id, brief=brief, narration=narration_choice)
        connection = self._connection(project_id); now = self._now_iso()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM draft_readiness WHERE project_id = ? AND idempotency_key = ?", (project_id, idempotency_key)).fetchone()
            if existing is not None:
                connection.commit(); return self._draft_readiness_payload(existing)
            readiness_id = f"readiness_{uuid.uuid4().hex[:12]}"
            result = prepared_result
            status = "asset_check" if defer else ("needs_assets" if result["gap_slots"] else "ready")
            connection.execute("INSERT INTO draft_readiness (readiness_id, project_id, brief_id, approved_brief_revision, input_fingerprint, narration_json, capability_json, idempotency_key, status, revision, result_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)", (readiness_id, project_id, brief_id, brief["revision"], fingerprint, json.dumps(narration_choice, ensure_ascii=False), json.dumps(capability or {}, ensure_ascii=False), idempotency_key, status, json.dumps(result, ensure_ascii=False) if result else None, now, now))
            row = connection.execute("SELECT * FROM draft_readiness WHERE readiness_id = ?", (readiness_id,)).fetchone(); connection.commit(); return self._draft_readiness_payload(row)
        except sqlite3.IntegrityError:
            if connection.in_transaction:
                connection.rollback()
            existing = self._fetchone(
                project_id,
                "SELECT * FROM draft_readiness WHERE project_id = ? AND idempotency_key = ?",
                (project_id, idempotency_key),
            )
            if existing is None:
                raise
            return self._draft_readiness_payload(existing)
        except Exception:
            if connection.in_transaction: connection.rollback()
            raise
        finally: connection.close()

    def get_draft_readiness(self, *, project_id: str, readiness_id: str) -> dict[str, Any]:
        row = self._fetchone(project_id, "SELECT * FROM draft_readiness WHERE project_id = ? AND readiness_id = ?", (project_id, readiness_id))
        if row is None: raise KeyError(f"Draft readiness not found: {readiness_id}")
        payload = self._draft_readiness_payload(row)
        if payload["status"] not in {"ready", "needs_assets"} or not payload["result"]:
            return payload
        normalized_result = self._normalize_draft_readiness_result(project_id=project_id, payload=payload)
        normalized_status = "needs_assets" if normalized_result.get("gap_slots") else payload["status"]
        if normalized_result == payload["result"] and normalized_status == payload["status"]:
            return payload
        self._execute(project_id, "UPDATE draft_readiness SET result_json = ?, status = ?, revision = revision + 1, updated_at = ? WHERE readiness_id = ? AND revision = ?", (json.dumps(normalized_result, ensure_ascii=False), normalized_status, self._now_iso(), readiness_id, payload["revision"]))
        refreshed = self._fetchone(project_id, "SELECT * FROM draft_readiness WHERE project_id = ? AND readiness_id = ?", (project_id, readiness_id))
        if refreshed is None: raise KeyError(f"Draft readiness not found: {readiness_id}")
        return self._draft_readiness_payload(refreshed)

    def list_draft_readiness(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            readiness_ids = [str(row["readiness_id"]) for row in connection.execute("SELECT readiness_id FROM draft_readiness WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()]
        finally:
            connection.close()
        return [self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id) for readiness_id in readiness_ids]

    def list_editing_sessions(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try: return [dict(row) for row in connection.execute("SELECT * FROM editing_sessions WHERE project_id = ?", (project_id,)).fetchall()]
        finally: connection.close()

    # Task 33 / F-9 follow-up. F-9 decided landscape is the default and fixed
    # build_timeline, but the owner's drafts never pass through build_timeline
    # -- they come from here, which set no output and so fell back to
    # CompositionPlan's vertical default. Long-form was still rendering
    # 1080x1920. Setting it explicitly is what makes the F-9 decision real.
    _ORIENTATION_OUTPUT_SIZES = {
        "landscape": {"width": 1920, "height": 1080},
        "vertical": {"width": 1080, "height": 1920},
    }

    def materialize_atomic_draft_bundle(
        self, *, project_id: str, brief_id: str, expected_brief_revision: int,
        readiness_id: str, expected_readiness_revision: int, idempotency_key: str,
        allow_placeholder: bool = False, orientation: str | None = None,
    ) -> dict[str, Any]:
        """Create the first editable draft as one durable operation.

        This intentionally does not call ``save_timeline_run`` followed by
        ``save_editing_session``: either both rows (and their staged mirrors)
        become visible, or neither does.  A readiness snapshot is rechecked
        under the writer lock so a later script/media change cannot be applied.
        """
        resolved_orientation = "landscape" if orientation is None else orientation
        if resolved_orientation not in self._ORIENTATION_OUTPUT_SIZES:
            raise ValueError(
                f"orientation must be one of {sorted(self._ORIENTATION_OUTPUT_SIZES)}, got {orientation!r}"
            )
        if not idempotency_key.strip():
            raise ValueError("atomic_draft_bundle_idempotency_required")
        brief = self.get_creation_brief(project_id=project_id, brief_id=brief_id)
        readiness = self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)
        if brief["status"] != "approved": raise ValueError("atomic_draft_bundle_brief_not_approved")
        if int(brief["revision"]) != int(expected_brief_revision): raise ValueError("atomic_draft_bundle_brief_revision_conflict")
        if readiness["brief_id"] != brief_id: raise ValueError("atomic_draft_bundle_brief_mismatch")
        if int(readiness["revision"]) != int(expected_readiness_revision): raise ValueError("atomic_draft_bundle_readiness_revision_conflict")
        if readiness["status"] not in {"ready", "needs_assets"}: raise ValueError("atomic_draft_bundle_not_ready")
        result = readiness.get("result") or {}
        gaps = list(result.get("gap_slots") or [])
        if gaps and not allow_placeholder: raise ValueError("atomic_draft_bundle_gaps_require_placeholder_approval")
        fingerprint = hashlib.sha256(json.dumps({"brief": [brief_id, brief["revision"], brief.get("script_asset_id")], "readiness": [readiness_id, readiness["revision"], readiness.get("input_fingerprint")], "placeholder": allow_placeholder}, sort_keys=True).encode()).hexdigest()
        root = self.project_root(project_id); stage = root / "staging" / f"draft-bundle-{uuid.uuid4().hex}"
        stage.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, Any] = {
            "kind": "atomic_draft_bundle",
            "status": "staging",
            "fingerprint": fingerprint,
            "artifacts": [],
        }
        self._write_atomic_bundle_manifest(stage, manifest)
        created: list[Path] = []
        try:
            def publish(staged: Path, target: Path, *, kind: str) -> None:
                """Record source SHA first, then atomically mirror one staged artifact."""
                digest = sha256_file(staged)
                manifest["artifacts"].append(
                    {
                        "kind": kind,
                        "staged_name": staged.name,
                        "target_uri": self._path_to_uri(project_id, target),
                        "sha256": digest,
                    }
                )
                self._write_atomic_bundle_manifest(stage, manifest)
                temporary = target.with_suffix(target.suffix + ".stage")
                shutil.copy2(staged, temporary)
                if sha256_file(temporary) != digest:
                    temporary.unlink(missing_ok=True)
                    raise OSError("atomic_draft_bundle_staged_copy_sha_mismatch")
                temporary.replace(target)
                created.append(target)
                self._atomic_bundle_fault(f"after_copy:{len(created)}")
            connection = self._connection(project_id)
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute("SELECT * FROM atomic_draft_bundles WHERE project_id=? AND idempotency_key=?", (project_id, idempotency_key)).fetchone()
                if existing is not None:
                    if str(existing["input_fingerprint"]) != fingerprint: raise ValueError("atomic_draft_bundle_idempotency_conflict")
                    connection.commit(); return json.loads(str(existing["result_json"]))
                current_brief = connection.execute("SELECT revision,status FROM creation_briefs WHERE brief_id=? AND project_id=?", (brief_id, project_id)).fetchone()
                current_readiness = connection.execute("SELECT revision,status,result_json FROM draft_readiness WHERE readiness_id=? AND project_id=?", (readiness_id, project_id)).fetchone()
                if current_brief is None or str(current_brief["status"]) != "approved" or int(current_brief["revision"]) != int(expected_brief_revision): raise ValueError("atomic_draft_bundle_brief_revision_conflict")
                if current_readiness is None or int(current_readiness["revision"]) != int(expected_readiness_revision): raise ValueError("atomic_draft_bundle_readiness_revision_conflict")
                current_result = json.loads(str(current_readiness["result_json"] or "{}")); current_gaps = list(current_result.get("gap_slots") or [])
                if current_gaps and not allow_placeholder: raise ValueError("atomic_draft_bundle_gaps_require_placeholder_approval")
                for snapshot in current_result.get("source_snapshot", []):
                    source = connection.execute("SELECT storage_uri,created_at FROM assets WHERE project_id=? AND asset_id=?", (project_id, str(snapshot.get("asset_id") or ""))).fetchone()
                    if source is None or str(source["created_at"]) != str(snapshot.get("media_revision") or ""):
                        raise ValueError("atomic_draft_bundle_source_revision_conflict")
                    path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(source["storage_uri"]))
                    if not path.is_file() or sha256_file(path) != str(snapshot.get("sha256") or ""):
                        raise ValueError("atomic_draft_bundle_source_sha_conflict")
                timeline_id = f"timeline_draft_{uuid.uuid4().hex[:12]}"; session_id = f"editing_session_draft_{uuid.uuid4().hex[:12]}"; bundle_id = f"draft_bundle_{uuid.uuid4().hex[:12]}"; timeline_job_id = f"timeline_build_job_draft_{uuid.uuid4().hex[:12]}"
                narration = dict(readiness.get("narration") or {}); narration_asset_id = narration.get("asset_id")
                asset_ids: list[str] = []; silence_stage: Path | None = None
                if narration.get("kind") == "silent":
                    import wave
                    narration_asset_id = f"asset_silence_{uuid.uuid4().hex[:12]}"; silence_stage = stage / "silence.wav"
                    with wave.open(str(silence_stage), "wb") as wav:
                        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(b"\x00\x00" * 16000)
                    destination = root / "assets" / "narration_audio" / f"{narration_asset_id}.wav"; destination.parent.mkdir(parents=True, exist_ok=True)
                    publish(silence_stage, destination, kind="narration_silence")
                    uri = self._path_to_uri(project_id, destination)
                    connection.execute("INSERT INTO assets (asset_id,project_id,asset_type,storage_uri,source_kind,mime_type,duration_sec,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (narration_asset_id, project_id, AssetType.NARRATION_AUDIO.value, uri, "deterministic_silence", "audio/wav", 1.0, json.dumps({"draft_bundle_id": bundle_id, "provenance": "local deterministic silence"}), self._now_iso()))
                    asset_ids.append(narration_asset_id)
                elif narration.get("kind") == "source_video" and narration_asset_id:
                    source = connection.execute("SELECT asset_type,storage_uri FROM assets WHERE project_id=? AND asset_id=?", (project_id, narration_asset_id)).fetchone()
                    if source is None or str(source["asset_type"]) != AssetType.RAW_VIDEO.value:
                        raise ValueError("atomic_draft_bundle_narration_invalid")
                    # CapCut's narration track accepts audio only.  Keep the raw-video
                    # source snapshot immutable and derive a local, inspectable WAV
                    # inside this operation rather than silently asking an external
                    # provider to extract it.
                    normalized_stage = stage / "source-video-narration.wav"
                    source_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(source["storage_uri"]))
                    try:
                        subprocess.run(
                            ["ffmpeg", "-y", "-i", str(source_path), "-vn", "-ac", "1", "-ar", "16000", str(normalized_stage)],
                            check=True, capture_output=True, timeout=60,
                        )
                    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                        raise ValueError("atomic_draft_bundle_source_video_audio_normalization_failed") from exc
                    narration_asset_id = f"asset_source_video_narration_{uuid.uuid4().hex[:12]}"
                    destination = root / "assets" / "narration_audio" / f"{narration_asset_id}.wav"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    publish(normalized_stage, destination, kind="source_video_narration")
                    uri = self._path_to_uri(project_id, destination)
                    connection.execute(
                        "INSERT INTO assets (asset_id,project_id,asset_type,storage_uri,source_kind,mime_type,duration_sec,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (narration_asset_id, project_id, AssetType.NARRATION_AUDIO.value, uri, "source_video_audio_normalized", "audio/wav", None, json.dumps({"draft_bundle_id": bundle_id, "source_asset_id": narration.get("asset_id")}), self._now_iso()),
                    )
                    asset_ids.append(narration_asset_id)
                elif narration_asset_id:
                    source = connection.execute("SELECT asset_type FROM assets WHERE project_id=? AND asset_id=?", (project_id, narration_asset_id)).fetchone()
                    if source is None or str(source["asset_type"]) == AssetType.VOICE_SAMPLE_AUDIO.value: raise ValueError("atomic_draft_bundle_narration_invalid")
                    asset_ids.append(str(narration_asset_id))
                else: raise ValueError("atomic_draft_bundle_narration_missing")
                narration_asset = connection.execute("SELECT storage_uri,created_at FROM assets WHERE project_id=? AND asset_id=?", (project_id, narration_asset_id)).fetchone()
                if narration_asset is None:
                    raise ValueError("atomic_draft_bundle_narration_missing")
                narration_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(narration_asset["storage_uri"]))
                narration_sha256 = sha256_file(narration_path)
                narration_provenance = {"sha256": narration_sha256, "media_revision": str(narration_asset["created_at"])}
                placeholder_assets: list[tuple[str, dict[str, Any], str, str]] = []
                if current_gaps:
                    for gap in current_gaps:
                        placeholder_asset_id = f"asset_gap_placeholder_{uuid.uuid4().hex[:12]}"
                        destination = root / "assets" / "broll_video" / f"{placeholder_asset_id}.svg"; destination.parent.mkdir(parents=True, exist_ok=True)
                        placeholder_svg = "<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720'><rect width='100%' height='100%' fill='#f7f7f7'/><text x='640' y='360' text-anchor='middle' fill='#555' font-size='36'>자산이 필요한 임시 장면</text></svg>"
                        staged_placeholder = stage / destination.name
                        staged_placeholder.write_text(placeholder_svg, encoding="utf-8")
                        publish(staged_placeholder, destination, kind="gap_placeholder")
                        uri = self._path_to_uri(project_id, destination)
                        placeholder_created_at = self._now_iso(); placeholder_sha256 = sha256_file(destination)
                        connection.execute("INSERT INTO assets (asset_id,project_id,asset_type,storage_uri,source_kind,mime_type,duration_sec,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (placeholder_asset_id, project_id, AssetType.BROLL_VIDEO.value, uri, "draft_gap_placeholder", "image/svg+xml", None, json.dumps({"draft_bundle_id": bundle_id, "gap_slot_id": gap.get("gap_slot_id"), "label": "자산이 필요한 임시 장면", "in_app_only": True}), placeholder_created_at))
                        asset_ids.append(placeholder_asset_id)
                        placeholder_assets.append((placeholder_asset_id, gap, placeholder_sha256, placeholder_created_at))
                provenance_by_asset = {str(item.get("asset_id")): item for item in current_result.get("source_snapshot", []) if isinstance(item, dict)}
                segments = list(current_result.get("script_segments") or []); clips: list[dict[str, Any]] = []
                visible_segment_by_source_id: dict[str, dict[str, Any]] = {}
                for index, item in enumerate(segments):
                    source_segment_id = str(item.get("segment_id") or f"script-{index + 1}")
                    segment_id = f"segment_draft_{uuid.uuid4().hex[:10]}"
                    # Task 36: clip_type is what the read contract identifies a
                    # clip by, exactly as broll clips already declare theirs.
                    # Captions carry no asset file, so asset_uri stays absent.
                    caption_clip = {"clip_id": f"clip_caption_{uuid.uuid4().hex[:10]}", "segment_id": segment_id, "source_segment_id": source_segment_id, "clip_type": "caption", "text": item.get("text", ""), "start_sec": item.get("start_sec", index * 5), "end_sec": item.get("end_sec", (index + 1) * 5)}
                    clips.append(caption_clip)
                    visible_segment_by_source_id[source_segment_id] = caption_clip
                    connection.execute("INSERT INTO segments (segment_id,project_id,start_sec,end_sec,text,source_asset_id,metadata_json) VALUES (?,?,?,?,?,?,?)", (segment_id, project_id, clips[-1]["start_sec"], clips[-1]["end_sec"], clips[-1]["text"], brief.get("script_asset_id"), json.dumps({"draft_bundle_id": bundle_id})))
                broll = [item for item in current_result.get("broll_candidates", []) if not item.get("skipped")]
                for item in broll:
                    asset_ids.append(str(item["asset_id"])); provenance = provenance_by_asset.get(str(item["asset_id"]), {})
                    source_segment_id = str(item.get("segment_id") or "")
                    visible_segment = visible_segment_by_source_id.get(source_segment_id)
                    if visible_segment is None:
                        raise ValueError("atomic_draft_bundle_segment_alignment_invalid")
                    source_range = item.get("target_range") if isinstance(item.get("target_range"), dict) else {}
                    source_in_sec = float(source_range.get("start_sec", 0))
                    source_out_sec = float(source_range.get("end_sec", 5))
                    target_duration_sec = float(visible_segment["end_sec"]) - float(visible_segment["start_sec"])
                    clips.append({"clip_id": f"clip_broll_{uuid.uuid4().hex[:10]}", "clip_type": "broll", "asset_id": item["asset_id"], "segment_id": visible_segment["segment_id"], "source_segment_id": source_segment_id, "start_sec": visible_segment["start_sec"], "end_sec": visible_segment["end_sec"], "media_controls": {"in_sec": source_in_sec, "out_sec": source_out_sec, "loop": False, "pad": source_out_sec - source_in_sec < target_duration_sec}, "expected_content_sha256": provenance.get("sha256"), "media_revision": provenance.get("media_revision")})
                aligned_gaps = []
                for gap in current_gaps:
                    aligned_gap = deepcopy(gap)
                    source_segment_id = str(gap.get("segment_id") or "")
                    visible_segment = visible_segment_by_source_id.get(source_segment_id)
                    if visible_segment is not None:
                        aligned_gap["source_segment_id"] = source_segment_id
                        aligned_gap["segment_id"] = visible_segment["segment_id"]
                        aligned_gap["target_range"] = {
                            "start_sec": visible_segment["start_sec"],
                            "end_sec": visible_segment["end_sec"],
                        }
                    aligned_gaps.append(aligned_gap)
                aligned_gap_by_id = {
                    str(gap.get("gap_slot_id") or ""): gap
                    for gap in aligned_gaps
                }
                for placeholder_asset_id, source_gap, placeholder_sha256, placeholder_created_at in placeholder_assets:
                    gap = aligned_gap_by_id.get(str(source_gap.get("gap_slot_id") or ""), source_gap)
                    clips.append({"clip_id": f"clip_gap_placeholder_{uuid.uuid4().hex[:10]}", "clip_type": "broll", "asset_id": placeholder_asset_id, "segment_id": gap.get("segment_id") or gap.get("gap_slot_id"), "source_segment_id": gap.get("source_segment_id"), "gap_slot_id": gap.get("gap_slot_id"), "label": "자산이 필요한 임시 장면", "start_sec": gap.get("target_range", {}).get("start_sec", 0), "end_sec": gap.get("target_range", {}).get("end_sec", 5), "media_controls": {}, "expected_content_sha256": placeholder_sha256, "media_revision": placeholder_created_at})
                asset_uris = {str(row["asset_id"]): str(row["storage_uri"]) for row in connection.execute("SELECT asset_id,storage_uri FROM assets WHERE project_id=?", (project_id,)).fetchall()}
                narration_clip = {"clip_id": f"clip_narration_{uuid.uuid4().hex[:10]}", "clip_type": "narration", "asset_id": narration_asset_id, "segment_id": clips[0]["segment_id"] if clips else "segment_narration", "asset_uri": asset_uris[str(narration_asset_id)], "start_sec": 0, "end_sec": max([c["end_sec"] for c in clips] or [1]), "media_controls": {}, "expected_content_sha256": narration_provenance.get("sha256"), "media_revision": narration_provenance.get("media_revision")}
                broll_clips = [{**c, "asset_uri": asset_uris.get(str(c.get("asset_id")), "")} for c in clips if "asset_id" in c and c.get("asset_id") != narration_asset_id]
                tracks = [{"track_id": f"track_narration_{uuid.uuid4().hex[:8]}", "track_type": "narration", "clips": [narration_clip]}, {"track_id": f"track_caption_{uuid.uuid4().hex[:8]}", "track_type": "caption", "clips": [c for c in clips if "text" in c]}, {"track_id": f"track_broll_{uuid.uuid4().hex[:8]}", "track_type": "broll", "clips": broll_clips}]
                review_flags = [{"code": "draft_gap_placeholder", "segment_id": gap.get("segment_id") or gap.get("gap_slot_id"), "message": "자산이 필요한 임시 장면입니다."} for gap in aligned_gaps]
                timeline = {"timeline_id": timeline_id, "project_id": project_id, "version": "draft-v1", "source_session_id": session_id, "source_session_revision": 1, "tracks": tracks, "gap_slots": aligned_gaps, "review_flags": review_flags, "pending_recommendations": [], "applied_recommendations": [], "bgm_policy": current_result.get("bgm"), "sfx_policy": current_result.get("sfx"), "placeholder_policy": "in_app_only" if current_gaps else None, "output": dict(self._ORIENTATION_OUTPUT_SIZES[resolved_orientation]), "output_mode": "review"}
                session_segments = [
                    {
                        "segment_id": clip["segment_id"],
                        "caption_text": str(clip.get("text") or ""),
                        "start_sec": float(clip["start_sec"]),
                        "end_sec": float(clip["end_sec"]),
                        "cut_action": "keep",
                        "review_required": bool(current_gaps),
                        "broll_override": None,
                        "visual_overlays": [],
                        "music_override": None,
                        "sfx_override": None,
                        "tts_replacement": None,
                    }
                    for clip in clips if "text" in clip
                ]
                session = {"session_id": session_id, "project_id": project_id, "timeline_id": timeline_id, "tracks": tracks, "segments": session_segments, "gap_slots": aligned_gaps, "draft_bundle_id": bundle_id, "session_revision": 1, "history": [], "undo_stack": [], "redo_stack": []}
                timeline_path = root / "timelines" / f"{timeline_id}.json"; session_path = root / "editing_sessions" / f"{session_id}.json"; timeline_path.parent.mkdir(parents=True, exist_ok=True); session_path.parent.mkdir(parents=True, exist_ok=True)
                for target, payload, kind in ((timeline_path, timeline, "timeline_mirror"), (session_path, session, "session_mirror")):
                    staged = stage / target.name
                    staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                    publish(staged, target, kind=kind)
                now = self._now_iso(); timeline_uri = self._path_to_uri(project_id, timeline_path); session_uri = self._path_to_uri(project_id, session_path)
                connection.execute("INSERT INTO timelines (timeline_id,project_id,version,output_mode,file_uri,summary_json,created_at) VALUES (?,?,?,?,?,?,?)", (timeline_id, project_id, "draft-v1", "review", timeline_uri, json.dumps({"track_count": len(tracks), "gap_count": len(current_gaps)}), now))
                connection.execute("INSERT INTO editing_sessions (session_id,project_id,timeline_id,file_uri,summary_json,session_revision,session_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (session_id, project_id, timeline_id, session_uri, json.dumps({"draft_bundle_id": bundle_id}), 1, json.dumps(session, ensure_ascii=False), now, now))
                connection.execute("INSERT INTO jobs (job_id,project_id,job_type,status,input_ref,output_ref,error_message,started_at,finished_at) VALUES (?,?,?,?,?,?,?,?,?)", (timeline_job_id, project_id, JobType.TIMELINE_BUILD.value, JobStatus.SUCCEEDED.value, readiness_id, timeline_id, None, now, now))
                connection.execute("INSERT INTO review_approvals (timeline_id,project_id,status,approved_at,updated_at,source_session_revision,is_current) VALUES (?,?,?,?,?,?,?)", (timeline_id, project_id, "blocked" if current_gaps else "draft", None, now, 1, 1))
                response = {"bundle_id": bundle_id, "session_id": session_id, "timeline_id": timeline_id, "timeline_job_id": timeline_job_id, "segment_ids": [c["segment_id"] for c in clips if "text" in c], "asset_ids": list(dict.fromkeys(asset_ids)), "clip_ids": [c["clip_id"] for c in clips], "gap_slots": aligned_gaps, "output_blocked": bool(current_gaps)}
                connection.execute("INSERT INTO atomic_draft_bundles (bundle_id,project_id,brief_id,readiness_id,input_fingerprint,idempotency_key,session_id,timeline_id,result_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (bundle_id, project_id, brief_id, readiness_id, fingerprint, idempotency_key, session_id, timeline_id, json.dumps(response, ensure_ascii=False), now))
                self._atomic_bundle_fault("before_db_commit")
                connection.commit()
                manifest["status"] = "committed"
                self._write_atomic_bundle_manifest(stage, manifest)
                return response
            except sqlite3.IntegrityError:
                if connection.in_transaction:
                    connection.rollback()
                existing = connection.execute(
                    "SELECT * FROM atomic_draft_bundles WHERE project_id=? AND idempotency_key=?",
                    (project_id, idempotency_key),
                ).fetchone()
                for path in created:
                    path.unlink(missing_ok=True)
                if existing is None:
                    raise
                if str(existing["input_fingerprint"]) != fingerprint:
                    raise ValueError("atomic_draft_bundle_idempotency_conflict")
                return json.loads(str(existing["result_json"]))
            except Exception:
                if connection.in_transaction: connection.rollback()
                for path in created:
                    path.unlink(missing_ok=True)
                raise
            finally: connection.close()
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def cancel_draft_readiness(self, *, project_id: str, readiness_id: str, expected_revision: int) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE"); row = connection.execute("SELECT * FROM draft_readiness WHERE project_id = ? AND readiness_id = ?", (project_id, readiness_id)).fetchone()
            if row is None: raise KeyError(f"Draft readiness not found: {readiness_id}")
            if int(row["revision"]) != expected_revision: raise ValueError("draft_readiness_revision_conflict")
            if row["status"] in {"ready", "needs_assets", "cancelled"}: raise ValueError("draft_readiness_not_cancellable")
            connection.execute("UPDATE draft_readiness SET status = 'cancelled', cancel_requested = 1, revision = revision + 1, updated_at = ? WHERE readiness_id = ?", (self._now_iso(), readiness_id)); row = connection.execute("SELECT * FROM draft_readiness WHERE readiness_id = ?", (readiness_id,)).fetchone(); connection.commit(); return self._draft_readiness_payload(row)
        except Exception:
            if connection.in_transaction: connection.rollback()
            raise
        finally: connection.close()

    def begin_draft_readiness_planning(self, *, project_id: str, readiness_id: str, expected_revision: int) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE"); row = connection.execute("SELECT * FROM draft_readiness WHERE project_id = ? AND readiness_id = ?", (project_id, readiness_id)).fetchone()
            if row is None: raise KeyError(f"Draft readiness not found: {readiness_id}")
            if int(row["revision"]) != expected_revision: raise ValueError("draft_readiness_revision_conflict")
            if row["status"] not in {"asset_check", "cancelled", "failed", "needs_assets"}: raise ValueError("draft_readiness_not_plannable")
            connection.execute("UPDATE draft_readiness SET status = 'planning', cancel_requested = 0, error_code = NULL, revision = revision + 1, updated_at = ? WHERE readiness_id = ?", (self._now_iso(), readiness_id))
            row = connection.execute("SELECT * FROM draft_readiness WHERE readiness_id = ?", (readiness_id,)).fetchone(); connection.commit(); return self._draft_readiness_payload(row)
        except Exception:
            if connection.in_transaction: connection.rollback()
            raise
        finally: connection.close()

    def complete_draft_readiness(self, *, project_id: str, readiness_id: str, expected_revision: int) -> dict[str, Any]:
        row = self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)
        if row["status"] == "cancelled": raise ValueError("draft_readiness_cancelled")
        if row["revision"] != expected_revision: raise ValueError("draft_readiness_revision_conflict")
        if row["status"] != "planning": raise ValueError("draft_readiness_not_planning")
        try:
            brief = self.get_creation_brief(project_id=project_id, brief_id=row["brief_id"]); result = self._draft_readiness_plan(project_id=project_id, brief=brief, narration=row["narration"])
        except Exception:
            self._execute(project_id, "UPDATE draft_readiness SET status = 'failed', error_code = 'draft_readiness_planning_failed', revision = revision + 1, updated_at = ? WHERE readiness_id = ? AND revision = ?", (self._now_iso(), readiness_id, expected_revision))
            raise
        self._execute(project_id, "UPDATE draft_readiness SET status = ?, result_json = ?, revision = revision + 1, updated_at = ? WHERE readiness_id = ? AND revision = ?", ("needs_assets" if result["gap_slots"] else "ready", json.dumps(result, ensure_ascii=False), self._now_iso(), readiness_id, expected_revision))
        return self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)

    def update_draft_readiness_candidate(self, *, project_id: str, readiness_id: str, asset_id: str, skipped: bool, expected_revision: int) -> dict[str, Any]:
        row = self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)
        if row["revision"] != expected_revision: raise ValueError("draft_readiness_revision_conflict")
        if row["status"] not in {"ready", "needs_assets"} or not row["result"]: raise ValueError("draft_readiness_candidate_not_editable")
        result = row["result"]
        candidates = result.get("broll_candidates", [])
        candidate = next((item for item in candidates if item.get("asset_id") == asset_id), None)
        if candidate is None: raise KeyError(f"Draft readiness candidate not found: {asset_id}")
        candidate["skipped"] = bool(skipped)
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("UPDATE draft_readiness SET result_json = ?, revision = revision + 1, updated_at = ? WHERE readiness_id = ? AND revision = ?", (json.dumps(result, ensure_ascii=False), self._now_iso(), readiness_id, expected_revision))
            connection.commit()
            if cursor.rowcount != 1: raise ValueError("draft_readiness_revision_conflict")
        finally:
            connection.close()
        return self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)

    def update_draft_readiness_candidate_range(self, *, project_id: str, readiness_id: str, asset_id: str, start_sec: float, end_sec: float, expected_revision: int) -> dict[str, Any]:
        if not math.isfinite(start_sec) or not math.isfinite(end_sec) or start_sec < 0 or end_sec <= start_sec: raise ValueError("draft_readiness_candidate_range_invalid")
        asset = self.get_asset(project_id=project_id, asset_id=asset_id)
        raw_duration = asset.get("duration_sec")
        if raw_duration is not None:
            duration_sec = float(raw_duration)
            if not math.isfinite(duration_sec) or duration_sec <= 0 or end_sec > duration_sec:
                raise ValueError("draft_readiness_candidate_range_invalid")
        row = self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)
        if row["revision"] != expected_revision: raise ValueError("draft_readiness_revision_conflict")
        if not row["result"]: raise ValueError("draft_readiness_candidate_not_editable")
        candidate = next((item for item in row["result"].get("broll_candidates", []) if item.get("asset_id") == asset_id), None)
        if candidate is None: raise KeyError(f"Draft readiness candidate not found: {asset_id}")
        candidate["target_range"] = {"start_sec": start_sec, "end_sec": end_sec}
        result = row["result"]
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("UPDATE draft_readiness SET result_json = ?, revision = revision + 1, updated_at = ? WHERE readiness_id = ? AND revision = ?", (json.dumps(result, ensure_ascii=False), self._now_iso(), readiness_id, expected_revision)); connection.commit()
            if cursor.rowcount != 1: raise ValueError("draft_readiness_revision_conflict")
        finally: connection.close()
        return self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)

    def register_asset(
        self,
        *,
        project_id: str,
        asset_type: AssetType,
        source_path: Path,
        source_kind: str = "local_file",
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRecord:
        resolved_source = Path(source_path)
        if not resolved_source.exists():
            raise FileNotFoundError(f"Source asset does not exist: {resolved_source}")

        destination_dir = self.project_root(project_id) / self._asset_directory(asset_type)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / resolved_source.name
        if destination_path.exists():
            destination_path = destination_dir / f"{uuid.uuid4().hex}-{resolved_source.name}"
        shutil.copy2(resolved_source, destination_path)
        storage_uri = self._path_to_uri(project_id, destination_path)
        asset = AssetRecord.create(
            project_id=project_id,
            asset_type=asset_type,
            storage_uri=storage_uri,
        )
        self._execute_asset_index_mutation(
            project_id,
            """
            INSERT INTO assets (
                asset_id,
                project_id,
                asset_type,
                storage_uri,
                source_kind,
                mime_type,
                duration_sec,
                metadata_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset.asset_id,
                asset.project_id,
                asset.asset_type.value,
                asset.storage_uri,
                source_kind,
                mime_type,
                None,
                json.dumps(metadata or {}, ensure_ascii=True),
                asset.created_at.isoformat(),
            ),
        )
        return asset

    def save_transcript(
        self,
        *,
        project_id: str,
        source_asset_id: str,
        transcript_text: str,
        segments: list[dict[str, Any]],
        provider_name: str = "mock_stt",
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "analysis" / "transcripts",
            "transcript_*.json",
        )
        file_name = f"transcript_{sequence:03d}.json"
        transcript_path = self.project_root(project_id) / "analysis" / "transcripts" / file_name
        transcript_uri = self._path_to_uri(project_id, transcript_path)
        transcript = TranscriptRecord.create(
            project_id=project_id,
            source_asset_id=source_asset_id,
            transcript_uri=transcript_uri,
            transcript_text=transcript_text,
            provider_name=provider_name,
            transcript_id=f"transcript_{sequence:03d}",
        )
        payload = {
            "transcript_id": transcript.transcript_id,
            "project_id": transcript.project_id,
            "source_asset_id": transcript.source_asset_id,
            "transcript_uri": transcript.transcript_uri,
            "transcript_text": transcript.transcript_text,
            "provider_name": transcript.provider_name,
            "segments": segments,
            "created_at": transcript.created_at.isoformat(),
        }
        transcript_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        self._execute(
            project_id,
            """
            INSERT INTO transcripts (
                transcript_id,
                project_id,
                source_asset_id,
                transcript_uri,
                transcript_text,
                provider_name,
                segments_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transcript.transcript_id,
                transcript.project_id,
                transcript.source_asset_id,
                transcript.transcript_uri,
                transcript.transcript_text,
                transcript.provider_name,
                json.dumps(segments, ensure_ascii=True),
                transcript.created_at.isoformat(),
            ),
        )
        return payload

    def save_segment_analysis(
        self,
        *,
        project_id: str,
        transcript_id: str,
        script_asset_id: str | None,
        segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "analysis" / "segments",
            "segment_analysis_*.json",
        )
        file_name = f"segment_analysis_{sequence:03d}.json"
        analysis_path = self.project_root(project_id) / "analysis" / "segments" / file_name
        analysis_id = f"segment_analysis_{sequence:03d}"
        payload = {
            "segment_analysis_id": analysis_id,
            "project_id": project_id,
            "transcript_id": transcript_id,
            "script_asset_id": script_asset_id,
            "file_uri": self._path_to_uri(project_id, analysis_path),
            "segments_uri": self._path_to_uri(project_id, analysis_path),
            "segments": segments,
        }
        analysis_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        self._execute(
            project_id,
            """
            INSERT INTO segment_analysis_runs (
                segment_analysis_id,
                project_id,
                transcript_id,
                script_asset_id,
                file_uri,
                segments_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                analysis_id,
                project_id,
                transcript_id,
                script_asset_id,
                payload["file_uri"],
                json.dumps(segments, ensure_ascii=True),
            ),
        )
        for index, segment in enumerate(segments, start=1):
            segment_metadata = {
                "transcript_id": transcript_id,
                "script_asset_id": script_asset_id,
            }
            if "provider_trace" in segment:
                segment_metadata["provider_trace"] = segment["provider_trace"]
            self._execute(
                project_id,
                """
                INSERT INTO segments (
                    segment_id,
                    project_id,
                    start_sec,
                    end_sec,
                    text,
                    source_asset_id,
                    confidence,
                    cleanup_decision,
                    review_required,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment.get("segment_id", f"seg_{index:03d}_{analysis_id}"),
                    project_id,
                    segment.get("start_sec"),
                    segment.get("end_sec"),
                    segment.get("text"),
                    segment.get("source_asset_id"),
                    segment.get("confidence"),
                    segment.get("cleanup_decision"),
                    1 if _normalize_boolish(segment.get("review_required")) else 0,
                    json.dumps(segment_metadata, ensure_ascii=True),
                ),
            )
        return payload

    def save_recommendation_run(
        self,
        *,
        project_id: str,
        recommendation_type: RecommendationType,
        source_job_id: str,
        recommendations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "analysis" / "recommendations",
            f"{recommendation_type.value}_*.json",
        )
        run_id = f"{recommendation_type.value}_{sequence:03d}"
        recommendation_path = (
            self.project_root(project_id) / "analysis" / "recommendations" / f"{run_id}.json"
        )
        persisted_items: list[dict[str, Any]] = []
        for item in recommendations:
            record = RecommendationRecord.create(
                project_id=project_id,
                target_segment_id=item["target_segment_id"],
                recommendation_type=recommendation_type,
                selected_asset_id=item.get("selected_asset_id"),
                reason=item["reason"],
                score=float(item["score"]),
                payload=item.get("payload"),
            )
            persisted = {
                "recommendation_id": record.recommendation_id,
                "project_id": project_id,
                "target_segment_id": record.target_segment_id,
                "recommendation_type": recommendation_type.value,
                "selected_asset_id": record.selected_asset_id,
                "score": record.score,
                "reason": record.reason,
                "auto_apply_allowed": _normalize_boolish(
                    item.get("auto_apply_allowed", record.auto_apply_allowed)
                ),
                "review_required": _normalize_boolish(
                    item.get("review_required", record.review_required)
                ),
                "payload": item.get("payload", record.payload or {}),
                "created_at": record.created_at.isoformat(),
            }
            persisted["decision_state"] = self._derive_recommendation_decision_state(persisted)
            persisted_items.append(persisted)
            self._execute(
                project_id,
                """
                INSERT INTO recommendations (
                    recommendation_id,
                    project_id,
                    target_segment_id,
                    recommendation_type,
                    selected_asset_id,
                    score,
                    reason,
                    auto_apply_allowed,
                    review_required,
                    decision_state,
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.recommendation_id,
                    project_id,
                    record.target_segment_id,
                    recommendation_type.value,
                    record.selected_asset_id,
                    record.score,
                    record.reason,
                    1 if persisted["auto_apply_allowed"] else 0,
                    1 if persisted["review_required"] else 0,
                    persisted["decision_state"],
                    json.dumps(persisted["payload"], ensure_ascii=True),
                    record.created_at.isoformat(),
                ),
            )
        payload = {
            "recommendation_run_id": run_id,
            "project_id": project_id,
            "source_job_id": source_job_id,
            "recommendation_type": recommendation_type.value,
            "file_uri": self._path_to_uri(project_id, recommendation_path),
            "recommendations": persisted_items,
        }
        recommendation_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        return payload

    def save_timeline_run(
        self,
        *,
        project_id: str,
        output_mode: str,
        timeline_payload: dict[str, Any],
        source_session_id: str | None = None,
        source_session_revision: int | None = None,
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "timelines",
            "timeline_*.json",
        )
        timeline_id = f"timeline_{sequence:03d}"
        timeline_path = self.project_root(project_id) / "timelines" / f"{timeline_id}.json"
        file_uri = self._path_to_uri(project_id, timeline_path)
        payload = {
            "timeline_id": timeline_id,
            "project_id": project_id,
            "version": str(timeline_payload.get("version", "v001")),
            "output_mode": output_mode,
            "file_uri": file_uri,
            "created_at": self._now_iso(),
            **timeline_payload,
        }
        if source_session_id is not None:
            payload["source_session_id"] = str(source_session_id)
        if source_session_revision is not None:
            payload["source_session_revision"] = int(source_session_revision)
        timeline_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        summary_json = _timeline_summary_json(payload)
        self._execute(
            project_id,
            """
            INSERT INTO timelines (
                timeline_id,
                project_id,
                version,
                output_mode,
                file_uri,
                summary_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timeline_id,
                project_id,
                payload["version"],
                output_mode,
                file_uri,
                summary_json,
                payload["created_at"],
            ),
        )
        recommendation_blocker_sources: list[dict[str, Any]] = []
        for collection_key in ("pending_recommendations", "applied_recommendations"):
            collection = payload.get(collection_key)
            if isinstance(collection, list):
                recommendation_blocker_sources.extend(
                    item for item in collection if isinstance(item, dict)
                )
        has_pending_like_recommendation = any(
            _is_store_blocking_pending_recommendation(item)
            for item in recommendation_blocker_sources
        )
        review_flags = payload.get("review_flags")
        has_blocking_review_flag = isinstance(review_flags, list) and any(
            _is_store_blocking_review_flag(flag) for flag in review_flags
        )
        initial_review_status = (
            "blocked"
            if has_blocking_review_flag or has_pending_like_recommendation
            else "draft"
        )
        self.save_review_state(
            project_id=project_id,
            timeline_id=timeline_id,
            status=initial_review_status,
            source_session_id=source_session_id,
            source_session_revision=source_session_revision,
        )
        return {"timeline_id": timeline_id, "file_uri": file_uri, "timeline": payload}

    def save_editing_session(
        self,
        *,
        project_id: str,
        timeline_id: str,
        session_payload: dict[str, Any],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "editing_sessions",
            "editing_session_*.json",
        )
        session_id = f"editing_session_{sequence:03d}"
        saved = self._write_editing_session(
            project_id=project_id,
            timeline_id=timeline_id,
            session_id=session_id,
            session_payload=session_payload,
            is_new=True,
        )
        try:
            self.bind_timeline_to_editing_session_revision(
                project_id=project_id,
                timeline_id=timeline_id,
                session_id=session_id,
                session_revision=int(saved["session_revision"]),
            )
        except KeyError:
            # A pre-timeline draft session cannot authorize any output until bound.
            pass
        return saved

    def bind_timeline_to_editing_session_revision(
        self,
        *,
        project_id: str,
        timeline_id: str,
        session_id: str,
        session_revision: int,
    ) -> dict[str, Any]:
        """Persist the editing-session revision consumed by a timeline and review."""
        timeline = self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
        timeline["source_session_id"] = str(session_id)
        timeline["source_session_revision"] = int(session_revision)
        updated = self.update_timeline_run(
            project_id=project_id,
            timeline_id=timeline_id,
            timeline_payload=timeline,
        )
        review = self.get_review_state(project_id=project_id, timeline_id=timeline_id)
        self.save_review_state(
            project_id=project_id,
            timeline_id=timeline_id,
            status=str(review["status"]),
            source_session_id=str(session_id),
            source_session_revision=int(session_revision),
        )
        return updated

    def update_editing_session(
        self,
        *,
        project_id: str,
        session_id: str,
        session_payload: dict[str, Any],
        timeline_id: str | None = None,
        expected_revision: int | None = None,
        invalidate_output_freshness: bool = True,
    ) -> dict[str, Any]:
        existing = self.get_editing_session(project_id=project_id, session_id=session_id)
        current_revision = int(existing.get("session_revision") or 1)
        expected_revision = current_revision if expected_revision is None else expected_revision
        session_payload = deepcopy(session_payload)
        if int(session_payload.get("session_revision") or 0) <= current_revision:
            session_payload["session_revision"] = current_revision + 1
        created_at = str(existing.get("created_at") or self._now_iso())
        return self._write_editing_session(
            project_id=project_id,
            timeline_id=timeline_id or str(existing["timeline_id"]),
            session_id=session_id,
            session_payload=session_payload,
            is_new=False,
            created_at=created_at,
            expected_revision=expected_revision,
            invalidate_output_freshness=invalidate_output_freshness,
        )

    def restore_editing_session_after_failed_publication(
        self,
        *,
        project_id: str,
        session_id: str,
        session_payload: dict[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        """CAS-restore the exact pre-publication session without staling its outputs.

        A partial regeneration briefly advances the session to bind its candidate
        timeline.  If publishing the result/job fails, that candidate never became
        observable, so the original revision and its artifacts remain authoritative.
        """
        existing = self.get_editing_session(project_id=project_id, session_id=session_id)
        payload = deepcopy(session_payload)
        return self._write_editing_session(
            project_id=project_id,
            timeline_id=str(payload["timeline_id"]),
            session_id=session_id,
            session_payload=payload,
            is_new=False,
            created_at=str(existing["created_at"]),
            expected_revision=expected_revision,
            invalidate_output_freshness=False,
        )

    def apply_director_proposal_transaction(
        self, *, project_id: str, session_id: str, proposal_id: str,
        session_payload: dict[str, Any], expected_revision: int,
        proposal_base_revision: int, materialized_expectations: list[tuple[str, str, int]],
    ) -> dict[str, Any]:
        """Commit the session CAS and proposal consumption in the same SQLite transaction."""
        existing = self.get_editing_session(project_id=project_id, session_id=session_id)
        payload = deepcopy(session_payload)
        if int(payload.get("session_revision") or 0) <= int(existing.get("session_revision") or 1):
            payload["session_revision"] = int(existing.get("session_revision") or 1) + 1

        def consume(connection: sqlite3.Connection) -> None:
            proposal_row = connection.execute("SELECT proposal_json, status FROM director_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
            if proposal_row is None or str(proposal_row["status"]) != "ready":
                raise EditingSessionRevisionConflict("Director proposal is no longer ready.")
            if int(json.loads(str(proposal_row["proposal_json"])).get("base_session_revision") or 0) != proposal_base_revision:
                raise EditingSessionRevisionConflict("Director proposal base revision changed.")
            revision_row = connection.execute("SELECT revision FROM director_asset_index_revisions WHERE project_id = ?", (project_id,)).fetchone()
            current_index_revision = int(revision_row["revision"]) if revision_row is not None else 0
            for asset_id, expected_sha256, expected_index_revision in materialized_expectations:
                row = connection.execute("SELECT storage_uri, metadata_json FROM assets WHERE project_id = ? AND asset_id = ?", (project_id, asset_id)).fetchone()
                if row is None or current_index_revision != expected_index_revision:
                    raise EditingSessionRevisionConflict("Materialized asset index changed during proposal apply.")
                metadata = json.loads(str(row["metadata_json"] or "{}"))
                if int(metadata.get("director_materialized_asset_index_revision") or -1) != expected_index_revision:
                    raise EditingSessionRevisionConflict("Materialized asset revision changed during proposal apply.")
                path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["storage_uri"]))
                if not path.is_file() or sha256_file(path) != expected_sha256:
                    raise EditingSessionRevisionConflict("Materialized bytes changed during proposal apply.")
            now = self._now_iso()
            changed = connection.execute(
                "UPDATE director_proposals SET status = ?, updated_at = ? WHERE proposal_id = ? AND status = 'ready'",
                ("applied", now, proposal_id),
            )
            if changed.rowcount != 1:
                raise EditingSessionRevisionConflict("Director proposal is no longer ready.")
            connection.execute(
                "INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)",
                (proposal_id, "applied", "session_apply", now),
            )

        return self._write_editing_session(
            project_id=project_id, timeline_id=str(existing["timeline_id"]), session_id=session_id,
            session_payload=payload, is_new=False, created_at=str(existing["created_at"]),
            expected_revision=expected_revision, transaction_hook=consume,
            transaction_start_hook=self._begin_director_session_transaction,
        )

    @staticmethod
    def _begin_director_session_transaction(connection: Any) -> None:
        """Serialize director attestation truth before the session CAS write."""
        if isinstance(connection, sqlite3.Connection):
            connection.execute("BEGIN IMMEDIATE")
            return
        connection.execute("BEGIN")
        # Preserve the common writer order: session CAS, asset registration,
        # asset-index revision, proposal state, then dependent outputs.
        connection.execute(
            "LOCK TABLE editing_sessions, assets, director_asset_index_revisions, "
            "director_proposals, tts_candidates, review_approvals, subtitle_renders, "
            "preview_renders, exports, exact_preview_renders "
            "IN SHARE ROW EXCLUSIVE MODE"
        )

    def update_yujin_image_overlay_transaction(
        self,
        *,
        project_id: str,
        session_id: str,
        proposal_id: str,
        candidate_id: str,
        segment_id: str,
        asset_id: str,
        text: str,
        session_payload: dict[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        """Atomically re-attest one Yujin image overlay and save its session CAS."""
        existing = self.get_editing_session(
            project_id=project_id,
            session_id=session_id,
        )
        payload = deepcopy(session_payload)
        if int(payload.get("session_revision") or 0) <= int(
            existing.get("session_revision") or 1
        ):
            payload["session_revision"] = int(
                existing.get("session_revision") or 1
            ) + 1

        def attest(connection: sqlite3.Connection) -> None:
            try:
                proposal_row = connection.execute(
                    "SELECT proposal_json, status FROM director_proposals "
                    "WHERE project_id = ? AND proposal_id = ?",
                    (project_id, proposal_id),
                ).fetchone()
                if proposal_row is None or str(proposal_row["status"]) != "ready":
                    raise ValueError("proposal_not_ready")
                proposal = proposal_from_payload(
                    json.loads(str(proposal_row["proposal_json"]))
                )
                candidate = next(
                    item
                    for item in proposal.candidates
                    if item.candidate_id == candidate_id
                )
                metadata = candidate.canonical_metadata
                controls = candidate.controls
                revision_row = connection.execute(
                    "SELECT revision FROM director_asset_index_revisions "
                    "WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
                current_asset_index_revision = (
                    int(revision_row["revision"])
                    if revision_row is not None
                    else 0
                )
                asset_row = connection.execute(
                    "SELECT asset_type, storage_uri, created_at FROM assets "
                    "WHERE project_id = ? AND asset_id = ?",
                    (project_id, asset_id),
                ).fetchone()
                if (
                    proposal.status != "ready"
                    or proposal.diff.get("proposal_mode")
                    != "yujin_actionable_v1"
                    or proposal.source_session_id != session_id
                    or proposal.base_session_revision != expected_revision
                    or segment_id not in proposal.target_segment_ids
                    or current_asset_index_revision
                    != proposal.asset_index_revision
                    or candidate.availability != "actionable"
                    or candidate.review_status != "approved"
                    or candidate.media_type != "overlay"
                    or candidate.asset_id != asset_id
                    or metadata.get("schema_version")
                    != "videobox.yujin-response.v1"
                    or metadata.get("yujin_actionable_operation") is not True
                    or metadata.get("command_kind") != "apply_overlay"
                    or metadata.get("source_media_kind") != "image"
                    or metadata.get("target_segment_id") != segment_id
                    or metadata.get("requires_materialization") is not False
                    or not _valid_b4_candidate_controls(candidate)
                    or not _has_exact_keys(
                        controls, {"overlay_kind", "asset_id", "text"}
                    )
                    or controls.get("overlay_kind") != "image"
                    or controls.get("asset_id") != asset_id
                    or controls.get("text") != text
                    or not candidate.expected_content_sha256
                    or not candidate.media_revision
                    or asset_row is None
                    or str(asset_row["asset_type"]) != AssetType.IMAGE.value
                    or str(asset_row["created_at"] or "")
                    != candidate.media_revision
                ):
                    raise ValueError("attestation_mismatch")
                source = self.resolve_storage_uri(
                    project_id=project_id,
                    storage_uri=str(asset_row["storage_uri"]),
                )
                if (
                    not source.is_file()
                    or sha256_file(source)
                    != candidate.expected_content_sha256
                    or not _session_image_overlay_matches_identity(
                        session_payload=payload,
                        segment_id=segment_id,
                        asset_id=asset_id,
                        text=str(controls["text"]).strip(),
                        asset_uri=str(asset_row["storage_uri"]),
                        expected_content_sha256=candidate.expected_content_sha256,
                        media_revision=candidate.media_revision,
                    )
                ):
                    raise ValueError("source_identity_mismatch")
            except (
                KeyError,
                OSError,
                StopIteration,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                raise EditingSessionRevisionConflict(
                    "Yujin image overlay attestation changed before session save."
                ) from None

        return self._write_editing_session(
            project_id=project_id,
            timeline_id=str(existing["timeline_id"]),
            session_id=session_id,
            session_payload=payload,
            is_new=False,
            created_at=str(existing["created_at"]),
            expected_revision=expected_revision,
            transaction_hook=attest,
            transaction_start_hook=self._begin_director_session_transaction,
        )

    def update_yujin_b4_command_transaction(
        self,
        *,
        project_id: str,
        session_id: str,
        proposal_id: str,
        candidate_id: str,
        command_kind: str,
        segment_id: str,
        controls: dict[str, Any],
        session_payload: dict[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        """Atomically bind one non-image Yujin command to its persisted candidate."""
        existing = self.get_editing_session(
            project_id=project_id,
            session_id=session_id,
        )
        payload = deepcopy(session_payload)
        if int(payload.get("session_revision") or 0) <= int(
            existing.get("session_revision") or 1
        ):
            payload["session_revision"] = int(
                existing.get("session_revision") or 1
            ) + 1

        def attest(connection: sqlite3.Connection) -> None:
            try:
                proposal_row = connection.execute(
                    "SELECT proposal_json, status FROM director_proposals "
                    "WHERE project_id = ? AND proposal_id = ?",
                    (project_id, proposal_id),
                ).fetchone()
                if proposal_row is None or str(proposal_row["status"]) != "ready":
                    raise ValueError("proposal_not_ready")
                proposal = proposal_from_payload(
                    json.loads(str(proposal_row["proposal_json"]))
                )
                candidate = next(
                    item
                    for item in proposal.candidates
                    if item.candidate_id == candidate_id
                )
                metadata = candidate.canonical_metadata
                revision_row = connection.execute(
                    "SELECT revision FROM director_asset_index_revisions "
                    "WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
                current_asset_index_revision = (
                    int(revision_row["revision"])
                    if revision_row is not None
                    else 0
                )
                expected_media_type = {
                    "set_caption_text": "caption",
                    "set_caption_style": "caption",
                    "apply_tts_candidate": "voice",
                    "apply_overlay": "overlay",
                }.get(command_kind)
                if (
                    expected_media_type is None
                    or proposal.status != "ready"
                    or proposal.diff.get("proposal_mode")
                    != "yujin_actionable_v1"
                    or proposal.source_session_id != session_id
                    or proposal.base_session_revision != expected_revision
                    or segment_id not in proposal.target_segment_ids
                    or current_asset_index_revision
                    != proposal.asset_index_revision
                    or candidate.availability != "actionable"
                    or candidate.review_status != "approved"
                    or candidate.media_type != expected_media_type
                    or metadata.get("schema_version")
                    != "videobox.yujin-response.v1"
                    or metadata.get("yujin_actionable_operation") is not True
                    or metadata.get("command_kind") != command_kind
                    or metadata.get("target_segment_id") != segment_id
                    or metadata.get("requires_materialization") is not False
                    or not _valid_b4_candidate_controls(candidate)
                    or _json_plain_value(candidate.controls)
                    != _json_plain_value(controls)
                    or not _session_matches_yujin_b4_command(
                        session_payload=payload,
                        segment_id=segment_id,
                        command_kind=command_kind,
                        controls=controls,
                    )
                ):
                    raise ValueError("attestation_mismatch")
                if command_kind == "apply_tts_candidate":
                    asset_row = connection.execute(
                        "SELECT project_id, asset_type, storage_uri, created_at "
                        "FROM assets WHERE project_id = ? AND asset_id = ?",
                        (project_id, controls["asset_id"]),
                    ).fetchone()
                    persisted = connection.execute(
                        "SELECT segment_id, asset_id, technical_status, "
                        "operator_review_status FROM tts_candidates "
                        "WHERE project_id = ? AND candidate_id = ?",
                        (project_id, controls["candidate_id"]),
                    ).fetchone()
                    if (
                        candidate.asset_id != controls["asset_id"]
                        or not candidate.expected_content_sha256
                        or not candidate.media_revision
                        or metadata.get("source_media_kind")
                        != AssetType.GENERATED_TTS_AUDIO.value
                        or asset_row is None
                        or str(asset_row["project_id"]) != project_id
                        or str(asset_row["asset_type"])
                        != AssetType.GENERATED_TTS_AUDIO.value
                        or str(asset_row["created_at"] or "")
                        != candidate.media_revision
                        or persisted is None
                        or str(persisted["segment_id"]) != segment_id
                        or str(persisted["asset_id"]) != controls["asset_id"]
                        or str(persisted["technical_status"]) != "accepted"
                        or str(persisted["operator_review_status"]) != "approved"
                    ):
                        raise ValueError("tts_attestation_mismatch")
                    source = self.resolve_storage_uri(
                        project_id=project_id,
                        storage_uri=str(asset_row["storage_uri"]),
                    )
                    if (
                        not source.is_file()
                        or sha256_file(source)
                        != candidate.expected_content_sha256
                    ):
                        raise ValueError("tts_source_identity_mismatch")
            except (
                KeyError,
                OSError,
                StopIteration,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                raise EditingSessionRevisionConflict(
                    "Yujin command attestation changed before session save."
                ) from None

        return self._write_editing_session(
            project_id=project_id,
            timeline_id=str(existing["timeline_id"]),
            session_id=session_id,
            session_payload=payload,
            is_new=False,
            created_at=str(existing["created_at"]),
            expected_revision=expected_revision,
            transaction_hook=attest,
            transaction_start_hook=self._begin_director_session_transaction,
        )

    def batch_apply_director_proposal_transaction(
        self, *, project_id: str, session_id: str, proposal_id: str,
        session_payload: dict[str, Any], expected_revision: int, proposal_base_revision: int,
        expected_asset_index_revision: int, staged_assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Register already-verified staged bytes and consume a proposal in one CAS write.

        Filesystem moves cannot participate in SQLite rollback, so every copied
        destination is tracked and removed on any failed database/session write.
        The caller owns removal of the disposable stage files in all cases.
        """
        existing = self.get_editing_session(project_id=project_id, session_id=session_id)
        payload = deepcopy(session_payload)
        if int(payload.get("session_revision") or 0) <= int(existing.get("session_revision") or 1):
            payload["session_revision"] = int(existing.get("session_revision") or 1) + 1
        copied_paths: list[Path] = []

        def consume(connection: sqlite3.Connection) -> None:
            proposal_row = connection.execute("SELECT proposal_json, status FROM director_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
            if proposal_row is None or str(proposal_row["status"]) != "ready":
                raise EditingSessionRevisionConflict("Director proposal is no longer ready.")
            if int(json.loads(str(proposal_row["proposal_json"])).get("base_session_revision") or 0) != proposal_base_revision:
                raise EditingSessionRevisionConflict("Director proposal base revision changed.")
            revision_row = connection.execute("SELECT revision FROM director_asset_index_revisions WHERE project_id = ?", (project_id,)).fetchone()
            current_revision = int(revision_row["revision"]) if revision_row is not None else 0
            if current_revision != expected_asset_index_revision:
                raise EditingSessionRevisionConflict("Director asset index changed before batch apply.")
            for item in staged_assets:
                staged = Path(str(item["staged_path"]))
                destination = Path(str(item["destination_path"]))
                digest = str(item["sha256"])
                if not staged.is_file() or sha256_file(staged) != digest:
                    raise ValueError("candidate_staging_sha_mismatch")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise ValueError("batch_destination_exists")
                shutil.copy2(staged, destination)
                copied_paths.append(destination)
                if sha256_file(destination) != digest:
                    raise ValueError("candidate_project_sha_mismatch")
            materialized_revision = current_revision + 1
            for item in staged_assets:
                record: AssetRecord = item["asset_record"]
                metadata = dict(item["metadata"])
                metadata["director_materialized_asset_index_revision"] = materialized_revision
                connection.execute(
                    """INSERT INTO assets (asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (record.asset_id, record.project_id, record.asset_type.value, record.storage_uri,
                     "director_materialized", None, None, json.dumps(metadata, ensure_ascii=True), record.created_at.isoformat()),
                )
            if staged_assets:
                actual_revision = self._increment_asset_index_revision_with_connection(connection, project_id)
                if actual_revision != materialized_revision:
                    raise EditingSessionRevisionConflict("Director asset index changed during batch apply.")
            now = self._now_iso()
            changed = connection.execute("UPDATE director_proposals SET status = ?, updated_at = ? WHERE proposal_id = ? AND status = 'ready'", ("applied", now, proposal_id))
            if changed.rowcount != 1:
                raise EditingSessionRevisionConflict("Director proposal is no longer ready.")
            connection.execute("INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)", (proposal_id, "applied", "batch_session_apply", now))

        try:
            result = self._write_editing_session(
                project_id=project_id, timeline_id=str(existing["timeline_id"]), session_id=session_id,
                session_payload=payload, is_new=False, created_at=str(existing["created_at"]),
                expected_revision=expected_revision, transaction_hook=consume,
                transaction_start_hook=self._begin_director_session_transaction,
            )
            for manifest_path in {Path(str(item.get("manifest_path"))) for item in staged_assets if item.get("manifest_path")}:
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if isinstance(manifest, dict):
                        manifest["status"] = "committed"
                        temporary = manifest_path.with_suffix(".tmp")
                        temporary.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
                        temporary.replace(manifest_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    # Database commit is authoritative; the next startup can
                    # still prove and reconcile a stale manifest.
                    pass
            return result
        except EditingSessionPostCommitFileWriteError:
            # The DB transaction owns these assets now.  The read path repairs
            # its JSON mirror from SQLite, so preserving the bytes is safer
            # than trying to undo a committed transaction.
            raise
        except Exception:
            for path in copied_paths:
                if path.exists():
                    path.unlink()
            raise

    def refresh_review_for_current_edit(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        """검토본과 승인 기록을 지금 편집본에 맞춰 다시 세운다.

        편집이 승인 기록을 내리는 것 자체는 옳다 -- 옛 편집본을 검토한 결과로 새 편집본을
        승인할 수는 없다. 문제는 **다시 세우는 곳이 초안 생성 한 곳뿐**이었다는 것이다.
        그래서 한 번 편집하면 그 프로젝트는 내보내기까지 갈 길이 없었고, 빈 구간을
        채우려면 편집해야 하는데 그 편집이 승인을 죽여서 빠져나갈 수도 없었다.

        **합성을 다시 계산하지 않는다.** 출력 경로는 언제나 timeline과 session을 함께
        materialize 하므로 timeline의 tracks는 손댈 것이 없다. 여기서 하는 일은
        지금 편집본에서 **아직 비어 있는 장면만** 확인할 항목으로 남기고, 그 결과를
        timeline과 승인 기록에 같은 revision으로 적는 것이다.

        승인까지 하지는 않는다. 상태는 `blocked`(아직 빈 장면이 있음) 또는 `draft`이며,
        `approved`로 올리는 것은 owner가 검토 화면에서 누를 일이다.
        """
        session = self.get_editing_session(project_id=project_id, session_id=session_id)
        timeline_id = str(session.get("timeline_id") or "").strip()
        if not timeline_id:
            raise KeyError(f"Editing session has no timeline: {session_id}")
        session_revision = int(session.get("session_revision") or 1)
        file_path = self._timeline_file_path(project_id=project_id, timeline_id=timeline_id)
        timeline = json.loads(file_path.read_text(encoding="utf-8"))
        materialized = materialize_editing_session_timeline(
            timeline=timeline, editing_session=session, project_id=project_id
        )
        # 자산을 채운 장면은 override가 임시 클립 구간을 덮으므로 materialize 결과에서
        # 사라진다. 확인할 항목을 저장된 목록에서 베끼지 않고 여기서 다시 유도하는
        # 이유다 -- 베끼면 owner가 채운 뒤에도 "자산이 필요하다"가 남는다.
        remaining_gap_slot_ids = {
            str(clip.get("gap_slot_id") or "")
            for track in materialized.get("tracks", [])
            if isinstance(track, dict)
            for clip in track.get("clips", [])
            if isinstance(clip, dict) and str(clip.get("gap_slot_id") or "").strip()
        }
        remaining_gaps = [
            gap
            for gap in timeline.get("gap_slots", [])
            if isinstance(gap, dict) and str(gap.get("gap_slot_id") or "") in remaining_gap_slot_ids
        ]
        review_flags = [
            {
                "code": "draft_gap_placeholder",
                "segment_id": gap.get("segment_id") or gap.get("gap_slot_id"),
                "message": "자산이 필요한 임시 장면입니다.",
            }
            for gap in remaining_gaps
        ]
        timeline["source_session_id"] = session_id
        timeline["source_session_revision"] = session_revision
        timeline["review_flags"] = review_flags
        # 완성본·CapCut 관문은 확인할 항목이 아니라 이 둘을 본다
        # (`local_pipeline.assert_timeline_output_allowed`). 초안 때 적어 둔 값을 그대로
        # 두면 owner가 빈 장면을 다 채워도 완성본을 만들 수 없다. 임시 클립은 렌더에
        # 들어가지도 않는다 -- 렌더도 session을 materialize 한 뒤 합성한다.
        timeline["gap_slots"] = remaining_gaps
        timeline["placeholder_policy"] = "in_app_only" if remaining_gaps else None
        file_path.write_text(json.dumps(timeline, indent=2, ensure_ascii=True), encoding="utf-8")
        return self.save_review_state(
            project_id=project_id,
            timeline_id=timeline_id,
            status="blocked" if review_flags else "draft",
            source_session_id=session_id,
            source_session_revision=session_revision,
            source_variant_id=(str(timeline.get("source_variant_id")) if timeline.get("source_variant_id") else None),
            source_variant_revision=(
                int(timeline["source_variant_revision"])
                if timeline.get("source_variant_revision") is not None
                else None
            ),
        )

    def save_review_state(
        self,
        *,
        project_id: str,
        timeline_id: str,
        status: str,
        source_session_id: str | None = None,
        source_session_revision: int | None = None,
        source_variant_id: str | None = None,
        source_variant_revision: int | None = None,
    ) -> dict[str, Any]:
        if status not in {"draft", "blocked", "approved"}:
            raise ValueError(f"Unsupported review status: {status}")
        if source_session_id is None:
            session = self._fetchone(
                project_id,
                """
                SELECT session_id, session_revision
                FROM editing_sessions
                WHERE project_id = ? AND timeline_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (project_id, timeline_id),
            )
        else:
            session = self._fetchone(
                project_id,
                """
                SELECT session_id, session_revision
                FROM editing_sessions
                WHERE project_id = ? AND timeline_id = ? AND session_id = ?
                """,
                (project_id, timeline_id, source_session_id),
            )
        if session is not None:
            source_session_id = str(session["session_id"])
            if source_session_revision is None:
                source_session_revision = int(session["session_revision"])
        approved_at = self._now_iso() if status == "approved" else None
        updated_at = self._now_iso()
        self._execute(
            project_id,
            """
            INSERT INTO review_approvals (
                timeline_id,
                project_id,
                status,
                approved_at,
                updated_at,
                source_session_id,
                source_session_revision,
                source_variant_id,
                source_variant_revision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(timeline_id) DO UPDATE SET
                status = excluded.status,
                approved_at = excluded.approved_at,
                updated_at = excluded.updated_at,
                source_session_id = excluded.source_session_id,
                source_session_revision = excluded.source_session_revision,
                source_variant_id = excluded.source_variant_id,
                source_variant_revision = excluded.source_variant_revision,
                is_current = 1,
                invalidated_at = NULL,
                invalidated_reason = NULL
            """,
            (
                timeline_id,
                project_id,
                status,
                approved_at,
                updated_at,
                source_session_id,
                source_session_revision,
                source_variant_id,
                source_variant_revision,
            ),
        )
        self.clear_operator_guidance(project_id=project_id, timeline_id=timeline_id)
        return self.get_review_state(project_id=project_id, timeline_id=timeline_id)

    def update_recommendation_review(
        self,
        *,
        project_id: str,
        recommendation_id: str,
        auto_apply_allowed: bool,
        review_required: bool,
        decision_state: str | None = None,
    ) -> None:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """
                UPDATE recommendations
                SET auto_apply_allowed = ?, review_required = ?, decision_state = COALESCE(?, decision_state)
                WHERE recommendation_id = ? AND project_id = ?
                """,
                (
                    1 if auto_apply_allowed else 0,
                    1 if review_required else 0,
                    decision_state,
                    recommendation_id,
                    project_id,
                ),
            )
            connection.commit()
        finally:
            connection.close()
        if cursor.rowcount == 0:
            raise KeyError(f"Recommendation not found: {recommendation_id}")

    def update_timeline_run(
        self,
        *,
        project_id: str,
        timeline_id: str,
        timeline_payload: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
        payload = deepcopy(timeline_payload)
        payload.pop("summary", None)
        payload["timeline_id"] = timeline_id
        payload["project_id"] = project_id
        payload["version"] = str(payload.get("version", existing.get("version", "v001")))
        payload["output_mode"] = str(payload.get("output_mode", existing.get("output_mode", "review")))
        payload["file_uri"] = str(existing.get("file_uri"))
        payload["created_at"] = str(existing.get("created_at"))

        file_path = self._timeline_file_path(project_id=project_id, timeline_id=timeline_id)
        file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

        summary_json = _timeline_summary_json(payload)
        self._execute(
            project_id,
            """
            UPDATE timelines
            SET version = ?, output_mode = ?, summary_json = ?
            WHERE timeline_id = ? AND project_id = ?
            """,
            (
                payload["version"],
                payload["output_mode"],
                summary_json,
                timeline_id,
                project_id,
            ),
        )
        return self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)

    def discard_partial_regeneration_timeline(
        self,
        *,
        project_id: str,
        timeline_id: str,
    ) -> None:
        """Remove a timeline published before its owning session CAS lost.

        Partial regeneration constructs a new timeline before it can atomically
        advance the editing session.  A losing CAS must therefore make that
        timeline and its initial review ineligible before reporting conflict.
        """
        connection = self._connection(project_id)
        timeline_path: Path | None = None
        try:
            row = connection.execute(
                "SELECT file_uri FROM timelines WHERE project_id = ? AND timeline_id = ?",
                (project_id, timeline_id),
            ).fetchone()
            if row is None:
                return
            timeline_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE review_approvals SET is_current = 0, invalidated_at = ?, invalidated_reason = ? WHERE project_id = ? AND timeline_id = ?",
                (self._now_iso(), "partial_regeneration_cas_conflict", project_id, timeline_id),
            )
            connection.execute(
                "DELETE FROM review_approvals WHERE project_id = ? AND timeline_id = ?",
                (project_id, timeline_id),
            )
            connection.execute(
                "DELETE FROM timelines WHERE project_id = ? AND timeline_id = ?",
                (project_id, timeline_id),
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        if timeline_path is not None:
            timeline_path.unlink(missing_ok=True)

    def mark_partial_regeneration_cleanup_needed(
        self,
        *,
        project_id: str,
        timeline_id: str,
    ) -> None:
        """Make a failed-to-delete candidate ineligible while reconciliation retries."""
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE review_approvals SET is_current = 0, invalidated_at = ?, invalidated_reason = ? "
                "WHERE project_id = ? AND timeline_id = ?",
                (
                    self._now_iso(),
                    "partial_regeneration_cleanup_failed",
                    project_id,
                    timeline_id,
                ),
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def save_partial_regeneration_run(
        self,
        *,
        project_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "analysis" / "partial_regenerations",
            "partial_regeneration_*.json",
        )
        partial_regeneration_id = f"partial_regeneration_{sequence:03d}"
        created_at = self._now_iso()
        run_payload = {
            "partial_regeneration_id": partial_regeneration_id,
            "created_at": created_at,
            **payload,
        }
        file_path = (
            self.project_root(project_id)
            / "analysis"
            / "partial_regenerations"
            / f"{partial_regeneration_id}.json"
        )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(run_payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return run_payload

    def get_partial_regeneration_run(
        self,
        *,
        project_id: str,
        partial_regeneration_id: str,
    ) -> dict[str, Any]:
        file_path = (
            self.project_root(project_id)
            / "analysis"
            / "partial_regenerations"
            / f"{partial_regeneration_id}.json"
        )
        if not file_path.exists():
            raise KeyError(f"Partial regeneration run not found: {partial_regeneration_id}")
        return json.loads(file_path.read_text(encoding="utf-8"))

    def discard_partial_regeneration_run(
        self,
        *,
        project_id: str,
        partial_regeneration_id: str,
    ) -> None:
        """Remove a run that was written before its owning job was published."""
        file_path = (
            self.project_root(project_id)
            / "analysis"
            / "partial_regenerations"
            / f"{partial_regeneration_id}.json"
        )
        file_path.unlink(missing_ok=True)

    def update_partial_regeneration_run(
        self,
        *,
        project_id: str,
        partial_regeneration_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self.get_partial_regeneration_run(
            project_id=project_id,
            partial_regeneration_id=partial_regeneration_id,
        )

        updated = {
            **existing,
            **deepcopy(payload),
            "partial_regeneration_id": partial_regeneration_id,
            "created_at": str(existing["created_at"]),
        }
        file_path = (
            self.project_root(project_id)
            / "analysis"
            / "partial_regenerations"
            / f"{partial_regeneration_id}.json"
        )
        file_path.write_text(json.dumps(updated, indent=2, ensure_ascii=True), encoding="utf-8")
        return updated

    def create_director_conversation(self, *, project_id: str, session_id: str, conversation_id: str) -> dict[str, Any]:
        self.get_editing_session(project_id=project_id, session_id=session_id)
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            connection.execute(
                "INSERT INTO director_conversations (conversation_id, project_id, session_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, project_id, session_id, now, now),
            )
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            row = connection.execute("SELECT project_id, session_id FROM director_conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            if row is None or str(row["project_id"]) != project_id or str(row["session_id"]) != session_id:
                raise ValueError("conversation_id_conflict") from None
        finally:
            connection.close()
        return {"conversation_id": conversation_id, "project_id": project_id, "session_id": session_id}

    def get_director_conversation(self, *, project_id: str, conversation_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            "SELECT conversation_id, project_id, session_id FROM director_conversations WHERE conversation_id = ? AND project_id = ?",
            (conversation_id, project_id),
        )
        if row is None:
            raise KeyError("director_conversation_missing")
        return dict(row)

    def list_director_conversations(self, *, project_id: str) -> list[dict[str, Any]]:
        """지울 수 있으려면 무엇이 있는지부터 보여야 한다."""
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT c.conversation_id, c.session_id, c.created_at, c.updated_at,
                       (SELECT COUNT(*) FROM director_messages m
                         WHERE m.conversation_id = c.conversation_id
                           AND m.project_id = c.project_id) AS message_count
                FROM director_conversations c
                WHERE c.project_id = ?
                ORDER BY c.updated_at DESC, c.conversation_id
                """,
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def delete_director_conversation(self, *, project_id: str, conversation_id: str) -> bool:
        """대화와 그 메시지를 함께 지운다.

        대화만 지우고 메시지를 남기면 주인 없는 기록이 남는다. 지울 것이
        없으면 지웠다고 하지 않는다 -- 화면이 지운 척하면 owner는 목록이
        왜 그대로인지 알 수 없다.
        """
        connection = self._connection(project_id)
        try:
            connection.execute(
                "DELETE FROM director_messages WHERE conversation_id = ? AND project_id = ?",
                (conversation_id, project_id),
            )
            cursor = connection.execute(
                "DELETE FROM director_conversations WHERE conversation_id = ? AND project_id = ?",
                (conversation_id, project_id),
            )
            connection.commit()
            return int(cursor.rowcount) > 0
        finally:
            connection.close()

    def latest_director_conversation(self, *, project_id: str, session_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            project_id,
            "SELECT conversation_id, project_id, session_id FROM director_conversations WHERE project_id = ? AND session_id = ? ORDER BY updated_at DESC, conversation_id DESC LIMIT 1",
            (project_id, session_id),
        )
        return dict(row) if row is not None else None

    def append_director_message(
        self, *, project_id: str, session_id: str, conversation_id: str, role: str,
        text: str, proposal_id: str | None = None, client_message_id: str | None = None,
    ) -> dict[str, Any]:
        if role not in {"user", "assistant"} or not text.strip():
            raise ValueError("director message requires a supported role and text")
        now = self._now_iso()
        message_id = uuid.uuid4().hex
        connection = self._connection(project_id)
        try:
            self._begin_director_hermes_transaction(connection)
            session = connection.execute("SELECT session_id FROM editing_sessions WHERE session_id = ? AND project_id = ?", (session_id, project_id)).fetchone()
            if session is None:
                raise KeyError("editing_session_missing")
            conversation = connection.execute("SELECT project_id, session_id FROM director_conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            if conversation is None:
                raise KeyError("director_conversation_missing")
            if str(conversation["project_id"]) != project_id or str(conversation["session_id"]) != session_id:
                raise ValueError("conversation_scope_mismatch")
            message_order = self._next_director_message_order(
                connection, conversation_id=conversation_id
            )
            connection.execute(
                "INSERT INTO director_messages (message_id, conversation_id, project_id, session_id, role, text, proposal_id, metadata_json, client_message_id, message_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?, ?)",
                (message_id, conversation_id, project_id, session_id, role, text, proposal_id, client_message_id, message_order, now),
            )
            connection.execute("UPDATE director_conversations SET updated_at = ? WHERE conversation_id = ?", (now, conversation_id))
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        return {"message_id": message_id, "conversation_id": conversation_id, "project_id": project_id, "session_id": session_id, "role": role, "text": text, "proposal_id": proposal_id, "client_message_id": client_message_id, "created_at": now}

    def list_director_messages(self, *, project_id: str, conversation_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            project_id,
            """
            SELECT message_id, conversation_id, project_id, session_id, role,
                   text, proposal_id, metadata_json, client_message_id, created_at
            FROM director_messages
            WHERE conversation_id = ? AND project_id = ?
            ORDER BY message_order, message_id
            """,
            (conversation_id, project_id),
        )
        return [self._director_message_payload(row) for row in rows]

    def get_director_exchange_by_client_message_id(self, *, project_id: str, session_id: str, conversation_id: str, client_message_id: str, user_text: str) -> dict[str, Any] | None:
        conversation = self._fetchone(project_id, "SELECT session_id FROM director_conversations WHERE conversation_id = ? AND project_id = ?", (conversation_id, project_id))
        if conversation is None:
            raise KeyError("director_conversation_missing")
        if str(conversation["session_id"]) != session_id:
            raise ValueError("conversation_scope_mismatch")
        hermes_run = self._fetchone(
            project_id,
            """
            SELECT user_text, user_message_id, assistant_message_id
            FROM director_hermes_runs
            WHERE project_id = ? AND session_id = ? AND conversation_id = ?
              AND client_message_id = ?
            """,
            (project_id, session_id, conversation_id, client_message_id),
        )
        if hermes_run is not None:
            if str(hermes_run["user_text"]) != user_text:
                raise ValueError("client_message_id_reused_with_different_content")
            assistant_message_id = hermes_run["assistant_message_id"]
            if assistant_message_id is None:
                raise ValueError("incomplete persisted director exchange")
            user_row = self._fetchone(
                project_id,
                """
                SELECT message_id, conversation_id, project_id, session_id, role,
                       text, proposal_id, metadata_json, client_message_id, created_at
                FROM director_messages
                WHERE project_id = ? AND conversation_id = ? AND message_id = ?
                """,
                (project_id, conversation_id, str(hermes_run["user_message_id"])),
            )
            assistant_row = self._fetchone(
                project_id,
                """
                SELECT message_id, conversation_id, project_id, session_id, role,
                       text, proposal_id, metadata_json, client_message_id, created_at
                FROM director_messages
                WHERE project_id = ? AND conversation_id = ? AND message_id = ?
                """,
                (project_id, conversation_id, str(assistant_message_id)),
            )
            if user_row is None or assistant_row is None:
                raise ValueError("incomplete persisted director exchange")
            return {
                "user_message": self._director_message_payload(user_row),
                "assistant_message": self._director_message_payload(assistant_row),
            }
        rows = self.list_director_messages(project_id=project_id, conversation_id=conversation_id)
        for index, item in enumerate(rows):
            if item.get("client_message_id") != client_message_id:
                continue
            if item.get("text") != user_text:
                raise ValueError("client_message_id_reused_with_different_content")
            if index + 1 >= len(rows) or rows[index + 1].get("role") != "assistant":
                raise ValueError("incomplete persisted director exchange")
            return {"user_message": item, "assistant_message": rows[index + 1]}
        return None

    def claim_director_message(self, *, project_id: str, session_id: str, conversation_id: str, client_message_id: str, user_text: str) -> str | None:
        """Exactly one caller owns local generation for a client message ID."""
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            now, token = self._now_iso(), uuid.uuid4().hex
            conversation = connection.execute("SELECT project_id, session_id FROM director_conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            if conversation is None:
                raise KeyError("director_conversation_missing")
            if str(conversation["project_id"]) != project_id or str(conversation["session_id"]) != session_id:
                raise ValueError("conversation_scope_mismatch")
            row = connection.execute("SELECT project_id, session_id, user_text, heartbeat_at FROM director_message_claims WHERE conversation_id = ? AND client_message_id = ?", (conversation_id, client_message_id)).fetchone()
            if row is not None:
                if str(row["project_id"]) != project_id or str(row["session_id"]) != session_id:
                    raise ValueError("conversation_scope_mismatch")
                if str(row["user_text"]) != user_text:
                    raise ValueError("client_message_id_reused_with_different_content")
                claimed_at = datetime.fromisoformat(str(row["heartbeat_at"]))
                # Local runtime generation has a bounded 30s request timeout;
                # keep the lease materially above it so a live slow request is
                # never reclaimed merely for crossing that timeout boundary.
                if claimed_at.astimezone(UTC) <= self._clock().astimezone(UTC) - timedelta(seconds=300):
                    connection.execute(
                        "UPDATE director_message_claims SET owner_token = ?, heartbeat_at = ? WHERE conversation_id = ? AND client_message_id = ?",
                        (token, now, conversation_id, client_message_id),
                    )
                    connection.commit()
                    return token
                connection.commit()
                return False
            connection.execute("INSERT INTO director_message_claims (conversation_id, client_message_id, project_id, session_id, user_text, created_at, owner_token, heartbeat_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (conversation_id, client_message_id, project_id, session_id, user_text, now, token, now))
            connection.commit()
            return token
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def heartbeat_director_message_claim(self, *, project_id: str, conversation_id: str, client_message_id: str, owner_token: str) -> bool:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("UPDATE director_message_claims SET heartbeat_at = ? WHERE conversation_id = ? AND client_message_id = ? AND owner_token = ?", (self._now_iso(), conversation_id, client_message_id, owner_token))
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def append_director_exchange(
        self, *, project_id: str, session_id: str, conversation_id: str, client_message_id: str,
        user_text: str, assistant_text: str, proposal_id: str | None = None, assistant_metadata: dict[str, Any] | None = None, owner_token: str | None = None,
    ) -> dict[str, Any]:
        """Persist the request and response atomically; retry returns the original DTO."""
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            self._begin_director_hermes_transaction(connection)
            session = connection.execute("SELECT session_id FROM editing_sessions WHERE session_id = ? AND project_id = ?", (session_id, project_id)).fetchone()
            if session is None:
                raise KeyError("editing_session_missing")
            if owner_token is not None:
                claim = connection.execute("SELECT owner_token FROM director_message_claims WHERE conversation_id = ? AND client_message_id = ?", (conversation_id, client_message_id)).fetchone()
                if claim is None or str(claim["owner_token"]) != owner_token:
                    raise ValueError("director_message_claim_lost")
            conversation = connection.execute("SELECT project_id, session_id FROM director_conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            if conversation is None:
                raise KeyError("director_conversation_missing")
            if str(conversation["project_id"]) != project_id or str(conversation["session_id"]) != session_id:
                raise ValueError("conversation_scope_mismatch")
            existing = connection.execute(
                """
                SELECT message_id, conversation_id, project_id, session_id, role,
                       text, proposal_id, metadata_json, client_message_id,
                       message_order, created_at
                FROM director_messages
                WHERE conversation_id = ? AND client_message_id = ?
                """,
                (conversation_id, client_message_id),
            ).fetchone()
            if existing is not None:
                if str(existing["text"]) != user_text:
                    raise ValueError("client_message_id_reused_with_different_content")
                assistant_rows = connection.execute(
                    """
                    SELECT message_id, conversation_id, project_id, session_id,
                           role, text, proposal_id, metadata_json,
                           client_message_id, message_order, created_at
                    FROM director_messages
                    WHERE conversation_id = ? AND role = 'assistant'
                      AND message_order = ?
                    """,
                    (conversation_id, int(existing["message_order"]) + 1),
                ).fetchall()
                if len(assistant_rows) != 1:
                    raise ValueError("incomplete persisted director exchange")
                connection.commit()
                return {
                    "user_message": self._director_message_payload(existing),
                    "assistant_message": self._director_message_payload(
                        assistant_rows[0]
                    ),
                }
            user_id, assistant_id = uuid.uuid4().hex, uuid.uuid4().hex
            user_message_order = self._next_director_message_order(
                connection, conversation_id=conversation_id
            )
            connection.execute("INSERT INTO director_messages (message_id, conversation_id, project_id, session_id, role, text, proposal_id, metadata_json, client_message_id, message_order, created_at) VALUES (?, ?, ?, ?, 'user', ?, NULL, '{}', ?, ?, ?)", (user_id, conversation_id, project_id, session_id, user_text, client_message_id, user_message_order, now))
            connection.execute("INSERT INTO director_messages (message_id, conversation_id, project_id, session_id, role, text, proposal_id, metadata_json, client_message_id, message_order, created_at) VALUES (?, ?, ?, ?, 'assistant', ?, ?, ?, NULL, ?, ?)", (assistant_id, conversation_id, project_id, session_id, assistant_text, proposal_id, json.dumps(assistant_metadata or {}, ensure_ascii=True, sort_keys=True), user_message_order + 1, now))
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        return {"user_message": {"message_id": user_id, "conversation_id": conversation_id, "project_id": project_id, "session_id": session_id, "role": "user", "text": user_text, "proposal_id": None, "metadata": {}, "client_message_id": client_message_id, "created_at": now}, "assistant_message": {"message_id": assistant_id, "conversation_id": conversation_id, "project_id": project_id, "session_id": session_id, "role": "assistant", "text": assistant_text, "proposal_id": proposal_id, "metadata": assistant_metadata or {}, "client_message_id": None, "created_at": now}}

    def _director_message_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload.pop("message_order", None)
        payload["metadata"] = self._json_object(str(payload.pop("metadata_json", "{}")))
        return payload

    @staticmethod
    def _next_director_message_order(
        connection: Any, *, conversation_id: str
    ) -> int:
        if not isinstance(connection, sqlite3.Connection):
            connection.execute(
                "SELECT conversation_id FROM director_conversations "
                "WHERE conversation_id = ? FOR UPDATE",
                (conversation_id,),
            )
        row = connection.execute(
            "SELECT MAX(message_order) AS max_message_order "
            "FROM director_messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return int(row["max_message_order"] or 0) + 1

    def director_proposal_exists(
        self, *, project_id: str, proposal_id: str
    ) -> bool:
        row = self._fetchone(
            project_id,
            "SELECT 1 FROM director_proposals "
            "WHERE project_id = ? AND proposal_id = ?",
            (project_id, proposal_id),
        )
        return row is not None

    def save_director_proposal(self, project_id: str, proposal: DirectorProposal) -> DirectorProposal:
        payload = proposal_to_payload(proposal)
        canonical_payload = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""
            INSERT INTO director_proposals (proposal_id, project_id, status, source_session_id, source_script_segment_ids_json, proposal_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (proposal.proposal_id, project_id, proposal.status, proposal.source_session_id, json.dumps(list(proposal.source_script_segment_ids)), canonical_payload, now, now))
            connection.execute("INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)", (proposal.proposal_id, proposal.status, "created", now))
            connection.commit()
        except sqlite3.IntegrityError:
            if connection.in_transaction:
                connection.rollback()
            existing = self._fetchone(project_id, "SELECT proposal_json FROM director_proposals WHERE proposal_id = ?", (proposal.proposal_id,))
            if existing is not None:
                stored = json.dumps(json.loads(str(existing["proposal_json"])), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                if stored == canonical_payload:
                    return proposal
            raise ValueError(f"Director proposal is immutable and cannot be overwritten: {proposal.proposal_id}") from None
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        return proposal

    def get_director_proposal(self, project_id: str, proposal_id: str, now: datetime | None = None) -> DirectorProposal:
        row = self._fetchone(project_id, "SELECT proposal_json, status FROM director_proposals WHERE proposal_id = ?", (proposal_id,))
        if row is None:
            raise KeyError(f"Director proposal not found: {proposal_id}")
        proposal = proposal_from_payload(json.loads(str(row["proposal_json"])))
        current_status = str(row["status"])
        instant = now or self._clock()
        if current_status == "ready" and proposal.expires_at and datetime.fromisoformat(proposal.expires_at).astimezone(UTC) <= instant.astimezone(UTC):
            changed_at = self._now_iso()
            connection = self._connection(project_id)
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE director_proposals SET status = ?, updated_at = ? WHERE proposal_id = ?", ("expired", changed_at, proposal_id))
                connection.execute("INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)", (proposal_id, "expired", "expiry", changed_at))
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()
            current_status = "expired"
        if proposal.status != current_status:
            from dataclasses import replace
            proposal = replace(proposal, status=current_status)
        return proposal

    def list_director_proposals(self, project_id: str) -> list[DirectorProposal]:
        rows = self._fetchall(project_id, "SELECT proposal_id FROM director_proposals ORDER BY created_at, proposal_id", ())
        return [self.get_director_proposal(project_id, str(row["proposal_id"])) for row in rows]

    def get_director_proposal_lifecycle(self, project_id: str, proposal_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(project_id, "SELECT status, reason, changed_at FROM director_proposal_lifecycle_events WHERE proposal_id = ? ORDER BY event_id", (proposal_id,))
        return [dict(row) for row in rows]

    def save_director_preferences(self, project_id: str, preferences: dict[str, Any]) -> dict[str, list[str]]:
        allowed = ("pin_asset", "exclude_asset", "exclude_creator", "exclude_tag")
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT preferences_json FROM director_preferences WHERE project_id = ?", (project_id,)).fetchone()
            current = json.loads(str(row["preferences_json"])) if row else {key: [] for key in allowed}
            canonical = {
                key: sorted({str(value).strip() for value in preferences[key] if str(value).strip()})
                if key in preferences else list(current.get(key, []))
                for key in allowed
            }
            connection.execute("INSERT INTO director_preferences (project_id, preferences_json, updated_at) VALUES (?, ?, ?) ON CONFLICT(project_id) DO UPDATE SET preferences_json=excluded.preferences_json, updated_at=excluded.updated_at", (project_id, json.dumps(canonical, ensure_ascii=True), self._now_iso()))
            connection.commit()
            return canonical
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def get_director_preferences(self, project_id: str) -> dict[str, list[str]]:
        row = self._fetchone(project_id, "SELECT preferences_json FROM director_preferences WHERE project_id = ?", (project_id,))
        return json.loads(str(row["preferences_json"])) if row else {"pin_asset": [], "exclude_asset": [], "exclude_creator": [], "exclude_tag": []}

    def get_project_media_library_preferences(self, project_id: str) -> dict[str, list[str]]:
        row = self._fetchone(
            project_id,
            "SELECT preferences_json FROM project_media_library_preferences WHERE project_id = ?",
            (project_id,),
        )
        return json.loads(str(row["preferences_json"])) if row else {"favorite_asset_ids": [], "recent_asset_ids": []}

    def set_project_media_library_favorite(
        self, *, project_id: str, library_asset_id: str, enabled: bool,
    ) -> dict[str, list[str]]:
        return self._mutate_project_media_library_preferences(
            project_id=project_id,
            mutate=lambda preferences: {
                **preferences,
                "favorite_asset_ids": sorted(
                    ([item for item in preferences["favorite_asset_ids"] if item != library_asset_id] + ([library_asset_id] if enabled else []))
                ),
            },
        )

    def mark_project_media_library_recent(
        self, *, project_id: str, library_asset_id: str,
    ) -> dict[str, list[str]]:
        return self._mutate_project_media_library_preferences(
            project_id=project_id,
            mutate=lambda preferences: {
                **preferences,
                "recent_asset_ids": [library_asset_id, *[item for item in preferences["recent_asset_ids"] if item != library_asset_id]][:10],
            },
        )

    def _mutate_project_media_library_preferences(self, *, project_id: str, mutate: Callable[[dict[str, list[str]]], dict[str, list[str]]]) -> dict[str, list[str]]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT preferences_json FROM project_media_library_preferences WHERE project_id = ?", (project_id,)).fetchone()
            current = json.loads(str(row["preferences_json"])) if row else {"favorite_asset_ids": [], "recent_asset_ids": []}
            preferences = mutate({key: list(current.get(key, [])) for key in ("favorite_asset_ids", "recent_asset_ids")})
            self._save_project_media_library_preferences_with_connection(connection, project_id, preferences)
            connection.commit()
            return preferences
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _save_project_media_library_preferences(self, project_id: str, preferences: dict[str, list[str]]) -> None:
        canonical = {
            key: [str(value).strip() for value in preferences.get(key, []) if str(value).strip()]
            for key in ("favorite_asset_ids", "recent_asset_ids")
        }
        self._execute(
            project_id,
            "INSERT INTO project_media_library_preferences (project_id, preferences_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(project_id) DO UPDATE SET preferences_json=excluded.preferences_json, updated_at=excluded.updated_at",
            (project_id, json.dumps(canonical, ensure_ascii=True), self._now_iso()),
        )

    def _save_project_media_library_preferences_with_connection(self, connection: sqlite3.Connection, project_id: str, preferences: dict[str, list[str]]) -> None:
        canonical = {
            key: [str(value).strip() for value in preferences.get(key, []) if str(value).strip()]
            for key in ("favorite_asset_ids", "recent_asset_ids")
        }
        connection.execute(
            "INSERT INTO project_media_library_preferences (project_id, preferences_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(project_id) DO UPDATE SET preferences_json=excluded.preferences_json, updated_at=excluded.updated_at",
            (project_id, json.dumps(canonical, ensure_ascii=True), self._now_iso()),
        )

    def get_asset_index_revision(self, project_id: str) -> int:
        row = self._fetchone(project_id, "SELECT revision FROM director_asset_index_revisions WHERE project_id = ?", (project_id,))
        return int(row["revision"]) if row else 0

    def read_director_proposal_snapshot(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        """Return every proposal input from one SQLite read snapshot.

        Proposal composition must never pair candidates from one library state
        with a revision from another state.
        """
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN")
            session_row = connection.execute(
                "SELECT session_json, summary_json, session_revision, created_at, updated_at FROM editing_sessions WHERE project_id = ? AND session_id = ?",
                (project_id, session_id),
            ).fetchone()
            if session_row is None:
                raise KeyError(f"Editing session not found: {session_id}")
            session = json.loads(str(session_row["session_json"] or "{}"))
            session["summary"] = json.loads(str(session_row["summary_json"] or "{}"))
            session["session_revision"] = int(session_row["session_revision"])
            session["created_at"], session["updated_at"] = session_row["created_at"], session_row["updated_at"]
            asset_rows = connection.execute("SELECT asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at FROM assets WHERE project_id = ? ORDER BY created_at ASC", (project_id,)).fetchall()
            analysis_rows = connection.execute("SELECT * FROM media_analysis_runs WHERE project_id = ? ORDER BY created_at ASC, analysis_id ASC", (project_id,)).fetchall()
            preference_row = connection.execute("SELECT preferences_json FROM director_preferences WHERE project_id = ?", (project_id,)).fetchone()
            revision_row = connection.execute("SELECT revision FROM director_asset_index_revisions WHERE project_id = ?", (project_id,)).fetchone()
            hook = getattr(self, "_director_proposal_snapshot_hook", None)
            if hook is not None:
                hook()
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        assets = [{**dict(row), "metadata": json.loads(str(row["metadata_json"] or "{}"))} for row in asset_rows]
        analyses = [self._media_analysis_payload(row) for row in analysis_rows]
        return {
            "session": session, "assets": assets, "analyses": analyses,
            "preferences": json.loads(str(preference_row["preferences_json"])) if preference_row else {"pin_asset": [], "exclude_asset": [], "exclude_creator": [], "exclude_tag": []},
            "asset_index_revision": int(revision_row["revision"]) if revision_row else 0,
        }

    def next_director_proposal_revision(self, project_id: str) -> int:
        """Allocate a durable, project-scoped monotonic proposal revision."""
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO director_proposal_revisions (project_id, revision) VALUES (?, 1) ON CONFLICT(project_id) DO UPDATE SET revision = revision + 1",
                (project_id,),
            )
            row = connection.execute("SELECT revision FROM director_proposal_revisions WHERE project_id = ?", (project_id,)).fetchone()
            connection.commit()
            return int(row["revision"])
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def bump_asset_index_revision(self, project_id: str) -> int:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            revision = self._increment_asset_index_revision_with_connection(connection, project_id)
            connection.commit()
            return revision
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _increment_asset_index_revision_with_connection(self, connection: sqlite3.Connection, project_id: str) -> int:
        connection.execute("INSERT INTO director_asset_index_revisions (project_id, revision) VALUES (?, 1) ON CONFLICT(project_id) DO UPDATE SET revision = revision + 1", (project_id,))
        row = connection.execute("SELECT revision FROM director_asset_index_revisions WHERE project_id = ?", (project_id,)).fetchone()
        return int(row["revision"])

    def _execute_asset_index_mutation(self, project_id: str, statement: str, parameters: tuple[Any, ...]) -> None:
        """Commit an eligible asset-index mutation and its revision as one unit."""
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(statement, parameters)
            self._increment_asset_index_revision_with_connection(connection, project_id)
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def mark_director_proposals_stale_for_script_alignment(self, project_id: str, source_session_id: str, source_script_segment_ids: list[str]) -> int:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            changed = self._mark_director_proposals_stale_with_connection(connection, project_id, source_session_id, source_script_segment_ids)
            connection.commit()
            return changed
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _mark_director_proposals_stale_with_connection(self, connection: sqlite3.Connection, project_id: str, source_session_id: str, source_script_segment_ids: list[str]) -> int:
        wanted = set(source_script_segment_ids)
        rows = connection.execute("SELECT proposal_id, proposal_json FROM director_proposals WHERE source_session_id = ? AND status = 'ready'", (source_session_id,)).fetchall()
        changed = 0
        for row in rows:
            payload = json.loads(str(row["proposal_json"]))
            if not wanted.intersection(payload.get("source_script_segment_ids", [])):
                continue
            changed_at = self._now_iso()
            connection.execute("UPDATE director_proposals SET status = 'stale', updated_at = ? WHERE proposal_id = ?", (changed_at, row["proposal_id"]))
            connection.execute("INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)", (row["proposal_id"], "stale", "script_alignment", changed_at))
            changed += 1
        return changed

    def update_script_draft_alignment_and_stale_proposals(self, *, project_id: str, session_id: str, session_payload: dict[str, Any], expected_revision: int, source_script_segment_ids: list[str]) -> dict[str, Any]:
        existing = self.get_editing_session(project_id=project_id, session_id=session_id)
        payload = deepcopy(session_payload)
        if int(payload.get("session_revision") or 0) <= int(existing.get("session_revision") or 1):
            payload["session_revision"] = int(existing.get("session_revision") or 1) + 1
        return self._write_editing_session(project_id=project_id, timeline_id=str(existing["timeline_id"]), session_id=session_id, session_payload=payload, is_new=False, created_at=str(existing["created_at"]), expected_revision=expected_revision, transaction_hook=lambda connection: self._mark_director_proposals_stale_with_connection(connection, project_id, session_id, source_script_segment_ids))

    def save_tts_candidate(
        self,
        *,
        project_id: str,
        segment_id: str,
        asset_id: str,
        source_text: str,
        acceptance: Any | None = None,
    ) -> dict[str, Any]:
        sequence = self._count_rows(project_id, "tts_candidates") + 1
        candidate_id = f"tts_candidate_{sequence:03d}"
        created_at = self._now_iso()
        self._execute(
            project_id,
            """
            INSERT INTO tts_candidates (
                candidate_id, project_id, segment_id, asset_id, source_text,
                technical_status, operator_review_status, target_duration_sec,
                actual_duration_sec, failure_code, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                project_id,
                segment_id,
                asset_id,
                source_text,
                getattr(acceptance, "technical_status", "legacy_unverified"),
                getattr(acceptance, "operator_review_status", "pending"),
                getattr(acceptance, "target_duration_sec", None),
                getattr(acceptance, "actual_duration_sec", None),
                getattr(acceptance, "failure_code", None),
                created_at,
            ),
        )
        return {
            "candidate_id": candidate_id,
            "project_id": project_id,
            "segment_id": segment_id,
            "asset_id": asset_id,
            "source_text": source_text,
            "technical_status": getattr(acceptance, "technical_status", "legacy_unverified"),
            "operator_review_status": getattr(acceptance, "operator_review_status", "pending"),
            "target_duration_sec": getattr(acceptance, "target_duration_sec", None),
            "actual_duration_sec": getattr(acceptance, "actual_duration_sec", None),
            "failure_code": getattr(acceptance, "failure_code", None),
            "created_at": created_at,
        }

    def list_tts_candidates(self, *, project_id: str, segment_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            project_id,
            """
            SELECT candidate_id, project_id, segment_id, asset_id, source_text,
                   technical_status, operator_review_status, target_duration_sec,
                   actual_duration_sec, failure_code, created_at
            FROM tts_candidates
            WHERE project_id = ? AND segment_id = ?
            ORDER BY created_at ASC, candidate_id ASC
            """,
            (project_id, segment_id),
        )
        return [dict(row) for row in rows]

    def get_tts_candidate(self, *, project_id: str, candidate_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT candidate_id, project_id, segment_id, asset_id, source_text,
                   technical_status, operator_review_status, target_duration_sec,
                   actual_duration_sec, failure_code, created_at
            FROM tts_candidates
            WHERE project_id = ? AND candidate_id = ?
            """,
            (project_id, candidate_id),
        )
        if row is None:
            raise KeyError(f"TTS candidate not found: {candidate_id}")
        return dict(row)

    def update_tts_candidate_listening_review(
        self,
        *,
        project_id: str,
        candidate_id: str,
        decision: str,
    ) -> dict[str, Any]:
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"approved", "rejected"}:
            raise ValueError("Listening review decision must be approved or rejected.")
        candidate = self.get_tts_candidate(project_id=project_id, candidate_id=candidate_id)
        if candidate["technical_status"] != "accepted":
            raise ValueError("Only technically accepted TTS candidates can receive a listening review.")
        if candidate["operator_review_status"] != "pending":
            raise ValueError("TTS candidate listening review has already been decided.")
        self._execute(
            project_id,
            "UPDATE tts_candidates SET operator_review_status = ? WHERE project_id = ? AND candidate_id = ?",
            (normalized_decision, project_id, candidate_id),
        )
        candidate["operator_review_status"] = normalized_decision
        return candidate

    def get_review_state_if_timeline_started(
        self, *, project_id: str, timeline_id: str
    ) -> dict[str, Any] | None:
        """Tell "no timeline yet" apart from "timeline exists, review missing".

        `get_review_state` alone can't -- it raises `KeyError` either way.
        This answers both in one query, since the caller sits on a hot path.

        A session's `timeline_id` legitimately has no `timelines` row yet
        for two real, current product paths: a blank pre-draft session
        (`blank_editing_session.py`) and a pasted-script draft session
        (`script_draft_session.py`) -- neither has produced a real timeline
        to review, so this returns `None`. Every path that DOES write a
        `timelines` row (`save_timeline_run`, the atomic draft bundle) also
        writes its `review_approvals` row in the same call; a `timelines`
        row existing with no matching review row is a genuine data
        inconsistency, and this raises `KeyError` for that, same as
        `get_review_state` does.
        """
        row = self._fetchone(
            project_id,
            """
            SELECT t.timeline_id, t.project_id, r.status, r.approved_at, r.updated_at, r.source_session_id, r.source_session_revision, r.source_variant_id, r.source_variant_revision, r.is_current, r.invalidated_at, r.invalidated_reason
            FROM timelines t
            LEFT JOIN review_approvals r ON r.project_id = t.project_id AND r.timeline_id = t.timeline_id
            WHERE t.project_id = ? AND t.timeline_id = ?
            """,
            (project_id, timeline_id),
        )
        if row is None:
            return None
        if row["status"] is None:
            raise KeyError(f"Review state not found: {timeline_id}")
        payload = dict(row)
        payload["status"] = str(payload.get("status") or "").strip().lower()
        payload["is_current"] = bool(payload.get("is_current"))
        return payload

    def get_review_state(self, *, project_id: str, timeline_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT timeline_id, project_id, status, approved_at, updated_at, source_session_id, source_session_revision, source_variant_id, source_variant_revision, is_current, invalidated_at, invalidated_reason
            FROM review_approvals
            WHERE project_id = ? AND timeline_id = ?
            """,
            (project_id, timeline_id),
        )
        if row is None:
            raise KeyError(f"Review state not found: {timeline_id}")
        payload = dict(row)
        payload["status"] = str(payload.get("status") or "").strip().lower()
        payload["is_current"] = bool(payload.get("is_current"))
        return payload

    def save_subtitle_run(
        self,
        *,
        project_id: str,
        timeline_id: str,
        subtitle_payload: dict[str, Any],
        source_session_id: str | None = None,
        source_session_revision: int | None = None,
        source_session_absent: bool = False,
        source_fence: Callable[[Any], bool] | None = None,
    ) -> dict[str, Any]:
        if source_session_absent and (
            source_session_id is not None or source_session_revision is not None
        ):
            raise ValueError("subtitle_render_session_lineage_is_ambiguous")
        subtitle_root = self.project_root(project_id) / "subtitles"
        subtitle_root.mkdir(parents=True, exist_ok=True)
        staging_path = subtitle_root / f".{uuid.uuid4().hex}.staging.srt"
        entries = subtitle_payload.get("entries", [])
        created_at = self._now_iso()
        payload = {
            "project_id": project_id,
            "timeline_id": timeline_id,
            "format": subtitle_payload.get("format", "srt"),
            "status": "succeeded",
            "created_at": created_at,
            "notes": subtitle_payload.get("notes", []),
        }
        summary_json = json.dumps(
            {
                "entry_count": len(entries),
                "notes": payload["notes"],
            },
            ensure_ascii=True,
        )
        connection: Any | None = None
        subtitle_path: Path | None = None
        published_path_owned = False
        try:
            staging_path.write_text(
                self._serialize_srt(entries),
                encoding="utf-8",
            )
            connection = self._connection(project_id)
            self._begin_output_publish_transaction(connection)
            sequence = self._next_sequence(subtitle_root, "subtitle_*.srt")
            subtitle_id = f"subtitle_{sequence:03d}"
            subtitle_path = subtitle_root / f"{subtitle_id}.srt"
            if source_session_id is not None:
                session = connection.execute(
                    """SELECT timeline_id, session_revision FROM editing_sessions
                       WHERE project_id = ? AND session_id = ?""",
                    (project_id, source_session_id),
                ).fetchone()
                if (
                    session is None
                    or str(session["timeline_id"]) != timeline_id
                    or source_session_revision is None
                    or int(session["session_revision"]) != int(source_session_revision)
                ):
                    raise EditingSessionRevisionConflict(
                        "subtitle_render_session_revision_changed"
                    )
            elif source_session_revision is not None:
                raise EditingSessionRevisionConflict(
                    "subtitle_render_session_lineage_required"
                )
            elif source_session_absent:
                session = connection.execute(
                    """SELECT session_id FROM editing_sessions
                       WHERE project_id = ? AND timeline_id = ?
                       ORDER BY updated_at DESC LIMIT 1""",
                    (project_id, timeline_id),
                ).fetchone()
                if session is not None:
                    raise EditingSessionRevisionConflict(
                        "subtitle_render_session_presence_changed"
                    )
            if source_fence is not None and not bool(source_fence(connection)):
                raise EditingSessionRevisionConflict(
                    "subtitle_render_source_fence_failed"
                )
            staging_path.replace(subtitle_path)
            published_path_owned = True
            file_uri = self._path_to_uri(project_id, subtitle_path)
            connection.execute(
                """
                INSERT INTO subtitle_renders (
                    subtitle_id,
                    project_id,
                    timeline_id,
                    format,
                    file_uri,
                    status,
                    summary_json,
                    created_at,
                    source_session_id,
                    source_session_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    subtitle_id,
                    project_id,
                    timeline_id,
                    payload["format"],
                    file_uri,
                    payload["status"],
                    summary_json,
                    created_at,
                    source_session_id,
                    source_session_revision,
                ),
            )
            connection.commit()
        except Exception:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            if published_path_owned and subtitle_path is not None:
                subtitle_path.unlink(missing_ok=True)
            raise
        finally:
            if connection is not None:
                connection.close()
            staging_path.unlink(missing_ok=True)
        return {"subtitle_id": subtitle_id, "file_uri": file_uri, "subtitle": self.get_subtitle_run(project_id=project_id, subtitle_id=subtitle_id)}

    def save_preview_run(
        self,
        *,
        project_id: str,
        timeline_id: str,
        preview_payload: dict[str, Any],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "previews",
            "preview_*.json",
        )
        preview_id = f"preview_{sequence:03d}"
        preview_path = self.project_root(project_id) / "previews" / f"{preview_id}.json"
        player_path = self.project_root(project_id) / "previews" / f"{preview_id}.html"
        file_uri = self._path_to_uri(project_id, preview_path)
        player_uri = self._path_to_uri(project_id, player_path)
        payload = {
            "preview_id": preview_id,
            "project_id": project_id,
            "timeline_id": timeline_id,
            "file_uri": file_uri,
            "player_uri": player_uri,
            "status": "succeeded",
            "created_at": self._now_iso(),
            **{key: value for key, value in preview_payload.items() if key != "player_html"},
        }
        player_html = str(preview_payload.get("player_html", ""))
        player_path.write_text(player_html, encoding="utf-8")
        preview_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        summary_json = json.dumps(
            {
                "artifact_kind": payload.get("artifact_kind"),
                "clip_group_count": sum(
                    1 for clip_group in payload.get("clips", []) if _is_store_supported_track_summary(clip_group)
                )
                if isinstance(payload.get("clips", []), list)
                else 0,
            },
            ensure_ascii=True,
        )
        try:
            self._execute(
                project_id,
                """
                INSERT INTO preview_renders (
                    preview_id,
                    project_id,
                    timeline_id,
                    file_uri,
                    status,
                    summary_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preview_id,
                    project_id,
                    timeline_id,
                    file_uri,
                    payload["status"],
                    summary_json,
                    payload["created_at"],
                ),
            )
        except Exception:
            preview_path.unlink(missing_ok=True)
            player_path.unlink(missing_ok=True)
            raise
        return {"preview_id": preview_id, "file_uri": file_uri, "preview": self.get_preview_run(project_id=project_id, preview_id=preview_id)}

    def _next_export_sequence(self, project_id: str) -> int:
        # All export types (capcut / final_render / capcut_draft_export) share one
        # `exports` table with a single export_id primary key, but each type is
        # written to its own subdirectory. Numbering per-subdirectory would let two
        # different export types both compute "export_001" and collide on insert,
        # so the sequence must be derived from the shared table, not a directory.
        rows = self._fetchall(project_id, "SELECT export_id FROM exports WHERE project_id = ?", (project_id,))
        highest = 0
        for row in rows:
            match = re.search(r"(\d+)$", str(row["export_id"]))
            if match:
                highest = max(highest, int(match.group(1)))
        return highest + 1

    def _next_export_sequence_in_connection(self, *, project_id: str, connection: sqlite3.Connection) -> int:
        """Allocate the next shared export sequence under the caller's writer lock."""
        rows = connection.execute(
            "SELECT export_id FROM exports WHERE project_id = ?", (project_id,),
        ).fetchall()
        highest = 0
        for row in rows:
            match = re.search(r"(\d+)$", str(row["export_id"]))
            if match:
                highest = max(highest, int(match.group(1)))
        return highest + 1

    @staticmethod
    def _begin_output_publish_transaction(connection: Any) -> None:
        """Serialize output lineage checks and filesystem path allocation.

        SQLite's immediate transaction provides the project-wide writer lock.
        PostgreSQL needs an explicit table lock because its translated plain
        ``BEGIN`` does not prevent two publishers from selecting the same next
        sequence or validating the same source lineage concurrently.
        """
        if isinstance(connection, sqlite3.Connection):
            connection.execute("BEGIN IMMEDIATE")
            return
        connection.execute("BEGIN")
        # Match editing-session mutation order: session CAS, optional asset
        # materialization, then dependent-artifact invalidation.  Acquiring the
        # same tables in the reverse order lets a publisher and editor deadlock.
        connection.execute(
            "LOCK TABLE editing_sessions, assets, review_approvals, "
            "subtitle_renders, preview_renders, exports "
            "IN SHARE ROW EXCLUSIVE MODE"
        )

    def _prune_old_exports(
        self,
        *,
        project_id: str,
        export_type: str,
        keep_last: int = DEFAULT_EXPORT_RETENTION_COUNT,
    ) -> None:
        rows = self._fetchall(
            project_id,
            """
            SELECT export_id, file_uri
            FROM exports
            WHERE project_id = ? AND export_type = ?
            ORDER BY created_at DESC
            """,
            (project_id, export_type),
        )
        for row in rows[keep_last:]:
            artifact_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
            shutil.rmtree(artifact_path.parent, ignore_errors=True)
            self._execute(
                project_id,
                "DELETE FROM exports WHERE project_id = ? AND export_id = ?",
                (project_id, row["export_id"]),
            )

    def save_capcut_export(
        self,
        *,
        project_id: str,
        timeline_id: str,
        export_payload: dict[str, Any],
    ) -> dict[str, Any]:
        invariant_note = "CapCut remains an export target, not the internal source of truth."
        sequence = self._next_export_sequence(project_id)
        export_id = f"export_{sequence:03d}"
        export_directory = self.project_root(project_id) / "exports" / "capcut" / export_id
        export_directory.mkdir(parents=True, exist_ok=True)
        payload_path = export_directory / "capcut_payload.json"
        notes_path = export_directory / "README.txt"
        file_uri = self._path_to_uri(project_id, payload_path)
        payload = {
            "export_id": export_id,
            "project_id": project_id,
            "timeline_id": timeline_id,
            "export_type": "capcut",
            "file_uri": file_uri,
            "status": "succeeded",
            "created_at": self._now_iso(),
            **export_payload,
        }
        existing_notes = [str(note) for note in payload.get("notes", [])]
        if existing_notes:
            payload["notes"] = existing_notes
        else:
            payload["notes"] = ["CapCut export manifest generated for local post-editing handoff."]
        if invariant_note not in payload["notes"]:
            payload["notes"].append(invariant_note)
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        readme_lines = payload["notes"] or ["CapCut export payload generated from timeline JSON."]
        notes_path.write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
        metadata_json = json.dumps(
            {
                "timeline_id": timeline_id,
                "adapter": payload.get("adapter"),
                "track_count": sum(
                    1 for track in payload.get("tracks", []) if _is_store_supported_track(track)
                )
                if isinstance(payload.get("tracks", []), list)
                else 0,
            },
            ensure_ascii=True,
        )
        try:
            self._execute(
                project_id,
                """
                INSERT INTO exports (
                    export_id,
                    project_id,
                    timeline_id,
                    export_type,
                    file_uri,
                    status,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    export_id,
                    project_id,
                    timeline_id,
                    "capcut",
                    file_uri,
                    payload["status"],
                    metadata_json,
                    payload["created_at"],
                ),
            )
        except Exception:
            shutil.rmtree(export_directory, ignore_errors=True)
            raise
        self._prune_old_exports(project_id=project_id, export_type="capcut")
        return {"export_id": export_id, "file_uri": file_uri, "export": payload}

    def save_final_render(
        self,
        *,
        project_id: str,
        timeline_id: str,
        source_output_path: Path,
        source_session_id: str | None = None,
        source_session_revision: int | None = None,
        source_session_absent: bool = False,
        source_fence: Callable[[sqlite3.Connection], bool] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Publish a final MP4 only while its durable source lineage is current.

        Rendering and its first freshness check happen outside this method and
        can take minutes.  Stage the completed MP4 privately, then hold the
        project writer lock while checking the session CAS, rechecking the
        caller's materialized-source fence, moving the artifact, and inserting
        the observable export pointer.  A concurrent editing-session mutation
        therefore either wins before this transaction (and prevents the
        pointer), or waits and invalidates the just-published export as part of
        its own mutation transaction.
        """
        if source_session_absent and (
            source_session_id is not None or source_session_revision is not None
        ):
            raise ValueError("final_render_session_lineage_is_ambiguous")
        source_output_path = Path(source_output_path)
        if not source_output_path.is_file():
            raise FileNotFoundError(source_output_path)
        export_root = self.project_root(project_id) / "exports" / "final_render"
        export_directory: Path | None = None
        # A short private component keeps long Windows project roots below
        # MAX_PATH while retaining an unguessable per-publish staging owner.
        staging_directory = export_root / f".s{uuid.uuid4().hex[:8]}"
        try:
            staging_directory.mkdir(parents=True, exist_ok=False)
            staged_path = staging_directory / f"output{source_output_path.suffix or '.mp4'}"
            shutil.copy2(source_output_path, staged_path)
        except Exception:
            shutil.rmtree(staging_directory, ignore_errors=True)
            raise
        created_at = self._now_iso()
        connection = self._connection(project_id)
        published = False
        try:
            self._begin_output_publish_transaction(connection)
            sequence = self._next_export_sequence_in_connection(project_id=project_id, connection=connection)
            export_id = f"export_{sequence:03d}"
            export_directory = export_root / export_id
            if source_session_id is not None:
                session = connection.execute(
                    """SELECT timeline_id, session_revision FROM editing_sessions
                       WHERE project_id = ? AND session_id = ?""",
                    (project_id, source_session_id),
                ).fetchone()
                if (
                    session is None
                    or str(session["timeline_id"]) != timeline_id
                ):
                    raise EditingSessionRevisionConflict("final_render_session_revision_changed")
                if source_session_revision is None:
                    # Legacy storage callers did not carry the revision that
                    # existed before rendering.  Preserve their public API by
                    # recording the revision observed under this writer lock;
                    # new pipeline callers provide a revision and use the CAS
                    # branch below to fence render-to-publish races.
                    source_session_revision = int(session["session_revision"])
                elif int(session["session_revision"]) != int(source_session_revision):
                    raise EditingSessionRevisionConflict("final_render_session_revision_changed")
            elif source_session_revision is not None:
                raise EditingSessionRevisionConflict("final_render_session_lineage_required")
            elif source_session_absent:
                session = connection.execute(
                    """SELECT session_id FROM editing_sessions
                       WHERE project_id = ? AND timeline_id = ?
                       ORDER BY updated_at DESC LIMIT 1""",
                    (project_id, timeline_id),
                ).fetchone()
                if session is not None:
                    raise EditingSessionRevisionConflict(
                        "final_render_session_presence_changed"
                    )
            if source_fence is not None and not bool(source_fence(connection)):
                raise EditingSessionRevisionConflict("final_render_source_fence_failed")
            export_directory.mkdir(parents=False, exist_ok=False)
            destination_path = export_directory / staged_path.name
            staged_path.replace(destination_path)
            file_uri = self._path_to_uri(project_id, destination_path)
            connection.execute(
                """
                INSERT INTO exports (
                    export_id,
                    project_id,
                    timeline_id,
                    export_type,
                    file_uri,
                    status,
                    metadata_json,
                    created_at
                    ,source_session_id,source_session_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    export_id,
                    project_id,
                    timeline_id,
                    "final_render",
                    file_uri,
                    "succeeded",
                    json.dumps(metadata or {}, ensure_ascii=True),
                    created_at,
                    source_session_id,
                    source_session_revision,
                ),
            )
            connection.commit()
            published = True
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            if export_directory is not None:
                shutil.rmtree(export_directory, ignore_errors=True)
            raise
        finally:
            connection.close()
            shutil.rmtree(staging_directory, ignore_errors=True)
        if published:
            self._prune_old_exports(project_id=project_id, export_type="final_render")
            return {"export_id": export_id, "file_uri": file_uri, "created_at": created_at}
        raise RuntimeError("final_render_publish_failed")

    def get_final_render_export(self, *, project_id: str, export_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT export_id, project_id, timeline_id, export_type, file_uri, status, metadata_json, created_at, source_session_id, source_session_revision, is_current, invalidated_at, invalidated_reason
            FROM exports
            WHERE project_id = ? AND export_id = ?
            """,
            (project_id, export_id),
        )
        if row is None:
            raise KeyError(f"Export not found: {export_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Export artifact missing: {export_id}")
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        has_sound = metadata.get("has_sound")
        verdict = metadata.get("owner_verdict")
        # 잰 지표와 owner 판단을 갈라서 돌려준다. 기계가 잰 것과 사람이 정한 것을
        # 섞으면 나중에 무엇을 근거로 배웠는지 알 수 없다.
        quality_facts = {
            key: value for key, value in metadata.items()
            if key not in {"owner_verdict", "owner_verdict_note", "owner_verdict_at"}
        }
        return {
            "export_id": row["export_id"],
            "timeline_id": row["timeline_id"],
            "export_type": row["export_type"],
            "file_uri": row["file_uri"],
            "status": row["status"],
            "created_at": row["created_at"],
            "source_session_id": row["source_session_id"],
            "source_session_revision": row["source_session_revision"],
            "is_current": bool(row["is_current"]),
            "invalidated_at": row["invalidated_at"],
            "invalidated_reason": row["invalidated_reason"],
            # 옛 완성본은 잰 적이 없다. 그때는 None으로 두어 화면이 경고하지 않는다.
            "has_sound": bool(has_sound) if isinstance(has_sound, bool) else None,
            "quality_facts": quality_facts,
            # 판단하지 않은 것과 나쁘다는 것은 다르다.
            "owner_verdict": str(verdict) if isinstance(verdict, str) and verdict else None,
            "owner_verdict_note": metadata.get("owner_verdict_note") or None,
            "owner_verdict_at": metadata.get("owner_verdict_at") or None,
        }

    def record_final_render_verdict(
        self,
        *,
        project_id: str,
        export_id: str,
        verdict: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        """완성본에 대한 owner의 판단을 그 완성본 옆에 남긴다.

        기계가 잰 지표만으로는 "좋은 영상"을 배울 수 없다. 이 라벨이 학습 재료다.
        렌더 기록을 지우거나 덮어쓰지 않고 metadata에 얹기만 한다.
        """
        allowed = {"good", "bad"}
        if verdict not in allowed:
            raise ValueError(f"final_render_verdict must be one of {sorted(allowed)}")
        connection = self._connection(project_id)
        try:
            row = connection.execute(
                "SELECT metadata_json FROM exports WHERE project_id = ? AND export_id = ?",
                (project_id, export_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"Export not found: {export_id}")
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                metadata = {}
            metadata["owner_verdict"] = verdict
            metadata["owner_verdict_note"] = (note or "").strip() or None
            metadata["owner_verdict_at"] = self._now_iso()
            connection.execute(
                "UPDATE exports SET metadata_json = ? WHERE project_id = ? AND export_id = ?",
                (json.dumps(metadata, ensure_ascii=True), project_id, export_id),
            )
            connection.commit()
        finally:
            connection.close()
        return {"export_id": export_id, "owner_verdict": verdict}

    def save_capcut_draft_export(
        self,
        *,
        project_id: str,
        timeline_id: str,
        source_draft_path: Path,
        notes: list[str] | None = None,
        source_session_id: str | None = None,
        source_session_revision: int | None = None,
        source_session_absent: bool = False,
        source_fence: Callable[[Any], bool] | None = None,
    ) -> dict[str, Any]:
        if source_session_absent and (
            source_session_id is not None or source_session_revision is not None
        ):
            raise ValueError("capcut_draft_export_session_lineage_is_ambiguous")
        source_draft_path = Path(source_draft_path)
        if not source_draft_path.is_dir():
            raise FileNotFoundError(source_draft_path)
        export_root = self.project_root(project_id) / "exports" / "capcut_draft"
        export_root.mkdir(parents=True, exist_ok=True)
        # CapCut draft trees contain deeply nested, vendor-owned filenames.
        # Keep the private staging component short so Windows MAX_PATH does
        # not reject an otherwise valid project-local draft during copy.
        staging_directory = export_root / f".s{uuid.uuid4().hex[:8]}"
        staged_path = staging_directory / source_draft_path.name
        created_at = self._now_iso()
        connection: Any | None = None
        export_directory: Path | None = None
        export_directory_owned = False
        try:
            shutil.copytree(source_draft_path, staged_path)
            connection = self._connection(project_id)
            self._begin_output_publish_transaction(connection)
            sequence = self._next_export_sequence_in_connection(
                project_id=project_id,
                connection=connection,
            )
            export_id = f"export_{sequence:03d}"
            export_directory = export_root / export_id
            if source_session_id is not None:
                session = connection.execute(
                    """SELECT timeline_id, session_revision FROM editing_sessions
                       WHERE project_id = ? AND session_id = ?""",
                    (project_id, source_session_id),
                ).fetchone()
                if (
                    session is None
                    or str(session["timeline_id"]) != timeline_id
                    or source_session_revision is None
                    or int(session["session_revision"]) != int(source_session_revision)
                ):
                    raise EditingSessionRevisionConflict(
                        "capcut_draft_export_session_revision_changed"
                    )
            elif source_session_revision is not None:
                raise EditingSessionRevisionConflict(
                    "capcut_draft_export_session_lineage_required"
                )
            elif source_session_absent:
                session = connection.execute(
                    """SELECT session_id FROM editing_sessions
                       WHERE project_id = ? AND timeline_id = ?
                       ORDER BY updated_at DESC LIMIT 1""",
                    (project_id, timeline_id),
                ).fetchone()
                if session is not None:
                    raise EditingSessionRevisionConflict(
                        "capcut_draft_export_session_presence_changed"
                    )
            if source_fence is not None and not bool(source_fence(connection)):
                raise EditingSessionRevisionConflict(
                    "capcut_draft_export_source_fence_failed"
                )
            export_directory.mkdir(parents=False, exist_ok=False)
            export_directory_owned = True
            destination_path = export_directory / staged_path.name
            staged_path.replace(destination_path)
            file_uri = self._path_to_uri(project_id, destination_path)
            connection.execute(
                """
                INSERT INTO exports (
                    export_id,
                    project_id,
                    timeline_id,
                    export_type,
                    file_uri,
                    status,
                    metadata_json,
                    created_at,
                    source_session_id,
                    source_session_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    export_id,
                    project_id,
                    timeline_id,
                    "capcut_draft_export",
                    file_uri,
                    "succeeded",
                    json.dumps({"notes": notes or []}, ensure_ascii=True),
                    created_at,
                    source_session_id,
                    source_session_revision,
                ),
            )
            connection.commit()
        except Exception:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            if export_directory_owned and export_directory is not None:
                shutil.rmtree(export_directory, ignore_errors=True)
            raise
        finally:
            if connection is not None:
                connection.close()
            shutil.rmtree(staging_directory, ignore_errors=True)
        self._prune_old_exports(project_id=project_id, export_type="capcut_draft_export")
        return {"export_id": export_id, "file_uri": file_uri, "created_at": created_at}

    def get_capcut_draft_export(self, *, project_id: str, export_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT export_id, project_id, timeline_id, export_type, file_uri, status, metadata_json, created_at, source_session_id, source_session_revision, is_current, invalidated_at, invalidated_reason,
                   handoff_claim_token, handoff_claimed_at, handoff_claim_expires_at
            FROM exports
            WHERE project_id = ? AND export_id = ?
            """,
            (project_id, export_id),
        )
        if row is None:
            raise KeyError(f"Export not found: {export_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Export artifact missing: {export_id}")
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        handoff = metadata.get("handoff")
        if not isinstance(handoff, dict) and row["handoff_claim_token"] is not None:
            expires_at = str(row["handoff_claim_expires_at"] or "")
            try:
                active_claim = bool(expires_at) and datetime.fromisoformat(expires_at) > datetime.now(UTC)
            except (TypeError, ValueError):
                active_claim = False
            handoff = {
                "status": "in_progress" if active_claim else "failed",
                "source_file_uri": row["file_uri"],
                "registered_project_path": None,
                "error_message": None if active_claim else "CapCut 등록 요청이 중단되었어요. 다시 등록해 주세요.",
                "registered_at": None,
                "reused": False,
                "recoverable": not active_claim,
                "recoverable_at": expires_at or None,
            }
        elif isinstance(handoff, dict):
            handoff = {
                **handoff,
                "recoverable": bool(handoff.get("recoverable", handoff.get("status") == "failed")),
                "recoverable_at": handoff.get("recoverable_at"),
            }
        return {
            "export_id": row["export_id"],
            "timeline_id": row["timeline_id"],
            "export_type": row["export_type"],
            "file_uri": row["file_uri"],
            "status": row["status"],
            "notes": list(metadata.get("notes") or []),
            "handoff": handoff,
            "created_at": row["created_at"],
            "source_session_id": row["source_session_id"],
            "source_session_revision": row["source_session_revision"],
            "is_current": bool(row["is_current"]),
            "invalidated_at": row["invalidated_at"],
            "invalidated_reason": row["invalidated_reason"],
        }

    def update_capcut_draft_handoff(
        self, *, project_id: str, export_id: str, handoff: dict[str, Any]
    ) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            "SELECT metadata_json FROM exports WHERE project_id = ? AND export_id = ? AND export_type = ?",
            (project_id, export_id, "capcut_draft_export"),
        )
        if row is None:
            raise KeyError(f"CapCut draft export not found: {export_id}")
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        metadata["handoff"] = handoff
        self._execute(
            project_id,
            "UPDATE exports SET metadata_json = ? WHERE project_id = ? AND export_id = ?",
            (json.dumps(metadata, ensure_ascii=True), project_id, export_id),
        )
        return self.get_capcut_draft_export(project_id=project_id, export_id=export_id)

    def claim_capcut_draft_handoff(
        self, *, project_id: str, job_id: str
    ) -> dict[str, Any] | None:
        """Durably claim one current export before the external CapCut copy.

        The external copy runs after the transaction, but its owner token stays
        on the export.  A competing request therefore cannot start another copy
        while the first request is in flight, including after a process-local
        restart.
        """
        connection = self._connection(project_id)
        try:
            self._begin_capcut_draft_handoff_transaction(connection)
            job = connection.execute(
                """SELECT job_id, job_type, status, output_ref FROM jobs
                   WHERE project_id = ? AND job_id = ?""",
                (project_id, job_id),
            ).fetchone()
            if (
                job is None
                or str(job["job_type"]) != JobType.CAPCUT_DRAFT_EXPORT.value
                or str(job["status"]) != JobStatus.SUCCEEDED.value
                or not job["output_ref"]
            ):
                connection.rollback()
                return None
            export = connection.execute(
                """SELECT export_id, timeline_id, file_uri, status, is_current,
                          source_session_id, source_session_revision, metadata_json,
                          handoff_claim_token, handoff_claim_job_id, handoff_claimed_at,
                          handoff_claim_expires_at
                   FROM exports
                   WHERE project_id = ? AND export_id = ?
                     AND export_type = ?""",
                (project_id, str(job["output_ref"]), "capcut_draft_export"),
            ).fetchone()
            if (
                export is None
                or str(export["status"]) != JobStatus.SUCCEEDED.value
                or not bool(export["is_current"])
            ):
                connection.rollback()
                return None
            active_session = connection.execute(
                """SELECT session_id, timeline_id, session_revision
                   FROM editing_sessions
                   WHERE project_id = ?
                   ORDER BY updated_at DESC, created_at DESC, session_id DESC
                   LIMIT 1""",
                (project_id,),
            ).fetchone()
            export_session_id = export["source_session_id"]
            export_session_revision = export["source_session_revision"]
            if export_session_id is not None:
                if (
                    active_session is None
                    or str(active_session["session_id"]) != str(export_session_id)
                    or str(active_session["timeline_id"]) != str(export["timeline_id"])
                    or int(active_session["session_revision"]) != int(export_session_revision)
                ):
                    connection.rollback()
                    return None
            metadata = json.loads(str(export["metadata_json"] or "{}"))
            existing_handoff = metadata.get("handoff")
            if isinstance(existing_handoff, dict) and existing_handoff.get("status") == "ready":
                connection.commit()
                return {
                    "state": "ready",
                    "handoff": {**existing_handoff, "reused": True},
                }
            now = datetime.now(UTC)
            now_iso = now.isoformat()
            expires_at = str(export["handoff_claim_expires_at"] or "")
            try:
                active_claim = export["handoff_claim_token"] is not None and bool(expires_at) and datetime.fromisoformat(expires_at) > now
            except (TypeError, ValueError):
                active_claim = False
            if active_claim:
                connection.commit()
                return {"state": "in_progress", "recoverable_at": expires_at}

            claim_token = uuid.uuid4().hex
            expires_at = (now + timedelta(seconds=CAPCUT_DRAFT_HANDOFF_CLAIM_LEASE_SECONDS)).isoformat()
            cursor = connection.execute(
                """UPDATE exports
                   SET handoff_claim_token = ?, handoff_claim_job_id = ?, handoff_claimed_at = ?, handoff_claim_expires_at = ?
                   WHERE project_id = ? AND export_id = ? AND export_type = ?
                     AND status = ? AND is_current = 1
                     AND (handoff_claim_token IS NULL OR handoff_claim_expires_at IS NULL OR handoff_claim_expires_at <= ?)""",
                (
                    claim_token,
                    str(job["job_id"]),
                    now_iso,
                    expires_at,
                    project_id,
                    str(export["export_id"]),
                    "capcut_draft_export",
                    JobStatus.SUCCEEDED.value,
                    now_iso,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return {"state": "in_progress"}
            connection.commit()
            return {
                "state": "owner",
                "claim_token": claim_token,
                "job_id": str(job["job_id"]),
                "export_id": str(export["export_id"]),
                "timeline_id": str(export["timeline_id"]),
                "file_uri": str(export["file_uri"]),
                "export_source_session_id": str(export_session_id) if export_session_id is not None else None,
                "export_source_session_revision": int(export_session_revision) if export_session_revision is not None else None,
                "active_session_id": str(active_session["session_id"]) if active_session is not None else None,
                "active_session_revision": int(active_session["session_revision"]) if active_session is not None else None,
                "claimed_at": now_iso,
                "expires_at": expires_at,
            }
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def begin_director_hermes_run(
        self,
        *,
        project_id: str,
        session_id: str,
        conversation_id: str,
        client_message_id: str,
        user_text: str,
        expected_session_revision: int,
        expected_asset_index_revision: int,
        selected_segment_id: str | None = None,
        retry_of_run_id: str | None = None,
        stale_after_seconds: int = 300,
    ) -> dict[str, Any]:
        """Create a durable pending run and user/event rows.

        ``stale_after_seconds`` remains a source-compatible argument only.
        C1 never reclaims or redispatches an orphaned provider run.
        """
        now = self._now_iso()
        run_id = f"hermes-run-{uuid.uuid4().hex}"
        owner_token = uuid.uuid4().hex
        user_message_id = uuid.uuid4().hex
        connection = self._connection(project_id)
        try:
            self._begin_director_hermes_transaction(connection)
            existing = connection.execute(
                "SELECT * FROM director_hermes_runs "
                "WHERE conversation_id = ? AND client_message_id = ?",
                (conversation_id, client_message_id),
            ).fetchone()
            if existing is not None and (
                str(existing["status"]) != "pending"
                or (
                    int(existing["expected_session_revision"]) == 0
                    and int(existing["expected_asset_index_revision"]) == -1
                )
            ):
                result = self._director_hermes_existing_result(
                    connection=connection,
                    row=existing,
                    project_id=project_id,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    user_text=user_text,
                    expected_session_revision=expected_session_revision,
                    expected_asset_index_revision=expected_asset_index_revision,
                    selected_segment_id=selected_segment_id,
                    now=now,
                )
                connection.commit()
                return result
            if retry_of_run_id is not None:
                retry_source = connection.execute(
                    """
                    SELECT project_id, conversation_id, session_id, user_text,
                           expected_session_revision,
                           expected_asset_index_revision, selected_segment_id,
                           status
                    FROM director_hermes_runs
                    WHERE project_id = ? AND run_id = ?
                    """,
                    (project_id, retry_of_run_id),
                ).fetchone()
                if (
                    retry_source is None
                    or str(retry_source["conversation_id"]) != conversation_id
                ):
                    raise KeyError("director_hermes_run_missing")
                if str(retry_source["status"]) not in {"blocked", "interrupted"}:
                    raise ValueError("hermes_run_retry_not_eligible")
                if (
                    str(retry_source["session_id"]) != session_id
                    or str(retry_source["user_text"]) != user_text
                    or int(retry_source["expected_session_revision"])
                    != expected_session_revision
                    or int(retry_source["expected_asset_index_revision"])
                    != expected_asset_index_revision
                    or retry_source["selected_segment_id"] != selected_segment_id
                ):
                    raise ValueError("hermes_run_retry_identity_mismatch")
            session = connection.execute(
                "SELECT session_id, session_revision, session_json "
                "FROM editing_sessions WHERE session_id = ? AND project_id = ?",
                (session_id, project_id),
            ).fetchone()
            if session is None:
                raise KeyError("editing_session_missing")
            if int(session["session_revision"]) != expected_session_revision:
                raise ValueError("creator_context_session_revision_mismatch")
            asset_revision_row = connection.execute(
                "SELECT revision FROM director_asset_index_revisions "
                "WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            current_asset_revision = (
                int(asset_revision_row["revision"])
                if asset_revision_row is not None
                else 0
            )
            if current_asset_revision != expected_asset_index_revision:
                raise ValueError("creator_context_asset_revision_mismatch")
            if selected_segment_id is not None:
                session_payload = json.loads(str(session["session_json"] or "{}"))
                segment_ids = {
                    str(item.get("segment_id") or "")
                    for item in session_payload.get("segments", [])
                    if isinstance(item, dict)
                }
                if selected_segment_id not in segment_ids:
                    raise ValueError("creator_context_segment_mismatch")
            conversation = connection.execute(
                "SELECT project_id, session_id FROM director_conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if conversation is None:
                raise KeyError("director_conversation_missing")
            if (
                str(conversation["project_id"]) != project_id
                or str(conversation["session_id"]) != session_id
            ):
                raise ValueError("conversation_scope_mismatch")
            if existing is not None:
                result = self._director_hermes_existing_result(
                    connection=connection,
                    row=existing,
                    project_id=project_id,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    user_text=user_text,
                    expected_session_revision=expected_session_revision,
                    expected_asset_index_revision=expected_asset_index_revision,
                    selected_segment_id=selected_segment_id,
                    now=now,
                )
                connection.commit()
                return result
            user_message_order = self._next_director_message_order(
                connection, conversation_id=conversation_id
            )
            inserted = connection.execute(
                """
                INSERT INTO director_hermes_runs (
                    run_id, conversation_id, client_message_id, project_id,
                    session_id, expected_session_revision,
                    expected_asset_index_revision, selected_segment_id,
                    retry_of_run_id,
                    user_text, user_message_id, assistant_message_id,
                    status, owner_token, next_event_id, heartbeat_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'pending', ?, 2, ?, ?, ?)
                ON CONFLICT (conversation_id, client_message_id) DO NOTHING
                """,
                (
                    run_id,
                    conversation_id,
                    client_message_id,
                    project_id,
                    session_id,
                    expected_session_revision,
                    expected_asset_index_revision,
                    selected_segment_id,
                    retry_of_run_id,
                    user_text,
                    user_message_id,
                    owner_token,
                    now,
                    now,
                    now,
                ),
            )
            if inserted.rowcount == 1:
                connection.execute(
                    """
                    INSERT INTO director_messages (
                        message_id, conversation_id, project_id, session_id,
                        role, text, proposal_id, metadata_json,
                        client_message_id, message_order, created_at
                    ) VALUES (?, ?, ?, ?, 'user', ?, NULL, '{}', ?, ?, ?)
                    """,
                    (
                        user_message_id,
                        conversation_id,
                        project_id,
                        session_id,
                        user_text,
                        client_message_id,
                        user_message_order,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO director_hermes_run_events (
                        project_id, run_id, event_id, event_type, text,
                        retryable, created_at
                    ) VALUES (?, ?, 1, 'run_started', '', 0, ?)
                    """,
                    (project_id, run_id, now),
                )
                connection.execute(
                    "UPDATE director_conversations SET updated_at = ? WHERE conversation_id = ?",
                    (now, conversation_id),
                )
                connection.commit()
                return {
                    "run_id": run_id,
                    "status": "pending",
                    "owner_token": owner_token,
                    "dispatch": True,
                }
            row = connection.execute(
                "SELECT * FROM director_hermes_runs WHERE conversation_id = ? AND client_message_id = ?",
                (conversation_id, client_message_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("director_hermes_run_conflict")
            result = self._director_hermes_existing_result(
                connection=connection,
                row=row,
                project_id=project_id,
                session_id=session_id,
                conversation_id=conversation_id,
                user_text=user_text,
                expected_session_revision=expected_session_revision,
                expected_asset_index_revision=expected_asset_index_revision,
                selected_segment_id=selected_segment_id,
                now=now,
            )
            connection.commit()
            return result
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _begin_director_hermes_transaction(connection: Any) -> None:
        """Serialize run cursor/message state without translating SQLite locks."""
        if isinstance(connection, sqlite3.Connection):
            connection.execute("BEGIN IMMEDIATE")
            return
        connection.execute("BEGIN")
        connection.execute(
            "LOCK TABLE director_hermes_runs, director_hermes_run_events, "
            "director_messages IN SHARE ROW EXCLUSIVE MODE"
        )

    @staticmethod
    def _lock_director_hermes_run(
        connection: Any, *, project_id: str, run_id: str
    ) -> None:
        """Use PostgreSQL row ownership in addition to the cursor CAS."""
        if not isinstance(connection, sqlite3.Connection):
            connection.execute(
                "SELECT run_id FROM director_hermes_runs "
                "WHERE project_id = ? AND run_id = ? FOR UPDATE",
                (project_id, run_id),
            )

    def _director_hermes_existing_result(
        self,
        *,
        connection: Any,
        row: Any,
        project_id: str,
        session_id: str,
        conversation_id: str,
        user_text: str,
        expected_session_revision: int,
        expected_asset_index_revision: int,
        selected_segment_id: str | None,
        now: str,
    ) -> dict[str, Any]:
        if (
            str(row["project_id"]) != project_id
            or str(row["session_id"]) != session_id
        ):
            raise ValueError("conversation_scope_mismatch")
        if str(row["user_text"]) != user_text:
            raise ValueError("client_message_id_reused_with_different_content")
        legacy = (
            int(row["expected_session_revision"]) == 0
            and int(row["expected_asset_index_revision"]) == -1
        )
        status = str(row["status"])
        if not legacy and (
            int(row["expected_session_revision"])
            != int(expected_session_revision)
            or int(row["expected_asset_index_revision"])
            != int(expected_asset_index_revision)
            or row["selected_segment_id"] != selected_segment_id
        ):
            raise ValueError("client_message_id_reused_with_different_context")

        if legacy and status == "pending":
            assistant_message_id = uuid.uuid4().hex
            fallback = (
                "Hermes is temporarily unavailable. "
                "Manual Director remains available."
            )
            settled = connection.execute(
                """
                UPDATE director_hermes_runs
                SET status = 'blocked', assistant_message_id = ?, updated_at = ?
                WHERE project_id = ? AND run_id = ? AND status = 'pending'
                """,
                (assistant_message_id, now, project_id, str(row["run_id"])),
            )
            if settled.rowcount != 1:
                latest = connection.execute(
                    "SELECT * FROM director_hermes_runs "
                    "WHERE project_id = ? AND run_id = ?",
                    (project_id, str(row["run_id"])),
                ).fetchone()
                if latest is None:
                    raise RuntimeError("director_hermes_run_conflict")
                return self._director_hermes_existing_result(
                    connection=connection,
                    row=latest,
                    project_id=project_id,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    user_text=user_text,
                    expected_session_revision=expected_session_revision,
                    expected_asset_index_revision=expected_asset_index_revision,
                    selected_segment_id=selected_segment_id,
                    now=now,
                )
            assistant_message_order = self._next_director_message_order(
                connection, conversation_id=conversation_id
            )
            connection.execute(
                """
                INSERT INTO director_messages (
                    message_id, conversation_id, project_id, session_id, role,
                    text, proposal_id, metadata_json, client_message_id,
                    message_order, created_at
                ) VALUES (?, ?, ?, ?, 'assistant', ?, NULL, ?, NULL, ?, ?)
                """,
                (
                    assistant_message_id,
                    conversation_id,
                    project_id,
                    session_id,
                    fallback,
                    json.dumps(
                        {
                            "hermes_run_id": str(row["run_id"]),
                            "hermes_status": "blocked",
                            "retryable": True,
                            "legacy_context_recovered": True,
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    ),
                    assistant_message_order,
                    now,
                ),
            )
            connection.execute(
                "UPDATE director_conversations SET updated_at = ? "
                "WHERE conversation_id = ?",
                (now, conversation_id),
            )
            result = dict(row)
            result.update(
                {
                    "status": "blocked",
                    "assistant_message_id": assistant_message_id,
                    "assistant_text": fallback,
                    "dispatch": False,
                    "owner_token": None,
                }
            )
            return result

        result = dict(row)
        result["dispatch"] = False
        result["owner_token"] = None
        if row["assistant_message_id"] is not None:
            assistant = connection.execute(
                """
                SELECT text FROM director_messages
                WHERE project_id = ? AND conversation_id = ? AND message_id = ?
                """,
                (
                    project_id,
                    conversation_id,
                    str(row["assistant_message_id"]),
                ),
            ).fetchone()
            result["assistant_text"] = (
                str(assistant["text"]) if assistant is not None else ""
            )
        return result

    def append_director_hermes_draft(
        self,
        *,
        project_id: str,
        run_id: str,
        owner_token: str,
        assistant_draft_text: str,
    ) -> bool:
        """Compatibility wrapper that durably appends the matching public delta."""
        row = self.get_director_hermes_run(project_id=project_id, run_id=run_id)
        previous = str(row.get("assistant_draft_text") or "")
        if not assistant_draft_text.startswith(previous):
            return False
        return self.append_director_hermes_draft_event(
            project_id=project_id,
            run_id=run_id,
            owner_token=owner_token,
            assistant_draft_text=assistant_draft_text,
            event_text=assistant_draft_text[len(previous) :],
            expected_event_id=int(row.get("next_event_id") or 1),
        )

    def append_director_hermes_draft_event(
        self,
        *,
        project_id: str,
        run_id: str,
        owner_token: str,
        assistant_draft_text: str,
        event_text: str,
        expected_event_id: int,
    ) -> bool:
        """Atomically append a visible draft delta and advance its durable cursor."""
        if not assistant_draft_text:
            raise ValueError("director_hermes_draft_invalid")
        if not event_text or expected_event_id < 1:
            raise ValueError("director_hermes_event_invalid")
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            self._begin_director_hermes_transaction(connection)
            self._lock_director_hermes_run(
                connection, project_id=project_id, run_id=run_id
            )
            cursor = connection.execute(
                """
                UPDATE director_hermes_runs
                SET assistant_draft_text = ?, status = 'streaming',
                    next_event_id = next_event_id + 1,
                    heartbeat_at = ?, updated_at = ?
                WHERE project_id = ? AND run_id = ?
                  AND status IN ('pending', 'streaming')
                  AND owner_token = ? AND next_event_id = ?
                  AND substr(?, 1, length(assistant_draft_text)) = assistant_draft_text
                  AND substr(?, length(assistant_draft_text) + 1) = ?
                """,
                (
                    assistant_draft_text,
                    now,
                    now,
                    project_id,
                    run_id,
                    owner_token,
                    expected_event_id,
                    assistant_draft_text,
                    assistant_draft_text,
                    event_text,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False
            connection.execute(
                """
                INSERT INTO director_hermes_run_events (
                    project_id, run_id, event_id, event_type, text,
                    retryable, created_at
                ) VALUES (?, ?, ?, 'text_delta', ?, 0, ?)
                """,
                (project_id, run_id, expected_event_id, event_text, now),
            )
            connection.commit()
            return True
        except sqlite3.IntegrityError:
            if connection.in_transaction:
                connection.rollback()
            return False
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def complete_director_hermes_run(
        self,
        *,
        project_id: str,
        run_id: str,
        owner_token: str,
        status: str,
        assistant_text: str,
        retryable: bool,
        proposal: DirectorProposal | None = None,
        public_text: str | None = None,
        verified_publish_capability: Mapping[str, Any] | None = None,
    ) -> bool | Literal[
        "proposal_conflict",
        "proposal_stale",
        "publish_capability_denied",
    ]:
        """Owner-token-fenced active-to-terminal transition with durable events."""
        if status not in {"completed", "blocked", "interrupted"} or not assistant_text.strip():
            raise ValueError("director_hermes_terminal_invalid")
        if proposal is not None and (
            status != "completed"
            or (
                proposal.status != "candidate_only"
                and not _is_actionable_yujin_media_proposal(proposal)
            )
        ):
            raise ValueError("director_hermes_proposal_invalid")
        now = self._now_iso()
        assistant_message_id = uuid.uuid4().hex
        connection = self._connection(project_id)
        try:
            self._begin_director_hermes_transaction(connection)
            self._lock_director_hermes_run(
                connection, project_id=project_id, run_id=run_id
            )
            active = connection.execute(
                """
                SELECT conversation_id, session_id, assistant_draft_text,
                       next_event_id
                FROM director_hermes_runs
                WHERE project_id = ? AND run_id = ?
                  AND status IN ('pending', 'streaming') AND owner_token = ?
                """,
                (project_id, run_id, owner_token),
            ).fetchone()
            if active is None:
                connection.rollback()
                return False
            if proposal is not None:
                self._lock_terminal_current_truth(
                    connection=connection,
                    project_id=project_id,
                    session_id=str(active["session_id"]),
                )
            if (
                proposal is not None
                and any(
                    candidate.canonical_metadata.get("schema_version")
                    == "videobox.yujin-response.v1"
                    for candidate in proposal.candidates
                )
                and not self._ready_yujin_proposal_is_current(
                    connection=connection,
                    project_id=project_id,
                    proposal=proposal,
                )
            ):
                connection.rollback()
                return "proposal_stale"
            publish_decision = (
                self._decide_terminal_publish_capability(
                    connection=connection,
                    project_id=project_id,
                    run_id=run_id,
                    active=active,
                    proposal_exists=proposal is not None,
                    verified=verified_publish_capability,
                    occurred_at=now,
                )
            )
            if publish_decision != "accepted":
                connection.commit()
                return "publish_capability_denied"
            persisted_public = str(active["assistant_draft_text"] or "")
            terminal_public = persisted_public if public_text is None else public_text
            if (
                terminal_public != persisted_public
                or not assistant_text.startswith(terminal_public)
            ):
                connection.rollback()
                return False
            next_event_id = int(active["next_event_id"])
            remainder = assistant_text[len(terminal_public) :]
            terminal_event_id = next_event_id + (1 if remainder else 0)
            cursor = connection.execute(
                """
                UPDATE director_hermes_runs
                SET status = ?, assistant_message_id = ?, assistant_draft_text = '',
                    next_event_id = ?, updated_at = ?
                WHERE project_id = ? AND run_id = ?
                  AND status IN ('pending', 'streaming')
                  AND owner_token = ? AND next_event_id = ?
                """,
                (
                    status,
                    assistant_message_id,
                    terminal_event_id + 1,
                    now,
                    project_id,
                    run_id,
                    owner_token,
                    next_event_id,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False
            row = active
            stored_proposal = proposal
            if stored_proposal is not None:
                if stored_proposal.source_session_id != str(row["session_id"]):
                    raise ValueError("director_hermes_proposal_session_mismatch")
                existing_proposal = connection.execute(
                    "SELECT 1 FROM director_proposals "
                    "WHERE project_id = ? AND proposal_id = ?",
                    (project_id, stored_proposal.proposal_id),
                ).fetchone()
                if existing_proposal is not None:
                    connection.rollback()
                    return "proposal_conflict"
                connection.execute(
                    "INSERT INTO director_proposal_revisions (project_id, revision) "
                    "VALUES (?, 1) ON CONFLICT(project_id) DO UPDATE "
                    "SET revision = revision + 1",
                    (project_id,),
                )
                revision_row = connection.execute(
                    "SELECT revision FROM director_proposal_revisions "
                    "WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
                revision = int(revision_row["revision"])
                stored_proposal = replace(
                    stored_proposal,
                    revision=revision,
                    revision_code=f"P{revision:02d}",
                    candidates=tuple(
                        replace(
                            candidate,
                            visible_reference_code=(
                                f"P{revision:02d}"
                                + candidate.visible_reference_code[3:]
                            ),
                        )
                        for candidate in stored_proposal.candidates
                    ),
                )
                proposal_payload = proposal_to_payload(stored_proposal)
                canonical_proposal = json.dumps(
                    proposal_payload,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                connection.execute(
                    """
                    INSERT INTO director_proposals (
                        proposal_id, project_id, status, source_session_id,
                        source_script_segment_ids_json, proposal_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored_proposal.proposal_id,
                        project_id,
                        stored_proposal.status,
                        stored_proposal.source_session_id,
                        json.dumps(
                            list(stored_proposal.source_script_segment_ids)
                        ),
                        canonical_proposal,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO director_proposal_lifecycle_events "
                    "(proposal_id, status, reason, changed_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        stored_proposal.proposal_id,
                        stored_proposal.status,
                        "hermes_candidate_created",
                        now,
                    ),
                )
            metadata = {
                "hermes_run_id": run_id,
                "hermes_status": status,
                "retryable": retryable,
            }
            assistant_message_order = self._next_director_message_order(
                connection, conversation_id=str(row["conversation_id"])
            )
            connection.execute(
                """
                INSERT INTO director_messages (
                    message_id, conversation_id, project_id, session_id, role,
                    text, proposal_id, metadata_json, client_message_id,
                    message_order, created_at
                ) VALUES (?, ?, ?, ?, 'assistant', ?, ?, ?, NULL, ?, ?)
                """,
                (
                    assistant_message_id,
                    str(row["conversation_id"]),
                    project_id,
                    str(row["session_id"]),
                    assistant_text,
                    (
                        stored_proposal.proposal_id
                        if stored_proposal is not None
                        else None
                    ),
                    json.dumps(metadata, ensure_ascii=True, sort_keys=True),
                    assistant_message_order,
                    now,
                ),
            )
            connection.execute(
                "UPDATE director_conversations SET updated_at = ? WHERE conversation_id = ?",
                (now, str(row["conversation_id"])),
            )
            if remainder:
                connection.execute(
                    """
                    INSERT INTO director_hermes_run_events (
                        project_id, run_id, event_id, event_type, text,
                        retryable, created_at
                    ) VALUES (?, ?, ?, 'text_delta', ?, 0, ?)
                    """,
                    (project_id, run_id, next_event_id, remainder, now),
                )
            connection.execute(
                """
                INSERT INTO director_hermes_run_events (
                    project_id, run_id, event_id, event_type, text,
                    retryable, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    run_id,
                    terminal_event_id,
                    "run_completed" if status == "completed" else "blocked",
                    assistant_text,
                    int(retryable),
                    now,
                ),
            )
            connection.commit()
            try:
                self.prune_director_hermes_run_events(
                    project_id=project_id,
                    retention_days=30,
                    keep_terminal_streams=128,
                )
            except Exception:
                # Terminal truth is already committed. Retention is bounded
                # maintenance and must never turn that success into a retry.
                pass
            return True
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            if proposal is not None:
                existing_proposal = self._fetchone(
                    project_id,
                    "SELECT 1 FROM director_proposals "
                    "WHERE project_id = ? AND proposal_id = ?",
                    (project_id, proposal.proposal_id),
                )
                if existing_proposal is not None:
                    return "proposal_conflict"
            raise
        finally:
            connection.close()

    @staticmethod
    def _lock_terminal_current_truth(
        *,
        connection: Any,
        project_id: str,
        session_id: str,
    ) -> None:
        if isinstance(connection, sqlite3.Connection):
            return
        connection.execute(
            """
            SELECT session_id FROM editing_sessions
            WHERE project_id = ? AND session_id = ?
            FOR UPDATE
            """,
            (project_id, session_id),
        )
        connection.execute(
            """
            INSERT INTO director_asset_index_revisions (project_id, revision)
            VALUES (?, 0)
            ON CONFLICT (project_id) DO NOTHING
            """,
            (project_id,),
        )
        connection.execute(
            """
            SELECT revision FROM director_asset_index_revisions
            WHERE project_id = ?
            FOR UPDATE
            """,
            (project_id,),
        )

    def _decide_terminal_publish_capability(
        self,
        *,
        connection: Any,
        project_id: str,
        run_id: str,
        active: Mapping[str, Any],
        proposal_exists: bool,
        verified: Mapping[str, Any] | None,
        occurred_at: str,
    ) -> str:
        if not proposal_exists:
            self._revoke_issued_hermes_capabilities_with_connection(
                connection=connection,
                project_id=project_id,
                conversation_id=str(active["conversation_id"]),
                run_id=run_id,
                occurred_at=occurred_at,
            )
            return "accepted"
        lock_suffix = (
            "" if isinstance(connection, sqlite3.Connection) else " FOR UPDATE"
        )
        rows = connection.execute(
            """
            SELECT * FROM hermes_capability_ledger
            WHERE project_id = ?
              AND lifecycle_version = 'videobox.yujin-capability.v1'
              AND conversation_id = ?
              AND run_id = ?
              AND action = 'publish_proposal'
            ORDER BY jti
            """
            + lock_suffix,
            (
                project_id,
                str(active["conversation_id"]),
                run_id,
            ),
        ).fetchall()
        trusted = rows[0] if len(rows) == 1 else None

        expected_fields = {
            "capability_id",
            "project_id",
            "conversation_id",
            "run_id",
            "session_id",
            "session_revision",
            "asset_index_revision",
            "action",
            "issued_at",
            "not_before",
            "expires_at",
        }
        reason = ""
        if (
            not isinstance(verified, Mapping)
            or set(verified) != expected_fields
        ):
            reason = "hermes_capability_unavailable"
        elif trusted is None:
            reason = "hermes_capability_scope_forbidden"
        else:
            session = connection.execute(
                """
                SELECT session_revision FROM editing_sessions
                WHERE project_id = ? AND session_id = ?
                """,
                (project_id, str(active["session_id"])),
            ).fetchone()
            asset_revision = connection.execute(
                """
                SELECT revision FROM director_asset_index_revisions
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
            current_asset_revision = int(
                asset_revision["revision"]
                if asset_revision is not None
                else 0
            )
            verified_integers = (
                "session_revision",
                "asset_index_revision",
                "issued_at",
                "not_before",
                "expires_at",
            )
            if any(
                type(verified[field]) is not int
                for field in verified_integers
            ):
                reason = "hermes_capability_scope_forbidden"
            elif any(
                verified[field] != expected
                for field, expected in (
                    ("capability_id", str(trusted["jti"])),
                    ("project_id", project_id),
                    (
                        "conversation_id",
                        str(active["conversation_id"]),
                    ),
                    ("run_id", run_id),
                    ("session_id", str(active["session_id"])),
                    (
                        "session_revision",
                        int(trusted["session_revision"]),
                    ),
                    (
                        "asset_index_revision",
                        int(trusted["asset_index_revision"]),
                    ),
                    ("action", "publish_proposal"),
                    ("expires_at", int(trusted["expires_at"])),
                )
            ):
                reason = "hermes_capability_scope_forbidden"
            elif (
                session is None
                or int(session["session_revision"])
                != int(verified["session_revision"])
                or current_asset_revision
                != int(verified["asset_index_revision"])
            ):
                reason = "hermes_capability_scope_forbidden"
            elif int(trusted["expires_at"]) <= int(
                self._clock().timestamp()
            ):
                reason = "hermes_capability_expired"
            elif str(trusted["state"]) == "consumed":
                reason = "hermes_capability_replayed"
            elif str(trusted["state"]) == "revoked":
                reason = "hermes_capability_revoked"
            elif str(trusted["state"]) != "issued":
                reason = "hermes_capability_unavailable"

        if reason:
            self._append_hermes_capability_audit(
                connection,
                capability_id=(
                    str(trusted["jti"]) if trusted is not None else None
                ),
                project_id=project_id,
                conversation_id=str(active["conversation_id"]),
                run_id=run_id,
                action="publish_proposal",
                outcome="denied",
                reason=reason,
                occurred_at=occurred_at,
            )
            return reason

        assert trusted is not None
        updated = connection.execute(
            """
            UPDATE hermes_capability_ledger
            SET state = 'consumed', updated_at = ?
            WHERE project_id = ? AND jti = ? AND state = 'issued'
            """,
            (occurred_at, project_id, str(trusted["jti"])),
        )
        if updated.rowcount != 1:
            return "hermes_capability_unavailable"
        self._append_hermes_capability_audit(
            connection,
            capability_id=str(trusted["jti"]),
            project_id=project_id,
            conversation_id=str(active["conversation_id"]),
            run_id=run_id,
            action="publish_proposal",
            outcome="accepted",
            reason="hermes_capability_consumed",
            occurred_at=occurred_at,
        )
        return "accepted"

    def _ready_yujin_proposal_is_current(
        self,
        *,
        connection: sqlite3.Connection,
        project_id: str,
        proposal: DirectorProposal,
    ) -> bool:
        session = connection.execute(
            "SELECT session_revision, session_json, timeline_id FROM editing_sessions "
            "WHERE project_id = ? AND session_id = ?",
            (project_id, proposal.source_session_id),
        ).fetchone()
        asset_revision = connection.execute(
            "SELECT revision FROM director_asset_index_revisions "
            "WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if (
            session is None
            or int(session["session_revision"]) != proposal.base_session_revision
            or int(asset_revision["revision"] if asset_revision is not None else 0)
            != proposal.asset_index_revision
        ):
            return False
        try:
            session_payload = json.loads(str(session["session_json"] or "{}"))
            segment_ids = {
                str(item.get("segment_id") or "")
                for item in session_payload.get("segments", [])
                if isinstance(item, dict)
            }
            for candidate in proposal.candidates:
                metadata = candidate.canonical_metadata
                if metadata.get("yujin_read_only_finding") is True:
                    timeline = connection.execute(
                        "SELECT timeline_id, version, file_uri, summary_json FROM timelines "
                        "WHERE project_id = ? AND timeline_id = ?",
                        (project_id, str(session["timeline_id"])),
                    ).fetchone()
                    current_gap_count: int | None = None
                    if timeline is not None:
                        try:
                            summary = json.loads(
                                str(timeline["summary_json"] or "{}")
                            )
                            if not isinstance(summary, dict):
                                raise ValueError("timeline_summary_invalid")
                            timeline_path = self.resolve_storage_uri(
                                project_id=project_id,
                                storage_uri=str(timeline["file_uri"]),
                            )
                            timeline_payload = json.loads(
                                timeline_path.read_text(encoding="utf-8")
                            )
                            if not isinstance(timeline_payload, dict):
                                raise ValueError("timeline_payload_invalid")
                            raw_gaps = timeline_payload.get("gap_slots", [])
                            raw_gap_count = (
                                sum(
                                    1
                                    for gap in raw_gaps
                                    if isinstance(gap, dict)
                                )
                                if isinstance(raw_gaps, list)
                                else 0
                            )
                            persisted_gap_count = summary.get("gap_count")
                            if persisted_gap_count is not None and (
                                type(persisted_gap_count) is not int
                                or persisted_gap_count < 0
                                or persisted_gap_count != raw_gap_count
                            ):
                                raise ValueError("timeline_gap_summary_stale")
                            if (
                                str(timeline_payload.get("project_id") or "")
                                != project_id
                                or str(timeline_payload.get("timeline_id") or "")
                                != str(timeline["timeline_id"])
                                or str(timeline_payload.get("version") or "")
                                != str(timeline["version"])
                            ):
                                raise ValueError("timeline_payload_stale")
                            manifest = build_editor_playback_manifest(
                                project_id=project_id,
                                session=session_payload,
                                timeline=timeline_payload,
                                asset_content_url_prefix="",
                            )
                            source_status = manifest.get("source_status")
                            if (
                                not isinstance(source_status, dict)
                                or source_status.get("status") != "current"
                                or str(
                                    source_status.get("source_session_id") or ""
                                )
                                != proposal.source_session_id
                                or int(
                                    source_status.get(
                                        "source_session_revision"
                                    )
                                    or 0
                                )
                                != proposal.base_session_revision
                            ):
                                raise ValueError("timeline_source_stale")
                            current_gaps = manifest.get("gap_slots")
                            if not isinstance(current_gaps, list):
                                raise ValueError("timeline_gap_contract_invalid")
                            current_gap_count = len(current_gaps)
                        except (
                            KeyError,
                            OSError,
                            TypeError,
                            ValueError,
                            json.JSONDecodeError,
                        ):
                            current_gap_count = None
                    if (
                        current_gap_count is None
                        or candidate.availability != "read_only"
                        or not _has_exact_keys(
                            candidate.controls,
                            {"check", "gap_count"},
                        )
                        or candidate.controls.get("check") != "timeline_gaps"
                        or type(candidate.controls.get("gap_count")) is not int
                        or candidate.controls["gap_count"] < 0
                        or candidate.controls["gap_count"]
                        != current_gap_count
                    ):
                        return False
                    continue
                if candidate.availability != "actionable":
                    continue
                target_segment_id = str(metadata.get("target_segment_id") or "")
                if target_segment_id not in segment_ids:
                    return False
                command_kind = str(metadata.get("command_kind") or "")
                if metadata.get("yujin_actionable_operation") is True:
                    if not _valid_b4_candidate_controls(candidate):
                        return False
                    if candidate.media_type == "caption":
                        if command_kind not in {
                            "set_caption_text",
                            "set_caption_style",
                        }:
                            return False
                        continue
                    if candidate.media_type == "overlay" and candidate.controls.get(
                        "overlay_kind"
                    ) != "image":
                        if command_kind != "apply_overlay":
                            return False
                        continue
                asset = connection.execute(
                    "SELECT asset_type, storage_uri, created_at FROM assets "
                    "WHERE project_id = ? AND asset_id = ?",
                    (project_id, candidate.asset_id),
                ).fetchone()
                if asset is None:
                    return False
                actual_type = str(asset["asset_type"] or "")
                claimed_source_kind = str(
                    metadata.get("source_media_kind") or ""
                )
                type_matches = actual_type == claimed_source_kind
                source = self.resolve_storage_uri(
                    project_id=project_id,
                    storage_uri=str(asset["storage_uri"]),
                )
                if (
                    not type_matches
                    or str(asset["created_at"] or "") != candidate.media_revision
                    or not source.is_file()
                    or candidate.expected_content_sha256 is None
                    or sha256_file(source) != candidate.expected_content_sha256
                ):
                    return False
                if candidate.media_type == "voice":
                    tts_candidate_id = str(metadata.get("candidate_id") or "")
                    persisted = connection.execute(
                        "SELECT segment_id, asset_id, technical_status, "
                        "operator_review_status FROM tts_candidates "
                        "WHERE project_id = ? AND candidate_id = ?",
                        (project_id, tts_candidate_id),
                    ).fetchone()
                    if (
                        not tts_candidate_id.startswith("tts_candidate_")
                        or persisted is None
                        or str(persisted["segment_id"] or "")
                        != target_segment_id
                        or str(persisted["asset_id"] or "") != candidate.asset_id
                        or str(persisted["technical_status"] or "") != "accepted"
                        or str(persisted["operator_review_status"] or "")
                        != "approved"
                    ):
                        return False
        except (KeyError, OSError, TypeError, ValueError):
            return False
        return True

    def get_director_hermes_run(
        self, *, project_id: str, run_id: str
    ) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            "SELECT * FROM director_hermes_runs WHERE project_id = ? AND run_id = ?",
            (project_id, run_id),
        )
        if row is None:
            raise KeyError("director_hermes_run_missing")
        return dict(row)

    def list_director_hermes_run_events(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        after_event_id: int = 0,
    ) -> list[dict[str, Any]]:
        if type(after_event_id) is not int or after_event_id < 0:
            raise ValueError("hermes_run_cursor_invalid")
        if not any(
            str(project.get("project_id") or "") == project_id
            for project in self.list_projects()
        ):
            raise KeyError("director_hermes_run_missing")
        connection = self._connection(project_id)
        try:
            run = connection.execute(
                """
                SELECT next_event_id, events_pruned_at
                FROM director_hermes_runs
                WHERE project_id = ? AND conversation_id = ? AND run_id = ?
                """,
                (project_id, conversation_id, run_id),
            ).fetchone()
            if run is None:
                raise KeyError("director_hermes_run_missing")
            if run["events_pruned_at"] is not None:
                raise ValueError("hermes_run_events_expired")
            last_event_id = int(run["next_event_id"]) - 1
            if after_event_id > last_event_id:
                raise ValueError("hermes_run_cursor_out_of_range")
            rows = connection.execute(
                """
                SELECT event_id, event_type, text, retryable
                FROM director_hermes_run_events
                WHERE project_id = ? AND run_id = ? AND event_id > ?
                ORDER BY event_id
                """,
                (project_id, run_id, after_event_id),
            ).fetchall()
            return [
                {
                    "event_id": int(row["event_id"]),
                    "event_type": str(row["event_type"]),
                    "text": str(row["text"] or ""),
                    "retryable": bool(row["retryable"]),
                }
                for row in rows
            ]
        finally:
            connection.close()

    def recover_interrupted_director_hermes_runs(
        self,
        *,
        project_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        """Settle startup orphans once; recovery never grants a new provider owner."""
        excluded = tuple(sorted(set(exclude_run_ids)))
        for run_id in excluded:
            self._validate_hermes_authority_id(run_id)
        now = self._now_iso()
        fallback_suffix = (
            "Hermes is temporarily unavailable. "
            "Manual Director remains available."
        )
        recovered: list[dict[str, Any]] = []
        connection = self._connection(project_id)
        try:
            self._begin_director_hermes_transaction(connection)
            exclusion_sql = (
                " AND run_id NOT IN ("
                + ", ".join("?" for _ in excluded)
                + ")"
                if excluded
                else ""
            )
            rows = connection.execute(
                """
                SELECT run_id, conversation_id, session_id, assistant_draft_text,
                       next_event_id
                FROM director_hermes_runs
                WHERE project_id = ? AND status IN ('pending', 'streaming')
                """
                + exclusion_sql
                + """
                ORDER BY created_at, run_id
                """,
                (project_id, *excluded),
            ).fetchall()
            for row in rows:
                run_id = str(row["run_id"])
                public_text = str(row["assistant_draft_text"] or "")
                assistant_text = (
                    f"{public_text}\n\n{fallback_suffix}"
                    if public_text
                    else fallback_suffix
                )
                assistant_message_id = uuid.uuid4().hex
                next_event_id = int(row["next_event_id"])
                terminal_event_id = next_event_id + (0 if public_text else 0)
                changed = connection.execute(
                    """
                    UPDATE director_hermes_runs
                    SET status = 'interrupted', assistant_message_id = ?,
                        assistant_draft_text = '', next_event_id = ?,
                        updated_at = ?
                    WHERE project_id = ? AND run_id = ?
                      AND status IN ('pending', 'streaming')
                      AND next_event_id = ?
                    """,
                    (
                        assistant_message_id,
                        terminal_event_id + 1,
                        now,
                        project_id,
                        run_id,
                        next_event_id,
                    ),
                )
                if changed.rowcount != 1:
                    continue
                self._revoke_issued_hermes_capabilities_with_connection(
                    connection=connection,
                    project_id=project_id,
                    conversation_id=str(row["conversation_id"]),
                    run_id=run_id,
                    occurred_at=now,
                )
                assistant_message_order = self._next_director_message_order(
                    connection,
                    conversation_id=str(row["conversation_id"]),
                )
                connection.execute(
                    """
                    INSERT INTO director_messages (
                        message_id, conversation_id, project_id, session_id,
                        role, text, proposal_id, metadata_json,
                        client_message_id, message_order, created_at
                    ) VALUES (?, ?, ?, ?, 'assistant', ?, NULL, ?, NULL, ?, ?)
                    """,
                    (
                        assistant_message_id,
                        str(row["conversation_id"]),
                        project_id,
                        str(row["session_id"]),
                        assistant_text,
                        json.dumps(
                            {
                                "hermes_run_id": run_id,
                                "hermes_status": "interrupted",
                                "retryable": True,
                            },
                            ensure_ascii=True,
                            sort_keys=True,
                        ),
                        assistant_message_order,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO director_hermes_run_events (
                        project_id, run_id, event_id, event_type, text,
                        retryable, created_at
                    ) VALUES (?, ?, ?, 'blocked', ?, 1, ?)
                    """,
                    (
                        project_id,
                        run_id,
                        terminal_event_id,
                        assistant_text,
                        now,
                    ),
                )
                connection.execute(
                    "UPDATE director_conversations SET updated_at = ? "
                    "WHERE conversation_id = ?",
                    (now, str(row["conversation_id"])),
                )
                recovered.append(
                    {
                        "run_id": run_id,
                        "status": "interrupted",
                        "assistant_text": assistant_text,
                    }
                )
            connection.commit()
            return recovered
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def prune_director_hermes_run_events(
        self,
        *,
        project_id: str,
        retention_days: int = 30,
        keep_terminal_streams: int = 128,
    ) -> int:
        if retention_days < 1 or keep_terminal_streams < 1:
            raise ValueError("hermes_run_retention_invalid")
        cutoff = (self._clock() - timedelta(days=retention_days)).isoformat()
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            self._begin_director_hermes_transaction(connection)
            terminal = connection.execute(
                """
                SELECT run_id, updated_at
                FROM director_hermes_runs
                WHERE project_id = ?
                  AND status IN ('completed', 'blocked', 'interrupted')
                  AND events_pruned_at IS NULL
                ORDER BY updated_at DESC, run_id DESC
                """,
                (project_id,),
            ).fetchall()
            candidates = [
                str(row["run_id"])
                for index, row in enumerate(terminal)
                if index >= keep_terminal_streams
                or str(row["updated_at"]) <= cutoff
            ]
            for run_id in candidates:
                connection.execute(
                    "DELETE FROM director_hermes_run_events "
                    "WHERE project_id = ? AND run_id = ?",
                    (project_id, run_id),
                )
                connection.execute(
                    "UPDATE director_hermes_runs SET events_pruned_at = ? "
                    "WHERE project_id = ? AND run_id = ? "
                    "AND status IN ('completed', 'blocked', 'interrupted') "
                    "AND events_pruned_at IS NULL",
                    (now, project_id, run_id),
                )
            connection.commit()
            return len(candidates)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def capcut_draft_handoff_claim_renewal_interval_seconds() -> float:
        """Renew well before expiry while keeping a crashed owner recoverable."""
        return CAPCUT_DRAFT_HANDOFF_CLAIM_LEASE_SECONDS / 3

    def renew_capcut_draft_handoff_claim(self, *, project_id: str, claim: dict[str, Any]) -> bool:
        """Extend only this still-live owner token; a stale owner can never revive itself."""
        connection = self._connection(project_id)
        try:
            self._begin_capcut_draft_handoff_transaction(connection)
            now = datetime.now(UTC)
            now_iso = now.isoformat()
            expires_at = (now + timedelta(seconds=CAPCUT_DRAFT_HANDOFF_CLAIM_LEASE_SECONDS)).isoformat()
            cursor = connection.execute(
                """UPDATE exports
                   SET handoff_claim_expires_at = ?
                   WHERE project_id = ? AND export_id = ? AND export_type = ?
                     AND status = ? AND is_current = 1
                     AND handoff_claim_token = ? AND handoff_claim_job_id = ?
                     AND handoff_claim_expires_at > ?""",
                (
                    expires_at,
                    project_id,
                    str(claim["export_id"]),
                    "capcut_draft_export",
                    JobStatus.SUCCEEDED.value,
                    str(claim["claim_token"]),
                    str(claim["job_id"]),
                    now_iso,
                ),
            )
            connection.commit()
            return cursor.rowcount == 1
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def publish_capcut_draft_handoff_if_current(
        self, *, project_id: str, claim: dict[str, Any], handoff: dict[str, Any]
    ) -> bool:
        """Publish only for the exact durable owner while its lineage is current."""
        connection = self._connection(project_id)
        try:
            self._begin_capcut_draft_handoff_transaction(connection)
            job = connection.execute(
                """SELECT job_type, status, output_ref FROM jobs
                   WHERE project_id = ? AND job_id = ?""",
                (project_id, str(claim["job_id"])),
            ).fetchone()
            export = connection.execute(
                """SELECT timeline_id, status, is_current, source_session_id,
                          source_session_revision, metadata_json, handoff_claim_token,
                          handoff_claim_job_id, handoff_claim_expires_at
                   FROM exports
                   WHERE project_id = ? AND export_id = ?
                     AND export_type = ?""",
                (project_id, str(claim["export_id"]), "capcut_draft_export"),
            ).fetchone()
            active_session = connection.execute(
                """SELECT session_id, session_revision FROM editing_sessions
                   WHERE project_id = ?
                   ORDER BY updated_at DESC, created_at DESC, session_id DESC
                   LIMIT 1""",
                (project_id,),
            ).fetchone()
            now_iso = datetime.now(UTC).isoformat()
            try:
                claim_not_expired = bool(export and export["handoff_claim_expires_at"]) and datetime.fromisoformat(
                    str(export["handoff_claim_expires_at"])
                ) > datetime.fromisoformat(now_iso)
            except (TypeError, ValueError):
                claim_not_expired = False
            claim_is_current = (
                job is not None
                and str(job["job_type"]) == JobType.CAPCUT_DRAFT_EXPORT.value
                and str(job["status"]) == JobStatus.SUCCEEDED.value
                and str(job["output_ref"] or "") == str(claim["export_id"])
                and export is not None
                and str(export["timeline_id"]) == str(claim["timeline_id"])
                and str(export["status"]) == JobStatus.SUCCEEDED.value
                and bool(export["is_current"])
                and (str(export["source_session_id"]) if export["source_session_id"] is not None else None)
                == claim["export_source_session_id"]
                and (int(export["source_session_revision"]) if export["source_session_revision"] is not None else None)
                == claim["export_source_session_revision"]
                and (str(active_session["session_id"]) if active_session is not None else None)
                == claim["active_session_id"]
                and (int(active_session["session_revision"]) if active_session is not None else None)
                == claim["active_session_revision"]
                and str(export["handoff_claim_token"] or "") == str(claim["claim_token"])
                and str(export["handoff_claim_job_id"] or "") == str(claim["job_id"])
                and claim_not_expired
            )
            if not claim_is_current:
                connection.rollback()
                return False
            metadata = json.loads(str(export["metadata_json"] or "{}"))
            metadata["handoff"] = handoff
            cursor = connection.execute(
                """UPDATE exports
                   SET metadata_json = ?, handoff_claim_token = NULL, handoff_claim_job_id = NULL,
                       handoff_claimed_at = NULL, handoff_claim_expires_at = NULL
                   WHERE project_id = ? AND export_id = ? AND export_type = ?
                     AND status = ? AND is_current = 1
                     AND handoff_claim_token = ? AND handoff_claim_job_id = ?
                     AND handoff_claim_expires_at > ?""",
                (
                    json.dumps(metadata, ensure_ascii=True),
                    project_id,
                    str(claim["export_id"]),
                    "capcut_draft_export",
                    JobStatus.SUCCEEDED.value,
                    str(claim["claim_token"]),
                    str(claim["job_id"]),
                    now_iso,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False
            connection.commit()
            return True
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def release_capcut_draft_handoff_claim(self, *, project_id: str, claim: dict[str, Any]) -> bool:
        """Release only this owner token; never clear a claim reclaimed by another request."""
        connection = self._connection(project_id)
        try:
            self._begin_capcut_draft_handoff_transaction(connection)
            cursor = connection.execute(
                """UPDATE exports
                   SET handoff_claim_token = NULL, handoff_claim_job_id = NULL,
                       handoff_claimed_at = NULL, handoff_claim_expires_at = NULL
                   WHERE project_id = ? AND export_id = ? AND export_type = ?
                     AND handoff_claim_token = ? AND handoff_claim_job_id = ?""",
                (
                    project_id,
                    str(claim["export_id"]),
                    "capcut_draft_export",
                    str(claim["claim_token"]),
                    str(claim["job_id"]),
                ),
            )
            connection.commit()
            return cursor.rowcount == 1
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def create_job(
        self,
        *,
        project_id: str,
        job_type: JobType,
        input_ref: str | None = None,
        status: JobStatus = JobStatus.PENDING,
    ) -> dict[str, Any]:
        sequence = self._count_rows(project_id, "jobs") + 1
        job_id = f"{job_type.value}_job_{sequence:03d}"
        started_at = None if status is JobStatus.PENDING else self._now_iso()
        finished_at = started_at if status in {JobStatus.SUCCEEDED, JobStatus.FAILED} else None
        payload = {
            "job_id": job_id,
            "project_id": project_id,
            "job_type": job_type.value,
            "status": status.value,
            "input_ref": input_ref,
            "output_ref": None,
            "error_message": None,
            "started_at": started_at,
            "finished_at": finished_at,
            "progress_percent": None,
        }
        self._execute(
            project_id,
            """
            INSERT INTO jobs (
                job_id,
                project_id,
                job_type,
                status,
                input_ref,
                output_ref,
                error_message,
                started_at,
                finished_at,
                progress_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["job_id"],
                payload["project_id"],
                payload["job_type"],
                payload["status"],
                payload["input_ref"],
                payload["output_ref"],
                payload["error_message"],
                payload["started_at"],
                payload["finished_at"],
                payload["progress_percent"],
            ),
        )
        return payload

    def create_or_reuse_active_final_render_job(
        self,
        *,
        project_id: str,
        timeline_job_id: str,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically claim the one active final render for a timeline job."""
        return self._create_or_reuse_active_output_job(
            project_id=project_id,
            timeline_job_id=timeline_job_id,
            job_type=JobType.FINAL_RENDER,
        )

    def create_or_reuse_active_capcut_draft_export_job(
        self,
        *,
        project_id: str,
        timeline_job_id: str,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically claim the one active CapCut draft export for a timeline job."""
        return self._create_or_reuse_active_output_job(
            project_id=project_id,
            timeline_job_id=timeline_job_id,
            job_type=JobType.CAPCUT_DRAFT_EXPORT,
        )

    def create_or_reuse_active_asset_preview_job(
        self,
        *,
        project_id: str,
        input_ref: str,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically claim the one active browser proxy for a source identity."""
        return self._create_or_reuse_active_output_job(
            project_id=project_id,
            timeline_job_id=input_ref,
            job_type=JobType.ASSET_PREVIEW_PROXY,
        )

    def _create_or_reuse_active_output_job(
        self,
        *,
        project_id: str,
        timeline_job_id: str,
        job_type: JobType,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically claim one active output job for a timeline job.

        A terminal job deliberately is not reusable: a person may explicitly
        start a new render after a failure or after a completed export.  Only
        ``pending`` and ``running`` records are a live claim.
        """
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            # SQLite's BEGIN IMMEDIATE serializes writers.  PostgreSQL uses a
            # compatible connection wrapper, where the translated BEGIN needs
            # this narrow table lock to give the select-then-insert claim the
            # same serialization guarantee.
            if not isinstance(connection, sqlite3.Connection):
                connection.execute("LOCK TABLE jobs IN SHARE ROW EXCLUSIVE MODE")
            existing = connection.execute(
                """
                SELECT job_id, project_id, job_type, status, input_ref, output_ref,
                       error_message, started_at, finished_at, progress_percent
                FROM jobs
                WHERE project_id = ?
                  AND job_type = ?
                  AND input_ref = ?
                  AND status IN (?, ?)
                ORDER BY COALESCE(started_at, '') DESC, job_id DESC
                LIMIT 1
                """,
                (
                    project_id,
                    job_type.value,
                    timeline_job_id,
                    JobStatus.PENDING.value,
                    JobStatus.RUNNING.value,
                ),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return dict(existing), False

            sequence_row = connection.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE project_id = ?", (project_id,)
            ).fetchone()
            sequence = int(sequence_row["count"]) + 1
            job_id = f"{job_type.value}_job_{sequence:03d}"
            started_at = self._now_iso()
            payload = {
                "job_id": job_id,
                "project_id": project_id,
                "job_type": job_type.value,
                "status": JobStatus.RUNNING.value,
                "input_ref": timeline_job_id,
                "output_ref": None,
                "error_message": None,
                "started_at": started_at,
                "finished_at": None,
                "progress_percent": None,
            }
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, project_id, job_type, status, input_ref, output_ref,
                    error_message, started_at, finished_at, progress_percent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["job_id"],
                    payload["project_id"],
                    payload["job_type"],
                    payload["status"],
                    payload["input_ref"],
                    payload["output_ref"],
                    payload["error_message"],
                    payload["started_at"],
                    payload["finished_at"],
                    payload["progress_percent"],
                ),
            )
            connection.commit()
            return payload, True
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def update_job(
        self,
        *,
        project_id: str,
        job_id: str,
        status: JobStatus,
        output_ref: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        started_at = self._now_iso() if status is JobStatus.RUNNING else None
        finished_at = self._now_iso() if status in {JobStatus.SUCCEEDED, JobStatus.FAILED} else None
        # A finished job always reports a definite progress value so the UI
        # doesn't get stuck showing a stale in-flight percentage.
        finished_progress_percent = 100 if status is JobStatus.SUCCEEDED else None
        self._execute(
            project_id,
            """
            UPDATE jobs
            SET status = ?,
                output_ref = COALESCE(?, output_ref),
                error_message = ?,
                started_at = COALESCE(started_at, ?),
                finished_at = COALESCE(?, finished_at),
                progress_percent = COALESCE(?, progress_percent)
            WHERE project_id = ? AND job_id = ?
            """,
            (status.value, output_ref, error_message, started_at, finished_at, finished_progress_percent, project_id, job_id),
        )
        return self.get_job(project_id=project_id, job_id=job_id)

    def update_job_progress(self, *, project_id: str, job_id: str, progress_percent: int) -> None:
        self._execute(
            project_id,
            "UPDATE jobs SET progress_percent = ? WHERE project_id = ? AND job_id = ?",
            (max(0, min(100, progress_percent)), project_id, job_id),
        )

    def get_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT
                job_id,
                project_id,
                job_type,
                status,
                input_ref,
                output_ref,
                error_message,
                started_at,
                finished_at,
                progress_percent
            FROM jobs
            WHERE project_id = ? AND job_id = ?
            """,
            (project_id, job_id),
        )
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        return dict(row)

    def get_latest_asset_preview_job(
        self,
        *,
        project_id: str,
        input_ref: str,
    ) -> dict[str, Any] | None:
        row = self._fetchone(
            project_id,
            """
            SELECT
                job_id, project_id, job_type, status, input_ref, output_ref,
                error_message, started_at, finished_at, progress_percent
            FROM jobs
            WHERE project_id = ? AND job_type = ? AND input_ref = ?
            ORDER BY COALESCE(started_at, '') DESC, job_id DESC
            LIMIT 1
            """,
            (project_id, JobType.ASSET_PREVIEW_PROXY.value, input_ref),
        )
        return dict(row) if row is not None else None

    def recover_orphaned_asset_preview_jobs(self, *, project_id: str) -> int:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, error_message = ?, finished_at = ?
                WHERE project_id = ?
                  AND job_type = ?
                  AND status IN (?, ?)
                """,
                (
                    JobStatus.FAILED.value,
                    "PREVIEW_WORKER_RESTARTED",
                    self._now_iso(),
                    project_id,
                    JobType.ASSET_PREVIEW_PROXY.value,
                    JobStatus.PENDING.value,
                    JobStatus.RUNNING.value,
                ),
            )
            connection.commit()
            return int(cursor.rowcount)
        finally:
            connection.close()

    # Everything except the two types that own a recovery path of their own:
    # media analysis re-queues through the dispatcher, asset previews through
    # recover_orphaned_asset_preview_jobs. The rest run on a daemon thread in
    # the API process, so a restart leaves the row claiming `running` with no
    # thread behind it -- and retry_job only accepts `failed`.
    _IN_PROCESS_JOB_TYPES: tuple[str, ...] = tuple(
        job_type.value
        for job_type in JobType
        if job_type not in {JobType.MEDIA_ANALYSIS, JobType.ASSET_PREVIEW_PROXY}
    )

    def recover_orphaned_in_process_jobs(self, *, project_id: str) -> list[str]:
        """Fail jobs a restart stranded, so the owner's retry button works."""
        connection = self._connection(project_id)
        try:
            placeholders = ", ".join("?" for _ in self._IN_PROCESS_JOB_TYPES)
            select_sql = f"""
                SELECT job_id FROM jobs
                WHERE project_id = ?
                  AND job_type IN ({placeholders})
                  AND status IN (?, ?)
                """
            parameters = (
                project_id,
                *self._IN_PROCESS_JOB_TYPES,
                JobStatus.PENDING.value,
                JobStatus.RUNNING.value,
            )
            stranded = [str(row["job_id"]) for row in connection.execute(select_sql, parameters).fetchall()]
            if not stranded:
                return []
            connection.execute(
                f"""
                    UPDATE jobs
                    SET status = ?, error_message = ?, finished_at = ?
                    WHERE project_id = ?
                      AND job_type IN ({placeholders})
                      AND status IN (?, ?)
                    """,
                (
                    JobStatus.FAILED.value,
                    "WORKER_RESTARTED",
                    self._now_iso(),
                    *parameters,
                ),
            )
            connection.commit()
            return stranded
        finally:
            connection.close()

    def list_jobs(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT
                    job_id,
                    project_id,
                    job_type,
                    status,
                    input_ref,
                    output_ref,
                    error_message,
                    started_at,
                    finished_at,
                    progress_percent
                FROM jobs
                WHERE project_id = ?
                ORDER BY COALESCE(started_at, ''), job_id ASC
                """,
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def update_asset_metadata(self, *, project_id: str, asset_id: str, metadata_patch: dict[str, Any]) -> dict[str, Any]:
        asset = self.get_asset(project_id=project_id, asset_id=asset_id)
        merged_metadata = {**asset["metadata"], **metadata_patch}
        self._execute_asset_index_mutation(
            project_id,
            "UPDATE assets SET metadata_json = ? WHERE project_id = ? AND asset_id = ?",
            (json.dumps(merged_metadata, ensure_ascii=True), project_id, asset_id),
        )
        return self.get_asset(project_id=project_id, asset_id=asset_id)

    def get_asset(self, *, project_id: str, asset_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at
            FROM assets
            WHERE project_id = ? AND asset_id = ?
            """,
            (project_id, asset_id),
        )
        if row is None:
            raise KeyError(f"Asset not found: {asset_id}")
        payload = dict(row)
        payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
        return payload

    def list_assets(
        self,
        *,
        project_id: str,
        asset_type: AssetType | None = None,
    ) -> list[dict[str, Any]]:
        if asset_type is None:
            query = """
            SELECT asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at
            FROM assets
            WHERE project_id = ?
            ORDER BY created_at ASC
            """
            params: tuple[Any, ...] = (project_id,)
        else:
            query = """
            SELECT asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at
            FROM assets
            WHERE project_id = ? AND asset_type = ?
            ORDER BY created_at ASC
            """
            params = (project_id, asset_type.value)
        connection = self._connection(project_id)
        try:
            rows = connection.execute(query, params).fetchall()
        finally:
            connection.close()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
            items.append(payload)
        return items

    def list_segments(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT segment_id, project_id, start_sec, end_sec, text, source_asset_id,
                       confidence, cleanup_decision, review_required, metadata_json
                FROM segments
                WHERE project_id = ?
                ORDER BY start_sec ASC, segment_id ASC
                """,
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["review_required"] = _normalize_boolish(payload["review_required"])
            payload["metadata"] = self._json_object(payload.pop("metadata_json"))
            payload["provider_trace"] = payload["metadata"].get("provider_trace") or build_provider_trace(
                final_provider="heuristic_fallback"
            )
            items.append(payload)
        return items

    def list_recommendation_rows(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT recommendation_id, project_id, target_segment_id, recommendation_type,
                       selected_asset_id, score, reason, auto_apply_allowed,
                       review_required, decision_state, payload_json, created_at
                FROM recommendations
                WHERE project_id = ?
                ORDER BY created_at ASC
                """,
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["auto_apply_allowed"] = _normalize_boolish(payload["auto_apply_allowed"])
            payload["review_required"] = _normalize_boolish(payload["review_required"])
            payload["decision_state"] = self._normalize_recommendation_decision_state(payload)
            payload["payload"] = self._json_object(payload.pop("payload_json"))
            payload["provider_trace"] = payload["payload"].get("provider_trace") or build_provider_trace(
                final_provider="heuristic_fallback"
                if _canonical_recommendation_type(payload["recommendation_type"]) == RecommendationType.BROLL.value
                else "rule_based_fallback"
            )
            items.append(payload)
        return items

    def get_transcript(self, *, project_id: str, transcript_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT transcript_id, project_id, source_asset_id, transcript_uri, transcript_text, provider_name, segments_json, created_at
            FROM transcripts
            WHERE project_id = ? AND transcript_id = ?
            """,
            (project_id, transcript_id),
        )
        if row is None:
            raise KeyError(f"Transcript not found: {transcript_id}")
        payload = dict(row)
        payload["segments"] = json.loads(payload.pop("segments_json"))
        return payload

    def get_segment_analysis(self, *, project_id: str, segment_analysis_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT segment_analysis_id, project_id, transcript_id, script_asset_id, file_uri, segments_json, created_at
            FROM segment_analysis_runs
            WHERE project_id = ? AND segment_analysis_id = ?
            """,
            (project_id, segment_analysis_id),
        )
        if row is None:
            raise KeyError(f"Segment analysis not found: {segment_analysis_id}")
        payload = dict(row)
        payload["segments"] = json.loads(payload.pop("segments_json"))
        for segment in payload["segments"]:
            if "provider_trace" not in segment:
                metadata = segment.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                    segment["metadata"] = metadata
                segment["provider_trace"] = metadata.get("provider_trace") or build_provider_trace(
                    final_provider="heuristic_fallback"
                )
        return payload

    def get_recommendation_run(
        self,
        *,
        project_id: str,
        recommendation_run_id: str,
        recommendation_type: RecommendationType,
    ) -> dict[str, Any]:
        file_path = (
            self.project_root(project_id)
            / "analysis"
            / "recommendations"
            / f"{recommendation_run_id}.json"
        )
        if not file_path.exists():
            raise KeyError(f"Recommendation run not found: {recommendation_run_id}")
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if _canonical_recommendation_type(payload.get("recommendation_type")) != recommendation_type.value:
            raise KeyError(f"Recommendation run type mismatch: {recommendation_run_id}")
        payload["recommendation_type"] = _canonical_recommendation_type(payload.get("recommendation_type"))
        fallback_provider = (
            "heuristic_fallback"
            if recommendation_type == RecommendationType.BROLL
            else "rule_based_fallback"
        )
        for item in payload.get("recommendations", []):
            item_payload = item.get("payload")
            if not isinstance(item_payload, dict):
                item_payload = {}
                item["payload"] = item_payload
            item["provider_trace"] = item.get("provider_trace") or item_payload.get("provider_trace") or build_provider_trace(
                final_provider=fallback_provider
            )
        return payload

    def get_timeline_run(self, *, project_id: str, timeline_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT timeline_id, project_id, version, output_mode, file_uri, summary_json, created_at
            FROM timelines
            WHERE project_id = ? AND timeline_id = ?
            """,
            (project_id, timeline_id),
        )
        if row is None:
            raise KeyError(f"Timeline not found: {timeline_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Timeline JSON missing: {timeline_id}")
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        payload["summary"] = json.loads(row["summary_json"] or "{}")
        return payload

    def get_persisted_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
    ) -> dict[str, Any] | None:
        timeline_payload = self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
        operator_guidance = timeline_payload.get("operator_guidance")
        return operator_guidance if isinstance(operator_guidance, dict) else None

    def get_operator_guidance_reuse_key(
        self,
        *,
        project_id: str,
        timeline_id: str,
    ) -> str | None:
        timeline_payload = self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
        reuse_key = timeline_payload.get("_operator_guidance_reuse_key")
        if not isinstance(reuse_key, str):
            return None
        normalized_reuse_key = reuse_key.strip()
        return normalized_reuse_key or None

    def save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, Any],
    ) -> dict[str, Any]:
        file_path = self._timeline_file_path(project_id=project_id, timeline_id=timeline_id)
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        payload["operator_guidance"] = operator_guidance
        file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        try:
            self._append_provider_trace_audit_event(
                project_id=project_id,
                event={
                    "artifact_type": "review_guidance",
                    "artifact_id": f"{timeline_id}:review_guidance:{self._next_provider_trace_event_sequence(project_id=project_id):03d}",
                    "timeline_id": timeline_id,
                    "created_at": self._now_iso(),
                    "provider_trace": operator_guidance.get("provider_trace")
                    or build_provider_trace(final_provider="heuristic_fallback"),
                },
            )
        except OSError:
            pass
        return operator_guidance

    def save_operator_guidance_reuse_key(
        self,
        *,
        project_id: str,
        timeline_id: str,
        reuse_key: str,
    ) -> str:
        file_path = self._timeline_file_path(project_id=project_id, timeline_id=timeline_id)
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        normalized_reuse_key = str(reuse_key or "").strip()
        if normalized_reuse_key:
            payload["_operator_guidance_reuse_key"] = normalized_reuse_key
        else:
            payload.pop("_operator_guidance_reuse_key", None)
        file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return normalized_reuse_key

    def save_provider_trace_audit_event(self, *, project_id: str, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("created_at", self._now_iso())
        authoritative_error: Exception | None = None
        if str(payload.get("status") or "") == JobStatus.FAILED.value:
            try:
                self._save_failed_provider_trace_run(project_id=project_id, event=payload)
            except Exception as exc:
                authoritative_error = exc
        try:
            self._append_provider_trace_audit_event(project_id=project_id, event=payload)
        except OSError:
            if authoritative_error is not None:
                raise authoritative_error
        else:
            authoritative_error = None
        if authoritative_error is not None:
            raise authoritative_error
        return payload

    def clear_operator_guidance(self, *, project_id: str, timeline_id: str) -> None:
        file_path = self._timeline_file_path(project_id=project_id, timeline_id=timeline_id)
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if "operator_guidance" not in payload and "_operator_guidance_reuse_key" not in payload:
            return
        payload.pop("operator_guidance", None)
        payload.pop("_operator_guidance_reuse_key", None)
        file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    def get_preview_run(self, *, project_id: str, preview_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT preview_id, project_id, timeline_id, file_uri, status, summary_json, created_at, source_session_id, source_session_revision, is_current, invalidated_at, invalidated_reason
            FROM preview_renders
            WHERE project_id = ? AND preview_id = ?
            """,
            (project_id, preview_id),
        )
        if row is None:
            raise KeyError(f"Preview not found: {preview_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Preview artifact missing: {preview_id}")
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        payload["provider_trace"] = payload.get("provider_trace") or build_provider_trace(final_provider="static_fallback")
        payload["summary"] = json.loads(row["summary_json"] or "{}")
        payload["created_at"] = row["created_at"]
        payload["source_session_id"] = row["source_session_id"]
        payload["source_session_revision"] = row["source_session_revision"]
        payload["is_current"] = bool(row["is_current"])
        payload["invalidated_at"] = row["invalidated_at"]
        payload["invalidated_reason"] = row["invalidated_reason"]
        return payload

    def get_subtitle_run(self, *, project_id: str, subtitle_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT subtitle_id, project_id, timeline_id, format, file_uri, status, summary_json, created_at, source_session_id, source_session_revision, is_current, invalidated_at, invalidated_reason
            FROM subtitle_renders
            WHERE project_id = ? AND subtitle_id = ?
            """,
            (project_id, subtitle_id),
        )
        if row is None:
            raise KeyError(f"Subtitle not found: {subtitle_id}")
        payload = dict(row)
        summary = json.loads(payload.pop("summary_json") or "{}")
        payload["notes"] = summary.get("notes") or ["Subtitle file generated from approved review timeline."]
        payload["summary"] = summary
        payload["is_current"] = bool(payload.get("is_current"))
        return payload

    def get_export_run(self, *, project_id: str, export_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT export_id, project_id, timeline_id, export_type, file_uri, status, metadata_json, created_at, source_session_id, source_session_revision, is_current, invalidated_at, invalidated_reason
            FROM exports
            WHERE project_id = ? AND export_id = ?
            """,
            (project_id, export_id),
        )
        if row is None:
            raise KeyError(f"Export not found: {export_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Export artifact missing: {export_id}")
        # 이 함수는 CapCut 초안처럼 JSON 매니페스트를 담은 출력만 읽는다. 완성본은
        # mp4라 텍스트로 읽으면 디코딩이 깨지고, 그 오류가 그대로 사용자에게
        # 나갔다. 완성본 행은 `get_final_render_export`가 따로 읽는다.
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KeyError(f"Export is not a readable manifest: {export_id}") from exc
        payload["provider_trace"] = payload.get("provider_trace") or build_provider_trace(final_provider="static_fallback")
        payload["metadata"] = json.loads(row["metadata_json"] or "{}")
        payload["created_at"] = row["created_at"]
        payload["source_session_id"] = row["source_session_id"]
        payload["source_session_revision"] = row["source_session_revision"]
        payload["is_current"] = bool(row["is_current"])
        payload["invalidated_at"] = row["invalidated_at"]
        payload["invalidated_reason"] = row["invalidated_reason"]
        payload["is_current"] = bool(payload["is_current"])
        return payload

    def get_editing_session(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT session_id, project_id, timeline_id, file_uri, summary_json, session_revision, session_json, created_at, updated_at
            FROM editing_sessions
            WHERE project_id = ? AND session_id = ?
            """,
            (project_id, session_id),
        )
        if row is None:
            raise KeyError(f"Editing session not found: {session_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        canonical_json = str(row["session_json"] or "")
        try:
            payload = json.loads(canonical_json) if canonical_json and canonical_json != "{}" else {}
        except json.JSONDecodeError:
            payload = {}
        if not payload:
            if not file_path.exists():
                raise KeyError(f"Editing session JSON missing: {session_id}")
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        elif (not file_path.exists()) or file_path.read_text(encoding="utf-8") != canonical_json:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            recovery_path = file_path.with_name(f".{file_path.name}.{uuid.uuid4().hex}.tmp")
            recovery_path.write_text(canonical_json, encoding="utf-8")
            recovery_path.replace(file_path)
        payload["summary"] = json.loads(row["summary_json"] or "{}")
        payload["session_revision"] = int(row["session_revision"])
        payload["undo_count"] = len(payload.get("undo_stack", []))
        payload["redo_count"] = len(payload.get("redo_stack", []))
        payload["created_at"] = row["created_at"]
        payload["updated_at"] = row["updated_at"]
        return payload

    def get_latest_editing_session(self, *, project_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT session_id
            FROM editing_sessions
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, session_id DESC
            LIMIT 1
            """,
            (project_id,),
        )
        if row is None:
            raise KeyError(f"Editing session not found for project: {project_id}")
        return self.get_editing_session(project_id=project_id, session_id=str(row["session_id"]))

    def build_review_snapshot(
        self,
        *,
        project_id: str,
        timeline_id: str | None = None,
        segments: list[dict[str, Any]],
        recommendations: list[dict[str, Any]] | None = None,
        timeline_review_flags: list[dict[str, Any]],
        timeline_applied_recommendations: list[dict[str, Any]] | None = None,
        timeline_pending_recommendations: list[dict[str, Any]] | None = None,
        source_variant_id: str | None = None,
        source_variant_revision: int | None = None,
    ) -> dict[str, Any]:
        if timeline_applied_recommendations is not None or timeline_pending_recommendations is not None:
            applied_candidates: list[dict[str, Any]] = []
            for item in timeline_applied_recommendations or []:
                decision_state = self._normalize_recommendation_decision_state(item)
                applied_candidates.append(
                    self._review_snapshot_recommendation_payload(
                        item,
                        fallback_decision_state=decision_state,
                    )
                )
            pending_candidates: list[dict[str, Any]] = []
            for item in timeline_pending_recommendations or []:
                decision_state = self._normalize_recommendation_decision_state(item)
                pending_candidates.append(
                    self._review_snapshot_recommendation_payload(
                        item,
                        fallback_decision_state=decision_state,
                    )
                )
            applied = [
                item
                for item in applied_candidates
                if str(item.get("decision_state") or "") == "approved"
                and _is_store_supported_recommendation_type(item)
            ]
            applied.extend(
                item
                for item in pending_candidates
                if str(item.get("decision_state") or "") == "approved"
                and _is_store_supported_recommendation_type(item)
            )
            pending = [
                item
                for item in applied_candidates
                if str(item.get("decision_state") or "") == "pending"
                and _is_store_blocking_pending_recommendation(item)
            ]
            pending.extend(
                item
                for item in pending_candidates
                if str(item.get("decision_state") or "") == "pending"
                and _is_store_blocking_pending_recommendation(item)
            )
        else:
            recommendation_rows: list[dict[str, Any]] = []
            if any(
                isinstance(item, dict)
                and not str(item.get("recommendation_type") or "").strip()
                for item in recommendations or []
            ):
                recommendation_rows = self.list_recommendation_rows(project_id=project_id)
            normalized_recommendations = [
                self._review_snapshot_recommendation_payload(
                    self._hydrate_review_snapshot_recommendation_type(
                        recommendation=item,
                        recommendation_rows=recommendation_rows,
                    )
                )
                for item in recommendations or []
            ]
            applied = [
                item
                for item in normalized_recommendations
                if str(item.get("decision_state") or "") == "approved"
                and _is_store_supported_recommendation_type(item)
            ]
            pending = [
                item
                for item in normalized_recommendations
                if str(item.get("decision_state") or "") == "pending"
                and _is_store_blocking_pending_recommendation(item)
            ]
        has_blocking_review_flag = any(
            _is_store_blocking_review_flag(flag) for flag in timeline_review_flags
        )
        has_blocking_pending_recommendation = any(
            _is_store_blocking_pending_recommendation(item) for item in pending
        )
        if has_blocking_review_flag or has_blocking_pending_recommendation:
            review_status = "blocked"
        elif timeline_id:
            try:
                review_status = self.get_review_state(
                    project_id=project_id,
                    timeline_id=str(timeline_id),
                )["status"]
            except KeyError:
                review_status = "draft"
        else:
            review_status = "blocked"
        normalized_review_flags = _normalize_review_flag_payloads(timeline_review_flags)
        return {
            "project_id": project_id,
            "timeline_id": timeline_id,
            "source_variant_id": source_variant_id,
            "source_variant_revision": source_variant_revision,
            "review_status": review_status,
            "segments": segments,
            "applied_recommendations": applied,
            "pending_recommendations": pending,
            "review_flags": normalized_review_flags,
        }

    def _review_snapshot_recommendation_payload(
        self,
        recommendation: dict[str, Any],
        *,
        fallback_decision_state: str | None = None,
    ) -> dict[str, Any]:
        payload = deepcopy(recommendation)
        payload["decision_state"] = fallback_decision_state or self._normalize_recommendation_decision_state(
            payload
        )
        payload["provider_trace"] = payload.get("provider_trace") or payload.get("payload", {}).get(
            "provider_trace"
        ) or build_provider_trace(
            final_provider=(
                "heuristic_fallback"
                if _canonical_recommendation_type(payload.get("recommendation_type"))
                == RecommendationType.BROLL.value
                else "rule_based_fallback"
            )
        )
        return payload

    def _hydrate_review_snapshot_recommendation_type(
        self,
        *,
        recommendation: dict[str, Any],
        recommendation_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = deepcopy(recommendation)
        if str(payload.get("recommendation_type") or "").strip():
            return payload

        matched_types = {
            str(row.get("recommendation_type") or "").strip()
            for row in recommendation_rows
            if isinstance(row, dict)
            and str(row.get("target_segment_id") or "").strip()
            == str(payload.get("target_segment_id") or "").strip()
            and str(row.get("selected_asset_id") or "").strip()
            == str(payload.get("selected_asset_id") or "").strip()
            and str(row.get("reason") or "").strip() == str(payload.get("reason") or "").strip()
            and float(row.get("score") or 0.0) == float(payload.get("score") or 0.0)
        }
        if len(matched_types) == 1:
            payload["recommendation_type"] = next(iter(matched_types))
        return payload

    def get_provider_trace_audit(
        self,
        *,
        project_id: str,
        timeline_id: str | None = None,
        include_upstream: bool = False,
        job_type: str | None = None,
        artifact_type: str | None = None,
        final_provider: str | None = None,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        jobs = self.list_jobs(project_id=project_id)
        entries: list[dict[str, Any]] = []
        # 다른 조용한 실패를 진단하려고 여는 화면이다. 읽지 못한 산출물을
        # 그냥 건너뛰고 완전한 목록인 것처럼 내놓으면, 여기서부터 근거가
        # 없어진다. 빠뜨리는 동작은 그대로 두고 무엇을 못 읽었는지 남긴다.
        unreadable: list[str] = []
        first_error: list[Exception] = []

        def _skipped(kind: str, ref: str, error: Exception) -> None:
            unreadable.append(f"{kind}:{ref}")
            if not first_error:
                first_error.append(error)

        filter_timeline_id = self._normalized_provider_trace_filter_value(timeline_id)
        filter_job_type = self._normalized_provider_trace_filter_value(job_type)
        filter_artifact_type = self._normalized_provider_trace_filter_value(artifact_type)
        filter_final_provider = self._normalized_provider_trace_filter_value(final_provider)
        filter_fallback_reason = self._normalized_provider_trace_filter_value(fallback_reason)
        upstream_segment_job_ids: set[str] = set()
        upstream_recommendation_job_ids: set[str] = set()
        use_exact_recommendation_lineage = False
        timeline_jobs_by_timeline_id = {
            str(job.get("output_ref") or ""): job
            for job in jobs
            if job["job_type"] == JobType.TIMELINE_BUILD.value and job.get("output_ref")
        }
        review_guidance_jobs_by_timeline_id = dict(timeline_jobs_by_timeline_id)
        timeline_ids_by_timeline_job_id = {
            str(job.get("job_id") or ""): str(job.get("output_ref") or "")
            for job in jobs
            if job["job_type"] == JobType.TIMELINE_BUILD.value and job.get("output_ref")
        }
        for job in jobs:
            if job["job_type"] != JobType.PARTIAL_REGENERATION.value or not job.get("output_ref"):
                continue
            try:
                partial_regeneration = self.get_partial_regeneration_run(
                    project_id=project_id,
                    partial_regeneration_id=str(job["output_ref"]),
                )
            except Exception as exc:  # noqa: BLE001 - 하나가 나머지를 막지 않는다
                _skipped("partial_regeneration", str(job["output_ref"]), exc)
                continue
            timeline_payload = partial_regeneration.get("timeline")
            if not isinstance(timeline_payload, dict):
                continue
            timeline_id = str(timeline_payload.get("timeline_id") or "").strip()
            if timeline_id:
                review_guidance_jobs_by_timeline_id[timeline_id] = job
                timeline_ids_by_timeline_job_id[str(job.get("job_id") or "")] = timeline_id
        if include_upstream and filter_timeline_id is not None:
            timeline_job = timeline_jobs_by_timeline_id.get(filter_timeline_id)
            if timeline_job is not None:
                segment_job_id = str(timeline_job.get("input_ref") or "")
            else:
                segment_job_id = ""
            try:
                timeline_payload = self.get_timeline_run(project_id=project_id, timeline_id=filter_timeline_id)
            except Exception as exc:  # noqa: BLE001 - 상류 계보 없이도 목록은 낸다
                _skipped("timeline_lineage", str(filter_timeline_id), exc)
                timeline_payload = {}
            lineage = timeline_payload.get("lineage")
            if isinstance(lineage, dict):
                segment_job_id = str(lineage.get("segment_analysis_job_id") or segment_job_id)
                recommendation_job_ids = lineage.get("recommendation_job_ids")
                if isinstance(recommendation_job_ids, list):
                    upstream_recommendation_job_ids = {
                        str(job_id).strip()
                        for job_id in recommendation_job_ids
                        if str(job_id).strip()
                    }
                    use_exact_recommendation_lineage = True
            if segment_job_id:
                upstream_segment_job_ids.add(segment_job_id)

        for job in jobs:
            job_type = str(job["job_type"])
            if job_type == JobType.SEGMENT_ANALYSIS.value and job.get("output_ref"):
                try:
                    analysis = self.get_segment_analysis(
                        project_id=project_id,
                        segment_analysis_id=str(job["output_ref"]),
                    )
                except Exception as exc:  # noqa: BLE001 - 하나가 나머지를 막지 않는다
                    _skipped("segment_analysis", str(job["output_ref"]), exc)
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="segment_analysis",
                        artifact_id=str(analysis["segment_analysis_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(job.get("input_ref") or ""),
                        trace=self._merged_provider_trace(analysis.get("segments", [])),
                        timeline_id=None,
                    )
                )
            elif job_type == JobType.BROLL_RECOMMENDATION.value and job.get("output_ref"):
                try:
                    run = self.get_recommendation_run(
                        project_id=project_id,
                        recommendation_run_id=str(job["output_ref"]),
                        recommendation_type=RecommendationType.BROLL,
                    )
                except Exception as exc:  # noqa: BLE001 - 하나가 나머지를 막지 않는다
                    _skipped("broll_recommendation", str(job["output_ref"]), exc)
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="broll_recommendation",
                        artifact_id=str(run["recommendation_run_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(run.get("source_job_id") or job.get("input_ref") or ""),
                        trace=self._merged_provider_trace(run.get("recommendations", [])),
                        timeline_id=None,
                    )
                )
            elif job_type == JobType.MUSIC_RECOMMENDATION.value and job.get("output_ref"):
                try:
                    run = self.get_recommendation_run(
                        project_id=project_id,
                        recommendation_run_id=str(job["output_ref"]),
                        recommendation_type=RecommendationType.BGM,
                    )
                except Exception as exc:  # noqa: BLE001 - 하나가 나머지를 막지 않는다
                    _skipped("music_recommendation", str(job["output_ref"]), exc)
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="music_recommendation",
                        artifact_id=str(run["recommendation_run_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(run.get("source_job_id") or job.get("input_ref") or ""),
                        trace=self._merged_provider_trace(run.get("recommendations", [])),
                        timeline_id=None,
                    )
                )
            elif job_type == JobType.PREVIEW_RENDER.value and job.get("output_ref"):
                try:
                    preview = self.get_preview_run(project_id=project_id, preview_id=str(job["output_ref"]))
                except Exception as exc:  # noqa: BLE001 - 하나가 나머지를 막지 않는다
                    _skipped("preview_render", str(job["output_ref"]), exc)
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="preview_render",
                        artifact_id=str(preview["preview_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(job.get("input_ref") or ""),
                        trace=preview["provider_trace"],
                        timeline_id=str(preview.get("timeline_id") or ""),
                        created_at=str(preview.get("created_at") or ""),
                    )
                )
            elif job_type == JobType.SUBTITLE_RENDER.value and job.get("output_ref"):
                try:
                    subtitle = self.get_subtitle_run(project_id=project_id, subtitle_id=str(job["output_ref"]))
                except Exception as exc:  # noqa: BLE001 - 하나가 나머지를 막지 않는다
                    _skipped("subtitle_render", str(job["output_ref"]), exc)
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="subtitle_render",
                        artifact_id=str(subtitle["subtitle_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(job.get("input_ref") or ""),
                        trace=build_provider_trace(final_provider="static_fallback"),
                        timeline_id=str(subtitle.get("timeline_id") or ""),
                        created_at=str(subtitle.get("created_at") or ""),
                    )
                )
            elif job_type == JobType.CAPCUT_EXPORT.value and job.get("output_ref"):
                try:
                    export = self.get_export_run(project_id=project_id, export_id=str(job["output_ref"]))
                except Exception as exc:  # noqa: BLE001 - 하나가 나머지를 막지 않는다
                    _skipped("capcut_export", str(job["output_ref"]), exc)
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="capcut_export",
                        artifact_id=str(export["export_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(job.get("input_ref") or ""),
                        trace=export["provider_trace"],
                        timeline_id=str(export.get("timeline_id") or ""),
                        created_at=str(export.get("created_at") or ""),
                    )
                )

        failed_entries_by_job_id: dict[str, dict[str, Any]] = {}
        for item in self._list_provider_trace_failed_runs(project_id=project_id):
            trace = item.get("provider_trace")
            if not isinstance(trace, dict):
                trace = build_provider_trace(
                    final_provider="unknown_failure",
                    fallback_reasons=["missing_provider_trace"],
                )
            job_id = str(item.get("job_id") or "")
            source_job_id = str(item.get("source_job_id") or "")
            resolved_timeline_id = str(item.get("timeline_id") or "") or timeline_ids_by_timeline_job_id.get(source_job_id, "")
            artifact_type = str(item.get("artifact_type") or item.get("job_type") or "unknown_failure")
            entry = self._provider_trace_entry(
                artifact_type=artifact_type,
                artifact_id=str(item.get("artifact_id") or job_id),
                job_type=str(item.get("job_type") or artifact_type),
                job=None,
                source_job_id=source_job_id or None,
                trace=trace,
                timeline_id=resolved_timeline_id or None,
                status=JobStatus.FAILED.value,
                finished_at=str(item.get("finished_at") or ""),
                created_at=str(item.get("created_at") or ""),
                error_message=str(item.get("error_message") or ""),
                job_id=job_id or None,
            )
            if job_id:
                failed_entries_by_job_id[job_id] = entry
            else:
                entries.append(entry)

        audit_events = self._list_provider_trace_audit_events(project_id=project_id)
        review_guidance_attempt_entries_by_key: dict[str, dict[str, Any]] = {}
        guidance_timeline_ids_with_events: set[str] = set()
        for item in audit_events:
            if str(item.get("status") or "") == JobStatus.FAILED.value:
                trace = item.get("provider_trace")
                if not isinstance(trace, dict):
                    trace = build_provider_trace(
                        final_provider="unknown_failure",
                        fallback_reasons=["missing_provider_trace"],
                    )
                job_id = str(item.get("job_id") or "")
                source_job_id = str(item.get("source_job_id") or "")
                resolved_timeline_id = str(item.get("timeline_id") or "") or timeline_ids_by_timeline_job_id.get(source_job_id, "")
                artifact_type = str(item.get("artifact_type") or item.get("job_type") or "unknown_failure")
                entry = self._provider_trace_entry(
                    artifact_type=artifact_type,
                    artifact_id=str(item.get("artifact_id") or job_id),
                    job_type=str(item.get("job_type") or artifact_type),
                    job=None,
                    source_job_id=source_job_id or None,
                    trace=trace,
                    timeline_id=resolved_timeline_id or None,
                    status=JobStatus.FAILED.value,
                    finished_at=str(item.get("finished_at") or ""),
                    created_at=str(item.get("created_at") or ""),
                    error_message=str(item.get("error_message") or ""),
                    job_id=job_id or None,
                )
                if job_id and job_id in failed_entries_by_job_id:
                    failed_entries_by_job_id[job_id] = self._merge_provider_trace_failed_entries(
                        failed_entries_by_job_id[job_id],
                        entry,
                    )
                elif job_id:
                    failed_entries_by_job_id[job_id] = entry
                else:
                    entries.append(entry)
                continue
            if str(item.get("artifact_type") or "") == "review_guidance_attempt":
                timeline_id = str(item.get("timeline_id") or "")
                timeline_job = review_guidance_jobs_by_timeline_id.get(timeline_id)
                trace = item.get("provider_trace")
                if not isinstance(trace, dict):
                    trace = build_provider_trace(final_provider="heuristic_fallback")
                timeline_job_id = timeline_job["job_id"] if timeline_job else ""
                job_id = str(item.get("job_id") or timeline_job_id or "") or None
                review_guidance_attempt_entries_by_key[f"{job_id or ''}|{timeline_id}|review_guidance_attempt"] = (
                    self._provider_trace_entry(
                        artifact_type="review_guidance_attempt",
                        artifact_id=str(item.get("artifact_id") or timeline_id),
                        job_type=str(item.get("job_type") or JobType.TIMELINE_BUILD.value),
                        job=None,
                        source_job_id=str(item.get("source_job_id") or timeline_job_id or "") or None,
                        trace=trace,
                        timeline_id=timeline_id or None,
                        status=str(item.get("status") or "available"),
                        finished_at=str(item.get("finished_at") or timeline_job.get("finished_at") or "") if timeline_job else str(item.get("finished_at") or ""),
                        created_at=str(item.get("created_at") or ""),
                        error_message=str(item.get("error_message") or "") or None,
                        job_id=job_id,
                    )
                )
                continue
            if str(item.get("artifact_type") or "") != "review_guidance":
                continue
            timeline_id = str(item.get("timeline_id") or "")
            if timeline_id:
                guidance_timeline_ids_with_events.add(timeline_id)
            timeline_job = review_guidance_jobs_by_timeline_id.get(timeline_id)
            trace = item.get("provider_trace")
            if not isinstance(trace, dict):
                trace = build_provider_trace(final_provider="heuristic_fallback")
            entries.append(
                self._provider_trace_entry(
                    artifact_type="review_guidance",
                    artifact_id=str(item.get("artifact_id") or timeline_id),
                    job_type=str(timeline_job.get("job_type") or JobType.TIMELINE_BUILD.value)
                    if timeline_job
                    else JobType.TIMELINE_BUILD.value,
                    job=None,
                    source_job_id=timeline_job["job_id"] if timeline_job else None,
                    trace=trace,
                    timeline_id=timeline_id or None,
                    status="available",
                    finished_at=str(timeline_job.get("finished_at") or "") if timeline_job else None,
                    created_at=str(item.get("created_at") or ""),
                    error_message=None,
                    job_id=timeline_job["job_id"] if timeline_job else None,
                    )
                )

        for timeline_id in self._list_timeline_ids(project_id=project_id):
            if timeline_id in guidance_timeline_ids_with_events:
                continue
            try:
                timeline_payload = self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
            except Exception as exc:  # noqa: BLE001 - 하나가 나머지를 막지 않는다
                _skipped("review_guidance_timeline", str(timeline_id), exc)
                continue
            legacy_history = timeline_payload.get("operator_guidance_history")
            legacy_entries: list[dict[str, Any]] = []
            if isinstance(legacy_history, list):
                legacy_entries = [item for item in legacy_history if isinstance(item, dict)]
            elif isinstance(timeline_payload.get("operator_guidance"), dict):
                legacy_entries = [
                    {
                        "artifact_id": f"{timeline_id}:review_guidance:001",
                        "created_at": str(timeline_payload.get("created_at") or ""),
                        "provider_trace": timeline_payload["operator_guidance"].get("provider_trace")
                        or build_provider_trace(final_provider="heuristic_fallback"),
                    }
                ]
            timeline_job = review_guidance_jobs_by_timeline_id.get(timeline_id)
            for item in legacy_entries:
                trace = item.get("provider_trace")
                if not isinstance(trace, dict):
                    trace = build_provider_trace(final_provider="heuristic_fallback")
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="review_guidance",
                        artifact_id=str(item.get("artifact_id") or timeline_id),
                        job_type=str(timeline_job.get("job_type") or JobType.TIMELINE_BUILD.value)
                        if timeline_job
                        else JobType.TIMELINE_BUILD.value,
                        job=None,
                        source_job_id=timeline_job["job_id"] if timeline_job else None,
                        trace=trace,
                        timeline_id=timeline_id,
                        status="available",
                        finished_at=str(timeline_job.get("finished_at") or "") if timeline_job else None,
                        created_at=str(item.get("created_at") or ""),
                        error_message=None,
                        job_id=timeline_job["job_id"] if timeline_job else None,
                    )
                )

        entries.extend(failed_entries_by_job_id.values())
        entries.extend(review_guidance_attempt_entries_by_key.values())
        entries = [
                entry
                for entry in entries
                if self._provider_trace_entry_matches_filters(
                    entry,
                    timeline_id=filter_timeline_id,
                    include_upstream=include_upstream,
                    upstream_segment_job_ids=upstream_segment_job_ids,
                    upstream_recommendation_job_ids=upstream_recommendation_job_ids,
                    use_exact_recommendation_lineage=use_exact_recommendation_lineage,
                    job_type=filter_job_type,
                    artifact_type=filter_artifact_type,
                    final_provider=filter_final_provider,
                    fallback_reason=filter_fallback_reason,
                )
        ]
        entries.sort(key=lambda item: (item["finished_at"] or item["created_at"] or "", item["artifact_type"]))
        direct_entries, upstream_entries = self._group_provider_trace_entries(
            entries,
            timeline_id=filter_timeline_id,
            include_upstream=include_upstream,
            upstream_segment_job_ids=upstream_segment_job_ids,
            upstream_recommendation_job_ids=upstream_recommendation_job_ids,
            use_exact_recommendation_lineage=use_exact_recommendation_lineage,
        )
        if unreadable:
            # 목록에서 빼는 동작은 그대로다. 항목마다 찍지 않고 한 번에 모은다.
            _LOGGER.warning(
                "감사 목록에서 산출물 %d개를 읽지 못해 뺐습니다. 목록이 완전하지 "
                "않습니다 (project=%s, 항목=%s).",
                len(unreadable),
                project_id,
                ", ".join(unreadable[:10]),
                exc_info=first_error[0] if first_error else None,
            )
        return {
            "summary": self._provider_trace_summary(entries),
            "entries": entries,
            "direct_entries": direct_entries,
            "upstream_entries": upstream_entries,
        }

    def resolve_storage_uri(self, *, project_id: str, storage_uri: str) -> Path:
        prefix = f"local://projects/{project_id}/"
        if not storage_uri.startswith(prefix):
            raise ValueError(f"Unsupported storage URI: {storage_uri}")
        project_root = self.project_root(project_id).resolve()
        relative_path = Path(*storage_uri.removeprefix(prefix).split("/"))
        resolved_path = (project_root / relative_path).resolve()
        if not _is_relative_to(resolved_path, project_root):
            raise ValueError("storage_uri_path_escape")
        return resolved_path

    def _create_project_layout(self, project_root: Path) -> None:
        for directory in (
            project_root / "db",
            project_root / "inputs" / "narration",
            project_root / "inputs" / "raw_video",
            project_root / "inputs" / "scripts",
            project_root / "inputs" / "voice_samples",
            project_root / "assets" / "imported",
            project_root / "assets" / "generated",
            project_root / "analysis" / "transcripts",
            project_root / "analysis" / "segments",
            project_root / "analysis" / "recommendations",
            project_root / "analysis" / "partial_regenerations",
            project_root / "editing_sessions",
            project_root / "timelines",
            project_root / "previews",
            project_root / "subtitles",
            project_root / "exports" / "capcut",
            project_root / "cache",
            project_root / "logs",
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _bootstrap_database(self, database_path: Path, project: ProjectRecord) -> None:
        connection = sqlite3.connect(database_path)
        try:
            for statement in PROJECT_SCHEMA_STATEMENTS:
                connection.execute(statement)
            self._ensure_yujin_memory_operation_columns(connection)
            self._ensure_hermes_capability_lifecycle_schema(connection)
            connection.execute(f"DROP TABLE IF EXISTS {RETIRED_CREDENTIAL_TABLE}")
            self._ensure_recommendation_decision_state_column(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO projects (
                    project_id,
                    name,
                    status,
                    root_storage_uri,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project.project_id,
                    project.name,
                    project.status.value,
                    project.root_storage_uri,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _asset_directory(self, asset_type: AssetType) -> Path:
        mapping = {
            AssetType.NARRATION_AUDIO: Path("inputs") / "narration",
            AssetType.SCRIPT_DOCUMENT: Path("inputs") / "scripts",
            AssetType.VOICE_SAMPLE_AUDIO: Path("inputs") / "voice_samples",
            AssetType.RAW_VIDEO: Path("inputs") / "raw_video",
            AssetType.BROLL_VIDEO: Path("assets") / "imported",
        }
        return mapping.get(asset_type, Path("assets") / "imported")

    def _path_to_uri(self, project_id: str, path: Path) -> str:
        relative_path = path.relative_to(self.project_root(project_id)).as_posix()
        return f"local://projects/{project_id}/{relative_path}"

    def _next_sequence(self, directory: Path, pattern: str) -> int:
        # Based on the highest existing numeric suffix, not the count of entries:
        # once older entries can be pruned (see _prune_old_exports), a count-based
        # sequence collides with still-existing higher-numbered entries.
        highest = 0
        for path in directory.glob(pattern):
            match = re.search(r"(\d+)$", path.stem)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest + 1

    def _connection(self, project_id: str) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path(project_id), timeout=5.0)
        try:
            # WAL lets readers proceed while a writer holds the lock, and
            # busy_timeout makes any remaining contention retry instead of
            # immediately raising "database is locked" — both matter once
            # background job threads (see run_*_job in local_pipeline.py) write
            # to the same per-project database concurrently with polling reads.
            connection.execute("PRAGMA busy_timeout=5000")
            # The database is initialized in WAL mode.  Concurrently asking SQLite
            # to change journal mode can itself take an exclusive lock; a racing
            # connection may safely continue with the already-established mode.
            try:
                connection.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
            for statement in PROJECT_SCHEMA_STATEMENTS:
                connection.execute(statement)
            self._ensure_yujin_memory_operation_columns(connection)
            self._ensure_hermes_capability_lifecycle_schema(connection)
            connection.execute(f"DROP TABLE IF EXISTS {RETIRED_CREDENTIAL_TABLE}")
            self._ensure_recommendation_decision_state_column(connection)
            self._ensure_job_progress_percent_column(connection)
            self._ensure_editing_session_revision_column(connection)
            self._ensure_editing_session_json_column(connection)
            self._ensure_tts_candidate_acceptance_columns(connection)
            self._ensure_artifact_freshness_columns(connection)
            self._ensure_capcut_draft_handoff_claim_columns(connection)
            self._ensure_director_message_metadata_column(connection)
            self._ensure_director_message_order_column(connection)
            self._ensure_director_claim_columns(connection)
            self._ensure_director_hermes_run_context_columns(connection)
            self._ensure_creation_brief_columns(connection)
            self._ensure_exact_preview_columns(connection)
            self._ensure_proposal_preview_columns(connection)
            self._ensure_artifact_freshness_triggers(connection)
            connection.commit()
            connection.row_factory = sqlite3.Row
            return connection
        except Exception:
            connection.close()
            raise

    def _ensure_creation_brief_columns(self, connection: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(creation_briefs)").fetchall()}
        if columns and "summary_text" not in columns:
            connection.execute("ALTER TABLE creation_briefs ADD COLUMN summary_text TEXT NOT NULL DEFAULT ''")
        if columns and "script_asset_owned" not in columns:
            connection.execute("ALTER TABLE creation_briefs ADD COLUMN script_asset_owned INTEGER NOT NULL DEFAULT 0")

    @staticmethod
    def _ensure_yujin_memory_operation_columns(
        connection: sqlite3.Connection,
    ) -> None:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(yujin_memory_candidates)"
            ).fetchall()
        }
        additions = (
            ("external_ref", "TEXT"),
            ("operation_id", "TEXT"),
            ("provider_event_ref", "TEXT"),
            ("provider_memory_ref", "TEXT"),
            ("store_client_request_id", "TEXT"),
            ("write_claim_token", "TEXT"),
            ("write_claimed_at", "TEXT"),
            ("provider_call_started_at", "TEXT"),
            ("attempt_count", "INTEGER NOT NULL DEFAULT 0"),
            (
                "storage_status",
                "TEXT NOT NULL DEFAULT 'not_requested'",
            ),
        )
        for column, declaration in additions:
            if column not in columns:
                try:
                    connection.execute(
                        f"ALTER TABLE yujin_memory_candidates "
                        f"ADD COLUMN {column} {declaration}"
                    )
                except sqlite3.OperationalError as error:
                    if (
                        str(error).casefold()
                        != f"duplicate column name: {column}".casefold()
                    ):
                        raise
                    current_columns = {
                        str(row[1])
                        for row in connection.execute(
                            "PRAGMA table_info(yujin_memory_candidates)"
                        ).fetchall()
                    }
                    if column not in current_columns:
                        raise
                columns.add(column)

    def _ensure_exact_preview_columns(self, connection: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(exact_preview_renders)").fetchall()}
        if columns and "duration_sec" not in columns:
            connection.execute("ALTER TABLE exact_preview_renders ADD COLUMN duration_sec REAL")

    def _ensure_proposal_preview_columns(self, connection: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(proposal_preview_renders)").fetchall()}
        if columns and "claimed_at" not in columns:
            connection.execute("ALTER TABLE proposal_preview_renders ADD COLUMN claimed_at TEXT")

    def _ensure_director_message_metadata_column(self, connection: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(director_messages)").fetchall()}
        if "metadata_json" not in columns:
            connection.execute("ALTER TABLE director_messages ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")

    def _ensure_director_message_order_column(
        self, connection: sqlite3.Connection
    ) -> None:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(director_messages)"
            ).fetchall()
        }
        if "message_order" not in columns:
            connection.execute(
                "ALTER TABLE director_messages ADD COLUMN message_order INTEGER"
            )
        connection.execute(
            """
            UPDATE director_messages
            SET message_order = (
                SELECT COUNT(*)
                FROM director_messages AS ordered
                WHERE ordered.conversation_id =
                      director_messages.conversation_id
                  AND ordered.rowid <= director_messages.rowid
            )
            WHERE message_order IS NULL
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                director_messages_conversation_order_idx
            ON director_messages (conversation_id, message_order)
            """
        )
        connection.commit()

    def _ensure_director_claim_columns(self, connection: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(director_message_claims)").fetchall()}
        if "owner_token" not in columns:
            connection.execute("ALTER TABLE director_message_claims ADD COLUMN owner_token TEXT NOT NULL DEFAULT ''")
        if "heartbeat_at" not in columns:
            connection.execute("ALTER TABLE director_message_claims ADD COLUMN heartbeat_at TEXT NOT NULL DEFAULT ''")

    def _ensure_director_hermes_run_context_columns(
        self, connection: sqlite3.Connection
    ) -> None:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(director_hermes_runs)"
            ).fetchall()
        }
        if "expected_session_revision" not in columns:
            try:
                connection.execute(
                    "ALTER TABLE director_hermes_runs "
                    "ADD COLUMN expected_session_revision INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        if "selected_segment_id" not in columns:
            try:
                connection.execute(
                    "ALTER TABLE director_hermes_runs ADD COLUMN selected_segment_id TEXT"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        if "expected_asset_index_revision" not in columns:
            try:
                connection.execute(
                    "ALTER TABLE director_hermes_runs "
                    "ADD COLUMN expected_asset_index_revision INTEGER NOT NULL DEFAULT -1"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        if "assistant_draft_text" not in columns:
            try:
                connection.execute(
                    "ALTER TABLE director_hermes_runs "
                    "ADD COLUMN assistant_draft_text TEXT NOT NULL DEFAULT ''"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        if "next_event_id" not in columns:
            try:
                connection.execute(
                    "ALTER TABLE director_hermes_runs "
                    "ADD COLUMN next_event_id INTEGER NOT NULL DEFAULT 1"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        if "events_pruned_at" not in columns:
            try:
                connection.execute(
                    "ALTER TABLE director_hermes_runs ADD COLUMN events_pruned_at TEXT"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        if "retry_of_run_id" not in columns:
            try:
                connection.execute(
                    "ALTER TABLE director_hermes_runs ADD COLUMN retry_of_run_id TEXT"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        legacy_rows = connection.execute(
            """
            SELECT run_id, project_id, status, assistant_message_id,
                   created_at, updated_at
            FROM director_hermes_runs AS run
            WHERE next_event_id = 1 AND events_pruned_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM director_hermes_run_events AS event
                  WHERE event.project_id = run.project_id
                    AND event.run_id = run.run_id
              )
            """
        ).fetchall()
        for row in legacy_rows:
            run_id = str(row[0])
            project_id = str(row[1])
            status = str(row[2])
            assistant_message_id = row[3]
            created_at = str(row[4])
            updated_at = str(row[5])
            connection.execute(
                """
                INSERT INTO director_hermes_run_events (
                    project_id, run_id, event_id, event_type, text,
                    retryable, created_at
                ) VALUES (?, ?, 1, 'run_started', '', 0, ?)
                """,
                (project_id, run_id, created_at),
            )
            assistant = None
            if (
                status in {"completed", "blocked", "interrupted"}
                and assistant_message_id is not None
            ):
                assistant = connection.execute(
                    "SELECT text FROM director_messages "
                    "WHERE project_id = ? AND message_id = ?",
                    (
                        project_id,
                        str(assistant_message_id),
                    ),
                ).fetchone()
            if assistant is not None:
                connection.execute(
                    """
                    INSERT INTO director_hermes_run_events (
                        project_id, run_id, event_id, event_type, text,
                        retryable, created_at
                    ) VALUES (?, ?, 2, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        run_id,
                        "run_completed" if status == "completed" else "blocked",
                        str(assistant[0]),
                        int(status != "completed"),
                        updated_at,
                    ),
                )
                connection.execute(
                    "UPDATE director_hermes_runs SET next_event_id = 3 "
                    "WHERE project_id = ? AND run_id = ? AND next_event_id = 1",
                    (project_id, run_id),
                )
            elif status in {"completed", "blocked", "interrupted"}:
                connection.execute(
                    "UPDATE director_hermes_runs SET events_pruned_at = updated_at "
                    "WHERE project_id = ? AND run_id = ? AND next_event_id = 1",
                    (project_id, run_id),
                )
            else:
                connection.execute(
                    "UPDATE director_hermes_runs SET next_event_id = 2 "
                    "WHERE project_id = ? AND run_id = ? AND next_event_id = 1",
                    (project_id, run_id),
                )
        if legacy_rows:
            connection.commit()

    def _ensure_recommendation_decision_state_column(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(recommendations)").fetchall()
        }
        if "decision_state" not in existing_columns:
            connection.execute("ALTER TABLE recommendations ADD COLUMN decision_state TEXT")

    def _ensure_job_progress_percent_column(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "progress_percent" not in existing_columns:
            try:
                connection.execute("ALTER TABLE jobs ADD COLUMN progress_percent INTEGER")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    def _ensure_editing_session_revision_column(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(editing_sessions)").fetchall()
        }
        if "session_revision" not in existing_columns:
            connection.execute("ALTER TABLE editing_sessions ADD COLUMN session_revision INTEGER NOT NULL DEFAULT 1")

    def _ensure_artifact_freshness_columns(self, connection: sqlite3.Connection) -> None:
        # The schema intentionally remains backward-compatible with project
        # databases created before artifact lineage existed.  The column check
        # and ALTER therefore have to share a writer transaction: otherwise
        # two first-use connections can both observe a missing column and the
        # losing connection raises "duplicate column name".
        owns_transaction = not connection.in_transaction
        if owns_transaction:
            connection.execute("BEGIN IMMEDIATE")
        try:
            for table in ("review_approvals", "preview_renders", "subtitle_renders", "exports"):
                existing = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
                for column, declaration in (
                    ("source_session_id", "TEXT"),
                    ("source_session_revision", "INTEGER"),
                    ("is_current", "INTEGER NOT NULL DEFAULT 1"),
                    ("invalidated_at", "TEXT"),
                    ("invalidated_reason", "TEXT"),
                ):
                    if column not in existing:
                        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
            review_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(review_approvals)").fetchall()
            }
            for column, declaration in (("source_variant_id", "TEXT"), ("source_variant_revision", "INTEGER")):
                if column not in review_columns:
                    connection.execute(f"ALTER TABLE review_approvals ADD COLUMN {column} {declaration}")
            for statement in ARTIFACT_SOURCE_SESSION_BACKFILL_STATEMENTS:
                connection.execute(statement)
            if owns_transaction:
                connection.commit()
        except Exception:
            if owns_transaction:
                connection.rollback()
            raise

    def _ensure_capcut_draft_handoff_claim_columns(self, connection: sqlite3.Connection) -> None:
        owns_transaction = not connection.in_transaction
        if owns_transaction:
            connection.execute("BEGIN IMMEDIATE")
        try:
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(exports)").fetchall()}
            for column, declaration in (
                ("handoff_claim_token", "TEXT"),
                ("handoff_claim_job_id", "TEXT"),
                ("handoff_claimed_at", "TEXT"),
                ("handoff_claim_expires_at", "TEXT"),
            ):
                if column not in columns:
                    connection.execute(f"ALTER TABLE exports ADD COLUMN {column} {declaration}")
            if owns_transaction:
                connection.commit()
        except Exception:
            if owns_transaction:
                connection.rollback()
            raise

    @staticmethod
    def _begin_capcut_draft_handoff_transaction(connection: Any) -> None:
        """Start a claim/publish transaction without treating SQLite syntax as portable."""
        if isinstance(connection, sqlite3.Connection):
            connection.execute("BEGIN IMMEDIATE")
            return
        connection.execute("BEGIN")
        connection.execute("LOCK TABLE editing_sessions, jobs, exports IN SHARE ROW EXCLUSIVE MODE")

    def _ensure_artifact_freshness_triggers(self, connection: sqlite3.Connection) -> None:
        # This migration deliberately replaces an earlier trigger definition so
        # that an explicit lineage revision is preserved.  _connection() is also
        # used by background jobs, so the replacement must be one SQLite writer
        # transaction; otherwise two connections can both observe a missing
        # trigger between DROP and CREATE.
        connection.execute("BEGIN IMMEDIATE")
        try:
            for table, identifier in (("review_approvals", "timeline_id"), ("preview_renders", "preview_id"), ("subtitle_renders", "subtitle_id"), ("exports", "export_id")):
                trigger = f"set_{table}_session_freshness"
                connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                connection.execute(
                    f"CREATE TRIGGER {trigger} AFTER INSERT ON {table} BEGIN "
                    f"UPDATE {table} SET source_session_id = COALESCE(NEW.source_session_id, CASE WHEN (SELECT COUNT(*) FROM editing_sessions WHERE project_id = NEW.project_id AND timeline_id = NEW.timeline_id) = 1 THEN (SELECT session_id FROM editing_sessions WHERE project_id = NEW.project_id AND timeline_id = NEW.timeline_id AND (NEW.source_session_revision IS NULL OR session_revision = NEW.source_session_revision) LIMIT 1) END), source_session_revision = COALESCE(NEW.source_session_revision, CASE WHEN (SELECT COUNT(*) FROM editing_sessions WHERE project_id = NEW.project_id AND timeline_id = NEW.timeline_id) = 1 THEN (SELECT session_revision FROM editing_sessions WHERE project_id = NEW.project_id AND timeline_id = NEW.timeline_id LIMIT 1) END, 1), is_current = 1 WHERE {identifier} = NEW.{identifier}; END"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def _ensure_editing_session_json_column(self, connection: sqlite3.Connection) -> None:
        existing_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(editing_sessions)").fetchall()}
        if "session_json" not in existing_columns:
            connection.execute("ALTER TABLE editing_sessions ADD COLUMN session_json TEXT NOT NULL DEFAULT '{}'")

    def _ensure_tts_candidate_acceptance_columns(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(tts_candidates)").fetchall()
        }
        additions = (
            ("technical_status", "TEXT NOT NULL DEFAULT 'legacy_unverified'"),
            ("operator_review_status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("target_duration_sec", "REAL"),
            ("actual_duration_sec", "REAL"),
            ("failure_code", "TEXT"),
        )
        for column_name, column_definition in additions:
            if column_name not in existing_columns:
                connection.execute(f"ALTER TABLE tts_candidates ADD COLUMN {column_name} {column_definition}")

    def _derive_recommendation_decision_state(self, recommendation: dict[str, Any]) -> str:
        if _normalize_boolish(recommendation.get("auto_apply_allowed")) and not _normalize_boolish(
            recommendation.get("review_required")
        ):
            return "approved"
        return "pending"

    def _normalize_recommendation_decision_state(self, recommendation: dict[str, Any]) -> str:
        decision_state = str(recommendation.get("decision_state") or "").strip().lower()
        if decision_state in {"approved", "pending", "rejected"}:
            return decision_state
        return self._derive_recommendation_decision_state(recommendation)

    def _execute(self, project_id: str, query: str, params: tuple[Any, ...]) -> None:
        connection = self._connection(project_id)
        try:
            connection.execute(query, params)
            connection.commit()
        finally:
            connection.close()

    def _fetchone(
        self,
        project_id: str,
        query: str,
        params: tuple[Any, ...],
    ) -> sqlite3.Row | None:
        connection = self._connection(project_id)
        try:
            return connection.execute(query, params).fetchone()
        finally:
            connection.close()

    def _fetchall(
        self,
        project_id: str,
        query: str,
        params: tuple[Any, ...],
    ) -> list[sqlite3.Row]:
        connection = self._connection(project_id)
        try:
            return connection.execute(query, params).fetchall()
        finally:
            connection.close()

    def _count_rows(self, project_id: str, table_name: str) -> int:
        row = self._fetchone(project_id, f"SELECT COUNT(*) AS count FROM {table_name} WHERE project_id = ?", (project_id,))
        return int(row["count"]) if row is not None else 0

    def _now_iso(self) -> str:
        return self._clock().isoformat()

    def get_latest_subtitle_for_timeline(self, *, project_id: str, timeline_id: str, include_stale: bool = False) -> dict[str, Any] | None:
        current_filter = "" if include_stale else " AND COALESCE(is_current, 1) = 1"
        row = self._fetchone(
            project_id,
            """
            SELECT subtitle_id
            FROM subtitle_renders
            WHERE project_id = ? AND timeline_id = ?""" + current_filter + """
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (project_id, timeline_id),
        )
        if row is None:
            return None
        return self.get_subtitle_run(project_id=project_id, subtitle_id=str(row["subtitle_id"]))

    def _serialize_srt(self, entries: list[dict[str, Any]]) -> str:
        blocks: list[str] = []
        for entry in entries:
            blocks.append(
                "\n".join(
                    [
                        str(entry["index"]),
                        f"{self._format_srt_timestamp(float(entry['start_sec']))} --> {self._format_srt_timestamp(float(entry['end_sec']))}",
                        str(entry["text"]),
                    ]
                )
            )
        return "\n\n".join(blocks) + ("\n" if blocks else "")

    def _format_srt_timestamp(self, seconds: float) -> str:
        total_milliseconds = int(round(seconds * 1000))
        hours, remainder = divmod(total_milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, milliseconds = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    def _mask_api_key(self, api_key_secret: str) -> str:
        if len(api_key_secret) <= 8:
            return "*" * len(api_key_secret)
        return f"{api_key_secret[:4]}***{api_key_secret[-4:]}"

    def _json_object(self, raw_value: str | None) -> dict[str, Any]:
        decoded = json.loads(raw_value or "{}")
        return decoded if isinstance(decoded, dict) else {}

    def _write_editing_session(
        self,
        *,
        project_id: str,
        timeline_id: str,
        session_id: str,
        session_payload: dict[str, Any],
        is_new: bool,
        created_at: str | None = None,
        expected_revision: int | None = None,
        transaction_hook: Callable[[sqlite3.Connection], None] | None = None,
        transaction_start_hook: Callable[[Any], None] | None = None,
        invalidate_output_freshness: bool = True,
    ) -> dict[str, Any]:
        session_path = self.project_root(project_id) / "editing_sessions" / f"{session_id}.json"
        file_uri = self._path_to_uri(project_id, session_path)
        created_value = created_at or self._now_iso()
        updated_at = self._now_iso()
        payload = {
            "session_id": session_id,
            "project_id": project_id,
            "timeline_id": timeline_id,
            "session_revision": int(session_payload.get("session_revision") or 1),
            "caption_style": session_payload.get("caption_style"),
            "segments": session_payload.get("segments", []),
            "history": session_payload.get("history", []),
            "undo_stack": session_payload.get("undo_stack", []),
            "redo_stack": session_payload.get("redo_stack", []),
            "timeline_placement_overrides": session_payload.get("timeline_placement_overrides", {}),
            "created_at": created_value,
            "updated_at": updated_at,
        }
        for key in (
            "script_asset_id",
            "timing_source",
            "narration_alignment_required",
            "stale_proposal_source_script_segment_ids",
            "output_freshness",
            # 트랙 눈·음소거. 켠 적이 없으면 아예 없는 칸이라 옛 저장분도
            # 그대로 읽힌다(`track_states.py`가 없는 값을 "전부 기본"으로 본다).
            "track_states",
            # 완성본에 실을 자막 언어. 고른 적이 없으면 없는 칸이고, 그때는
            # 원본(한국어)으로 나간다.
            "caption_language",
        ):
            if key in session_payload:
                payload[key] = session_payload[key]
        summary_json = json.dumps(
            {
                "segment_count": len(payload["segments"]),
                "history_count": len(payload["history"]),
                "undo_count": len(payload["undo_stack"]),
                "redo_count": len(payload["redo_stack"]),
            },
            ensure_ascii=True,
        )
        serialized_payload = json.dumps(payload, indent=2, ensure_ascii=True)
        if is_new:
            session_path.write_text(serialized_payload, encoding="utf-8")
            self._execute(
                project_id,
                """
                INSERT INTO editing_sessions (
                    session_id,
                    project_id,
                    timeline_id,
                    file_uri,
                    summary_json,
                    session_revision,
                    session_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    project_id,
                    timeline_id,
                    file_uri,
                    summary_json,
                    payload["session_revision"],
                    serialized_payload,
                    created_value,
                    updated_at,
                ),
            )
        else:
            connection = self._connection(project_id)
            # Keep the atomic mirror name independent of the session filename.
            # Long project roots can otherwise cross the Windows MAX_PATH limit
            # even though the canonical JSON path itself remains valid.
            temporary_path = session_path.with_name(f".es-{uuid.uuid4().hex[:12]}.tmp")
            try:
                if transaction_start_hook is None:
                    connection.execute("BEGIN IMMEDIATE")
                else:
                    transaction_start_hook(connection)
                cursor = connection.execute(
                    """
                    UPDATE editing_sessions
                    SET timeline_id = ?, summary_json = ?, session_revision = ?, session_json = ?, updated_at = ?
                    WHERE project_id = ? AND session_id = ? AND (? IS NULL OR session_revision = ?)
                    """,
                    (
                        timeline_id,
                        summary_json,
                        payload["session_revision"],
                        serialized_payload,
                        updated_at,
                        project_id,
                        session_id,
                        expected_revision,
                        expected_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    raise EditingSessionRevisionConflict("Editing session revision is stale.")
                if transaction_hook is not None:
                    transaction_hook(connection)
                if invalidate_output_freshness:
                    self._invalidate_output_freshness_with_connection(
                        connection, project_id=project_id, timeline_id=timeline_id,
                        source_session_id=session_id, source_session_revision=payload["session_revision"], reason="editing_session_mutation",
                    )
                connection.commit()
                try:
                    temporary_path.write_text(serialized_payload, encoding="utf-8")
                    temporary_path.replace(session_path)
                except Exception as exc:
                    raise EditingSessionPostCommitFileWriteError(
                        f"Editing-session SQLite commit succeeded but JSON mirror write failed: {exc}"
                    ) from exc
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                if temporary_path.exists():
                    temporary_path.unlink()
                raise
            finally:
                connection.close()
        return self.get_editing_session(project_id=project_id, session_id=session_id)

    def _invalidate_output_freshness_with_connection(
        self, connection: sqlite3.Connection, *, project_id: str, timeline_id: str,
        source_session_id: str, source_session_revision: int, reason: str,
    ) -> None:
        now = self._now_iso()
        for table in ("review_approvals", "subtitle_renders", "preview_renders", "exports"):
            connection.execute(
                f"UPDATE {table} SET is_current = 0, invalidated_at = ?, invalidated_reason = ? "
                f"WHERE project_id = ? AND timeline_id = ? AND COALESCE(is_current, 1) = 1",
                (now, reason, project_id, timeline_id),
            )
        connection.execute(
            """UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?,
               invalidated_reason = ?, updated_at = ?
               WHERE project_id = ? AND session_id = ? AND expected_revision < ?
               AND state IN ('pending', 'running', 'succeeded')""",
            (now, reason, now, project_id, source_session_id, source_session_revision),
        )

    def _timeline_file_path(self, *, project_id: str, timeline_id: str) -> Path:
        row = self._fetchone(
            project_id,
            """
            SELECT file_uri
            FROM timelines
            WHERE project_id = ? AND timeline_id = ?
            """,
            (project_id, timeline_id),
        )
        if row is None:
            raise KeyError(f"Timeline not found: {timeline_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Timeline JSON missing: {timeline_id}")
        return file_path

    def _provider_trace_audit_log_path(self, *, project_id: str) -> Path:
        return self.project_root(project_id) / "logs" / "provider_trace_audit.jsonl"

    def _ensure_provider_trace_failed_runs_table(self, *, project_id: str) -> None:
        self._execute(
            project_id,
            """
            CREATE TABLE IF NOT EXISTS provider_trace_failed_runs (
                job_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                source_job_id TEXT,
                artifact_id TEXT,
                timeline_id TEXT,
                error_message TEXT,
                provider_trace_json TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            )
            """,
            (),
        )

    def _save_failed_provider_trace_run(self, *, project_id: str, event: dict[str, Any]) -> None:
        self._ensure_provider_trace_failed_runs_table(project_id=project_id)
        provider_trace = event.get("provider_trace")
        self._execute(
            project_id,
            """
            INSERT OR REPLACE INTO provider_trace_failed_runs (
                job_id,
                project_id,
                job_type,
                source_job_id,
                artifact_id,
                timeline_id,
                error_message,
                provider_trace_json,
                created_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.get("job_id") or ""),
                project_id,
                str(event.get("job_type") or event.get("artifact_type") or ""),
                str(event.get("source_job_id") or "") or None,
                str(event.get("artifact_id") or event.get("job_id") or ""),
                str(event.get("timeline_id") or "") or None,
                str(event.get("error_message") or ""),
                json.dumps(provider_trace, ensure_ascii=True) if isinstance(provider_trace, dict) else None,
                str(event.get("created_at") or self._now_iso()),
                str(event.get("finished_at") or ""),
            ),
        )

    def _list_provider_trace_failed_runs(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            try:
                rows = connection.execute(
                    """
                    SELECT
                        job_id,
                        project_id,
                        job_type,
                        source_job_id,
                        artifact_id,
                        timeline_id,
                        error_message,
                        provider_trace_json,
                        created_at,
                        finished_at
                    FROM provider_trace_failed_runs
                    ORDER BY created_at ASC, job_id ASC
                    """
                ).fetchall()
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc).lower():
                    return []
                raise
        finally:
            connection.close()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            raw_trace = payload.pop("provider_trace_json", None)
            try:
                decoded_trace = json.loads(raw_trace) if raw_trace else None
            except json.JSONDecodeError:
                decoded_trace = None
            payload["provider_trace"] = decoded_trace if isinstance(decoded_trace, dict) else None
            payload["artifact_type"] = str(payload.get("job_type") or "")
            items.append(payload)
        return items

    def _append_provider_trace_audit_event(self, *, project_id: str, event: dict[str, Any]) -> None:
        log_path = self._provider_trace_audit_log_path(project_id=project_id)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")

    def _list_provider_trace_audit_events(self, *, project_id: str) -> list[dict[str, Any]]:
        log_path = self._provider_trace_audit_log_path(project_id=project_id)
        if not log_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                events.append(decoded)
        return events

    def _next_provider_trace_event_sequence(self, *, project_id: str) -> int:
        return len(self._list_provider_trace_audit_events(project_id=project_id)) + 1

    def _list_timeline_ids(self, *, project_id: str) -> list[str]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT timeline_id
                FROM timelines
                WHERE project_id = ?
                ORDER BY created_at ASC, timeline_id ASC
                """,
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        return [str(row["timeline_id"]) for row in rows]

    def _merged_provider_trace(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        traces = [
            item.get("provider_trace")
            for item in items
            if isinstance(item.get("provider_trace"), dict)
        ]
        if not traces:
            return build_provider_trace(final_provider="heuristic_fallback")
        final_providers = {str(trace.get("final_provider") or "unknown") for trace in traces}
        fallback_reasons: list[str] = []
        for trace in traces:
            for reason in trace.get("fallback_reasons", []):
                text = str(reason).strip()
                if text and text not in fallback_reasons:
                    fallback_reasons.append(text)
        if len(final_providers) == 1:
            final_provider = next(iter(final_providers))
        else:
            final_provider = "mixed"
        return build_provider_trace(
            final_provider=final_provider,
            fallback_reasons=fallback_reasons,
            routing_mode=str(traces[0].get("routing_mode") or "local_only"),
        )

    def _provider_trace_entry(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        job_type: str | None,
        trace: dict[str, Any],
        job: dict[str, Any] | None = None,
        source_job_id: str | None = None,
        timeline_id: str | None = None,
        status: str | None = None,
        finished_at: str | None = None,
        created_at: str | None = None,
        error_message: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_job_id = job_id
        if resolved_job_id is None and job is not None:
            resolved_job_id = str(job.get("job_id") or "")
        resolved_job_type = job_type
        if resolved_job_type is None and job is not None:
            resolved_job_type = str(job.get("job_type") or "")
        resolved_source_job_id = source_job_id
        if resolved_source_job_id is None and job is not None:
            resolved_source_job_id = str(job.get("input_ref") or "")
        resolved_status = status
        if resolved_status is None and job is not None:
            resolved_status = str(job.get("status") or "")
        resolved_finished_at = finished_at
        if resolved_finished_at is None and job is not None:
            resolved_finished_at = str(job.get("finished_at") or "")
        resolved_error_message = error_message
        if resolved_error_message is None and job is not None:
            resolved_error_message = str(job.get("error_message") or "")
        return {
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "job_type": resolved_job_type,
            "job_id": resolved_job_id,
            "source_job_id": resolved_source_job_id,
            "timeline_id": timeline_id or None,
            "status": resolved_status or "available",
            "finished_at": resolved_finished_at,
            "created_at": created_at,
            "error_message": resolved_error_message,
            "provider_trace": trace,
        }

    def _provider_trace_summary(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        provider_counts: dict[str, int] = {}
        fallback_reason_counts: dict[str, int] = {}
        artifact_type_counts: dict[str, int] = {}
        fallback_entry_count = 0
        for entry in entries:
            artifact_type = str(entry["artifact_type"])
            artifact_type_counts[artifact_type] = artifact_type_counts.get(artifact_type, 0) + 1
            trace = entry["provider_trace"]
            final_provider = str(trace.get("final_provider") or "unknown")
            provider_counts[final_provider] = provider_counts.get(final_provider, 0) + 1
            reasons = [str(reason).strip() for reason in trace.get("fallback_reasons", []) if str(reason).strip()]
            if reasons:
                fallback_entry_count += 1
            for reason in reasons:
                fallback_reason_counts[reason] = fallback_reason_counts.get(reason, 0) + 1
        return {
            "total_entries": len(entries),
            "provider_counts": provider_counts,
            "fallback_entry_count": fallback_entry_count,
            "fallback_reason_counts": fallback_reason_counts,
            "artifact_type_counts": artifact_type_counts,
        }

    def _group_provider_trace_entries(
        self,
        entries: list[dict[str, Any]],
        *,
        timeline_id: str | None,
        include_upstream: bool,
        upstream_segment_job_ids: set[str],
        upstream_recommendation_job_ids: set[str],
        use_exact_recommendation_lineage: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if timeline_id is None or not include_upstream:
            return entries, []

        direct_entries: list[dict[str, Any]] = []
        upstream_entries: list[dict[str, Any]] = []
        for entry in entries:
            entry_timeline_id = str(entry.get("timeline_id") or "")
            if entry_timeline_id == timeline_id:
                direct_entries.append(entry)
                continue
            if self._is_upstream_provider_trace_entry(
                entry,
                upstream_segment_job_ids=upstream_segment_job_ids,
                upstream_recommendation_job_ids=upstream_recommendation_job_ids,
                use_exact_recommendation_lineage=use_exact_recommendation_lineage,
            ):
                upstream_entries.append(entry)
                continue
            direct_entries.append(entry)
        return direct_entries, upstream_entries

    def _provider_trace_entry_matches_filters(
        self,
        entry: dict[str, Any],
        *,
        timeline_id: str | None = None,
        include_upstream: bool = False,
        upstream_segment_job_ids: set[str] | None = None,
        upstream_recommendation_job_ids: set[str] | None = None,
        use_exact_recommendation_lineage: bool = False,
        job_type: str | None = None,
        artifact_type: str | None = None,
        final_provider: str | None = None,
        fallback_reason: str | None = None,
    ) -> bool:
        if timeline_id is not None:
            entry_timeline_id = str(entry.get("timeline_id") or "")
            if entry_timeline_id != timeline_id:
                if not include_upstream or not self._is_upstream_provider_trace_entry(
                    entry,
                    upstream_segment_job_ids=upstream_segment_job_ids or set(),
                    upstream_recommendation_job_ids=upstream_recommendation_job_ids or set(),
                    use_exact_recommendation_lineage=use_exact_recommendation_lineage,
                ):
                    return False
        if job_type is not None and str(entry.get("job_type") or "") != job_type:
            return False
        if artifact_type is not None and str(entry.get("artifact_type") or "") != artifact_type:
            return False
        trace = entry.get("provider_trace")
        if not isinstance(trace, dict):
            return False
        if final_provider is not None and str(trace.get("final_provider") or "") != final_provider:
            return False
        if fallback_reason is not None:
            reasons = [str(reason).strip() for reason in trace.get("fallback_reasons", []) if str(reason).strip()]
            if fallback_reason not in reasons:
                return False
        return True

    def _normalized_provider_trace_filter_value(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _is_upstream_provider_trace_entry(
        self,
        entry: dict[str, Any],
        *,
        upstream_segment_job_ids: set[str],
        upstream_recommendation_job_ids: set[str],
        use_exact_recommendation_lineage: bool,
    ) -> bool:
        if not upstream_segment_job_ids:
            return False
        entry_job_id = str(entry.get("job_id") or "")
        entry_source_job_id = str(entry.get("source_job_id") or "")
        if entry_job_id in upstream_segment_job_ids:
            return True
        if use_exact_recommendation_lineage:
            return entry_job_id in upstream_recommendation_job_ids
        return entry_source_job_id in upstream_segment_job_ids

    def _merge_provider_trace_failed_entries(
        self,
        primary: dict[str, Any],
        secondary: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(primary)
        for key in ("artifact_id", "job_type", "job_id", "source_job_id", "timeline_id", "status", "finished_at", "created_at", "error_message"):
            if not merged.get(key) and secondary.get(key):
                merged[key] = secondary[key]
        primary_trace = primary.get("provider_trace")
        secondary_trace = secondary.get("provider_trace")
        if self._is_missing_provider_trace(primary_trace) and isinstance(secondary_trace, dict):
            merged["provider_trace"] = secondary_trace
        return merged

    def _is_missing_provider_trace(self, trace: Any) -> bool:
        return isinstance(trace, dict) and trace == build_provider_trace(
            final_provider="unknown_failure",
            fallback_reasons=["missing_provider_trace"],
        )
