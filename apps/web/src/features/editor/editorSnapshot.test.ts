import { describe, expect, it } from "vitest";

import type { EditingSession, EditorPlaybackManifest } from "../../api";
import { joinEditorSnapshot } from "./editorSnapshot";

function manifest(overrides: Partial<EditorPlaybackManifest> = {}): EditorPlaybackManifest {
  return {
    project_id: "project-a",
    session_id: "session-a",
    timeline_id: "timeline-a",
    session_revision: 4,
    timeline_version: "v4",
    timebase: "seconds",
    fps: { num: 30, den: 1 },
    output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 2 },
    tracks: [],
    captions: [],
    gap_slots: [],
    source_status: { status: "current", source_session_id: "session-a", source_session_revision: 4 },
    audition: { asset_urls: {} },
    exact_preview: { status: "unavailable", url: null },
    ...overrides,
  };
}

function session(overrides: Partial<EditingSession> = {}): EditingSession {
  return {
    project_id: "project-a",
    session_id: "session-a",
    timeline_id: "timeline-a",
    session_revision: 4,
    segments: [{
      segment_id: "segment-a",
      caption_text: "caption",
      start_sec: 0,
      end_sec: 2,
      cut_action: "keep",
      review_required: false,
      broll_override: null,
      visual_overlays: [],
      music_override: {
        asset_id: "music-a",
        asset_uri: "local://projects/project-a/assets/music-a",
        expected_content_sha256: "a".repeat(64),
        media_revision: "music-r3",
        media_controls: { gain_db: -7, fade_in_sec: 0.25, fade_out_sec: 0.5, ducking: true },
      },
      sfx_override: {
        asset_id: "sfx-a",
        media_controls: { gain_db: -3, fade_in_sec: 0.1, fade_out_sec: 0.2, ducking: false },
      },
      tts_replacement: null,
    }],
    history: [],
    undo_count: 3,
    redo_count: 1,
    updated_at: "2026-07-23T12:34:56Z",
    ...overrides,
  };
}

describe("joinEditorSnapshot", () => {
  it("publishes one typed snapshot with authoritative session controls and history metadata", () => {
    const snapshot = joinEditorSnapshot(manifest(), session());

    expect(snapshot.view.expectedRevision).toBe(4);
    expect(snapshot.session).toEqual({
      projectId: "project-a",
      sessionId: "session-a",
      timelineId: "timeline-a",
      expectedRevision: 4,
      undoCount: 3,
      redoCount: 1,
      updatedAt: "2026-07-23T12:34:56Z",
      segments: [{
        segmentId: "segment-a",
        cutAction: "keep",
        bgm: {
          assetId: "music-a",
          assetUri: "local://projects/project-a/assets/music-a",
          expectedContentSha256: "a".repeat(64),
          mediaRevision: "music-r3",
          controls: { gainDb: -7, fadeInSec: 0.25, fadeOutSec: 0.5, ducking: true },
        },
        sfx: {
          assetId: "sfx-a",
          assetUri: null,
          expectedContentSha256: null,
          mediaRevision: null,
          controls: { gainDb: -3, fadeInSec: 0.1, fadeOutSec: 0.2, ducking: false },
        },
      }],
    });
  });

  it.each([
    ["project", manifest(), session({ project_id: "project-b" })],
    ["session", manifest(), session({ session_id: "session-b" })],
    ["timeline", manifest(), session({ timeline_id: "timeline-b" })],
    ["revision", manifest(), session({ session_revision: 3 })],
    ["missing session id", manifest(), session({ session_id: "" })],
  ])("fails closed on a %s identity mismatch", (_label, playback, editingSession) => {
    expect(() => joinEditorSnapshot(playback, editingSession)).toThrow("editor_snapshot_identity_mismatch");
  });
});
