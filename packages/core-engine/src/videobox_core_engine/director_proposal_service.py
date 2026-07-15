from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import replace
from typing import Any
from videobox_storage.local_project_store import sha256_file

from videobox_core_engine.director_proposals import create_and_save_proposal
from videobox_core_engine.media_ranking import rank_candidates
from videobox_domain_models.director_proposals import DirectorProposal


class DirectorProposalBlockedError(Exception):
    def __init__(self, lifecycle: dict[str, object]) -> None:
        super().__init__("Director proposal requires applicable local media analysis.")
        self.lifecycle = lifecycle


class DirectorProposalService:
    """Read-only composition boundary for immutable director proposals."""

    def __init__(self, store: object) -> None:
        self.store = store

    def create(self, *, project_id: str, session_id: str, expires_at: str | None = None) -> DirectorProposal:
        snapshot = self.store.read_director_proposal_snapshot(project_id=project_id, session_id=session_id)
        session = snapshot["session"]
        analyses = {str(item["asset_id"]): item for item in snapshot["analyses"]}
        def eligible(item: dict[str, Any]) -> bool:
            asset_type = str(item.get("asset_type") or "")
            # Music/SFX are metadata-indexed library candidates; only B-roll
            # requires an applicable visual analysis run.
            source = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(item["storage_uri"]))
            if not source.exists():
                return False
            metadata = dict(item.get("metadata") or {})
            if asset_type in {"music", "bgm", "sfx"}:
                required = ("mood", "energy", "genre", "recommended_use") if asset_type in {"music", "bgm"} else ("action_event", "intensity", "recommended_use")
                return metadata.get("canonical_metadata_indexed") is True and all(metadata.get(field) not in (None, "") for field in required)
            analysis = analyses.get(str(item["asset_id"]))
            if not (analysis and analysis.get("status") == "succeeded" and not analysis.get("cancel_requested")):
                return False
            expected_sha = str(analysis.get("idempotency_key") or "").split("::", 1)[-1].split(":", 1)[0]
            return bool(expected_sha and sha256_file(source) == expected_sha and analysis.get("result"))
        assets = [self._rankable_asset(item) for item in snapshot["assets"] if eligible(item)]
        if not assets:
            states = sorted({str(item.get("status") or "unavailable") for item in snapshot["analyses"]})
            raise DirectorProposalBlockedError({"status": "blocked", "analysis_states": states or ["missing"], "recovery_action": "analyse_or_retry_assets"})
        preferences = snapshot["preferences"]
        candidates = []
        placement_targets: dict[str, str] = {}
        source_ids: list[str] = []
        target_ids: list[str] = []
        for segment in session.get("segments", []):
            if not isinstance(segment, dict):
                continue
            source_id = str(segment.get("source_script_segment_id") or segment.get("segment_id") or "")
            if not source_id:
                continue
            source_ids.append(source_id)
            target_ids.append(str(segment.get("segment_id") or source_id))
            ranked = rank_candidates({"text": segment.get("caption_text") or segment.get("text") or "", "duration_sec": float(segment.get("end_sec", 0) or 0) - float(segment.get("start_sec", 0) or 0)}, assets, preferences)
            for candidate in ranked:
                scoped = replace(candidate, candidate_id=f"candidate:{source_id}:{candidate.asset_id}")
                candidates.append(scoped)
                placement_targets[scoped.candidate_id] = target_ids[-1]
        placements = [{"target_segment_id": placement_targets[candidate.candidate_id], "candidate_id": candidate.candidate_id, "asset_id": candidate.asset_id, "controls": candidate.controls, "caption_impact": "none"} for candidate in candidates]
        # The proposal is descriptive only: each bucket is an explicit future
        # edit, never an editing-session mutation.
        diff = {
            "kind": "director_proposal", "candidate_count": len(candidates), "selection_scope": target_ids,
            "placements": {"add": placements, "replace": placements, "remove": [{"target_segment_id": target} for target in target_ids]},
            "scene_controls": [{"candidate_id": c.candidate_id, "controls": dict(c.controls)} for c in candidates],
            "gain_ducking": [{"candidate_id": c.candidate_id, "gain_db": c.controls.get("gain_db", 0), "ducking_db": c.controls.get("ducking_db", 0)} for c in candidates],
            "caption_impact": [{"target_segment_id": target, "impact": "none"} for target in target_ids],
        }
        return create_and_save_proposal(store=self.store, project_id=project_id, base_session_revision=int(session.get("session_revision") or 1), asset_index_revision=int(snapshot["asset_index_revision"]), source_session_id=session_id, source_script_segment_ids=source_ids, target_segment_ids=target_ids, candidates=candidates, expires_at=expires_at, diff=diff)

    def get(self, *, project_id: str, proposal_id: str) -> DirectorProposal:
        return self.store.get_director_proposal(project_id, proposal_id)

    def refresh(self, *, project_id: str, proposal_id: str) -> DirectorProposal:
        proposal = self.get(project_id=project_id, proposal_id=proposal_id)
        # A refresh must create a usable revision, never clone an already expired TTL.
        expires_at = proposal.expires_at
        if expires_at and datetime.fromisoformat(expires_at).astimezone(UTC) <= datetime.now(UTC):
            expires_at = None
        return self.create(project_id=project_id, session_id=proposal.source_session_id, expires_at=expires_at)

    def stale_reasons(self, *, project_id: str, proposal: DirectorProposal) -> list[str]:
        reasons: list[str] = []
        if proposal.status != "ready":
            reasons.append(f"proposal_{proposal.status}")
        try:
            session = self.store.get_editing_session(project_id=project_id, session_id=proposal.source_session_id)
            if int(session.get("session_revision") or 0) != proposal.base_session_revision:
                reasons.append("session_revision")
        except KeyError:
            reasons.append("session_missing")
        if self.store.get_asset_index_revision(project_id) != proposal.asset_index_revision:
            reasons.append("asset_index_revision")
        for candidate in proposal.candidates:
            try:
                asset = self.store.get_asset(project_id=project_id, asset_id=candidate.asset_id)
                source = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
                if not source.exists():
                    reasons.append("source_unavailable")
                    break
                if candidate.expected_content_sha256 and sha256_file(source) != candidate.expected_content_sha256:
                    reasons.append("source_sha256")
                    break
                if candidate.media_type == "broll":
                    analyses = [item for item in self.store.list_media_analysis(project_id=project_id) if str(item["asset_id"]) == candidate.asset_id]
                    if not analyses or not any(self.store.can_apply_media_analysis(project_id=project_id, analysis_id=str(item["analysis_id"])) and bool(item.get("result")) for item in analyses):
                        reasons.append("analysis_unavailable")
                        break
                if candidate.media_revision != str(asset.get("created_at") or ""):
                    reasons.append("media_revision")
                    break
            except KeyError:
                reasons.append("source_missing")
                break
        return sorted(set(reasons))

    def _rankable_asset(self, asset: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(asset.get("metadata") or {})
        asset_type = str(asset.get("asset_type") or "")
        media_type = {"broll_video": "broll", "music": "bgm", "bgm": "bgm", "sfx": "sfx"}.get(asset_type, metadata.get("media_type", "broll"))
        return {**metadata, "asset_id": asset["asset_id"], "media_type": media_type, "source_kind": asset.get("source_kind", "local_file"), "availability": metadata.get("availability", "available"), "review_status": metadata.get("review_status", "approved"), "license": metadata.get("license", "valid"), "license_policy": metadata.get("license_policy"), "warning_provenance": metadata.get("warning_provenance", ()), "content_sha256": sha256_file(self.store.resolve_storage_uri(project_id=asset["project_id"], storage_uri=str(asset["storage_uri"]))), "media_revision": str(asset.get("created_at") or ""), "preview_uri": metadata.get("preview_uri")}
