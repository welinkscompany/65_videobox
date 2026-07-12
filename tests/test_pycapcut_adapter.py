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


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_export_timeline_maps_editing_session_caption_style_to_real_capcut_text_segment(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Styled Caption CapCut Draft")
    narration_path = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(narration_path)])
    narration_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_path)
    result = PyCapCutRealExportAdapter(store=store).export_timeline(
        project_id=project.project_id,
        timeline={"narration_source_uri": narration_asset.storage_uri, "tracks": [{"track_type": "narration", "clips": [{"asset_uri": f"local://projects/{project.project_id}/segments/seg_001", "start_sec": 0.0, "end_sec": 2.0}]}]},
        editing_session={"caption_style": {"font_size_px": 64, "text_color": "#00FF00FF", "outline_width_px": 3, "background_color": "#000000AA", "shadow_blur_px": 2}, "segments": [{"caption_text": "CAPTION STYLE", "start_sec": 0.2, "end_sec": 1.5}]},
        drafts_root=tmp_path / "drafts",
        draft_name="styled-caption",
    )

    content = json.loads((result.draft_path / "draft_content.json").read_text(encoding="utf-8"))
    captions = next(track["segments"] for track in content["tracks"] if track["name"] == "subtitle")
    material = next(item for item in content["materials"]["texts"] if "CAPTION STYLE" in item["content"])
    assert captions[0]["target_timerange"] == {"start": 200_000, "duration": 1_300_000}
    assert '"color": [0.0, 1.0, 0.0]' in material["content"]
    assert "shadow_blur_px is not supported by CapCut export" in result.capcut_compatibility_warnings


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


def test_real_capcut_draft_materializes_sfx_audio_track(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="SFX CapCut Draft Project")
    narration_path = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(narration_path)])
    narration_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_path)
    sfx_path = tmp_path / "impact.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=1", str(sfx_path)])
    sfx_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.SFX, source_path=sfx_path)

    draft_path = PyCapCutRealExportAdapter(store=store).export_timeline(
        project_id=project.project_id,
        timeline={
            "narration_source_uri": narration_asset.storage_uri,
            "tracks": [
                {"track_type": "narration", "clips": [{"asset_uri": f"local://projects/{project.project_id}/segments/seg_001", "start_sec": 0.0, "end_sec": 2.0}]},
                {"track_type": "sfx", "clips": [{"asset_uri": f"local://projects/{project.project_id}/assets/{sfx_asset.asset_id}", "start_sec": 1.0, "end_sec": 2.0}]},
            ],
            "export_overlays": [],
        },
        drafts_root=tmp_path / "drafts",
        draft_name="sfx-draft",
    )

    content = json.loads((draft_path / "draft_content.json").read_text(encoding="utf-8"))
    stored_sfx_path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=sfx_asset.storage_uri)
    assert any(Path(material["path"]) == stored_sfx_path for material in content["materials"]["audios"])


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_real_capcut_draft_preserves_broll_trim_crop_loop_pad_and_audio_controls(tmp_path: Path) -> None:
    """The editable draft must carry the same controls as the final renderer."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut Media Control Contract")
    narration_path = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(narration_path)])
    narration_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_path)
    broll_path = tmp_path / "portrait_broll.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=240x320:rate=15", str(broll_path)])
    broll_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_path)
    bgm_path = tmp_path / "bgm.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=4", str(bgm_path)])
    bgm_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BGM, source_path=bgm_path)

    result = PyCapCutRealExportAdapter(store=store, video_width=320, video_height=240).export_timeline(
        project_id=project.project_id,
        timeline={
            "narration_source_uri": narration_asset.storage_uri,
            "tracks": [
                {"track_type": "narration", "clips": [{"asset_uri": f"local://projects/{project.project_id}/segments/seg_001", "start_sec": 0.0, "end_sec": 4.0}]},
                {"track_type": "broll", "clips": [{"asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}", "start_sec": 0.0, "end_sec": 4.0, "media_controls": {"fit": "crop", "loop": False, "pad": True, "trim_start_sec": 0.2}}]},
                {"track_type": "bgm", "clips": [{"asset_uri": f"local://projects/{project.project_id}/assets/{bgm_asset.asset_id}", "start_sec": 0.0, "end_sec": 4.0, "media_controls": {"gain_db": -6, "fade_in_sec": 0.5, "fade_out_sec": 0.5, "ducking": True}}]},
            ],
        },
        drafts_root=tmp_path / "drafts",
        draft_name="media-control-contract",
        editing_session={"caption_style": {}, "segments": []},
    )

    content = json.loads((result.draft_path / "draft_content.json").read_text(encoding="utf-8"))
    tracks = {track["name"]: track["segments"] for track in content["tracks"]}
    broll_segments = tracks["broll"]
    assert sum(segment["target_timerange"]["duration"] for segment in broll_segments) == 4_000_000
    assert broll_segments[0]["source_timerange"]["start"] == 200_000
    broll_material = next(material for material in content["materials"]["videos"] if material["path"].endswith("portrait_broll.mp4"))
    assert broll_material["crop"]["upper_left_y"] > 0
    assert any(Path(material["path"]).name.startswith("videobox_black_pad_") for material in content["materials"]["videos"])
    assert tracks["bgm"][0]["volume"] == pytest.approx(0.25 * 10 ** (-6 / 20))
    assert tracks["bgm"][0]["extra_material_refs"]
    assert "ducking is not natively supported by CapCut draft export; apply it in CapCut after import" in result.capcut_compatibility_warnings
