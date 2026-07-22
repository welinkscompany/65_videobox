import { describe, expect, it } from "vitest";
import type { EditorPlaybackManifest } from "../../api";
import { VideoBoxEditorAdapter } from "./editorViewModel";

const manifest: EditorPlaybackManifest = {
  project_id: "project-1", session_id: "session-1", timeline_id: "timeline-1", session_revision: 4, timeline_version: "v4",
  timebase: "seconds", fps: { num: 30000, den: 1001 },
  output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 6 },
  tracks: [
    { track_id: "narration", track_type: "narration", clips: [{ clip_id: "n-1", segment_id: "seg-1", clip_type: "narration", asset_id: "a-n", asset_uri: "storage://x", start_sec: 0, end_sec: 3, media_controls: {} }] },
    { track_id: "broll", track_type: "broll", clips: [{ clip_id: "b-1", segment_id: "seg-1", clip_type: "broll", asset_id: "a-b", asset_uri: "storage://x", start_sec: 0, end_sec: 3, media_controls: { volume: 0.5 } }] },
  ],
  captions: [{ segment_id: "seg-1", caption_id: "caption:seg-1", placement_id: "caption:caption:seg-1", text: "안녕하세요", start_sec: 0, end_sec: 3, style: { font_family: "Pretendard", font_size_px: 28, text_color: "#fff", outline_color: "#000", outline_width_px: 1, background_color: "#00000000", position_x_percent: 50, position_y_percent: 90, horizontal_align: "center", safe_area_enabled: true, shadow_blur_px: 0 } }],
  gap_slots: [{ gap_id: "gap-1", segment_id: "seg-2", start_sec: 3, end_sec: 6, reason: "asset_required" }],
  source_status: { status: "current", source_session_id: "session-1", source_session_revision: 4 },
  audition: { asset_urls: { "a-b": "/api/projects/project-1/assets/a-b/content" } },
  exact_preview: { status: "stale", url: "/api/projects/project-1/final-renders/r1/content", source_session_id: "session-1", source_session_revision: 3 },
};

describe("VideoBoxEditorAdapter", () => {
  it("maps the authoritative manifest into typed tracks, captions, gaps, and distinct playback states", () => {
    const view = new VideoBoxEditorAdapter(manifest).viewModel;
    expect(view.timebase).toBe("seconds");
    expect(view.timelineVersion).toBe("v4");
    expect(view.output).toEqual({ width: 1080, height: 1920, sampleAspectRatio: "1:1", rotation: 0, durationSec: 6 });
    expect(view.tracks[1]).toMatchObject({ role: "broll", clips: [{ type: "broll", assetId: "a-b", assetUri: "storage://x", controls: { volume: 0.5 } }] });
    expect(view.captions[0]).toMatchObject({ segmentId: "seg-1", text: "안녕하세요" });
    expect(view.gaps).toEqual([{ gapId: "gap-1", segmentId: "seg-2", startSec: 3, endSec: 6, reason: "asset_required" }]);
    expect(view.source).toEqual({ status: "current", sourceSessionId: "session-1", sourceSessionRevision: 4 });
    expect(view.playback).toEqual({ auditionUrls: { "a-b": "/api/projects/project-1/assets/a-b/content" }, exactPreview: { status: "stale", url: "/api/projects/project-1/final-renders/r1/content", sourceSessionId: "session-1", sourceSessionRevision: 3 } });
  });

  it("preserves typed source provenance for every clip", () => {
    const richManifest: EditorPlaybackManifest = { ...manifest, tracks: [{ ...manifest.tracks[0], clips: [{ ...manifest.tracks[0].clips[0], expected_content_sha256: "sha-1", media_revision: "media-r2" }] }] };
    expect(new VideoBoxEditorAdapter(richManifest).viewModel.tracks[0].clips[0]).toMatchObject({ expectedContentSha256: "sha-1", mediaRevision: "media-r2" });
  });

  it("keeps selection and seeking as local state", () => {
    const adapter = new VideoBoxEditorAdapter(manifest);
    adapter.select("seg-1");
    adapter.seek(2.5);
    expect(adapter.viewModel.local).toEqual({ selectedSegmentId: "seg-1", seekSec: 2.5 });
  });
});

// Compile-time contract: editor views cannot reach generic trim, caption timing, or raw controls.
if (false) {
  const view = new VideoBoxEditorAdapter(manifest).viewModel;
  // @ts-expect-error generic trim is intentionally not part of the view model
  view.trim;
  // @ts-expect-error raw controls are intentionally not exposed
  view.tracks[0].clips[0].controls.unexpected;
}
