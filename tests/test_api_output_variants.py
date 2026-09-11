from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _client(tmp_path: Path) -> tuple[TestClient, str, dict]:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "Output variants API"}).json()
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                {"segment_id": "seg-a", "text": "a"},
                {"segment_id": "seg-b", "text": "b"},
            ],
            "history": [],
        },
    )
    return client, project["project_id"], session


def test_list_variants_lazily_seeds_defaults_with_source_identity(tmp_path: Path) -> None:
    client, project_id, session = _client(tmp_path)
    response = client.get(
        f"/api/projects/{project_id}/output-variants",
        params={"session_id": session["session_id"]},
    )

    assert response.status_code == 200
    variants = response.json()["variants"]
    assert [item["kind"] for item in variants] == ["horizontal", "vertical_full"]
    assert variants[0]["source_session_id"] == session["session_id"]
    assert variants[0]["source_session_revision"] == 1
    assert variants[0]["variant_revision"] == 1


def test_create_highlight_is_explicit_and_optional(tmp_path: Path) -> None:
    client, project_id, session = _client(tmp_path)
    response = client.post(
        f"/api/projects/{project_id}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert response.status_code == 201
    assert response.json()["variant"]["kind"] == "vertical_highlight"


def test_create_highlight_auto_selects_dense_caption_segments(tmp_path: Path) -> None:
    # owner 결정(2026-08-28): "하이라이트 변형 만들기 -- 이것도 자동으로 만들도록
    # 해줘." 전에는 만들자마자 `selected_segment_ids`가 비어 있어서 전체 장면이
    # 그대로 하이라이트가 됐다 -- 자막이 빽빽한 장면 위주로 골라서 실제로 원본보다
    # 짧아지는지 확인한다.
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "Auto highlight"}).json()
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                # 말이 빽빽한 짧은 구간 -- 높은 점수, 골라야 한다.
                {"segment_id": "seg-dense", "caption_text": "정말 중요한 대사가 여기 가득 담겨 있어요", "start_sec": 0.0, "end_sec": 2.0},
                # 자막이 아예 없는 긴 정적 구간 -- 낮은 점수, 빠져야 한다.
                {"segment_id": "seg-silent", "caption_text": "", "start_sec": 2.0, "end_sec": 30.0},
            ],
            "history": [],
        },
    )
    response = client.post(
        f"/api/projects/{project['project_id']}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert response.status_code == 201
    variant = response.json()["variant"]
    assert variant["selected_segment_ids"] == ["seg-dense"]
    assert variant["master_segment_ids"] == ["seg-dense", "seg-silent"]


def test_patch_and_rebase_return_revisioned_variant_conflicts(tmp_path: Path) -> None:
    client, project_id, _ = _client(tmp_path)
    variant = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"][0]
    patched = client.patch(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}",
        json={
            "expected_variant_revision": 1,
            "patch": {"overrides": {"crop": {"mode": "cover"}}, "lock_fields": ["crop"]},
        },
    )
    assert patched.status_code == 200
    assert patched.json()["variant"]["variant_revision"] == 2

    rebased = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/rebase",
        json={"new_master_revision": 2, "changed_fields": ["crop"]},
    )
    assert rebased.status_code == 200, rebased.text
    assert rebased.json()["variant"]["source_session_revision"] == 2
    assert rebased.json()["variant"]["conflicts"][0]["field"] == "crop"

    resolved = client.patch(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}",
        json={
            "expected_variant_revision": rebased.json()["variant"]["variant_revision"],
            "patch": {"resolve_conflicts": {"crop": "keep_local"}},
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["variant"]["conflicts"] == []
    assert resolved.json()["variant"]["locks"][0]["field"] == "crop"


def test_materialize_writes_derived_timeline_with_full_identity(tmp_path: Path) -> None:
    client, project_id, session = _client(tmp_path)
    variant = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"][0]
    response = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/materialize",
        json={"expected_master_session_revision": 1},
    )

    assert response.status_code == 201
    timeline = response.json()["materialization"]
    assert timeline["source_session_id"] == session["session_id"]
    assert timeline["source_session_revision"] == 1
    assert timeline["source_variant_id"] == variant["variant_id"]
    assert timeline["source_variant_revision"] == 1
    assert timeline["timeline_id"]


def test_materialize_route_gives_each_shape_its_own_canvas(tmp_path: Path) -> None:
    """**변형본을 만드는 자리가 둘이다.** 여기(편집기의 `가로·세로 비교` 준비)와
    `local_pipeline._materialize_variant_for_output`(출력 화면의 `가로·세로 출력
    만들기`)이 같은 복사 로직을 따로 갖고 있었다.

    2026-09-11에 크기 결함을 파이프라인 쪽만 고쳤는데, 이 라우터가 먼저 돌면
    틀린 크기의 타임라인이 `save_variant_materialization`에 캐시되고 파이프라인은
    **그걸 재사용한다** -- 고친 것이 조용히 건너뛰어진다. 그래서 두 자리를 한
    함수로 묶고, 이 시험이 그 자리를 지킨다.
    """
    client, project_id, _ = _client(tmp_path)
    variants = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"]
    sizes = {}
    for variant in variants:
        response = client.post(
            f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/materialize",
            json={"expected_master_session_revision": 1},
        )
        assert response.status_code == 201, response.text
        timeline = client.app.state.store.get_timeline_run(
            project_id=project_id,
            timeline_id=response.json()["materialization"]["timeline_id"],
        )
        sizes[variant["kind"]] = timeline.get("output")

    assert sizes["horizontal"] == {"width": 1920, "height": 1080}
    assert sizes["vertical_full"] == {"width": 1080, "height": 1920}


def test_materialize_carries_current_approved_review_to_variant_timeline(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "Approved variant"}).json()
    store = app.state.store
    source = store.save_timeline_run(
        project_id=project["project_id"],
        output_mode="review",
        source_session_id="pending-session",
        source_session_revision=1,
        timeline_payload={"segments": [{"segment_id": "seg-a", "text": "a"}], "tracks": []},
    )
    session = store.save_editing_session(
        project_id=project["project_id"],
        timeline_id=source["timeline_id"],
        session_payload={"segments": [{"segment_id": "seg-a", "text": "a"}], "history": []},
    )
    store.save_review_state(
        project_id=project["project_id"],
        timeline_id=source["timeline_id"],
        status="approved",
        source_session_id=session["session_id"],
        source_session_revision=session["session_revision"],
    )
    variant = client.get(
        f"/api/projects/{project['project_id']}/output-variants",
        params={"session_id": session["session_id"]},
    ).json()["variants"][0]

    response = client.post(
        f"/api/projects/{project['project_id']}/output-variants/{variant['variant_id']}/materialize",
        json={"expected_master_session_revision": 1},
    )

    assert response.status_code == 201, response.text
    materialization = response.json()["materialization"]
    review = store.get_review_state(
        project_id=project["project_id"],
        timeline_id=materialization["timeline_id"],
    )
    assert review["status"] == "approved"
    assert review["source_session_id"] == session["session_id"]
    assert review["source_session_revision"] == 1
    assert review["source_variant_id"] == variant["variant_id"]
    assert review["source_variant_revision"] == variant["variant_revision"]


def test_materialize_stale_master_revision_fails_closed(tmp_path: Path) -> None:
    client, project_id, _ = _client(tmp_path)
    variant = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"][0]
    response = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/materialize",
        json={"expected_master_session_revision": 999},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "stale_master_revision"


def test_patch_stale_variant_revision_does_not_mutate(tmp_path: Path) -> None:
    client, project_id, _ = _client(tmp_path)
    variant = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"][0]
    response = client.patch(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}",
        json={
            "expected_variant_revision": 0,
            "patch": {"overrides": {"audio": {"gain_db": -3}}},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "stale_variant_revision"
    current = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"][0]
    assert current["variant_revision"] == 1
    assert current["overrides"]["audio"] is None


def test_materialize_reuses_revision_identity_and_preserves_master_tracks(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "Materialization reuse"}).json()
    store = app.state.store
    source = store.save_timeline_run(
        project_id=project["project_id"],
        output_mode="horizontal",
        source_session_id="pending-session",
        source_session_revision=1,
        timeline_payload={
            "tracks": [{"track_type": "narration", "clips": [{"clip_id": "clip-1"}]}],
            "segments": [{"segment_id": "seg-a", "text": "a"}],
        },
    )
    session = store.save_editing_session(
        project_id=project["project_id"],
        timeline_id=source["timeline_id"],
        session_payload={"segments": [{"segment_id": "seg-a", "text": "a"}], "history": []},
    )
    variants_url = f"/api/projects/{project['project_id']}/output-variants"
    variant = client.get(variants_url, params={"session_id": session["session_id"]}).json()["variants"][0]
    materialize_url = f"{variants_url}/{variant['variant_id']}/materialize"

    first = client.post(materialize_url, json={"expected_master_session_revision": 1})
    second = client.post(materialize_url, json={"expected_master_session_revision": 1})

    assert first.status_code == 201
    assert second.status_code == 201
    first_materialization = first.json()["materialization"]
    second_materialization = second.json()["materialization"]
    assert second_materialization["timeline_id"] == first_materialization["timeline_id"]
    derived = store.get_timeline_run(
        project_id=project["project_id"],
        timeline_id=first_materialization["timeline_id"],
    )
    assert derived["tracks"] == [{"track_type": "narration", "clips": [{"clip_id": "clip-1"}]}]


def test_materialize_route_rebuilds_a_cache_left_by_the_old_copy_logic(tmp_path: Path) -> None:
    """이 라우터도 `_materialize_variant_for_output`과 같은 함정에 걸린다.

    2026-09-11 실물 측정(project-e6c75c36): 캔버스 크기 결함을 고친 뒤에도
    owner의 세로 변형본은 여전히 1920x1080이었다 -- `source_variant_revision`이
    안 바뀌었으니 `get_variant_materialization`이 옛(버그가 있던) 조립 로직이
    만든 타임라인을 그대로 돌려줬기 때문이다. 이 라우터(`가로·세로 비교` 준비)와
    출력 화면 쪽(`local_pipeline._materialize_variant_for_output`) 둘 다 같은
    `existing is not None`이면 무조건 재사용하는 모양을 갖고 있었다 -- 여기서
    라우터 쪽을 따로 잰다. 옛 로직이 만들었을 법한(마스터와 같은 가로 크기)
    타임라인을 캐시 행에 직접 심어 두고 materialize를 호출한다.
    """
    client, project_id, session = _client(tmp_path)
    store = client.app.state.store
    variants = client.get(
        f"/api/projects/{project_id}/output-variants",
        params={"session_id": session["session_id"]},
    ).json()["variants"]
    vertical = next(item for item in variants if item["kind"] == "vertical_full")

    stale_timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        source_session_id=vertical["source_session_id"],
        source_session_revision=vertical["source_session_revision"],
        timeline_payload={"tracks": [], "segments": [], "output": {"width": 1920, "height": 1080}},
    )
    store.save_variant_materialization(
        project_id=project_id,
        variant_id=vertical["variant_id"],
        source_session_id=vertical["source_session_id"],
        source_session_revision=vertical["source_session_revision"],
        source_variant_revision=vertical["variant_revision"],
        timeline_id=stale_timeline["timeline_id"],
        segments=[],
    )

    response = client.post(
        f"/api/projects/{project_id}/output-variants/{vertical['variant_id']}/materialize",
        json={"expected_master_session_revision": vertical["source_session_revision"]},
    )

    assert response.status_code == 201, response.text
    materialization = response.json()["materialization"]
    assert materialization["timeline_id"] != stale_timeline["timeline_id"]
    rebuilt = store.get_timeline_run(
        project_id=project_id, timeline_id=materialization["timeline_id"]
    )
    assert rebuilt["output"] == {"width": 1080, "height": 1920}


def _short_form_project(tmp_path: Path):
    """장면 셋짜리 프로젝트와, 그 위에 만들어진 숏폼(세로 하이라이트) 모양."""
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "숏폼 장면 고르기"}).json()
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                {"segment_id": "seg-hook", "caption_text": "이것만 보세요", "start_sec": 0.0, "end_sec": 3.0},
                {"segment_id": "seg-middle", "caption_text": "중간 설명", "start_sec": 3.0, "end_sec": 20.0},
                {"segment_id": "seg-close", "caption_text": "결론입니다", "start_sec": 20.0, "end_sec": 24.0},
            ],
            "history": [],
        },
    )
    variant = client.post(
        f"/api/projects/{project['project_id']}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    ).json()["variant"]
    return app, client, project["project_id"], session, variant


def _save_short_form_proposal(app, project_id: str, session: dict, variant: dict, segment_ids: list[str]) -> str:
    """유진이 실제로 돌려주는 모양 그대로 만들어 저장한다 (파싱 -> 되짚기 -> 저장)."""
    import json as _json

    from videobox_core_engine.yujin_creator_proposal_adapter import (
        activate_yujin_media_projection,
        parse_and_project_yujin_creator_output,
    )
    from videobox_domain_models.yujin_creator_context import YujinCreatorContext

    store = app.state.store
    asset_index_revision = int(store.get_asset_index_revision(project_id))
    session_revision = int(session["session_revision"])
    context = YujinCreatorContext.model_validate(
        {
            "schema_version": "videobox.yujin-context.v1",
            "project_id": project_id,
            "session_id": session["session_id"],
            "session_revision": session_revision,
            "asset_index_revision": asset_index_revision,
            "timeline_id": "timeline-source",
            "timeline_version": "v001",
            "segment_summaries": tuple(
                {
                    "segment_id": str(item["segment_id"]),
                    "start_sec": float(item["start_sec"]),
                    "end_sec": float(item["end_sec"]),
                    "text": str(item["caption_text"]),
                }
                for item in session["segments"]
            ),
            "media_candidates": (),
            "timeline_summary": {
                "duration_sec": 24.0,
                "track_count": 1,
                "clip_count": 3,
                "gap_count": 0,
            },
            "supported_controls": ({"kind": "output_variant", "mode": "recommendation_only"},),
            "current_surface": "edit",
            "selection_kind": "variant",
            "master_session_id": session["session_id"],
            "master_session_revision": session_revision,
            "variant_id": str(variant["variant_id"]),
            "variant_kind": "vertical_highlight",
            "variant_revision": int(variant["variant_revision"]),
        }
    )
    payload = {
        "schema_version": "videobox.yujin-response.v1",
        "reply_text": "숏폼에 쓸 장면을 골랐어요.",
        "proposal": {
            "proposal_id": "proposal-short-form",
            "base_revision": f"session:{session['session_id']}:revision:{session_revision}:assets:{asset_index_revision}",
            "title": "숏폼 장면 고르기",
            "rationale": "훅과 결론만 남깁니다.",
            "variant_id": str(variant["variant_id"]),
            "base_variant_revision": int(variant["variant_revision"]),
            "operations": [
                {
                    "operation_id": "short-form-selection",
                    "kind": "output_variant",
                    "target": {
                        "variant_id": str(variant["variant_id"]),
                        "track_id": "output-variant",
                    },
                    "parameters": {"action": "select_segments", "segment_ids": segment_ids},
                    "requires_materialization": False,
                    "preview_summary": "숏폼에 넣을 장면 목록",
                }
            ],
        },
    }
    raw = (
        "숏폼에 쓸 장면을 골랐어요.\n"
        "```videobox-yujin-response\n"
        f"{_json.dumps(payload, ensure_ascii=False)}\n"
        "```"
    )
    projection = parse_and_project_yujin_creator_output(
        raw,
        context,
        revision=1,
        trusted_project_id=project_id,
        trusted_run_id="run-short-form",
    )
    assert projection.proposal is not None, projection.validation_outcome
    projection = activate_yujin_media_projection(
        store=store,
        project_id=project_id,
        context=context,
        projection=projection,
    )
    proposal = projection.proposal
    assert proposal is not None
    assert proposal.status == "ready", proposal.diff.get("proposal_mode")
    store.save_director_proposal(project_id, proposal)
    return proposal.proposal_id


def test_yujin_short_form_cut_applies_through_the_real_apply_route(tmp_path: Path) -> None:
    """유진이 고른 숏폼 장면이 **실제 적용 경로**를 통과해 저장된다.

    이 저장소가 반복해서 겪은 함정이라 화면이 밟는 경로 그대로 잰다 -- 스키마와
    적용기가 있어도 라우터가 `overrides`만 합치고 있으면 장면 선택은
    어디에도 닿지 않는다.
    """
    app, client, project_id, session, variant = _short_form_project(tmp_path)
    before = list(variant["selected_segment_ids"] or [])
    proposal_id = _save_short_form_proposal(
        app, project_id, session, variant, ["seg-hook", "seg-close"]
    )
    candidate_id = app.state.store.get_director_proposal(
        project_id=project_id, proposal_id=proposal_id
    ).candidates[0].candidate_id

    response = client.post(
        f"/api/projects/{project_id}/director/proposals/{proposal_id}/batch-apply",
        json={
            "candidate_ids": [candidate_id],
            "expected_revision": int(session["session_revision"]),
        },
    )

    assert response.status_code == 200, response.text
    applied = response.json()["variant"]
    assert applied["selected_segment_ids"] == ["seg-hook", "seg-close"]
    assert applied["variant_revision"] == int(variant["variant_revision"]) + 1

    # 되돌리기 -- 화면의 `전체 장면으로 되돌리기`와 **같은 문**(통째 목록 PATCH)이다.
    undone = client.patch(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}",
        json={
            "expected_variant_revision": applied["variant_revision"],
            "patch": {"selected_segment_ids": before},
        },
    )

    assert undone.status_code == 200, undone.text
    assert undone.json()["variant"]["selected_segment_ids"] == before
