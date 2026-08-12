"""Non-destructive, explainable footage organization proposals."""

from __future__ import annotations

import hashlib
import math
import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping

from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_domain_models.footage_organizer import (
    FootageProposal,
    FootageProposalSegment,
    FootageSourceSegment,
)
from videobox_storage.footage_organizer_store import (
    FootageOrganizerStore,
    OptimisticRevisionConflict,
)


class FootageOrganizerService:
    """Build and edit proposal drafts while keeping source media immutable.

    ``detector`` is intentionally injected: production callers pass an
    ``FfmpegAutoCutExecutor`` and tests can pass a deterministic measurement
    function.  No method here touches an editing session or renders media.
    """

    def __init__(
        self,
        *,
        store: FootageOrganizerStore,
        detector: Any | None = None,
        asset_store: Any | None = None,
        planner: AutoCutPlanner | None = None,
    ) -> None:
        self.store = store
        self.detector = detector
        self.asset_store = asset_store
        self.planner = planner or AutoCutPlanner()

    def propose_segments(self, library_asset_id: str, idempotency_key: str) -> FootageProposal:
        if not isinstance(library_asset_id, str) or not library_asset_id.strip():
            raise ValueError("library_asset_id is required")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        library_asset_id = library_asset_id.strip()
        idempotency_key = idempotency_key.strip()

        asset = self._asset(library_asset_id)
        source = self._source(library_asset_id, asset)
        for existing in self.store.list_proposals(source_id=source.source_id):
            if existing.machine_fields.get("idempotency_key") == idempotency_key:
                return existing

        analysis = self._analysis(asset, library_asset_id)
        duration = self._duration(analysis)
        if duration <= 0:
            raise ValueError("footage analysis requires a positive finite duration")
        analysis_windows = (
            analysis.get("analysis_windows")
            or analysis.get("windows")
            or analysis.get("segment_samples")
            or []
        )
        static_windows = analysis.get("static_windows") or analysis.get("static_regions") or []
        if not static_windows:
            static_windows = [
                window
                for window in analysis_windows
                if isinstance(window, Mapping)
                and window.get("scene_change_count") == 0
                and self._window_duration(window) > self.planner.config.static_duration
            ]
        suggestions = self.planner.build_footage_suggestions(
            total_duration=duration,
            scene_timestamps=analysis.get("scene_timestamps") or [],
            black_regions=analysis.get("black_regions") or [],
            static_windows=static_windows,
            audio_windows=analysis.get("audio_windows") or analysis.get("audio_activity_windows") or [],
            analysis_windows=analysis_windows,
        )
        # A short take is itself useful.  Avoid turning incidental detector
        # timestamps into a noisy collection of tiny draft windows.
        if not self.planner.should_auto_cut(total_duration=duration):
            suggestions = self.planner.build_footage_suggestions(total_duration=duration)

        source_segments: list[FootageSourceSegment] = []
        for suggestion in suggestions:
            reason_codes = list(suggestion["reason_codes"])
            machine_fields = {
                "reason_codes": reason_codes,
                "reason_labels": list(suggestion["reason_labels"]),
                "organizer": "footage_organizer_v1",
            }
            source_segments.append(
                self._ensure_source_segment(
                    source_id=source.source_id,
                    source_sha256=source.source_sha256,
                    start_sec=float(suggestion["start_sec"]),
                    end_sec=float(suggestion["end_sec"]),
                    machine_fields=machine_fields,
                )
            )
        proposal_id = "fprop_" + hashlib.sha256(
            f"videobox-footage-proposal-v1\0{library_asset_id}\0{idempotency_key}".encode()
        ).hexdigest()[:32]
        machine_fields = {
            "idempotency_key": idempotency_key,
            "library_asset_id": library_asset_id,
            "duration_sec": duration,
            "analysis_kinds": sorted(
                key for key in ("scene_timestamps", "black_regions", "static_windows", "audio_windows", "analysis_windows")
                if analysis.get(key)
            ),
        }
        try:
            return self.store.create_proposal(
                source_id=source.source_id,
                source_sha256=source.source_sha256,
                segments=source_segments,
                proposal_id=proposal_id,
                machine_fields=machine_fields,
            )
        except sqlite3.IntegrityError:
            # A lost response after commit is a retry, not a second execution.
            for existing in self.store.list_proposals(source_id=source.source_id):
                if existing.proposal_id == proposal_id or existing.machine_fields.get("idempotency_key") == idempotency_key:
                    return existing
            raise

    def move_boundary(
        self, *, proposal_id: str, segment_id: str, boundary_sec: float, expected_revision: int
    ) -> FootageProposal:
        proposal = self._current(proposal_id, expected_revision)
        index = self._segment_index(proposal, segment_id)
        if index >= len(proposal.segments) - 1:
            raise ValueError("boundary requires a following segment")
        boundary = self._finite(boundary_sec)
        left, right = proposal.segments[index], proposal.segments[index + 1]
        if not left.start_sec < boundary < right.end_sec:
            raise ValueError("boundary must remain inside adjacent segments")
        updated = list(proposal.segments)
        updated[index] = self._window(left, left.start_sec, boundary)
        updated[index + 1] = self._window(right, boundary, right.end_sec)
        return self._reanalyze(proposal, updated, expected_revision)

    def split_draft(
        self, *, proposal_id: str, segment_id: str, split_sec: float, expected_revision: int
    ) -> FootageProposal:
        proposal = self._current(proposal_id, expected_revision)
        index = self._segment_index(proposal, segment_id)
        segment = proposal.segments[index]
        split = self._finite(split_sec)
        if not segment.start_sec < split < segment.end_sec:
            raise ValueError("split must be inside the draft segment")
        updated = list(proposal.segments)
        updated[index : index + 1] = [
            self._window(segment, segment.start_sec, split),
            self._window(segment, split, segment.end_sec),
        ]
        return self._reanalyze(proposal, updated, expected_revision)

    def merge_drafts(
        self, *, proposal_id: str, segment_ids: list[str] | tuple[str, ...], expected_revision: int
    ) -> FootageProposal:
        proposal = self._current(proposal_id, expected_revision)
        if len(segment_ids) < 2:
            raise ValueError("merge requires at least two draft segments")
        indexes = sorted(self._segment_index(proposal, segment_id) for segment_id in segment_ids)
        if indexes != list(range(indexes[0], indexes[-1] + 1)):
            raise ValueError("merge requires adjacent draft segments")
        first, last = proposal.segments[indexes[0]], proposal.segments[indexes[-1]]
        merged = self._window(first, first.start_sec, last.end_sec)
        reasons = []
        labels = []
        for segment in proposal.segments[indexes[0] : indexes[-1] + 1]:
            for reason in segment.machine_fields.get("reason_codes", []):
                if reason not in reasons:
                    reasons.append(reason)
            for label in segment.machine_fields.get("reason_labels", []):
                if label not in labels:
                    labels.append(label)
        merged.machine_fields.update({"reason_codes": reasons, "reason_labels": labels})
        updated = list(proposal.segments)
        updated[indexes[0] : indexes[-1] + 1] = [merged]
        return self._reanalyze(proposal, updated, expected_revision)

    def exclude_draft(
        self, *, proposal_id: str, segment_id: str, expected_revision: int
    ) -> FootageProposal:
        proposal = self._current(proposal_id, expected_revision)
        index = self._segment_index(proposal, segment_id)
        updated = list(proposal.segments)
        updated.pop(index)
        return self._reanalyze(proposal, updated, expected_revision)

    def _source(self, library_asset_id: str, asset: Mapping[str, Any]) -> Any:
        for source in self.store.list_sources():
            if source.library_asset_id == library_asset_id:
                return source
        digest = str(asset.get("content_sha256") or asset.get("sha256") or "").lower()
        if len(digest) != 64:
            raise ValueError("asset must provide its canonical SHA-256 before organization")
        return self.store.register_source(
            source_id=f"source:{library_asset_id}",
            source_sha256=digest,
            library_asset_id=library_asset_id,
            filename=str(asset.get("filename") or ""),
        )

    def _asset(self, library_asset_id: str) -> Mapping[str, Any]:
        store = self.asset_store
        if store is not None and hasattr(store, "get_verified_asset"):
            value = store.get_verified_asset(library_asset_id=library_asset_id)
            if value is None:
                raise KeyError(library_asset_id)
            return value
        if isinstance(store, Mapping):
            value = store.get(library_asset_id)
            if value is None:
                raise KeyError(library_asset_id)
            return value if isinstance(value, Mapping) else {"path": value}
        source = next((item for item in self.store.list_sources() if item.library_asset_id == library_asset_id), None)
        return {"library_asset_id": library_asset_id, "content_sha256": source.source_sha256 if source else ""}

    def _analysis(self, asset: Mapping[str, Any], library_asset_id: str) -> Mapping[str, Any]:
        if isinstance(asset.get("analysis"), Mapping):
            return asset["analysis"]
        if self.detector is None:
            raise ValueError("footage detector is required")
        runner = getattr(self.detector, "run_full_detection", None)
        if callable(runner):
            path = asset.get("path") or asset.get("storage_path") or asset.get("managed_path")
            if path is None:
                raise ValueError("asset path is required for ffmpeg footage detection")
            return runner(Path(str(path)))
        if callable(self.detector):
            try:
                value = self.detector(asset)
            except TypeError:
                value = self.detector(library_asset_id)
            if not isinstance(value, Mapping):
                raise ValueError("footage detector must return an object")
            return value
        raise ValueError("footage detector is not callable")

    @staticmethod
    def _duration(analysis: Mapping[str, Any]) -> float:
        try:
            duration = float(analysis.get("total_duration", 0.0))
        except (TypeError, ValueError):
            return 0.0
        return duration if math.isfinite(duration) else 0.0

    @staticmethod
    def _window_duration(window: Mapping[str, Any]) -> float:
        try:
            start = float(window.get("start_sec", window.get("start", 0.0)))
            end = float(window.get("end_sec", window.get("end", 0.0)))
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, end - start) if math.isfinite(start) and math.isfinite(end) else 0.0

    def _ensure_source_segment(self, *, source_id: str, source_sha256: str, start_sec: float, end_sec: float, machine_fields: Mapping[str, Any]) -> FootageSourceSegment:
        segment_id = "fseg_" + hashlib.sha256(
            f"{source_id}\0{start_sec:.6f}\0{end_sec:.6f}".encode()
        ).hexdigest()[:32]
        try:
            return self.store.create_source_segment(
                source_id=source_id,
                start_sec=start_sec,
                end_sec=end_sec,
                machine_fields=machine_fields,
                segment_id=segment_id,
            )
        except sqlite3.IntegrityError:
            return FootageSourceSegment.create(
                segment_id=segment_id,
                source_id=source_id,
                source_sha256=source_sha256,
                start_sec=start_sec,
                end_sec=end_sec,
                machine_fields=machine_fields,
            )

    def _window(self, original: FootageProposalSegment, start_sec: float, end_sec: float) -> FootageProposalSegment:
        # The proposal segment's immutable source identity is enough to bind a
        # new source window; the parent source is read from the proposal below.
        proposal_source = next(
            item for item in self.store.list_proposals() if any(s.segment_id == original.segment_id for s in item.segments)
        )
        source_segment = self._ensure_source_segment(
            source_id=proposal_source.source_id,
            source_sha256=proposal_source.source_sha256,
            start_sec=start_sec,
            end_sec=end_sec,
            machine_fields=original.machine_fields,
        )
        return FootageProposalSegment.create(
            source_segment_id=source_segment.segment_id,
            source_sha256=proposal_source.source_sha256,
            start_sec=start_sec,
            end_sec=end_sec,
            machine_fields=original.machine_fields,
            confirmed_fields=original.confirmed_fields,
        )

    def _reanalyze(self, proposal: FootageProposal, segments: list[FootageProposalSegment], expected_revision: int) -> FootageProposal:
        return self.store.reanalyze_proposal(
            proposal_id=proposal.proposal_id,
            expected_revision=expected_revision,
            segments=segments,
            machine_fields=proposal.machine_fields,
        )

    def _current(self, proposal_id: str, expected_revision: int) -> FootageProposal:
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        if proposal.revision != expected_revision:
            raise OptimisticRevisionConflict(
                f"proposal revision is {proposal.revision}, expected {expected_revision}"
            )
        return proposal

    @staticmethod
    def _segment_index(proposal: FootageProposal, segment_id: str) -> int:
        for index, segment in enumerate(proposal.segments):
            if segment.segment_id == segment_id:
                return index
        raise KeyError(segment_id)

    @staticmethod
    def _finite(value: float) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("boundary must be finite")
        return number


__all__ = ["FootageOrganizerService"]
