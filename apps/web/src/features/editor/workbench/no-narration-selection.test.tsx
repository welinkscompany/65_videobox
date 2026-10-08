import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { EditorWorkbench } from "./EditorWorkbench";
import { VideoBoxEditorAdapter, type EditorPlaybackManifest } from "../editorViewModel";
import manifestJson from "../__fixtures__/manifest-742e1924-no-narration.json";

// 2026-09-12-742e1924의 실제 매니페스트(읽기 전용으로 받아 둔 것, 2026-10-09 실기 점검).
// 내레이션 줄이 없고, 자막 15개 중 13개가 낡은 segment_id `…001__split_2`를 단 채 owning_segment_id만 장면별로 다르다.
const manifest = manifestJson as unknown as EditorPlaybackManifest;
const view = new VideoBoxEditorAdapter(manifest).viewModel;
const STALE = "timeline_001:001__split_2";

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1000 } as DOMRect);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.localStorage.clear(); });

const session = {
  projectId: view.projectId, sessionId: view.sessionId, timelineId: view.timelineId, expectedRevision: view.expectedRevision,
  undoCount: 0, redoCount: 0, updatedAt: null, captionLanguage: null, translatedLanguages: [],
  segments: manifest.captions.map((caption) => ({ segmentId: caption.owning_segment_id ?? caption.segment_id, cutAction: "keep", bgm: null, sfx: null, transitionIn: null, ttsReplacement: null })),
} as const;

const range = (start: number, end: number) => `${start.toFixed(2)}–${end.toFixed(2)}초 구간`;
function clipButton(clipId: string): HTMLElement {
  const clip = screen.getAllByTestId("timeline-clip").find((item) => item.getAttribute("data-clip-id") === clipId);
  const button = clip?.querySelector('[data-native-control="timeline-clip-select"]');
  if (!button) throw new Error(`Missing selection control for ${clipId}`);
  return button as HTMLElement;
}
/** 타임라인은 보이는 창 안의 클립만 그린다 -- 전체 보기로 120초가 다 들어오게 한다. */
function fitAll(): void { fireEvent.click(screen.getByRole("button", { name: "타임라인 전체 보기" })); }
function openInspector(): void {
  if (!screen.queryByRole("complementary", { name: "세부 정보" })) fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
}
const inspectorRanges = () => within(screen.getByRole("region", { name: "편집 항목" })).queryAllByText(/초 구간$/).map((node) => node.textContent);

describe("내레이션 줄이 없는 프로젝트 (742e1924 실제 모양)", () => {
  it("실제 모양 확인 -- 자막 대부분이 낡은 id를 달고 있고 소유 id만 장면마다 다르다", () => {
    expect(view.tracks.some((track) => track.role === "narration")).toBe(false);
    expect(view.captions.filter((caption) => caption.segmentId === STALE)).toHaveLength(14);
    expect(new Set(view.captions.map((caption) => caption.owningSegmentId)).size).toBe(15);
  });

  it("영상 클립 15개를 하나씩 눌러도 오른쪽 편집 항목은 누른 장면이다", () => {
    render(<EditorWorkbench view={view} session={session as never} />);
    openInspector();
    fitAll();
    const ownerRange = new Map(view.captions.map((caption) => [caption.owningSegmentId, caption] as const));
    for (const track of view.tracks.filter((item) => item.role === "broll")) {
      for (const clip of track.clips) {
        fireEvent.click(clipButton(`broll:${clip.clipId}`));
        const caption = ownerRange.get(clip.segmentId)!;
        expect(inspectorRanges(), clip.segmentId).toContain(range(caption.startSec, caption.endSec));
      }
    }
  });

  it("캡션 줄에서 3~15번째를 눌러도 그 장면이 잡히고 장면 2가 같이 잡히지 않는다", () => {
    render(<EditorWorkbench view={view} session={session as never} />);
    openInspector();
    fitAll();
    view.captions.forEach((caption, index) => {
      if (index < 2) return;
      fireEvent.click(clipButton(caption.placementId!));
      expect(inspectorRanges(), String(index)).toContain(range(caption.startSec, caption.endSec));
      expect(inspectorRanges()).not.toContain(range(12, 24));
    });
  });

  it("캡션 5번째에서 속도를 바꾸면 그 장면(소유 id)에 대한 명령이 나간다 -- 낡은 id가 아니다", () => {
    const onSetSegmentRippleSpeed = vi.fn();
    render(<EditorWorkbench view={view} session={session as never} onSetSegmentRippleSpeed={onSetSegmentRippleSpeed} />);
    openInspector();
    const fifth = view.captions[4];
    fireEvent.click(clipButton(fifth.placementId!));
    const speed = within(screen.getByRole("region", { name: "편집 항목" })).getByRole("spinbutton", { name: "속도", exact: true });
    fireEvent.change(speed, { target: { value: "2" } });
    fireEvent.keyDown(speed, { key: "Enter" });
    expect(onSetSegmentRippleSpeed).toHaveBeenCalledTimes(1);
    expect(onSetSegmentRippleSpeed).toHaveBeenCalledWith({ segmentId: fifth.owningSegmentId, rate: 2 });
    expect(fifth.owningSegmentId).not.toBe(STALE);
  });

  it("장면을 골라 두면 자르기 단추가 열리고, 빼기는 고른 장면(소유 id)에 대한 명령이다", () => {
    const onInspectorAction = vi.fn();
    render(<EditorWorkbench view={view} session={session as never} onInspectorAction={onInspectorAction} />);
    fitAll();
    const fifth = view.captions[4];
    fireEvent.click(clipButton(fifth.placementId!));
    const drop = screen.getByRole("button", { name: /^빼기/ });
    expect(drop).not.toBeDisabled();
    fireEvent.click(drop);
    expect(onInspectorAction).toHaveBeenCalledWith(expect.objectContaining({ kind: "set-cut-action", segmentId: fifth.owningSegmentId, cutAction: "remove" }));
  });
});
