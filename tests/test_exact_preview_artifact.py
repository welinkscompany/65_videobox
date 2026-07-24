from __future__ import annotations

import os
import sqlite3
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.exact_preview import ExactPreviewRequest, fingerprint_exact_preview
from videobox_core_engine.ffmpeg_final_renderer import FinalRenderError, FfmpegFinalRenderer
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.output_source_verifier import OutputSourceStaleError
from videobox_storage.local_project_store import LocalProjectStore
from videobox_domain_models.assets import AssetType


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


def test_exact_proxy_and_final_commands_share_the_same_composition_plan_and_caption_input(tmp_path: Path) -> None:
    """A proxy must not silently rebuild a different composition authority."""
    plan = CompositionPlan.from_timeline(
        timeline=_timeline(),
        captions=[{"segment_id": "caption-1", "start_sec": 0, "end_sec": 2, "caption_text": "canonical"}],
    )
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))

    final = renderer.build_final_render_inputs(composition_plan=plan)
    proxy = renderer.build_exact_preview_inputs(composition_plan=plan.for_range(start_sec=0, end_sec=2))

    assert final.composition_plan is plan
    assert final.captions is plan.captions
    assert proxy.captions[0].text == "canonical"
    assert proxy.composition_plan.captions is proxy.captions


def test_exact_proxy_uses_timeline_context_only_for_source_resolution_after_plan_extraction(tmp_path: Path) -> None:
    plan = CompositionPlan.from_timeline(timeline=_timeline(), captions=[{"start_sec": 0, "end_sec": 2, "caption_text": "canonical"}])
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))
    mutated_context = _timeline()
    mutated_context["tracks"] = [{"track_type": "broll", "clips": [{"clip_id": "late", "asset_uri": "local://late", "start_sec": 0, "end_sec": 99}]}]
    hydrated = renderer._timeline_from_plan(composition_plan=plan.for_range(start_sec=0, end_sec=2), timeline_context=mutated_context)

    assert [clip["clip_id"] for track in hydrated["tracks"] for clip in track["clips"]] == ["n1"]
    assert hydrated["tracks"][0]["clips"][0]["end_sec"] == 2.0


@pytest.mark.parametrize("mutated_source", ("music", "sfx", "image"))
def test_session_selected_audio_and_image_assets_keep_immutable_identity_for_final_and_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutated_source: str,
) -> None:
    """A changed manual BGM/SFX/image must stop both composition consumers."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="session media identity")
    music, sfx, image = tmp_path / "music.wav", tmp_path / "impact.wav", tmp_path / "overlay.png"
    music.write_bytes(b"selected music")
    sfx.write_bytes(b"selected effect")
    image.write_bytes(b"selected image")
    music_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BGM, source_path=music)
    sfx_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.SFX, source_path=sfx)
    image_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.IMAGE, source_path=image)
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-media-identity",
        session_payload={"segments": [{"segment_id": "seg_001", "start_sec": 0.0, "end_sec": 1.0}], "history": []},
    )
    runner = LocalPipelineRunner(store)
    session = runner.update_editing_session_segment_music_override(
        project_id=project.project_id, session_id=session["session_id"], segment_id="seg_001",
        asset_id=music_asset.asset_id, expected_revision=session["session_revision"],
    )
    session = runner.update_editing_session_segment_sfx_override(
        project_id=project.project_id, session_id=session["session_id"], segment_id="seg_001",
        asset_id=sfx_asset.asset_id, expected_revision=session["session_revision"],
    )
    session = runner.update_editing_session_segment_image_overlay(
        project_id=project.project_id, session_id=session["session_id"], segment_id="seg_001",
        asset_id=image_asset.asset_id, text="selected image", expected_revision=session["session_revision"],
    )
    segment = session["segments"][0]
    assert segment["music_override"]["expected_content_sha256"]
    assert segment["sfx_override"]["expected_content_sha256"]
    assert segment["visual_overlays"][0]["expected_content_sha256"]

    materialized = __import__("videobox_core_engine.composition_plan", fromlist=["materialize_editing_session_timeline"]).materialize_editing_session_timeline(
        timeline={"project_id": project.project_id, "tracks": []}, editing_session=session, project_id=project.project_id,
    )
    plan = CompositionPlan.from_timeline(timeline=materialized)
    selected_assets = {"music": music_asset, "sfx": sfx_asset, "image": image_asset}
    store.resolve_storage_uri(
        project_id=project.project_id, storage_uri=selected_assets[mutated_source].storage_uri,
    ).write_bytes(f"mutated {mutated_source}".encode())
    monkeypatch.setattr(FfmpegFinalRenderer, "_run", lambda _self, _command: pytest.fail("ffmpeg must not start for stale media"))
    renderer = FfmpegFinalRenderer(store=store)

    with pytest.raises(OutputSourceStaleError, match="stale_output_asset: content SHA-256 changed"):
        renderer.render_timeline_to_mp4(project_id=project.project_id, timeline=materialized, output_path=tmp_path / "final.mp4", composition_plan=plan)
    with pytest.raises(OutputSourceStaleError, match="stale_output_asset: content SHA-256 changed"):
        renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan, timeline_context=materialized, output_path=tmp_path / "proxy.mp4", subtitle_ass_path=None)


@pytest.mark.parametrize(
    ("asset_type", "field", "update_method"),
    [
        (AssetType.BGM, "music_override", "update_editing_session_segment_music_override"),
        (AssetType.SFX, "sfx_override", "update_editing_session_segment_sfx_override"),
    ],
)
def test_control_only_audio_update_preserves_identity_and_rejects_changed_registered_bytes(
    tmp_path: Path,
    asset_type: AssetType,
    field: str,
    update_method: str,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name=f"{asset_type.value} control identity")
    source = tmp_path / f"{asset_type.value}.wav"
    source.write_bytes(b"approved audio")
    asset = store.register_asset(project_id=project.project_id, asset_type=asset_type, source_path=source)
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-audio-control",
        session_payload={"segments": [{"segment_id": "seg_001", "start_sec": 0.0, "end_sec": 4.0}], "history": []},
    )
    runner = LocalPipelineRunner(store)
    update = getattr(runner, update_method)
    selected = update(
        project_id=project.project_id,
        session_id=session["session_id"],
        segment_id="seg_001",
        asset_id=asset.asset_id,
        expected_revision=session["session_revision"],
    )
    approved_identity = {
        key: selected["segments"][0][field][key]
        for key in ("asset_uri", "expected_content_sha256", "media_revision")
    }

    controlled = update(
        project_id=project.project_id,
        session_id=session["session_id"],
        segment_id="seg_001",
        asset_id=asset.asset_id,
        media_controls={"fade_in_sec": 0.25, "fade_out_sec": 0.5},
        expected_revision=selected["session_revision"],
    )

    assert {
        key: controlled["segments"][0][field][key]
        for key in approved_identity
    } == approved_identity
    store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri).write_bytes(b"changed after approval")

    with pytest.raises(OutputSourceStaleError, match="stale_output_asset: content SHA-256 changed"):
        update(
            project_id=project.project_id,
            session_id=session["session_id"],
            segment_id="seg_001",
            asset_id=asset.asset_id,
            media_controls={"fade_in_sec": 0.75},
            expected_revision=controlled["session_revision"],
        )
    persisted = store.get_editing_session(project_id=project.project_id, session_id=session["session_id"])
    assert persisted["session_revision"] == controlled["session_revision"]
    assert persisted["segments"][0][field]["expected_content_sha256"] == approved_identity["expected_content_sha256"]


def test_plan_renderer_explicitly_preserves_gaps_and_later_broll_wins_overlap(tmp_path: Path) -> None:
    plan = CompositionPlan.from_timeline(timeline={
        "output": {"width": 1280, "height": 720},
        "tracks": [{"track_type": "broll", "clips": [
            {"clip_id": "first", "asset_uri": "local://first", "start_sec": 2, "end_sec": 5},
            {"clip_id": "later", "asset_uri": "local://later", "start_sec": 3, "end_sec": 4},
        ]}],
    })
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))

    graph = renderer.build_plan_filter_graph(composition_plan=plan, source_indices={"first": 1, "later": 2})

    assert "color=c=black:s=1280x720" in graph and ":d=5.0" in graph
    assert "setpts=PTS+2.0/TB" in graph
    assert "setpts=PTS+3.0/TB" in graph
    assert graph.index("[v_first]") < graph.index("[v_later]")
    assert "OVERLAP_POLICY_LATER_BROLL_WINS" not in graph


def test_plan_renderer_places_resolved_export_overlay_from_the_same_plan(tmp_path: Path) -> None:
    plan = CompositionPlan.from_timeline(timeline={
        "output": {"width": 1280, "height": 720},
        "tracks": [],
        "export_overlays": [{"overlay_type": "image_overlay", "asset_uri": "local://overlay", "start_sec": 1, "end_sec": 2}],
    })
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))

    graph = renderer.build_plan_filter_graph(composition_plan=plan, source_indices={}, export_overlay_indices={0: 3})

    assert "[3:v]trim=duration=1.0" in graph
    assert "setpts=PTS+1.0/TB" in graph


def test_plan_renderer_draws_assetless_export_text_overlay_from_canonical_plan(tmp_path: Path) -> None:
    plan = CompositionPlan.from_timeline(timeline={
        "output": {"width": 1280, "height": 720}, "tracks": [],
        "export_overlays": [{"title": "O'Brien: safe", "start_sec": 1, "end_sec": 2}],
    })
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))

    graph = renderer.build_plan_filter_graph(composition_plan=plan, source_indices={})

    assert "drawtext=" in graph
    assert "O\\'Brien\\: safe" in graph
    assert "between(t,1.0,2.0)" in graph


def test_plan_renderer_fails_closed_when_track_overlay_source_cannot_be_resolved(tmp_path: Path) -> None:
    plan = CompositionPlan.from_timeline(timeline={
        "output": {"duration_sec": 1},
        "tracks": [{"track_type": "overlay", "clips": [{"clip_id": "overlay-1", "asset_uri": "local://overlay", "start_sec": 0, "end_sec": 1}]}],
    })
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))

    with pytest.raises(FinalRenderError, match="(?i)resolve media asset"):
        renderer.render_exact_preview_to_mp4(project_id="missing", composition_plan=plan, timeline_context={}, output_path=tmp_path / "out.mp4", subtitle_ass_path=None)


def test_plan_audio_graph_preserves_broll_and_music_controls(tmp_path: Path) -> None:
    plan = CompositionPlan.from_timeline(timeline={
        "output": {"width": 320, "height": 240},
        "tracks": [
            {"track_type": "broll", "clips": [{"clip_id": "b", "asset_uri": "local://b", "start_sec": 0, "end_sec": 2, "media_controls": {"loop": False, "pad": True, "preserve_source_audio": True}}]},
            {"track_type": "bgm", "clips": [{"clip_id": "m", "asset_uri": "local://m", "start_sec": 0, "end_sec": 2, "media_controls": {"gain_db": -9, "fade_in_sec": 0.2, "fade_out_sec": 0.3, "ducking": True}}]},
            {"track_type": "sfx", "clips": [{"clip_id": "s", "asset_uri": "local://s", "start_sec": 1, "end_sec": 2, "media_controls": {"gain_db": 3, "fade_in_sec": 0.1, "fade_out_sec": 0.2}}]},
        ],
    })
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))

    graph = renderer.build_plan_audio_filter_graph(composition_plan=plan, source_indices={"b": 0, "m": 1, "s": 2})

    assert "volume=-9.0dB" in graph and "afade=t=in:st=0:d=0.2" in graph
    assert "sidechaincompress" in graph
    assert "volume=3.0dB" in graph and "adelay=1000|1000" in graph


def test_plan_audio_ducks_bgm_against_the_mixed_full_narration_track(tmp_path: Path) -> None:
    plan = CompositionPlan.from_timeline(timeline={"tracks": [
        {"track_type": "narration", "clips": [{"clip_id": "n1", "asset_uri": "local://n1", "start_sec": 0, "end_sec": 1}, {"clip_id": "n2", "asset_uri": "local://n2", "start_sec": 1, "end_sec": 2}]},
        {"track_type": "bgm", "clips": [{"clip_id": "bgm", "asset_uri": "local://bgm", "start_sec": 0, "end_sec": 2, "media_controls": {"ducking": True}}]},
    ]})
    graph = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path)).build_plan_audio_filter_graph(composition_plan=plan, source_indices={"n1": 0, "n2": 1, "bgm": 2})

    assert "[a_n1][a_n2]amix=inputs=2:duration=longest[narration_mix]" in graph
    assert "[narration_mix]asplit=2[narration_final][narration_sidechain]" in graph
    assert "[a_bgm][narration_sidechain]sidechaincompress" in graph


def test_plan_audio_ducking_splits_the_single_narration_mix_before_final_mix(tmp_path: Path) -> None:
    plan = CompositionPlan.from_timeline(timeline={"tracks": [
        {"track_type": "narration", "clips": [
            {"clip_id": "n1", "asset_uri": "local://n1", "start_sec": 0, "end_sec": 1},
            {"clip_id": "n2", "asset_uri": "local://n2", "start_sec": 1, "end_sec": 2},
        ]},
        {"track_type": "bgm", "clips": [
            {"clip_id": "bgm", "asset_uri": "local://bgm", "start_sec": 0, "end_sec": 2, "media_controls": {"ducking": True}},
        ]},
    ]})

    graph = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path)).build_plan_audio_filter_graph(
        composition_plan=plan, source_indices={"n1": 0, "n2": 1, "bgm": 2}
    )

    assert "[a_n1][a_n2]amix=inputs=2:duration=longest[narration_mix]" in graph
    assert "[narration_mix]asplit=2[narration_final][narration_sidechain]" in graph
    assert "[a_bgm][narration_sidechain]sidechaincompress=threshold=0.05:ratio=8[duck_bgm]" in graph
    assert "[narration_final][duck_bgm]amix=inputs=2:duration=longest" in graph


def test_plan_broll_pad_uses_legacy_black_tpad_not_frame_clone(tmp_path: Path) -> None:
    plan = CompositionPlan.from_timeline(timeline={"tracks": [{"track_type": "broll", "clips": [{"clip_id": "b", "asset_uri": "local://b", "start_sec": 0, "end_sec": 2, "media_controls": {"loop": False, "pad": True}}]}]})
    graph = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path)).build_plan_filter_graph(composition_plan=plan, source_indices={"b": 0})

    assert "tpad=stop_mode=add" in graph
    assert "stop_mode=clone" not in graph


def test_plan_renderer_never_silently_drops_legacy_subtitle_file_without_ass(tmp_path: Path) -> None:
    plan = CompositionPlan.from_timeline(timeline={"tracks": [{"track_type": "broll", "clips": [{"clip_id": "b", "asset_uri": "local://b", "start_sec": 0, "end_sec": 1}]}]})
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))
    subtitle = tmp_path / "legacy.srt"; subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\ncaption\n", encoding="utf-8")

    ass = renderer.convert_legacy_subtitle_to_ass(subtitle_file_path=subtitle, output_dir=tmp_path)
    assert ass.suffix == ".ass" and "Dialogue:" in ass.read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fixture required")
def test_legacy_generated_ass_is_removed_when_canonical_render_fails(tmp_path: Path) -> None:
    class _FailAfterConversion(FfmpegFinalRenderer):
        def _run(self, command):  # type: ignore[no-untyped-def]
            if "-f" in command and command[command.index("-f") + 1] == "ass":
                return super()._run(command)
            raise FinalRenderError("forced final render failure")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="legacy subtitle cleanup")
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-pix_fmt", "yuv420p", str(source)], check=True, capture_output=True)
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    plan = CompositionPlan.from_timeline(timeline={"tracks": [{"track_type": "broll", "clips": [{"clip_id": "b", "asset_id": asset.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{asset.asset_id}", "start_sec": 0, "end_sec": 1}]}]})
    srt = tmp_path / "legacy.srt"; srt.write_text("1\n00:00:00,000 --> 00:00:01,000\ncaption\n", encoding="utf-8")

    with pytest.raises(FinalRenderError, match="forced"):
        _FailAfterConversion(store=store).render_timeline_to_mp4(project_id=project.project_id, timeline={}, output_path=tmp_path / "out.mp4", subtitle_file_path=srt, composition_plan=plan)
    assert not list(tmp_path.glob(".legacy_subtitle_*.ass"))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fixture required")
def test_plan_renderer_real_fixture_preserves_leading_gap_and_later_overlap(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="plan placement")
    red, blue, audio = tmp_path / "red.mp4", tmp_path / "blue.mp4", tmp_path / "audio.wav"
    for color, target in (("red", red), ("blue", blue)):
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d=3", "-pix_fmt", "yuv420p", str(target)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=5", str(audio)], check=True, capture_output=True)
    red_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=red)
    blue_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=blue)
    audio_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=audio)
    timeline = {"output": {"width": 320, "height": 240}, "tracks": [
        {"track_type": "narration", "clips": [{"clip_id": "n", "asset_id": audio_asset.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{audio_asset.asset_id}", "start_sec": 0, "end_sec": 5}]},
        {"track_type": "broll", "clips": [
            {"clip_id": "red", "asset_id": red_asset.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{red_asset.asset_id}", "start_sec": 2, "end_sec": 5},
            {"clip_id": "blue", "asset_id": blue_asset.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{blue_asset.asset_id}", "start_sec": 3, "end_sec": 4},
        ]},
    ]}
    plan = CompositionPlan.from_timeline(timeline=timeline)
    output = tmp_path / "placement.mp4"
    FfmpegFinalRenderer(store=store, video_width=320, video_height=240).render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan, timeline_context=timeline, output_path=output, subtitle_ass_path=None)

    def pixel_at(seconds: float) -> tuple[int, int, int]:
        frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(seconds), "-i", str(output), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
        return tuple(frame[:3])

    assert pixel_at(0.5) == (0, 0, 0)
    assert pixel_at(2.5)[0] > 200 and pixel_at(2.5)[2] < 30
    assert pixel_at(3.5)[2] > 200 and pixel_at(3.5)[0] < 30


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fixture required")
def test_plan_renderer_composites_track_overlay_only_in_window_and_shifts_selected_range(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="track overlay plan")
    base, overlay, audio = tmp_path / "base.mp4", tmp_path / "overlay.png", tmp_path / "audio.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2", "-pix_fmt", "yuv420p", str(base)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-frames:v", "1", str(overlay)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=2", str(audio)], check=True, capture_output=True)
    base_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=base)
    overlay_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=overlay)
    audio_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=audio)
    timeline = {"output": {"width": 320, "height": 240}, "tracks": [
        {"track_type": "narration", "clips": [{"clip_id": "n", "asset_id": audio_asset.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{audio_asset.asset_id}", "start_sec": 0, "end_sec": 2}]},
        {"track_type": "broll", "clips": [{"clip_id": "b", "asset_id": base_asset.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{base_asset.asset_id}", "start_sec": 0, "end_sec": 2}]},
        {"track_type": "overlay", "clips": [{"clip_id": "o", "asset_id": overlay_asset.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{overlay_asset.asset_id}", "start_sec": 0.5, "end_sec": 1.5}]},
    ]}
    plan = CompositionPlan.from_timeline(timeline=timeline)
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240)
    full, selected = tmp_path / "overlay-full.mp4", tmp_path / "overlay-selected.mp4"
    renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan, timeline_context=timeline, output_path=full, subtitle_ass_path=None)
    renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan.for_range(start_sec=0.5, end_sec=1.5), timeline_context=timeline, output_path=selected, subtitle_ass_path=None)

    def pixel(path: Path, seconds: float) -> tuple[int, int, int]:
        frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(seconds), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
        return tuple(frame[:3])

    assert pixel(full, 0.25)[2] > 200
    assert pixel(full, 1.0)[0] > 200
    assert pixel(full, 1.75)[2] > 200
    assert pixel(selected, 0.25)[0] > 200


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg fixture required")
def test_plan_renderer_composites_local_video_track_overlay(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="video track overlay")
    base, overlay = tmp_path / "base.mp4", tmp_path / "overlay.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2", "-pix_fmt", "yuv420p", str(base)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-pix_fmt", "yuv420p", str(overlay)], check=True, capture_output=True)
    base_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=base)
    overlay_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=overlay)
    timeline = {"output": {"width": 320, "height": 240}, "tracks": [
        {"track_type": "broll", "clips": [{"clip_id": "b", "asset_id": base_asset.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{base_asset.asset_id}", "start_sec": 0, "end_sec": 2}]},
        {"track_type": "overlay", "clips": [{"clip_id": "o", "asset_id": overlay_asset.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{overlay_asset.asset_id}", "start_sec": 0.5, "end_sec": 1.5}]},
    ]}
    output = tmp_path / "video-overlay.mp4"

    FfmpegFinalRenderer(store=store, video_width=320, video_height=240).render_exact_preview_to_mp4(
        project_id=project.project_id, composition_plan=CompositionPlan.from_timeline(timeline=timeline),
        timeline_context=timeline, output_path=output, subtitle_ass_path=None,
    )

    frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1", "-i", str(output), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
    assert frame[0] > 200 and frame[2] < 30


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


def test_exact_preview_publish_staging_name_is_bounded_for_long_windows_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview bounded staging")
    session = _session(store, project.project_id)
    record = store.begin_exact_preview(
        project_id=project.project_id,
        request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1),
        fingerprint="sha256:bounded-stage",
    )
    assert store.claim_exact_preview(
        project_id=project.project_id,
        generation_id=record["generation_id"],
        owner_token="worker",
    )
    worker_output = tmp_path / "worker.mp4"
    worker_output.write_bytes(b"proxy")
    original_copyfile = shutil.copyfile
    staging_names: list[str] = []

    def bounded_copyfile(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> str:
        staging_names.append(Path(destination).name)
        return str(original_copyfile(source, destination))

    monkeypatch.setattr("videobox_storage.local_project_store.shutil.copyfile", bounded_copyfile)

    assert store.finish_exact_preview(
        project_id=project.project_id,
        generation_id=record["generation_id"],
        fingerprint="sha256:bounded-stage",
        artifact_path=worker_output,
        owner_token="worker",
    )
    assert staging_names and len(staging_names[0]) <= 32


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


def test_fresh_pipeline_request_recovers_bounded_stale_running_claim_before_cache_hit(tmp_path: Path) -> None:
    from videobox_core_engine.local_pipeline import LocalPipelineRunner

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview restart recovery")
    timeline = store.save_timeline_run(project_id=project.project_id, output_mode="review", source_session_revision=1, timeline_payload={"output": {"duration_sec": 1}, "tracks": []})
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": [{"segment_id": "s", "caption_text": "caption", "start_sec": 0, "end_sec": 1}]})
    first_runner = LocalPipelineRunner(store)
    first = first_runner.start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=first["generation_id"], owner_token="crashed-worker")
    connection = sqlite3.connect(store.database_path(project.project_id))
    try:
        connection.execute("UPDATE exact_preview_renders SET claimed_at = '2000-01-01T00:00:00+00:00' WHERE generation_id = ?", (first["generation_id"],))
        connection.commit()
    finally:
        connection.close()

    restarted = LocalPipelineRunner(store).start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)

    assert restarted["generation_id"] != first["generation_id"]
    assert restarted["state"] == "pending"
    assert store.get_exact_preview(project_id=project.project_id, generation_id=first["generation_id"])["state"] == "failed"


def test_pipeline_start_prunes_bounded_stale_and_orphan_previews_without_deleting_current_generation(tmp_path: Path) -> None:
    from videobox_core_engine.local_pipeline import LocalPipelineRunner

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview lifecycle cleanup")
    timeline = store.save_timeline_run(project_id=project.project_id, output_mode="review", source_session_revision=1, timeline_payload={"output": {"duration_sec": 1}, "tracks": []})
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
    request = ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1)
    stale_generations: list[str] = []
    for ordinal in range(6):
        stale = store.begin_exact_preview(project_id=project.project_id, request=request, fingerprint=f"sha256:stale-{ordinal}")
        assert store.claim_exact_preview(project_id=project.project_id, generation_id=stale["generation_id"], owner_token=f"stale-{ordinal}")
        assert store.fail_exact_preview(project_id=project.project_id, generation_id=stale["generation_id"], owner_token=f"stale-{ordinal}", error_message="stale")
        stale_generations.append(str(stale["generation_id"]))
    preview_root = store.project_root(project.project_id) / "derived" / "exact_previews"
    preview_root.mkdir(parents=True)
    orphan = preview_root / "exact_preview_crashed.mp4"
    orphan.write_bytes(b"orphan")
    os.utime(orphan, (0, 0))

    runner = LocalPipelineRunner(store)
    current = runner.start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)

    assert current["state"] == "pending"
    assert not orphan.exists()
    assert sum(
        1
        for generation_id in stale_generations
        if _exact_preview_exists(store, project.project_id, generation_id)
    ) == 5
    current_publish_window = preview_root / f"{current['generation_id']}.mp4"
    current_publish_window.write_bytes(b"active")
    os.utime(current_publish_window, (0, 0))

    assert runner.start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)["generation_id"] == current["generation_id"]
    assert current_publish_window.exists()


def test_pipeline_start_ignores_best_effort_cleanup_failure_after_invoking_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from videobox_core_engine.local_pipeline import LocalPipelineRunner

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview cleanup failure")
    timeline = store.save_timeline_run(project_id=project.project_id, output_mode="review", source_session_revision=1, timeline_payload={"output": {"duration_sec": 1}, "tracks": []})
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
    calls = 0

    def _raise_cleanup(*, project_id: str, **_ignored: object) -> int:
        nonlocal calls
        calls += 1
        raise OSError("cleanup transient failure")

    monkeypatch.setattr(store, "cleanup_exact_preview_artifacts", _raise_cleanup)

    record = LocalPipelineRunner(store).start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)

    assert calls == 1
    assert record["state"] == "pending"


def _exact_preview_exists(store: LocalProjectStore, project_id: str, generation_id: str) -> bool:
    try:
        store.get_exact_preview(project_id=project_id, generation_id=generation_id)
    except KeyError:
        return False
    return True


def test_exact_preview_worker_failure_is_durably_recorded(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview worker failure")
    session = _session(store, project.project_id)
    record = store.begin_exact_preview(
        project_id=project.project_id,
        request=ExactPreviewRequest(session_id=str(session["session_id"]), expected_revision=1),
        fingerprint="sha256:failed",
    )
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=record["generation_id"], owner_token="worker")
    assert store.fail_exact_preview(
        project_id=project.project_id, generation_id=record["generation_id"], owner_token="worker", error_message="missing source"
    )
    assert store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])["state"] == "failed"


def test_exact_preview_missing_source_becomes_a_recoverable_failed_generation(tmp_path: Path) -> None:
    from videobox_core_engine.local_pipeline import LocalPipelineRunner

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="preview missing source")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={"output": {"duration_sec": 2}, "tracks": [
            {"track_type": "narration", "clips": [{"clip_id": "missing-narration", "asset_id": "missing-asset", "asset_uri": f"local://projects/{project.project_id}/assets/missing-asset", "start_sec": 0, "end_sec": 2}]},
            {"track_type": "broll", "clips": [{"clip_id": "missing", "asset_id": "missing-asset", "asset_uri": f"local://projects/{project.project_id}/assets/missing-asset", "start_sec": 0, "end_sec": 2}]},
        ]},
    )
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
    pipeline = LocalPipelineRunner(store)

    record = pipeline.start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)
    pipeline.run_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])

    failed = store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])
    assert failed["state"] == "failed"
    assert "missing" in str(failed["error_message"]).lower()


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg fixture required")
def test_exact_proxy_full_and_selected_range_are_h264_aac_faststart_with_burned_ass_only(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="exact preview ffmpeg")
    video_source, audio_source = tmp_path / "source.mp4", tmp_path / "source.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=navy:s=1280x720:d=2", "-pix_fmt", "yuv420p", str(video_source)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "pcm_s16le", str(audio_source)], check=True, capture_output=True)
    video = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video_source)
    audio = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=audio_source)
    timeline = {
        "output": {"width": 1280, "height": 720, "fps_num": 30000, "fps_den": 1001, "sample_aspect_ratio": "4:3", "rotation": 0},
        "tracks": [
            {"track_type": "narration", "clips": [{"clip_id": "n", "asset_id": audio.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{audio.asset_id}", "start_sec": 0, "end_sec": 2}]},
            {"track_type": "broll", "clips": [{"clip_id": "b", "asset_id": video.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{video.asset_id}", "start_sec": 0, "end_sec": 2, "media_controls": {"fit": "fit"}}]},
        ],
        "export_overlays": [{"title": "Exact preview", "start_sec": 0.2, "end_sec": 1.8}],
    }
    plan = CompositionPlan.from_timeline(timeline=timeline, captions=[{"start_sec": 0, "end_sec": 2, "caption_text": "burned"}])
    ass = tmp_path / "captions.ass"
    ass.write_text("[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,Arial,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,0,0,64,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\nDialogue: 0,0:00:00.20,0:00:01.80,Default,,0,0,0,,BURNED CAPTION\n", encoding="utf-8")
    renderer = FfmpegFinalRenderer(store=store)
    full, selected, baseline, selected_baseline = tmp_path / "full.mp4", tmp_path / "selected.mp4", tmp_path / "baseline.mp4", tmp_path / "selected-baseline.mp4"
    renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan, timeline_context=timeline, output_path=full, subtitle_ass_path=ass)
    selected_ass = tmp_path / "selected-captions.ass"
    selected_ass.write_text(ass.read_text(encoding="utf-8").replace("0:00:00.20,0:00:01.80", "0:00:00.00,0:00:01.00"), encoding="utf-8")
    renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan.for_range(start_sec=0.5, end_sec=1.5), timeline_context=timeline, output_path=selected, subtitle_ass_path=selected_ass)
    renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan.for_range(start_sec=0.5, end_sec=1.5), timeline_context=timeline, output_path=selected_baseline, subtitle_ass_path=None)
    renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan, timeline_context=timeline, output_path=baseline, subtitle_ass_path=None)
    legacy_srt = tmp_path / "legacy.srt"
    legacy_srt.write_text("1\n00:00:00,200 --> 00:00:01,800\nLEGACY CAPTION\n", encoding="utf-8")
    sessionless = tmp_path / "sessionless-final.mp4"
    renderer.render_timeline_to_mp4(project_id=project.project_id, timeline=timeline, output_path=sessionless, subtitle_file_path=legacy_srt, composition_plan=plan)

    for output, expected_duration in ((full, 2.0), (selected, 1.0)):
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)], check=True, capture_output=True, text=True)
        body = json.loads(probe.stdout)
        assert {stream["codec_type"] for stream in body["streams"]} == {"video", "audio"}
        assert next(stream for stream in body["streams"] if stream["codec_type"] == "video")["codec_name"] == "h264"
        assert next(stream for stream in body["streams"] if stream["codec_type"] == "video")["sample_aspect_ratio"] == "4:3"
        assert next(stream for stream in body["streams"] if stream["codec_type"] == "video")["avg_frame_rate"] == "30000/1001"
        assert next(stream for stream in body["streams"] if stream["codec_type"] == "audio")["codec_name"] == "aac"
        assert abs(float(body["format"]["duration"]) - expected_duration) < 0.15
        assert abs(float(body["format"].get("start_time") or 0.0)) < 0.001
        packets = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_packets", "-of", "json", str(output)], check=True, capture_output=True, text=True)
        assert abs(float(json.loads(packets.stdout)["packets"][0]["pts_time"])) < 0.001
        data = output.read_bytes()
        assert data.index(b"moov") < data.index(b"mdat")

    def frame_at(path: Path, seconds: float) -> bytes:
        return subprocess.run(["ffmpeg", "-v", "error", "-ss", str(seconds), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout

    assert frame_at(full, 1.0) != frame_at(baseline, 1.0)
    assert frame_at(selected, 0.05) != frame_at(selected_baseline, 0.05)
    sessionless_streams = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(sessionless)], check=True, capture_output=True, text=True).stdout)["streams"]
    assert {stream["codec_type"] for stream in sessionless_streams} == {"video", "audio"}
    assert frame_at(sessionless, 1.0) != frame_at(baseline, 1.0)


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
