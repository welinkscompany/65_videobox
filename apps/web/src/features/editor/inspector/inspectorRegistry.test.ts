import { describe, expect, it } from "vitest";
import type { EditorViewModel } from "../editorViewModel";
import { projectInspectorTargets } from "./inspectorRegistry";

const view = {
  projectId: "project-1", sessionId: "session-1", timelineId: "timeline-1", timelineVersion: "v1", expectedRevision: 1, timebase: "seconds",
  fps: { num: 30, den: 1 },
  output: { width: 1080, height: 1920, sampleAspectRatio: "1:1", rotation: 0, durationSec: 10 },
  tracks: [
    { trackId: "narration", role: "narration", clips: [{ clipId: "narration-1", segmentId: "segment-unsupported", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {} }] },
    ...(["broll", "bgm", "sfx"] as const).map((role) => ({ trackId: role, role, clips: [{ clipId: `${role}-1`, segmentId: "segment-1", type: role, assetId: `asset-${role}`, assetUri: null, startSec: 0, endSec: 1, controls: {} }] })),
    {
      trackId: "overlay", role: "overlay", clips: [
        { clipId: "explanation-1", segmentId: "segment-1", type: "overlay", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "explanation_card" },
        { clipId: "image-1", segmentId: "segment-1", type: "overlay", assetId: "asset-image", assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "image_overlay" },
        { clipId: "table-1", segmentId: "segment-1", type: "overlay", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "table_overlay" },
        { clipId: "unsupported-overlay", segmentId: "segment-1", type: "overlay", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: null },
      ],
    },
  ],
  captions: [{ segmentId: "segment-1", captionId: "caption-1", text: "연결 자막", startSec: 0, endSec: 1, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0 } }],
  gaps: [], source: { status: "current" }, playback: { auditionUrls: {}, exactPreview: { status: "unavailable" } }, local: { selectedSegmentId: null, seekSec: 0 },
} satisfies EditorViewModel;

describe("projectInspectorTargets", () => {
  it("projects only the existing media and linked-caption command fields for the selected segment", () => {
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-1" });

    for (const [id, mediaKind, label] of [["broll-1", "broll", "보조 영상"], ["bgm-1", "bgm", "배경 음악"], ["sfx-1", "sfx", "효과음"]] as const) {
      expect(targets).toContainEqual({ id: `clip:${id}`, kind: "media", label, segmentId: "segment-1", mediaKind, fields: ["volume", "crop", "speed", "fadeInSec", "fadeOutSec"] });
    }
    expect(targets).toContainEqual({ id: "caption:caption-1", kind: "caption", label: "연결 자막", segmentId: "segment-1", fields: ["text", "style"] });
  });

  it("projects only the three supported overlay variants with their typed fields", () => {
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-1" });

    expect(targets).toContainEqual({ id: "overlay:explanation-1", kind: "overlay", label: "설명 카드", segmentId: "segment-1", overlayKind: "explanation-card", fields: ["title", "body", "text"] });
    expect(targets).toContainEqual({ id: "overlay:image-1", kind: "overlay", label: "이미지", segmentId: "segment-1", overlayKind: "image", fields: ["assetId", "text"] });
    expect(targets).toContainEqual({ id: "overlay:table-1", kind: "overlay", label: "표", segmentId: "segment-1", overlayKind: "table", fields: ["columns", "rows", "text"] });
    expect(targets.find((target) => target.id === "overlay:unsupported-overlay")).toBeUndefined();
  });

  it("never projects unsupported voice, effect, or independent caption timing controls", () => {
    const fields = projectInspectorTargets({ view, selectedSegmentId: "segment-1" }).flatMap((target) => target.fields);

    expect(fields).not.toEqual(expect.arrayContaining(["voice", "effect", "keyframe", "mask", "transition", "captionStartSec", "captionEndSec"]));
  });

  it("returns no targets without a selection or for an unsupported selection", () => {
    expect(projectInspectorTargets({ view, selectedSegmentId: null })).toEqual([]);
    expect(projectInspectorTargets({ view, selectedSegmentId: "segment-unsupported" })).toEqual([]);
  });
});
