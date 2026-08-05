from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import replace
from typing import Any
from videobox_storage.local_project_store import sha256_file

from videobox_core_engine.director_proposals import create_and_save_proposal
from videobox_core_engine.media_ranking import rank_candidates
from videobox_domain_models.director_proposals import DirectorProposal
from videobox_provider_interfaces.embeddings import EmbeddingRequest


def is_actionable_yujin_media_candidate(candidate: object) -> bool:
    media_type = getattr(candidate, "media_type", None)
    metadata = getattr(candidate, "canonical_metadata", {})
    source_media_kind = metadata.get("source_media_kind")
    source_kind_matches = (
        source_media_kind in {"raw_video", "broll_video"}
        if media_type == "broll"
        else source_media_kind == media_type
    )
    return bool(
        getattr(candidate, "availability", None) == "actionable"
        and getattr(candidate, "review_status", None) == "approved"
        and media_type in {"broll", "bgm", "sfx"}
        and metadata.get("yujin_actionable_media") is True
        and source_kind_matches
        and metadata.get("target_segment_id")
    )


class DirectorProposalBlockedError(Exception):
    def __init__(self, lifecycle: dict[str, object]) -> None:
        super().__init__("Director proposal requires applicable local media analysis.")
        self.lifecycle = lifecycle


class DirectorProposalService:
    """Read-only composition boundary for immutable director proposals."""

    def __init__(self, store: object, *, embedding_provider: object = None, embedding_model_name: str | None = None) -> None:
        self.store = store
        self.embedding_provider = embedding_provider
        self.embedding_model_name = embedding_model_name

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
            segment_text = segment.get("caption_text") or segment.get("text") or ""
            scored_assets = self._apply_semantic_scores(project_id=project_id, segment_text=segment_text, assets=assets)
            ranked = rank_candidates({"text": segment_text, "duration_sec": float(segment.get("end_sec", 0) or 0) - float(segment.get("start_sec", 0) or 0)}, scored_assets, preferences)
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
        candidates = proposal.candidates
        if proposal.diff.get("proposal_mode") in {
            "yujin_actionable_media_v1",
            "yujin_actionable_v1",
        }:
            candidates = tuple(
                candidate
                for candidate in candidates
                if is_actionable_yujin_media_candidate(candidate)
                or (
                    candidate.availability == "actionable"
                    and candidate.media_type in {"voice", "overlay"}
                    and candidate.expected_content_sha256
                )
            )
        for candidate in candidates:
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
                if candidate.media_type == "voice":
                    tts_candidate_id = str(
                        candidate.canonical_metadata.get("candidate_id") or ""
                    )
                    tts_candidate = self.store.get_tts_candidate(
                        project_id=project_id,
                        candidate_id=tts_candidate_id,
                    )
                    if (
                        not tts_candidate_id.startswith("tts_candidate_")
                        or str(tts_candidate.get("segment_id") or "")
                        != str(
                            candidate.canonical_metadata.get(
                                "target_segment_id"
                            )
                            or ""
                        )
                        or str(tts_candidate.get("asset_id") or "")
                        != candidate.asset_id
                        or tts_candidate.get("technical_status") != "accepted"
                        or tts_candidate.get("operator_review_status")
                        != "approved"
                    ):
                        reasons.append("tts_candidate_stale")
                        break
                if candidate.media_revision != str(asset.get("created_at") or ""):
                    reasons.append("media_revision")
                    break
            except KeyError:
                reasons.append("source_missing")
                break
        return sorted(set(reasons))

    def _apply_semantic_scores(self, *, project_id: str, segment_text: str, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Look up semantic-similarity scores for `assets` against
        `segment_text` (A-1/Task 20). Query-time cosine ranking already
        existed in store.find_local_media_embedding_matches -- it was simply
        never called from the recommendation path, so semantic_similarity
        was always 0.0 and every candidate fell back to lexical tag
        matching. Fails open to that same lexical fallback on any embedding
        or lookup error; a slow/unreachable local model must not block
        proposal creation."""
        if self.embedding_provider is None or not self.embedding_model_name or not segment_text.strip():
            return assets
        try:
            response = self.embedding_provider.embed(
                EmbeddingRequest(model_name=self.embedding_model_name, inputs=(segment_text,))
            )
            query_vector = list(response.vectors[0])
            matches = self.store.find_local_media_embedding_matches(
                project_id=project_id, query_embedding=query_vector, limit=max(1, len(assets))
            )
        except Exception:
            return assets
        score_by_asset_id = {str(match["asset_id"]): float(match["score"]) for match in matches}
        return [
            {**asset, "semantic_score": score_by_asset_id[str(asset["asset_id"])]}
            if str(asset.get("asset_id")) in score_by_asset_id
            else asset
            for asset in assets
        ]

    def _rankable_asset(self, asset: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(asset.get("metadata") or {})
        asset_type = str(asset.get("asset_type") or "")
        media_type = {"broll_video": "broll", "music": "bgm", "bgm": "bgm", "sfx": "sfx"}.get(asset_type, metadata.get("media_type", "broll"))
        return {**metadata, "asset_id": asset["asset_id"], "media_type": media_type, "source_kind": asset.get("source_kind", "local_file"), "availability": metadata.get("availability", "available"), "review_status": metadata.get("review_status", "approved"), "license": metadata.get("license", "valid"), "license_policy": metadata.get("license_policy"), "warning_provenance": metadata.get("warning_provenance", ()), "content_sha256": sha256_file(self.store.resolve_storage_uri(project_id=asset["project_id"], storage_uri=str(asset["storage_uri"]))), "media_revision": str(asset.get("created_at") or ""), "preview_uri": metadata.get("preview_uri")}
