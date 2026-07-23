from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.editor_playback_manifest import (
    frame_to_seconds,
    seconds_to_frame,
)
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def _manifest_fixture(client: TestClient, tmp_path) -> tuple[str, str, str]:
    project_id = client.post("/api/projects", json={"name": "Manifest"}).json()["project_id"]
    other_project_id = client.post("/api/projects", json={"name": "Other"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={
            "version": "draft-v1",
            "fps_num": 30000,
            "fps_den": 1001,
            "output": {"width": 1080, "height": 1920, "sample_aspect_ratio": "1:1", "rotation": 0, "duration_sec": 2.0},
            "tracks": [{"track_id": "narration_primary", "track_type": "narration", "clips": [{"clip_id": "clip-narration-1", "segment_id": "segment-1", "clip_type": "narration", "asset_id": "asset-narration-1", "asset_uri": f"local://projects/{project_id}/assets/asset-narration-1", "start_sec": 0.0, "end_sec": 2.0, "media_controls": {"volume": 0.8}, "expected_content_sha256": "a" * 64, "media_revision": "media-r1"}]}, {"track_id": "broll_overlay", "track_type": "broll", "clips": [{"clip_id": "clip-broll-1", "segment_id": "segment-1", "clip_type": "broll", "asset_id": "asset-broll-1", "asset_uri": f"local://projects/{project_id}/assets/asset-broll-1", "start_sec": 0.0, "end_sec": 2.0, "media_controls": {"crop": "cover"}, "expected_content_sha256": "b" * 64, "media_revision": "media-r2"}]}],
            "gap_slots": [{"gap_id": "gap-1", "segment_id": "segment-1", "start_sec": 1.0, "end_sec": 1.5, "reason": "missing_broll"}],
            "review_flags": [],
        },
    )
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"caption_style": {"font_size_px": 48}, "history": [], "segments": [{"segment_id": "segment-1", "caption_text": "안녕하세요", "start_sec": 0.0, "end_sec": 2.0, "cut_action": "keep", "review_required": False, "source_sha256": "c" * 64, "media_revision": "media-r1", "content_windows": [{"caption_id": "caption-segment-1-0", "source_segment_id": "segment-1", "caption_text": "안녕하세요", "start_offset_sec": 0.0, "duration_sec": 2.0, "review_required": False, "visual_overlays": []}]}]},
    )
    return project_id, other_project_id, session["session_id"]


def test_seconds_frame_conversion_is_rational_nonnegative_half_up() -> None:
    assert seconds_to_frame(0.0, fps_num=30000, fps_den=1001) == 0
    assert seconds_to_frame(1.0 / 60.0, fps_num=30, fps_den=1) == 1
    assert seconds_to_frame(0.5 / 30.0, fps_num=30, fps_den=1) == 1
    assert frame_to_seconds(1, fps_num=30000, fps_den=1001) == 1001 / 30000


def test_explicit_session_manifest_has_authoritative_typed_editor_contract(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)

    response = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["timebase"] == "seconds"
    assert body["fps"] == {"num": 30000, "den": 1001}
    assert body["output"] == {"width": 1080, "height": 1920, "sample_aspect_ratio": "1:1", "rotation": 0, "duration_sec": 2.0}
    assert body["project_id"] == project_id and body["session_id"] == session_id
    assert body["timeline_id"].startswith("timeline_") and body["session_revision"] == 1
    assert body["tracks"][0]["track_type"] == "narration"
    assert body["tracks"][0]["clips"][0]["media_controls"] == {"volume": 0.8}
    assert body["tracks"][1]["clips"][0]["expected_content_sha256"] == "b" * 64
    assert body["captions"] == [{"segment_id": "segment-1", "caption_id": "caption-segment-1-0", "placement_id": "caption:caption-segment-1-0", "text": "안녕하세요", "start_sec": 0.0, "end_sec": 2.0, "style": {"font_family": "Arial", "font_size_px": 48, "text_color": "#FFFFFFFF", "outline_color": "#000000FF", "outline_width_px": 3, "background_color": "#00000000", "position_x_percent": 50, "position_y_percent": 88, "horizontal_align": "center", "safe_area_enabled": True, "shadow_blur_px": 0}}]
    assert body["gap_slots"][0]["gap_id"] == "gap-1"
    assert body["source_status"] == {"status": "current", "source_session_id": session_id, "source_session_revision": 1}
    assert body["audition"]["asset_urls"]["asset-narration-1"].endswith("/assets/asset-narration-1/content")
    assert body["exact_preview"] == {"status": "unavailable"}


def test_caption_patch_materializes_updated_content_window_in_playback_manifest(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)

    saved = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/segment-1/caption",
        json={"caption_text": "반가워요", "expected_revision": 1},
    )
    manifest = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest")

    assert saved.status_code == 200
    assert saved.json()["session_revision"] == 2
    assert manifest.status_code == 200
    assert manifest.json()["captions"][0]["text"] == "반가워요"


def test_overlay_patches_roundtrip_through_content_windows_and_typed_manifest(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)

    explanation = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/segment-1/explanation-card",
        json={"title": "핵심", "body": "설명", "text": "핵심 설명", "expected_revision": 1},
    )
    assert explanation.status_code == 200
    explanation_manifest = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest",
    )
    assert explanation_manifest.status_code == 200
    explanation_clip = next(
        clip
        for track in explanation_manifest.json()["tracks"]
        if track["track_type"] == "overlay"
        for clip in track["clips"]
    )
    assert explanation_clip["overlay_type"] == "explanation_card"
    assert explanation_clip["overlay_payload"]["text"] == "핵심 설명"

    removed = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/segment-1/explanation-card",
        params={"expected_revision": 2},
    )
    assert removed.status_code == 200
    removed_manifest = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest",
    )
    assert removed_manifest.status_code == 200
    assert all(track["track_type"] != "overlay" for track in removed_manifest.json()["tracks"])

    image_source = tmp_path / "overlay.png"
    image_source.write_bytes(b"local-image")
    image_asset = LocalProjectStore(tmp_path).register_asset(
        project_id=project_id,
        asset_type=AssetType.IMAGE,
        source_path=image_source,
    )
    image = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/segment-1/image-overlay",
        json={"asset_id": image_asset.asset_id, "text": "참고 이미지", "expected_revision": 3},
    )
    assert image.status_code == 200
    image_manifest = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest",
    )
    assert image_manifest.status_code == 200
    image_clip = next(
        clip
        for track in image_manifest.json()["tracks"]
        if track["track_type"] == "overlay"
        for clip in track["clips"]
    )
    assert image_clip["overlay_type"] == "image_overlay"
    assert image_clip["asset_id"] == image_asset.asset_id
    assert image_clip["overlay_payload"]["text"] == "참고 이미지"
    assert client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/segment-1/image-overlay",
        params={"expected_revision": 4},
    ).status_code == 200

    table = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/segment-1/table-overlay",
        json={"columns": ["항목"], "rows": [["값"]], "text": "항목 | 값", "expected_revision": 5},
    )
    assert table.status_code == 200
    table_manifest = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest",
    )
    assert table_manifest.status_code == 200
    table_clip = next(
        clip
        for track in table_manifest.json()["tracks"]
        if track["track_type"] == "overlay"
        for clip in track["clips"]
    )
    assert table_clip["overlay_type"] == "table_overlay"
    assert table_clip["overlay_payload"]["rows"] == [["값"]]
    assert client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/segment-1/table-overlay",
        params={"expected_revision": 6},
    ).status_code == 200
    final_manifest = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest",
    )
    assert final_manifest.status_code == 200
    assert all(track["track_type"] != "overlay" for track in final_manifest.json()["tracks"])


def test_manifest_never_substitutes_latest_session_and_is_project_isolated(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, other_project_id, session_id = _manifest_fixture(client, tmp_path)

    assert client.get(f"/api/projects/{project_id}/editing-sessions/latest/playback-manifest").status_code == 404
    assert client.get(f"/api/projects/{other_project_id}/editing-sessions/{session_id}/playback-manifest").status_code == 404


def test_timeline_placement_patch_reappears_in_the_authoritative_manifest(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)

    saved = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/timeline-placements",
        json={"expected_revision": 1, "changes": [{"placement_id": "broll:clip-broll-1", "kind": "broll", "start_sec": 0.5, "end_sec": 1.5}]},
    )
    manifest = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest")

    assert saved.status_code == 200
    assert saved.json()["session_revision"] == 2
    assert LocalProjectStore(tmp_path).get_editing_session(project_id=project_id, session_id=session_id)["timeline_placement_overrides"]["broll:clip-broll-1"]["start_sec"] == 0.5005
    assert manifest.status_code == 200
    broll = next(track for track in manifest.json()["tracks"] if track["track_type"] == "broll")["clips"][0]
    assert broll["placement_id"] == "broll:clip-broll-1"
    assert broll["start_sec"] == 0.5005
    assert broll["end_sec"] == 1.5015


def test_manifest_marks_old_timeline_source_stale_and_separates_stale_final(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)
    store = LocalProjectStore(tmp_path)
    session = store.get_editing_session(project_id=project_id, session_id=session_id)
    store.update_editing_session(project_id=project_id, session_id=session_id, session_payload=session, expected_revision=1)

    response = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest")

    assert response.status_code == 200
    assert response.json()["source_status"] == {"status": "stale", "source_session_id": session_id, "source_session_revision": 1}


def test_manifest_never_labels_a_legacy_final_render_as_an_exact_preview(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)
    store = LocalProjectStore(tmp_path)
    session = store.get_editing_session(project_id=project_id, session_id=session_id)
    source = tmp_path / "final.mp4"
    source.write_bytes(b"video")
    export = store.save_final_render(project_id=project_id, timeline_id=session["timeline_id"], source_output_path=source, source_session_id=session_id)
    job = store.create_job(project_id=project_id, job_type=JobType.FINAL_RENDER, status=JobStatus.SUCCEEDED)
    store.update_job(project_id=project_id, job_id=job["job_id"], status=JobStatus.SUCCEEDED, output_ref=export["export_id"])

    current = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest").json()
    assert current["exact_preview"] == {"status": "unavailable"}


def test_same_revision_from_another_session_never_makes_its_final_render_an_exact_preview(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_a = _manifest_fixture(client, tmp_path)
    store = LocalProjectStore(tmp_path)
    first = store.get_editing_session(project_id=project_id, session_id=session_a)
    output = tmp_path / "from-a.mp4"; output.write_bytes(b"a")
    export = store.save_final_render(project_id=project_id, timeline_id=first["timeline_id"], source_output_path=output, source_session_id=session_a)
    job = store.create_job(project_id=project_id, job_type=JobType.FINAL_RENDER, status=JobStatus.SUCCEEDED)
    store.update_job(project_id=project_id, job_id=job["job_id"], status=JobStatus.SUCCEEDED, output_ref=export["export_id"])
    session_b = store.save_editing_session(project_id=project_id, timeline_id=first["timeline_id"], session_payload={"history": [], "segments": []})

    manifest = client.get(f"/api/projects/{project_id}/editing-sessions/{session_b['session_id']}/playback-manifest").json()

    assert session_b["session_revision"] == 1
    assert manifest["source_status"]["status"] == "current"
    assert manifest["exact_preview"] == {"status": "unavailable"}


def test_final_export_fallback_uses_its_source_session_id_not_latest_timeline_session(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_a = _manifest_fixture(client, tmp_path)
    store = LocalProjectStore(tmp_path)
    first = store.get_editing_session(project_id=project_id, session_id=session_a)
    store.update_editing_session(project_id=project_id, session_id=session_a, session_payload=first, expected_revision=1)
    store.save_editing_session(project_id=project_id, timeline_id=first["timeline_id"], session_payload={"history": [], "segments": []})
    output = tmp_path / "from-a-r2.mp4"; output.write_bytes(b"a2")

    export = store.save_final_render(project_id=project_id, timeline_id=first["timeline_id"], source_output_path=output, source_session_id=session_a)

    persisted = store.get_final_render_export(project_id=project_id, export_id=export["export_id"])
    assert persisted["source_session_id"] == session_a
    assert persisted["source_session_revision"] == 2


def test_manifest_rejects_unsupported_track_roles_instead_of_emitting_generic_maps(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)
    store = LocalProjectStore(tmp_path)
    session = store.get_editing_session(project_id=project_id, session_id=session_id)
    timeline = store.get_timeline_run(project_id=project_id, timeline_id=session["timeline_id"])
    timeline["tracks"][0]["track_type"] = "freeform-anything"
    store.update_timeline_run(project_id=project_id, timeline_id=timeline["timeline_id"], timeline_payload=timeline)

    response = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest")
    assert response.status_code == 422


def test_manifest_rejects_overlay_without_supported_subtype_or_dict_payload(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)
    store = LocalProjectStore(tmp_path)
    session = store.get_editing_session(project_id=project_id, session_id=session_id)
    timeline = store.get_timeline_run(project_id=project_id, timeline_id=session["timeline_id"])
    timeline["tracks"].append({"track_id": "overlay", "track_type": "overlay", "clips": [{"clip_id": "overlay-1", "segment_id": "segment-1", "clip_type": "overlay", "start_sec": 0, "end_sec": 1, "media_controls": {}}]})
    store.update_timeline_run(project_id=project_id, timeline_id=timeline["timeline_id"], timeline_payload=timeline)

    assert client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest").status_code == 422

    timeline["tracks"][-1]["clips"][0].update({"overlay_type": "image_overlay", "overlay_payload": ["not", "a", "map"]})
    store.update_timeline_run(project_id=project_id, timeline_id=timeline["timeline_id"], timeline_payload=timeline)
    assert client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest").status_code == 422


def test_manifest_rejects_unsupported_persisted_caption_style_keys(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)
    store = LocalProjectStore(tmp_path)
    session = store.get_editing_session(project_id=project_id, session_id=session_id)
    session["caption_style"]["untrusted_css"] = "url(javascript:alert(1))"
    store.update_editing_session(project_id=project_id, session_id=session_id, session_payload=session, expected_revision=1)

    response = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest")
    assert response.status_code == 422
