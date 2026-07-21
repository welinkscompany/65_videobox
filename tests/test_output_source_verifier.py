from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from videobox_core_engine.output_source_verifier import (
    OutputSourceStaleError,
    capture_output_source_snapshots,
    verify_output_freshness,
    verify_output_source_snapshots,
    verify_output_sources,
)
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


@pytest.mark.parametrize("changed_input", ("broll", "bgm", "sfx", "export_overlay"))
def test_output_snapshots_fence_every_actual_composition_asset_without_preexisting_identity(
    tmp_path: Path, changed_input: str,
) -> None:
    """Base tracks and export overlays are render inputs even before Task-11 identity stamping."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="all composition source fence")
    paths = {kind: tmp_path / f"{kind}.bin" for kind in ("broll", "bgm", "sfx", "export_overlay")}
    for kind, path in paths.items():
        path.write_bytes(f"original-{kind}".encode())
    assets = {
        "broll": store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=paths["broll"]),
        "bgm": store.register_asset(project_id=project.project_id, asset_type=AssetType.BGM, source_path=paths["bgm"]),
        "sfx": store.register_asset(project_id=project.project_id, asset_type=AssetType.SFX, source_path=paths["sfx"]),
        "export_overlay": store.register_asset(project_id=project.project_id, asset_type=AssetType.IMAGE, source_path=paths["export_overlay"]),
    }
    timeline = {
        "tracks": [
            {"track_type": kind, "clips": [{"asset_id": assets[kind].asset_id, "asset_uri": assets[kind].storage_uri, "start_sec": 0, "end_sec": 1}]}
            for kind in ("broll", "bgm", "sfx")
        ],
        "export_overlays": [{"asset_id": assets["export_overlay"].asset_id, "asset_uri": assets["export_overlay"].storage_uri, "start_sec": 0, "end_sec": 1}],
    }

    snapshots = capture_output_source_snapshots(store=store, project_id=project.project_id, timeline=timeline)
    assert {snapshot.asset_id for snapshot in snapshots} == {asset.asset_id for asset in assets.values()}
    store.resolve_storage_uri(project_id=project.project_id, storage_uri=assets[changed_input].storage_uri).write_bytes(
        f"changed-{changed_input}".encode()
    )

    with pytest.raises(OutputSourceStaleError, match="stale_output_asset: content SHA-256 changed"):
        verify_output_source_snapshots(snapshots)


@pytest.mark.parametrize(
    ("input_kind", "asset_type"),
    (
        ("broll", AssetType.BROLL_VIDEO),
        ("bgm", AssetType.BGM),
        ("sfx", AssetType.SFX),
        ("export_overlay", AssetType.IMAGE),
    ),
)
def test_output_snapshots_bind_unstamped_direct_storage_uri_to_registered_asset(
    tmp_path: Path, input_kind: str, asset_type: AssetType,
) -> None:
    """A renderable direct URI may omit legacy identity fields but not its fence."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name=f"direct {input_kind} source fence")
    source = tmp_path / f"{input_kind}.bin"
    source.write_bytes(f"{input_kind}-before".encode())
    asset = store.register_asset(project_id=project.project_id, asset_type=asset_type, source_path=source)
    clip = {"clip_id": input_kind, "asset_uri": asset.storage_uri, "start_sec": 0, "end_sec": 1}
    timeline = {
        "tracks": [] if input_kind == "export_overlay" else [{"track_type": input_kind, "clips": [clip]}],
        "export_overlays": [clip] if input_kind == "export_overlay" else [],
    }

    snapshots = capture_output_source_snapshots(store=store, project_id=project.project_id, timeline=timeline)

    assert [snapshot.asset_id for snapshot in snapshots] == [asset.asset_id]
    store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri).write_bytes(b"direct-uri-changed")
    with pytest.raises(OutputSourceStaleError, match="stale_output_asset: content SHA-256 changed"):
        verify_output_source_snapshots(snapshots)


def test_output_snapshots_bind_segment_narration_to_its_actual_source_asset(tmp_path: Path) -> None:
    """Virtual narration segments consume narration_source_uri and need the same fence."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="segment narration source fence")
    source = tmp_path / "narration.wav"
    source.write_bytes(b"narration-before-render")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=source)
    timeline = {
        "narration_source_uri": asset.storage_uri,
        "tracks": [{"track_type": "narration", "clips": [{
            "clip_id": "segment-1",
            "asset_uri": f"local://projects/{project.project_id}/segments/segment-1",
            "start_sec": 0,
            "end_sec": 1,
        }]}],
    }

    snapshots = capture_output_source_snapshots(store=store, project_id=project.project_id, timeline=timeline)

    assert [snapshot.asset_id for snapshot in snapshots] == [asset.asset_id]
    store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri).write_bytes(b"narration-changed")
    with pytest.raises(OutputSourceStaleError, match="stale_output_asset: content SHA-256 changed"):
        verify_output_source_snapshots(snapshots)


@pytest.mark.parametrize("track_type", ("broll", "bgm", "sfx", "overlay"))
def test_output_snapshots_reject_segment_uri_outside_narration_track(tmp_path: Path, track_type: str) -> None:
    """Only narration owns virtual segment URI semantics; other tracks fail closed."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name=f"non narration segment {track_type}")
    source = tmp_path / "narration.wav"
    source.write_bytes(b"narration")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=source)
    timeline = {
        "narration_source_uri": asset.storage_uri,
        "tracks": [{"track_type": track_type, "clips": [{
            "clip_id": "wrong-segment-semantics",
            "asset_uri": f"local://projects/{project.project_id}/segments/segment-1",
            "start_sec": 0,
            "end_sec": 1,
        }]}],
    }

    with pytest.raises(OutputSourceStaleError, match="segment source is only valid for narration"):
        capture_output_source_snapshots(store=store, project_id=project.project_id, timeline=timeline)
