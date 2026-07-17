from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from videobox_core_engine.output_source_verifier import OutputSourceStaleError, verify_output_freshness, verify_output_sources
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def test_output_verifier_rejects_stale_revision_review_and_subtitle_then_accepts_regenerated_dependencies(tmp_path: Path) -> None:
    """Task 12: byte-identical media is still blocked by stale output dependencies."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="freshness")
    source = tmp_path / "source.wav"
    source.write_bytes(b"immutable bytes")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=source)
    sha = sha256(store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri).read_bytes()).hexdigest()
    registered_revision = store.get_asset(project_id=project.project_id, asset_id=asset.asset_id)["created_at"]
    timeline = {"source_session_revision": 2, "tracks": [{"track_type": "narration", "clips": [{"asset_id": asset.asset_id, "asset_uri": asset.storage_uri, "expected_content_sha256": sha, "media_revision": registered_revision, "media_controls": {"trim_start_sec": 0.1, "loop": False, "fit": "crop"}}]}]}
    verify_output_sources(store=store, project_id=project.project_id, timeline=timeline)
    with pytest.raises(OutputSourceStaleError, match="stale_output_asset: editing session revision changed"):
        verify_output_freshness(editing_session={"session_revision": 3}, timeline=timeline, review={"is_current": False, "source_session_revision": 2}, subtitle={"is_current": False, "source_session_revision": 2})
    with pytest.raises(OutputSourceStaleError, match="review freshness changed"):
        verify_output_freshness(editing_session={"session_revision": 2}, timeline=timeline, review={"is_current": False, "source_session_revision": 2}, subtitle={"is_current": False, "source_session_revision": 2})
    with pytest.raises(OutputSourceStaleError, match="subtitle freshness changed"):
        verify_output_freshness(editing_session={"session_revision": 2}, timeline=timeline, review={"is_current": True, "source_session_revision": 2}, subtitle={"is_current": False, "source_session_revision": 2})
    verify_output_freshness(editing_session={"session_revision": 2}, timeline=timeline, review={"is_current": True, "source_session_revision": 2}, subtitle={"is_current": True, "source_session_revision": 2})


def test_output_verifier_rejects_asset_id_uri_identity_mismatch(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="identity")
    first = tmp_path / "first.bin"; first.write_bytes(b"trusted")
    second = tmp_path / "second.bin"; second.write_bytes(b"renderer consumes this instead")
    trusted = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=first)
    rendered = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=second)
    timeline = {"tracks": [{"track_type": "broll", "clips": [{"asset_id": trusted.asset_id, "asset_uri": rendered.storage_uri, "expected_content_sha256": sha256(b"trusted").hexdigest()}]}]}

    with pytest.raises(OutputSourceStaleError, match="asset identity does not match source URI"):
        verify_output_sources(store=store, project_id=project.project_id, timeline=timeline)


def test_output_verifier_hashes_materialized_source_without_reading_whole_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="streaming")
    source = tmp_path / "source.bin"; source.write_bytes(b"chunked immutable bytes")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    stored = store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri)
    expected = sha256(stored.read_bytes()).hexdigest()
    monkeypatch.setattr(Path, "read_bytes", lambda _path: pytest.fail("verifier must stream source bytes"))

    verify_output_sources(store=store, project_id=project.project_id, timeline={"tracks": [{"track_type": "broll", "clips": [{"asset_id": asset.asset_id, "asset_uri": asset.storage_uri, "expected_content_sha256": expected}]}]})
