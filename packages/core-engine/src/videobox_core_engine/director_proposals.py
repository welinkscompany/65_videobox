from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Iterable
from videobox_domain_models.director_proposals import DirectorCandidate, DirectorProposal

def _json_value(value: object) -> object:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _json_value(item) for key, item in value.items()}  # type: ignore[union-attr]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    return value

def create_proposal(*, base_session_revision: int, asset_index_revision: int, source_session_id: str, candidates: Iterable[DirectorCandidate], revision: int, source_script_segment_ids: Iterable[str] = (), target_segment_ids: Iterable[str] = (), proposal_id: str | None = None, expires_at: str | None = None, diff: dict[str, object] | None = None) -> DirectorProposal:
    frozen_candidates = tuple(
        replace(candidate, visible_reference_code=f"P{revision:02d}" + candidate.visible_reference_code[3:])
        for candidate in candidates
    )
    return DirectorProposal(proposal_id=proposal_id or f"proposal:{uuid.uuid4().hex}", revision_code=f"P{revision:02d}", revision=revision, base_session_revision=base_session_revision, asset_index_revision=asset_index_revision, source_session_id=source_session_id, target_segment_ids=tuple(target_segment_ids), source_script_segment_ids=tuple(source_script_segment_ids), status="ready", diff=dict(diff or {}), expires_at=expires_at, candidates=frozen_candidates)

def create_and_save_proposal(*, store: object, project_id: str, base_session_revision: int, asset_index_revision: int, source_session_id: str, candidates: Iterable[DirectorCandidate], source_script_segment_ids: Iterable[str] = (), target_segment_ids: Iterable[str] = (), expires_at: str | None = None, diff: dict[str, object] | None = None) -> DirectorProposal:
    """The only convenience creation path: allocate then persist a project revision."""
    revision = store.next_director_proposal_revision(project_id)  # type: ignore[attr-defined]
    proposal = create_proposal(base_session_revision=base_session_revision, asset_index_revision=asset_index_revision, source_session_id=source_session_id, candidates=candidates, revision=revision, source_script_segment_ids=source_script_segment_ids, target_segment_ids=target_segment_ids, expires_at=expires_at, diff=diff)
    store.save_director_proposal(project_id, proposal)  # type: ignore[attr-defined]
    return proposal

def proposal_to_payload(proposal: DirectorProposal) -> dict[str, object]:
    return {
        "proposal_id": proposal.proposal_id, "revision_code": proposal.revision_code, "revision": proposal.revision,
        "base_session_revision": proposal.base_session_revision, "asset_index_revision": proposal.asset_index_revision,
        "source_session_id": proposal.source_session_id, "target_segment_ids": list(proposal.target_segment_ids),
        "source_script_segment_ids": list(proposal.source_script_segment_ids), "status": proposal.status,
        "diff": _json_value(proposal.diff), "expires_at": proposal.expires_at,
        "candidates": [{"candidate_id": c.candidate_id, "visible_reference_code": c.visible_reference_code,
            "media_type": c.media_type, "asset_id": c.asset_id, "library_asset_id": c.library_asset_id,
            "reason_chips": list(c.reason_chips), "scores": _json_value(c.scores), "availability": c.availability,
            "review_status": c.review_status, "preview_uri": c.preview_uri, "controls": _json_value(c.controls),
            "expected_content_sha256": c.expected_content_sha256, "media_revision": c.media_revision,
            "canonical_metadata": _json_value(c.canonical_metadata), "license_policy": c.license_policy,
            "warning_provenance": list(c.warning_provenance)} for c in proposal.candidates],
    }

def proposal_from_payload(payload: dict[str, object]) -> DirectorProposal:
    candidates = tuple(DirectorCandidate(**item) for item in payload.get("candidates", [])) # type: ignore[arg-type]
    return DirectorProposal(**{**payload, "target_segment_ids": tuple(payload.get("target_segment_ids", [])), "source_script_segment_ids": tuple(payload.get("source_script_segment_ids", [])), "candidates": candidates}) # type: ignore[arg-type]
