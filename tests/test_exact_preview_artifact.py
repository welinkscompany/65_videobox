from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.exact_preview import ExactPreviewRequest, fingerprint_exact_preview
from videobox_storage.local_project_store import LocalProjectStore


def _timeline() -> dict[str, object]:
    return {
        "output": {"width": 1080, "height": 1920, "fps_num": 30, "fps_den": 1, "sample_aspect_ratio": "1:1", "rotation": 0},
        "tracks": [
            {"track_type": "narration", "clips": [{"clip_id": "n1", "asset_uri": "local://n", "start_sec": 0, "end_sec": 10, "source_in_sec": 4, "source_out_sec": 14}]},
            {"track_type": "broll", "clips": [{"clip_id": "b1", "asset_uri": "local://b", "start_sec": 5, "end_sec": 15, "media_controls": {"fit": "contain"}}]},
            {"track_type": "overlay", "clips": [{"clip_id": "o1", "start_sec": 8, "end_sec": 12, "overlay_type": "explanation_card", "overlay_payload": {"text": "hello"}}]},
        ],
        # These are consumed by the existing final renderer outside generic
        # tracks, so they must participate in the exact identity too.
        "export_overlays": [{"overlay_type": "image_overlay", "asset_uri": "local://overlay", "start_sec": 8, "end_sec": 12}],
    }


def _session(store: LocalProjectStore, project_id: str) -> dict[str, object]:
    return store.save_editing_session(
        project_id=project_id,
        timeline_id="pre_timeline",
        session_payload={"segments": [], "caption_style": {}},
    )


def test_exact_preview_request_has_canonical_cache_key_and_validates_range() -> None:
    request = ExactPreviewRequest(session_id="session-1", expected_revision=7, start_sec=2.0, end_sec=12.0)
    assert request.cache_key(source_fingerprint="sha256:abc") == request.cache_key(source_fingerprint="sha256:abc")
    assert request.cache_key(source_fingerprint="sha256:abc") != request.cache_key(source_fingerprint="sha256:def")
    with pytest.raises(ValueError, match="exact_preview_invalid_range"):
        ExactPreviewRequest(session_id="session-1", expected_revision=7, start_sec=12, end_sec=2)
    with pytest.raises(ValueError, match="exact_preview_invalid_range"):
        ExactPreviewRequest(session_id="session-1", expected_revision=7, start_sec=float("nan"), end_sec=2)
    with pytest.raises(ValueError, match="exact_preview_invalid_range"):
        request.validate_duration(float("inf"))


def test_composition_plan_clips_crossing_sources_and_zero_bases_range_once() -> None:
    plan = CompositionPlan.from_timeline(timeline=_timeline(), captions=[{"start_sec": 6, "end_sec": 11, "text": "caption"}])
    ranged = plan.for_range(start_sec=7, end_sec=10)
    assert [(item.clip_id, item.start_sec, item.end_sec, item.source_in_sec, item.source_out_sec) for item in ranged.items] == [
        ("n1", 0.0, 3.0, 11.0, 14.0),
        ("b1", 0.0, 3.0, 2.0, 5.0),
        ("o1", 1.0, 3.0, 0.0, 2.0),
    ]
    assert ranged.captions[0].start_sec == 0.0
    assert ranged.captions[0].end_sec == 3.0
    assert ranged.export_overlays == ({"overlay_type": "image_overlay", "asset_uri": "local://overlay", "start_sec": 1.0, "end_sec": 3.0},)
    assert fingerprint_exact_preview(plan=ranged, session_captions=ranged.captions, used_asset_sha256={"asset-b": "b"}) == fingerprint_exact_preview(plan=ranged, session_captions=ranged.captions, used_asset_sha256={"asset-b": "b"})
    assert fingerprint_exact_preview(plan=ranged, session_captions=[], used_asset_sha256={}, overlay_inputs=False, settings=0) != fingerprint_exact_preview(plan=ranged, session_captions=[], used_asset_sha256={}, overlay_inputs=None, settings=None)
    with pytest.raises(ValueError, match="composition_plan_invalid_number"):
        CompositionPlan.from_timeline(timeline={"tracks": [{"track_type": "broll", "clips": [{"start_sec": float("inf"), "end_sec": 2}]}]})


def test_exact_preview_late_generation_cannot_publish_over_current(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="exact-preview")
    session = _session(store, project.project_id)
    first = store.begin_exact_preview(project_id=project.project_id, request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1), fingerprint="sha256:abc")
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=first["generation_id"], owner_token="old-worker")
    second = store.begin_exact_preview(project_id=project.project_id, request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1), fingerprint="sha256:def")
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=second["generation_id"], owner_token="new-worker")
    mp4 = tmp_path / "proxy.mp4"
    mp4.write_bytes(b"proxy")
    assert first["generation_id"] != second["generation_id"]
    assert store.finish_exact_preview(project_id=project.project_id, generation_id=first["generation_id"], fingerprint="sha256:abc", artifact_path=mp4, owner_token="old-worker") is False
    assert store.finish_exact_preview(project_id=project.project_id, generation_id=second["generation_id"], fingerprint="sha256:def", artifact_path=mp4, owner_token="new-worker") is True


def test_exact_preview_coalesces_and_session_mutation_obsoletes_in_same_store_transaction(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="exact-preview session fence")
    session = _session(store, project.project_id)
    request = ExactPreviewRequest(session_id=session["session_id"], expected_revision=1)
    first = store.begin_exact_preview(project_id=project.project_id, request=request, fingerprint="sha256:same")
    assert store.begin_exact_preview(project_id=project.project_id, request=request, fingerprint="sha256:same")["generation_id"] == first["generation_id"]
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=first["generation_id"], owner_token="worker-a") is True
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=first["generation_id"], owner_token="worker-b") is False
    store.update_editing_session(
        project_id=project.project_id,
        session_id=session["session_id"],
        expected_revision=1,
        session_payload={"segments": [], "caption_style": {}, "session_revision": 2},
    )
    assert store.get_exact_preview(project_id=project.project_id, generation_id=first["generation_id"])["state"] == "obsolete"


def test_exact_preview_record_is_project_scoped_and_publish_is_copied_under_project(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_a = store.bootstrap_project(name="preview A")
    project_b = store.bootstrap_project(name="preview B")
    session_a = _session(store, project_a.project_id)
    request = ExactPreviewRequest(session_id=str(session_a["session_id"]), expected_revision=1)
    record = store.begin_exact_preview(project_id=project_a.project_id, request=request, fingerprint="sha256:a")
    mp4 = tmp_path / "untrusted-worker-output.mp4"
    mp4.write_bytes(b"proxy")
    assert store.claim_exact_preview(project_id=project_a.project_id, generation_id=record["generation_id"], owner_token="worker")
    assert store.finish_exact_preview(project_id=project_a.project_id, generation_id=record["generation_id"], fingerprint="sha256:a", artifact_path=mp4, owner_token="worker")
    saved = store.get_exact_preview(project_id=project_a.project_id, generation_id=record["generation_id"])
    assert store.resolve_storage_uri(project_id=project_a.project_id, storage_uri=saved["artifact_uri"]).read_bytes() == b"proxy"
    with pytest.raises(KeyError):
        store.get_exact_preview(project_id=project_b.project_id, generation_id=record["generation_id"])


def test_exact_preview_retry_creates_a_new_generation_after_failure(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview retry")
    session = _session(store, project.project_id)
    first = store.begin_exact_preview(
        project_id=project.project_id,
        request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1),
        fingerprint="sha256:retry",
    )
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=first["generation_id"], owner_token="worker")
    # A zero age threshold is deterministic here because the claim timestamp
    # is strictly earlier than a later clock read in the store operation.
    assert store.recover_stale_exact_preview_claims(project_id=project.project_id, older_than_seconds=0) == 1
    retried = store.retry_exact_preview(project_id=project.project_id, generation_id=first["generation_id"])
    assert retried["generation_id"] != first["generation_id"]
    assert retried["state"] == "pending"


def test_exact_preview_cleanup_removes_crash_orphans_only_inside_exact_preview_root(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview orphan cleanup")
    preview_root = store.project_root(project.project_id) / "derived" / "exact_previews"
    preview_root.mkdir(parents=True)
    # Models a crash after temporary-to-final rename but before the fenced DB
    # pointer update.  It has no durable record and is safe to reclaim.
    orphan = preview_root / "exact_preview_crashed.mp4"
    orphan.write_bytes(b"orphan")
    temporary = preview_root / ".exact_preview_crashed.tmp"
    temporary.write_bytes(b"temporary")
    unrelated = preview_root / "user-note.txt"
    unrelated.write_text("keep", encoding="utf-8")
    os.utime(orphan, (0, 0))
    os.utime(temporary, (0, 0))
    assert store.cleanup_exact_preview_artifacts(project_id=project.project_id) == 2
    assert not orphan.exists()
    assert not temporary.exists()
    assert unrelated.exists()


def test_exact_preview_cleanup_never_claims_an_active_publish_window(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview publish window")
    session = _session(store, project.project_id)
    record = store.begin_exact_preview(
        project_id=project.project_id,
        request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1),
        fingerprint="sha256:publish-window",
    )
    preview_root = store.project_root(project.project_id) / "derived" / "exact_previews"
    preview_root.mkdir(parents=True)
    # This exact path is intentionally unreferenced until finish's fenced DB
    # publish.  A concurrent cleanup must recognize the active generation.
    in_window = preview_root / f"{record['generation_id']}.mp4"
    in_window.write_bytes(b"partial publish")
    os.utime(in_window, (0, 0))
    assert store.cleanup_exact_preview_artifacts(project_id=project.project_id, orphan_older_than_seconds=0) == 0
    worker_output = tmp_path / "worker.mp4"
    worker_output.write_bytes(b"complete proxy")
    # Unclaimed and wrong-owner completions cannot publish the active output.
    assert store.finish_exact_preview(project_id=project.project_id, generation_id=record["generation_id"], fingerprint="sha256:publish-window", artifact_path=worker_output, owner_token="wrong") is False
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=record["generation_id"], owner_token="right")
    assert store.finish_exact_preview(project_id=project.project_id, generation_id=record["generation_id"], fingerprint="sha256:publish-window", artifact_path=worker_output, owner_token="wrong") is False
    assert store.finish_exact_preview(
        project_id=project.project_id,
        generation_id=record["generation_id"],
        fingerprint="sha256:publish-window",
        artifact_path=worker_output,
        owner_token="right",
    )
    saved = store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])
    assert store.resolve_storage_uri(project_id=project.project_id, storage_uri=saved["artifact_uri"]).read_bytes() == b"complete proxy"


def test_exact_preview_rejects_unknown_or_stale_project_scoped_session(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview session required")
    with pytest.raises(KeyError, match="Editing session not found"):
        store.begin_exact_preview(project_id=project.project_id, request=ExactPreviewRequest(session_id="missing", expected_revision=1), fingerprint="sha256:missing")
    session = _session(store, project.project_id)
    with pytest.raises(Exception, match="exact preview session revision is stale"):
        store.begin_exact_preview(project_id=project.project_id, request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=2), fingerprint="sha256:stale")
    with pytest.raises(ValueError, match="exact_preview_invalid_range"):
        store.begin_exact_preview(
            project_id=project.project_id,
            request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1, start_sec=0, end_sec=3),
            fingerprint="sha256:range",
            duration_sec=2,
        )
    with pytest.raises(ValueError, match="exact_preview_duration_required"):
        store.begin_exact_preview(
            project_id=project.project_id,
            request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1, start_sec=0, end_sec=999),
            fingerprint="sha256:missing-duration",
        )


def test_exact_preview_finish_fails_closed_when_session_is_deleted_after_claim(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview deleted session")
    session = _session(store, project.project_id)
    record = store.begin_exact_preview(
        project_id=project.project_id,
        request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1),
        fingerprint="sha256:deleted-session",
    )
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=record["generation_id"], owner_token="worker")
    connection = sqlite3.connect(store.database_path(project.project_id))
    try:
        connection.execute("DELETE FROM editing_sessions WHERE project_id = ? AND session_id = ?", (project.project_id, session["session_id"]))
        connection.commit()
    finally:
        connection.close()
    worker_output = tmp_path / "worker.mp4"
    worker_output.write_bytes(b"proxy")
    assert store.finish_exact_preview(project_id=project.project_id, generation_id=record["generation_id"], fingerprint="sha256:deleted-session", artifact_path=worker_output, owner_token="worker") is False
    assert store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])["state"] == "obsolete"


def test_exact_preview_retry_rejects_pending_running_and_succeeded_records(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview retry state")
    session = _session(store, project.project_id)
    request = ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1)
    pending = store.begin_exact_preview(project_id=project.project_id, request=request, fingerprint="sha256:pending")
    with pytest.raises(ValueError, match="exact_preview_retry_not_failed"):
        store.retry_exact_preview(project_id=project.project_id, generation_id=pending["generation_id"])
    assert store.get_exact_preview(project_id=project.project_id, generation_id=pending["generation_id"])["state"] == "pending"
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=pending["generation_id"], owner_token="worker")
    with pytest.raises(ValueError, match="exact_preview_retry_not_failed"):
        store.retry_exact_preview(project_id=project.project_id, generation_id=pending["generation_id"])
    worker_output = tmp_path / "worker.mp4"
    worker_output.write_bytes(b"proxy")
    assert store.finish_exact_preview(project_id=project.project_id, generation_id=pending["generation_id"], fingerprint="sha256:pending", artifact_path=worker_output, owner_token="worker")
    with pytest.raises(ValueError, match="exact_preview_retry_not_failed"):
        store.retry_exact_preview(project_id=project.project_id, generation_id=pending["generation_id"])
    assert store.get_exact_preview(project_id=project.project_id, generation_id=pending["generation_id"])["state"] == "succeeded"


def test_exact_preview_retry_preserves_validated_ranged_duration_and_rejects_corruption(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview ranged retry")
    session = _session(store, project.project_id)
    record = store.begin_exact_preview(
        project_id=project.project_id,
        request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1, start_sec=0, end_sec=2),
        fingerprint="sha256:ranged-retry",
        duration_sec=2,
    )
    assert record["duration_sec"] == 2.0
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=record["generation_id"], owner_token="worker")
    assert store.recover_stale_exact_preview_claims(project_id=project.project_id, older_than_seconds=0) == 1
    retried = store.retry_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])
    assert retried["state"] == "pending"
    assert retried["start_sec"] == 0.0 and retried["end_sec"] == 2.0 and retried["duration_sec"] == 2.0

    assert store.claim_exact_preview(project_id=project.project_id, generation_id=retried["generation_id"], owner_token="worker-2")
    assert store.recover_stale_exact_preview_claims(project_id=project.project_id, older_than_seconds=0) == 1
    connection = sqlite3.connect(store.database_path(project.project_id))
    try:
        connection.execute("UPDATE exact_preview_renders SET duration_sec = 1 WHERE generation_id = ?", (retried["generation_id"],))
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ValueError, match="exact_preview_invalid_range"):
        store.retry_exact_preview(project_id=project.project_id, generation_id=retried["generation_id"])
    assert store.get_exact_preview(project_id=project.project_id, generation_id=retried["generation_id"])["state"] == "failed"
