import { describe, expect, it } from "vitest";

import { projectLegacySession } from "./legacySessionProjection";
import { VideoBoxEditorAdapter } from "./editorViewModel";
import type { EditorPlaybackManifest } from "../../api";

const manifest: EditorPlaybackManifest = { project_id: "project-b", session_id: "session-b", timeline_id: "timeline-b", session_revision: 7, timeline_version: "v7", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1, height: 1, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 2 }, tracks: [{ track_id: "n", track_type: "narration", clips: [{ clip_id: "n-b", segment_id: "segment-b", clip_type: "narration", asset_id: null, asset_uri: null, start_sec: 0, end_sec: 2, media_controls: {} }] }, ...(["broll", "bgm", "sfx", "overlay"] as const).map((track_type) => ({ track_id: track_type, track_type, clips: [{ clip_id: `${track_type}-b`, segment_id: "segment-b", clip_type: track_type, asset_id: `asset-${track_type}`, asset_uri: null, start_sec: 0, end_sec: 2, media_controls: { volume: 0.5 }, ...(track_type === "overlay" ? { overlay_type: "image_overlay" as const, overlay_payload: { text: "이미지" } } : {}) }] }))], captions: [{ segment_id: "segment-b", text: "B의 자막", start_sec: 0, end_sec: 2, style: { font_family: "Pretendard", font_size_px: 20, text_color: "#fff", outline_color: "#000", outline_width_px: 1, background_color: "#00000000", position_x_percent: 50, position_y_percent: 90, horizontal_align: "center", safe_area_enabled: true, shadow_blur_px: 0 } }], gap_slots: [], source_status: { status: "current" }, audition: { asset_urls: {} }, exact_preview: { status: "current" } };

describe("projectLegacySession", () => {
  it("uses only the pinned manifest identity and captions instead of a conflicting legacy session", () => {
    const session = projectLegacySession(new VideoBoxEditorAdapter(manifest).viewModel);
    expect(session).toMatchObject({ project_id: "project-b", session_id: "session-b", timeline_id: "timeline-b", session_revision: 7, segments: [{ segment_id: "segment-b", caption_text: "B의 자막", start_sec: 0, end_sec: 2 }] });
    expect(session.segments[0]).toMatchObject({
      broll_override: { asset_id: "asset-broll", media_controls: { volume: 0.5 } },
      music_override: { asset_id: "asset-bgm", media_controls: { volume: 0.5 } },
      sfx_override: { asset_id: "asset-sfx", media_controls: { volume: 0.5 } },
      visual_overlays: [{ overlay_type: "image_overlay", text: "이미지", asset_id: "asset-overlay", start_sec: 0, end_sec: 2, media_controls: { volume: 0.5 } }],
    });
  });
});
