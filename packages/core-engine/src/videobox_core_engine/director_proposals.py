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

def _placement_segment(proposal: DirectorProposal, candidate_id: str) -> str | None:
    placements = (proposal.diff or {}).get("placements") if isinstance(proposal.diff, dict) else None
    for placement in placements or []:
        if isinstance(placement, dict) and placement.get("candidate_id") == candidate_id:
            target = placement.get("target_segment_id")
            return str(target) if target is not None else None
    # placements 에 없으면 candidate_id 가 담고 있다: `candidate:{장면}:{자산}`
    parts = candidate_id.split(":")
    return parts[1] if len(parts) >= 3 else None


def proposal_to_payload(proposal: DirectorProposal) -> dict[str, object]:
    return {
        "proposal_id": proposal.proposal_id, "revision_code": proposal.revision_code, "revision": proposal.revision,
        "base_session_revision": proposal.base_session_revision, "asset_index_revision": proposal.asset_index_revision,
        "source_session_id": proposal.source_session_id, "target_segment_ids": list(proposal.target_segment_ids),
        "source_script_segment_ids": list(proposal.source_script_segment_ids), "status": proposal.status,
        "diff": _json_value(proposal.diff), "expires_at": proposal.expires_at,
        "candidates": [{"candidate_id": c.candidate_id, "visible_reference_code": c.visible_reference_code,
            # 같은 자산이 여러 장면에 추천될 수 있다. **어느 장면인지 없으면 카드가
            # 전부 똑같아 보인다** -- 2026-08-19 owner 화면이 그랬다. 장면은
            # placements 가 이미 알고 있었는데 후보에는 실리지 않았다.
            "target_segment_id": _placement_segment(proposal, c.candidate_id),
            "media_type": c.media_type, "asset_id": c.asset_id, "library_asset_id": c.library_asset_id,
            "reason_chips": list(c.reason_chips), "scores": _json_value(c.scores), "availability": c.availability,
            "review_status": c.review_status, "preview_uri": c.preview_uri, "controls": _json_value(c.controls),
            "expected_content_sha256": c.expected_content_sha256, "media_revision": c.media_revision,
            "canonical_metadata": _json_value(c.canonical_metadata), "license_policy": c.license_policy,
            "warning_provenance": list(c.warning_provenance)} for c in proposal.candidates],
    }

def proposal_from_payload(payload: dict[str, object]) -> DirectorProposal:
    # `target_segment_id`는 **보여 주기 위해 payload에만 싣는 값**이다(placements가
    # 원본이다). 모델은 그 칸을 갖고 있지 않으므로 되돌릴 때 걷어낸다 -- 안 걷으면
    # 저장분을 다시 읽는 모든 경로가 TypeError로 죽는다(2026-08-19에 39건이 그랬다).
    candidates = tuple(
        DirectorCandidate(**{key: value for key, value in item.items() if key != "target_segment_id"})  # type: ignore[union-attr]
        for item in payload.get("candidates", [])
    )
    return DirectorProposal(**{**payload, "target_segment_ids": tuple(payload.get("target_segment_ids", [])), "source_script_segment_ids": tuple(payload.get("source_script_segment_ids", [])), "candidates": candidates}) # type: ignore[arg-type]
