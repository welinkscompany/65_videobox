from __future__ import annotations

import inspect
from hashlib import sha256

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_api.routers import director_proposals
from videobox_domain_models.assets import AssetType


def _ready_proposal(tmp_path):
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "이유를 말하는 실패"}).json()["project_id"]
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"local-broll-bytes")
    asset = store.register_asset(
        project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source,
        metadata={"review_status": "approved"},
    )
    digest = sha256(source.read_bytes()).hexdigest()
    analysis = store.create_media_analysis(
        project_id=project_id, asset_id=asset.asset_id,
        idempotency_key=f"{digest}:local", cache_key="cause",
    )
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"])
    store.complete_media_analysis(
        project_id=project_id, analysis_id=analysis["analysis_id"],
        expected_attempt=claim["attempt"], result={"frames": [{"summary": "clip"}]},
    )
    session = store.save_editing_session(
        project_id=project_id, timeline_id="timeline",
        session_payload={"segments": [{"segment_id": "seg-1", "caption_text": "첫 장면"}], "history": []},
    )
    proposal = client.post(
        f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}
    ).json()
    return client, project_id, session, proposal


def test_a_rejected_apply_says_which_thing_was_wrong(tmp_path) -> None:
    """추천 적용이 422 `candidate_unavailable`로 막혔고, 그 한 낱말이 서로 다른
    원인 여덟 가지를 뭉개고 있었다 -- 후보 중복, 모르는 후보 id, 장면 없음, 분석
    없음, 색인 안 됨… 게다가 `from None`이 어디서 터졌는지까지 지웠다.

    **원인을 지우는 오류는 잘못된 진단을 만들어 낸다.** 2026-08-20에 실제로 그랬다:
    단서가 없으니 "지문이 80자에서 잘렸다"는 그럴듯하고 틀린 이야기가 나왔고,
    재 보니 지문은 149자로 온전했고 파일 해시도 정확히 일치했다.
    """
    client, project_id, session, proposal = _ready_proposal(tmp_path)
    candidate_id = proposal["candidates"][0]["candidate_id"]

    response = client.post(
        f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/batch-apply",
        json={"candidate_ids": [candidate_id, candidate_id], "expected_revision": session["session_revision"]},
    )

    assert response.status_code == 422
    # 무엇이 잘못됐는지 말해야 한다. 예전에는 이 자리가 `candidate_unavailable`였다.
    assert response.json()["detail"] == "candidate_ids_duplicate", response.text


def test_the_apply_paths_do_not_erase_where_it_broke(tmp_path) -> None:
    """`from None`은 추적을 지운다. 기록에 원인이 안 남으면 다음 사람도 추측한다."""
    source = inspect.getsource(director_proposals)
    offending = [
        line.strip()
        for line in source.splitlines()
        if "candidate_unavailable" in line and "from None" in line
    ]
    assert not offending, offending
