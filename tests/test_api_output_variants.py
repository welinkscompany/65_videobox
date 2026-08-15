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
