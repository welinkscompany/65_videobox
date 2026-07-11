from __future__ import annotations

import shutil
import subprocess
import json
from pathlib import Path

import pytest

from videobox_capcut_export.pycapcut_adapter import PyCapCutExportError, PyCapCutRealExportAdapter
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _generate(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_export_timeline_writes_a_real_capcut_draft(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut Export Project")

    narration_file = tmp_path / "narration_source.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", str(narration_file)])
    narration_asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file
    )

    broll_file = tmp_path / "broll_source.mp4"
    _generate(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=15", str(broll_file)]
    )
    broll_asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file
    )

    bgm_file = tmp_path / "bgm_source.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=6", str(bgm_file)])
    bgm_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BGM, source_path=bgm_file)

    timeline = {
        "narration_source_uri": narration_asset.storage_uri,
        "export_overlays": [
            {
                "overlay_type": "explanation_card",
                "text": "Overlay draft proof",
                "start_sec": 1.0,
                "end_sec": 3.0,
            }
        ],
        "tracks": [
            {
                "track_type": "narration",
                "clips": [
                    {
                        "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                        "start_sec": 0.0,
                        "end_sec": 3.0,
                    },
                    {
                        "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                        "start_sec": 3.0,
                        "end_sec": 6.0,
                    },
                ],
            },
            {
                "track_type": "broll",
                "clips": [
                    {
                        "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}",
                        "start_sec": 0.0,
                        "end_sec": 3.0,
                    },
                    {
                        "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}",
                        "start_sec": 3.0,
                        "end_sec": 6.0,
                    },
                ],
            },
            {
                "track_type": "bgm",
                "clips": [
                    {
                        "asset_uri": f"local://projects/{project.project_id}/assets/{bgm_asset.asset_id}",
                        "start_sec": 0.0,
                        "end_sec": 6.0,
                    }
                ],
            },
        ],
    }

    adapter = PyCapCutRealExportAdapter(store=store)
    drafts_root = tmp_path / "capcut_drafts"

    draft_path = adapter.export_timeline(
        project_id=project.project_id,
        timeline=timeline,
        drafts_root=drafts_root,
        draft_name="videobox_export_test",
    )

    assert draft_path.exists()
    draft_content = draft_path / "draft_content.json"
    assert draft_content.exists()
    assert draft_content.stat().st_size > 0
    assert "Overlay draft proof" in json.dumps(json.loads(draft_content.read_text(encoding="utf-8")), ensure_ascii=False)


def test_export_timeline_requires_narration_clips(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut Export Rejection Project")
    adapter = PyCapCutRealExportAdapter(store=store)

    with pytest.raises(PyCapCutExportError, match="narration"):
        adapter.export_timeline(
            project_id=project.project_id,
            timeline={"tracks": []},
            drafts_root=tmp_path / "capcut_drafts",
            draft_name="empty_export",
        )


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_export_timeline_repeats_short_broll_and_keeps_short_tts_in_its_timeline_window(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut Duration Contract")

    tts_file = tmp_path / "short_tts.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(tts_file)])
    tts_asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.GENERATED_TTS_AUDIO, source_path=tts_file
    )
    broll_file = tmp_path / "short_broll.mp4"
    _generate(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=15", str(broll_file)]
    )
    broll_asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file
    )
    timeline = {
        "tracks": [
            {
                "track_type": "narration",
                "clips": [
                    {
                        "asset_uri": f"local://projects/{project.project_id}/assets/{tts_asset.asset_id}",
                        "start_sec": 0.0,
                        "end_sec": 4.0,
                    }
                ],
            },
            {
                "track_type": "broll",
                "clips": [
                    {
                        "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}",
                        "start_sec": 0.0,
                        "end_sec": 4.0,
                    }
                ],
            },
        ],
    }

    draft_path = PyCapCutRealExportAdapter(store=store).export_timeline(
        project_id=project.project_id,
        timeline=timeline,
        drafts_root=tmp_path / "capcut_drafts",
        draft_name="duration_contract",
    )
    content = json.loads((draft_path / "draft_content.json").read_text(encoding="utf-8"))
    tracks = {track["name"]: track["segments"] for track in content["tracks"]}

    assert tracks["voiceover"][0]["target_timerange"] == {"start": 0, "duration": 1_000_000}
    assert tracks["voiceover"][0]["speed"] == pytest.approx(1.0)
    assert tracks["voiceover"][1]["target_timerange"] == {
        "start": 1_000_000,
        "duration": 3_000_000,
    }
    silence_material = next(
        material
        for material in content["materials"]["audios"]
        if Path(material["path"]).name.startswith("videobox_silence_")
    )
    assert tracks["voiceover"][1]["material_id"] == silence_material["id"]
    assert [segment["target_timerange"] for segment in tracks["broll"]] == [
        {"start": 0, "duration": 1_000_000},
        {"start": 1_000_000, "duration": 1_000_000},
        {"start": 2_000_000, "duration": 1_000_000},
        {"start": 3_000_000, "duration": 1_000_000},
    ]


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_export_timeline_materializes_image_overlay_in_real_capcut_draft(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut Image Overlay Contract")
    narration_file = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(narration_file)])
    narration_asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file
    )
    image_file = tmp_path / "overlay.png"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:size=32x24", "-frames:v", "1", str(image_file)])
    image_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.IMAGE, source_path=image_file)
    timeline = {
        "narration_source_uri": narration_asset.storage_uri,
        "export_overlays": [
            {
                "overlay_type": "image_overlay",
                "asset_id": image_asset.asset_id,
                "start_sec": 1.0,
                "end_sec": 3.0,
            }
        ],
        "tracks": [
            {
                "track_type": "narration",
                "clips": [
                    {
                        "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                        "start_sec": 0.0,
                        "end_sec": 4.0,
                    }
                ],
            }
        ],
    }

    draft_path = PyCapCutRealExportAdapter(store=store).export_timeline(
        project_id=project.project_id,
        timeline=timeline,
        drafts_root=tmp_path / "capcut_drafts",
        draft_name="image_overlay_contract",
    )
    content = json.loads((draft_path / "draft_content.json").read_text(encoding="utf-8"))
    tracks = {track["name"]: track["segments"] for track in content["tracks"]}
    image_material = next(material for material in content["materials"]["videos"] if material["path"].endswith("overlay.png"))

    assert len(tracks["videobox_image_overlays"]) == 1
    assert tracks["videobox_image_overlays"][0]["target_timerange"] == {
        "start": 1_000_000,
        "duration": 2_000_000,
    }
    assert tracks["videobox_image_overlays"][0]["material_id"] == image_material["id"]
