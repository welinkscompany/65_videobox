import { describe, expect, it, vi } from "vitest";
import type { EditorCommandApi } from "./editorCommandPort";
import { createEditorCommandPort } from "./editorCommandPort";

const api = {
  splitEditingSessionSegment: vi.fn(), mergeEditingSessionSegments: vi.fn(), updateEditingSessionSegmentBounds: vi.fn(), reorderEditingSessionSegments: vi.fn(), updateEditingSessionTimelinePlacements: vi.fn(),
  undoEditingSession: vi.fn(), redoEditingSession: vi.fn(), updateEditingSessionCutAction: vi.fn(),
  updateEditingSessionBroll: vi.fn(), clearEditingSessionBrollOverride: vi.fn(), updateEditingSessionMusicOverride: vi.fn(), clearEditingSessionMusicOverride: vi.fn(), updateEditingSessionSfxOverride: vi.fn(), clearEditingSessionSfxOverride: vi.fn(),
  updateEditingSessionExplanationCard: vi.fn(), removeEditingSessionExplanationCard: vi.fn(), updateEditingSessionImageOverlay: vi.fn(), removeEditingSessionImageOverlay: vi.fn(), updateEditingSessionTableOverlay: vi.fn(), removeEditingSessionTableOverlay: vi.fn(),
  updateEditingSessionCaption: vi.fn(), updateEditingSessionCaptionStyle: vi.fn(),
} satisfies EditorCommandApi;

describe("EditorCommandPort", () => {
  it("routes supported narration operations through their specific revisioned endpoints", async () => {
    const port = createEditorCommandPort({ projectId: "p", sessionId: "s", expectedRevision: 7 }, api);
    await port.splitNarration({ segmentId: "seg", splitSec: 1.25 });
    await port.mergeNarration({ leftSegmentId: "left", rightSegmentId: "right" });
    await port.setNarrationBounds({ segmentId: "seg", startSec: 0, endSec: 2 });
    await port.reorderNarration({ segmentIds: ["seg", "next"], boundsById: { seg: { startSec: 0, endSec: 1 }, next: { startSec: 1, endSec: 2 } } });
    expect(api.splitEditingSessionSegment).toHaveBeenCalledWith("p", "s", "seg", { split_sec: 1.25, expected_revision: 7 });
    expect(api.mergeEditingSessionSegments).toHaveBeenCalledWith("p", "s", { left_segment_id: "left", right_segment_id: "right", expected_revision: 7 });
    expect(api.updateEditingSessionSegmentBounds).toHaveBeenCalledWith("p", "s", "seg", { start_sec: 0, end_sec: 2, expected_revision: 7 });
    expect(api.reorderEditingSessionSegments).toHaveBeenCalledWith("p", "s", {
      segment_ids: ["seg", "next"],
      bounds_by_id: { seg: { start_sec: 0, end_sec: 1 }, next: { start_sec: 1, end_sec: 2 } },
      expected_revision: 7,
    });
  });

  it("sends the complete layout when reordering narration", async () => {
    const port = createEditorCommandPort({ projectId: "p", sessionId: "s", expectedRevision: 7 }, api);
    await port.reorderNarration({
      segmentIds: ["next", "seg"],
      boundsById: {
        next: { startSec: 0, endSec: 1.5 },
        seg: { startSec: 1.5, endSec: 3 },
      },
    });
    expect(api.reorderEditingSessionSegments).toHaveBeenCalledWith("p", "s", {
      segment_ids: ["next", "seg"],
      bounds_by_id: {
        next: { start_sec: 0, end_sec: 1.5 },
        seg: { start_sec: 1.5, end_sec: 3 },
      },
      expected_revision: 7,
    });
  });

  it("sends a revisioned timeline placement batch", async () => {
    const port = createEditorCommandPort({ projectId: "p", sessionId: "s", expectedRevision: 7 }, api);
    await port.setTimelinePlacements({ changes: [{ placementId: "caption:c-1", kind: "caption", startSec: 1, endSec: 2 }] });

    expect(api.updateEditingSessionTimelinePlacements).toHaveBeenCalledWith("p", "s", {
      expected_revision: 7,
      changes: [{ placement_id: "caption:c-1", kind: "caption", start_sec: 1, end_sec: 2 }],
    });
  });

  it("keeps B-roll, BGM, and SFX separate when applying, clearing, and updating controls", async () => {
    const port = createEditorCommandPort({ projectId: "p", sessionId: "s", expectedRevision: 7 }, api);
    await port.applyMedia({ kind: "broll", segmentId: "seg", assetId: "asset-b", controls: { volume: 0.6 } });
    await port.updateMediaControls({ kind: "bgm", segmentId: "seg", assetId: "asset-m", controls: { fadeInSec: 1 } });
    await port.clearMedia({ kind: "sfx", segmentId: "seg" });
    expect(api.updateEditingSessionBroll).toHaveBeenCalledWith("p", "s", "seg", { asset_id: "asset-b", media_controls: { volume: 0.6 }, expected_revision: 7 });
    expect(api.updateEditingSessionMusicOverride).toHaveBeenCalledWith("p", "s", "seg", { asset_id: "asset-m", media_controls: { fade_in_sec: 1 }, expected_revision: 7 });
    expect(api.clearEditingSessionSfxOverride).toHaveBeenCalledWith("p", "s", "seg", 7);
  });

  it("passes the current expected revision to undo, redo, and explicit cut actions", async () => {
    const port = createEditorCommandPort({ projectId: "p", sessionId: "s", expectedRevision: 11 }, api);

    await port.undo();
    await port.redo();
    await port.setCutAction({ segmentId: "seg-keep", cutAction: "keep" });
    await port.setCutAction({ segmentId: "seg-remove", cutAction: "remove" });

    expect(api.undoEditingSession).toHaveBeenCalledWith("p", "s", 11);
    expect(api.redoEditingSession).toHaveBeenCalledWith("p", "s", 11);
    expect(api.updateEditingSessionCutAction).toHaveBeenNthCalledWith(
      1,
      "p",
      "s",
      "seg-keep",
      { cut_action: "keep", expected_revision: 11 },
    );
    expect(api.updateEditingSessionCutAction).toHaveBeenNthCalledWith(
      2,
      "p",
      "s",
      "seg-remove",
      { cut_action: "remove", expected_revision: 11 },
    );
  });

  it("serializes authoritative BGM and SFX fade controls without replacing hidden gain or ducking", async () => {
    const port = createEditorCommandPort({ projectId: "p", sessionId: "s", expectedRevision: 7 }, api);

    await port.updateMediaControls({
      kind: "bgm",
      segmentId: "seg",
      assetId: "asset-m",
      controls: { gainDb: -7, fadeInSec: 1.25, fadeOutSec: 0.75, ducking: true },
    });
    await port.updateMediaControls({
      kind: "sfx",
      segmentId: "seg",
      assetId: "asset-s",
      controls: { gainDb: -3, fadeInSec: 0.2, fadeOutSec: 0.4, ducking: false },
    });

    expect(api.updateEditingSessionMusicOverride).toHaveBeenCalledWith("p", "s", "seg", {
      asset_id: "asset-m",
      media_controls: { gain_db: -7, fade_in_sec: 1.25, fade_out_sec: 0.75, ducking: true },
      expected_revision: 7,
    });
    expect(api.updateEditingSessionSfxOverride).toHaveBeenCalledWith("p", "s", "seg", {
      asset_id: "asset-s",
      media_controls: { gain_db: -3, fade_in_sec: 0.2, fade_out_sec: 0.4, ducking: false },
      expected_revision: 7,
    });
  });

  it("uses only supported discriminated overlays and caption endpoints", async () => {
    const port = createEditorCommandPort({ projectId: "p", sessionId: "s", expectedRevision: 7 }, api);
    await port.applyOverlay({ kind: "image", segmentId: "seg", assetId: "asset-image", text: "제품" });
    await port.clearOverlay({ kind: "table", segmentId: "seg" });
    await port.setCaptionText({ segmentId: "seg", text: "새 자막" });
    await port.setCaptionStyle({ segmentIds: ["seg"], scope: "current_caption", style: { fontFamily: "Pretendard", fontSizePx: 30, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0 } });
    expect(api.updateEditingSessionImageOverlay).toHaveBeenCalledWith("p", "s", "seg", { asset_id: "asset-image", text: "제품", expected_revision: 7 });
    expect(api.removeEditingSessionTableOverlay).toHaveBeenCalledWith("p", "s", "seg", 7);
    expect(api.updateEditingSessionCaption).toHaveBeenCalledWith("p", "s", "seg", { caption_text: "새 자막", expected_revision: 7 });
    expect(api.updateEditingSessionCaptionStyle).toHaveBeenCalledWith("p", "s", expect.objectContaining({ expected_revision: 7, segment_ids: ["seg"] }));
  });
});

if (false) {
  const port = createEditorCommandPort({ projectId: "p", sessionId: "s", expectedRevision: 1 }, api);
  // @ts-expect-error generic trim is prohibited
  port.trim({});
  // @ts-expect-error caption time resize is prohibited
  port.setCaptionBounds({});
  // @ts-expect-error unsupported overlay kind is prohibited
  port.applyOverlay({ kind: "blur", segmentId: "s" });
}
