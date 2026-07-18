import { describe, expect, it, vi } from "vitest";
import type { EditorCommandApi } from "./editorCommandPort";
import { createEditorCommandPort } from "./editorCommandPort";

const api = {
  splitEditingSessionSegment: vi.fn(), mergeEditingSessionSegments: vi.fn(), updateEditingSessionSegmentBounds: vi.fn(), reorderEditingSessionSegments: vi.fn(),
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
    await port.reorderNarration({ segmentIds: ["seg", "next"] });
    expect(api.splitEditingSessionSegment).toHaveBeenCalledWith("p", "s", "seg", { split_sec: 1.25, expected_revision: 7 });
    expect(api.mergeEditingSessionSegments).toHaveBeenCalledWith("p", "s", { left_segment_id: "left", right_segment_id: "right", expected_revision: 7 });
    expect(api.updateEditingSessionSegmentBounds).toHaveBeenCalledWith("p", "s", "seg", { start_sec: 0, end_sec: 2, expected_revision: 7 });
    expect(api.reorderEditingSessionSegments).toHaveBeenCalledWith("p", "s", { segment_ids: ["seg", "next"], expected_revision: 7 });
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
