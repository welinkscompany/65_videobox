import { describe, expect, it } from "vitest";

import { VideoBoxEditorAdapter, type EditorPlaybackManifest } from "./editorViewModel";
import manifestJson from "./__fixtures__/manifest-742e1924-no-narration.json";
import { captionOwnerSegmentId, playbackSelectionSpans, sceneSpanBySegmentId, sceneSpans } from "./sceneSpans";
import { frameDurationSec, resolvePlaybackSelection } from "./transcript/playbackNavigation";

const view = new VideoBoxEditorAdapter(manifestJson as unknown as EditorPlaybackManifest).viewModel;
const frame = frameDurationSec(view.fps);

describe("장면 구간 (742e1924 실제 모양: 내레이션 없음, 낡은 자막 id)", () => {
  it("자막의 장면은 소유 id다", () => {
    const owners = view.captions.map(captionOwnerSegmentId);
    expect(new Set(owners).size).toBe(15);
    expect(captionOwnerSegmentId({ segmentId: "old", owningSegmentId: "new" })).toBe("new");
    expect(captionOwnerSegmentId({ segmentId: "only" })).toBe("only");
  });

  it("장면 구간은 장면마다 하나이고 자막 구간을 따른다", () => {
    const spans = sceneSpans(view);
    expect(spans).toHaveLength(15);
    expect(new Set(spans.map((span) => span.segmentId)).size).toBe(15);
    const fifth = view.captions[4];
    expect(sceneSpanBySegmentId(view, fifth.owningSegmentId!)).toEqual({ segmentId: fifth.owningSegmentId, startSec: fifth.startSec, endSec: fifth.endSec });
  });

  it("모르는 id는 구간이 없다", () => {
    expect(sceneSpanBySegmentId(view, "timeline_001:no-such-scene")).toBeUndefined();
  });

  it("각 장면을 눌렀을 때(누름 + 시작 시각) 그 장면이 고정된다 -- 경계 직전 시각이어도", () => {
    const spans = playbackSelectionSpans(view);
    for (const caption of view.captions) {
      for (const t of [caption.startSec, Math.max(0, caption.startSec - 1e-6)]) {
        expect(resolvePlaybackSelection(spans, t, { pinnedSegmentId: caption.owningSegmentId!, frameSec: frame })).toBe(caption.owningSegmentId);
      }
    }
  });

  it("영상이 자막과 다른 시각에 놓인 장면(장면 1, 영상 90초)도 눌렀을 때 고정된다", () => {
    const sceneOne = view.captions[0].owningSegmentId!;
    const spans = playbackSelectionSpans(view);
    expect(resolvePlaybackSelection(spans, 90, { pinnedSegmentId: sceneOne, frameSec: frame })).toBe(sceneOne);
    // 고정이 없으면 90초는 그 시각을 덮는 자막 장면이 이긴다 -- 재생이 흐를 때는 시각이 판단한다.
    expect(resolvePlaybackSelection(spans, 90, { pinnedSegmentId: null, frameSec: frame })).not.toBe(sceneOne);
  });

  it("재생이 흐르면 매 시각의 자막 장면으로 넘어간다", () => {
    const spans = playbackSelectionSpans(view);
    for (const caption of view.captions.slice(1)) {
      const middle = (caption.startSec + caption.endSec) / 2;
      expect(resolvePlaybackSelection(spans, middle, { pinnedSegmentId: null, frameSec: frame })).toBe(caption.owningSegmentId);
    }
  });
});
