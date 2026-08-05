from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from videobox_domain_models.assets import AssetType
from videobox_domain_models.media_analysis import MediaAnalysisStatus
from videobox_core_engine.director_proposal_service import DirectorProposalService
from videobox_storage.local_project_store import LocalProjectStore


class _FakeEmbeddingProvider:
    """Returns a fixed vector regardless of prompt text -- tests only need to
    prove the query path calls embed() and feeds the store's cosine ranking,
    not that the embedding is semantically meaningful."""

    def __init__(self, vector: tuple[float, ...]) -> None:
        self.vector = vector
        self.calls: list[str] = []

    def embed(self, request):  # noqa: ANN001
        self.calls.append(request.inputs[0])
        from videobox_provider_interfaces.embeddings import EmbeddingResponse

        return EmbeddingResponse(
            provider_name="fake_embedding",
            model_name=request.model_name,
            vectors=(self.vector,),
        )


def _register_analyzed_broll(store, project_id, *, name: str, embedding: tuple[float, ...], tags: list[str]):
    path = Path(store.projects_root) / f"{name}.mp4"
    path.write_bytes(name.encode("utf-8"))
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=path,
        metadata={"tags": tags, "license": "valid", "review_status": "approved"},
    )
    digest = sha256(path.read_bytes()).hexdigest()
    analysis = store.create_media_analysis(
        project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:{name}", cache_key=name
    )
    claimed = store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"])
    assert claimed
    store.record_media_embedding(
        project_id=project_id,
        analysis_id=analysis["analysis_id"],
        source_sha256=digest,
        profile_hash=name,
        embedding=list(embedding),
    )
    store.complete_media_analysis(
        project_id=project_id,
        analysis_id=analysis["analysis_id"],
        expected_attempt=claimed["attempt"],
        result={"summary": name},
        status=MediaAnalysisStatus.SUCCEEDED,
    )
    return asset


def test_semantic_match_outranks_a_lexically_unrelated_but_embedding_close_asset(tmp_path):
    """The script sentence shares no words with either asset's tags, so
    without semantic search both assets would tie at zero. With semantic
    search wired, the asset whose stored embedding is closer to the query
    embedding must win, and its score must be attributed to
    semantic_similarity (not the lexical fallback)."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("semantic-search")
    near = _register_analyzed_broll(store, project.project_id, name="near", embedding=(1.0, 0.0), tags=["unrelated_tag_a"])
    far = _register_analyzed_broll(store, project.project_id, name="far", embedding=(0.0, 1.0), tags=["unrelated_tag_b"])
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="t",
        session_payload={"segments": [{"segment_id": "seg-1", "caption_text": "오늘은 카페에서 커피를 마셨다"}], "history": []},
    )

    embedding_provider = _FakeEmbeddingProvider(vector=(0.9, 0.1))
    service = DirectorProposalService(store, embedding_provider=embedding_provider, embedding_model_name="test-embedding-model")
    proposal = service.create(project_id=project.project_id, session_id=session["session_id"])

    assert embedding_provider.calls == ["오늘은 카페에서 커피를 마셨다"]
    ranked_asset_ids = [candidate.asset_id for candidate in proposal.candidates]
    assert ranked_asset_ids[0] == near.asset_id
    near_candidate = next(c for c in proposal.candidates if c.asset_id == near.asset_id)
    far_candidate = next(c for c in proposal.candidates if c.asset_id == far.asset_id)
    assert near_candidate.scores["semantic_similarity"] > far_candidate.scores["semantic_similarity"]
    assert near_candidate.canonical_metadata["semantic_provenance"] == "asset_semantic_score"


def test_without_an_embedding_provider_falls_back_to_lexical_scoring_unchanged(tmp_path):
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("no-embedding-provider")
    _register_analyzed_broll(store, project.project_id, name="only", embedding=(1.0, 0.0), tags=["여행"])
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="t",
        session_payload={"segments": [{"segment_id": "seg-1", "caption_text": "여행"}], "history": []},
    )

    proposal = DirectorProposalService(store).create(project_id=project.project_id, session_id=session["session_id"])

    assert proposal.candidates[0].canonical_metadata["semantic_provenance"] == "lexical_korean_synonym_fallback"


def test_embedding_provider_failure_falls_back_to_lexical_scoring_instead_of_blocking(tmp_path, caplog):
    class _ExplodingEmbeddingProvider:
        def embed(self, request):  # noqa: ANN001
            raise RuntimeError("LM Studio unreachable")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("embedding-failure")
    _register_analyzed_broll(store, project.project_id, name="only", embedding=(1.0, 0.0), tags=["여행"])
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="t",
        session_payload={"segments": [{"segment_id": "seg-1", "caption_text": "여행"}], "history": []},
    )

    service = DirectorProposalService(
        store, embedding_provider=_ExplodingEmbeddingProvider(), embedding_model_name="test-embedding-model"
    )
    with caplog.at_level("WARNING"):
        proposal = service.create(project_id=project.project_id, session_id=session["session_id"])

    assert proposal.candidates[0].canonical_metadata["semantic_provenance"] == "lexical_korean_synonym_fallback"
    assert any("fell back to lexical matching" in record.message for record in caplog.records)
