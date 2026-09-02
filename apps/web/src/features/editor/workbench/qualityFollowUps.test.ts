import { describe, expect, it } from "vitest";
import type { EditorViewModel } from "../editorViewModel";
import { buildQualityFollowUps } from "./qualityFollowUps";

function view(overrides: Partial<EditorViewModel> = {}): EditorViewModel {
  return {
    projectId: "project-1", sessionId: "session-1", timelineId: "timeline-1", timelineVersion: "v1",
    expectedRevision: 1, timebase: "seconds", fps: { num: 30, den: 1 },
    output: { width: 1080, height: 1920, sampleAspectRatio: "1:1", rotation: 0, durationSec: 10 },
    tracks: [],
    captions: [
      { segmentId: "seg-1", text: "짧은 자막", startSec: 0, endSec: 3, style: {} as never },
      { segmentId: "seg-2", text: "둘째 자막", startSec: 3, endSec: 6, style: {} as never },
    ],
    gaps: [], source: { status: "current" },
    playback: { auditionUrls: {}, exactPreview: { status: "unavailable" } },
    local: { selectedSegmentId: null, seekSec: 0 },
    ...overrides,
  } as EditorViewModel;
}

function track(role: "broll" | "bgm" | "sfx", segmentId: string, controls: Record<string, unknown> = {}) {
  return {
    trackId: role, role,
    clips: [{ clipId: `${role}-1`, segmentId, type: role, assetId: `asset-${role}`, assetUri: null, startSec: 0, endSec: 3, controls }],
  };
}

/** 장면 수는 자막이 아니라 **클립**이 센다(`sceneNumbersBySegmentId`). 장면이
 *  둘이라는 것을 시험 입력에서도 클립으로 드러내야 실제 편집본과 같은 모양이 된다. */
function narrationForBothScenes() {
  return {
    trackId: "narration", role: "narration",
    clips: [
      { clipId: "n-1", segmentId: "seg-1", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 3, controls: {} },
      { clipId: "n-2", segmentId: "seg-2", type: "narration", assetId: null, assetUri: null, startSec: 3, endSec: 6, controls: {} },
    ],
  };
}

describe("buildQualityFollowUps", () => {
  // owner 2026-09-01: "유진이와 질문 답변이 끝나면 꼬리질문도 3개 만들어서
  // 제안해줘 -- 영상 퀄리티를 더 좋게 만드는 방법으로."
  it("suggests exactly the three biggest gaps in the chosen scene", () => {
    const followUps = buildQualityFollowUps({
      view: view({ tracks: [narrationForBothScenes(), track("broll", "seg-1")] as never }),
      selectedSegmentId: "seg-1",
    });

    expect(followUps).toEqual([
      "1번 장면에 어울리는 배경 음악을 넣어 줘",
      "1번 장면에 어울리는 효과음을 넣어 줘",
      "1번 장면 색감을 따뜻하게 바꿔 줘",
    ]);
  });

  // **이미 해 둔 것을 다시 권하면 유진이 화면을 안 보고 있다는 뜻이 된다.**
  it("never suggests something the scene already has", () => {
    const followUps = buildQualityFollowUps({
      view: view({
        tracks: [
          narrationForBothScenes(),
          track("broll", "seg-1", { filter: { type: "warm" } }),
          track("bgm", "seg-1"),
          track("sfx", "seg-1"),
        ] as never,
      }),
      selectedSegmentId: "seg-1",
    });

    expect(followUps.some((item) => item.includes("1번 장면에 어울리는"))).toBe(false);
    expect(followUps.some((item) => item.includes("1번 장면 색감"))).toBe(false);
    // 음악·효과음·색감은 이미 있으니 안 권한다. 대신 **아직 안 켠 것**을 권한다 --
    // 이 장면은 손떨림 보정도 소리 크기 맞추기도 꺼져 있다(2026-09-02에 둘 다
    // 유진이 말로 할 수 있게 됐다).
    expect(followUps).toEqual([
      "1번 장면 흔들린 화면을 잡아 줘",
      "1번 장면 배경 음악 소리 크기를 고르게 맞춰 줘",
      "장면 순서를 더 자연스럽게 바꿔 줘",
    ]);
  });

  it("offers to tighten a caption that will wrap, and to speed up a scene that drags", () => {
    const followUps = buildQualityFollowUps({
      view: view({
        tracks: [narrationForBothScenes(), track("broll", "seg-1", { filter: { type: "warm" } }), track("bgm", "seg-1"), track("sfx", "seg-1")] as never,
        captions: [
          { segmentId: "seg-1", text: "화면에서 두 줄로 감길 만큼 충분히 긴 자막 문장을 하나 둔다", startSec: 0, endSec: 12, style: {} as never },
          { segmentId: "seg-2", text: "둘째", startSec: 12, endSec: 14, style: {} as never },
        ],
      }),
      selectedSegmentId: "seg-1",
    });

    expect(followUps).toEqual([
      "1번 장면 자막을 더 짧게 다듬어 줘",
      "1번 장면을 1.5배로 빠르게 해 줘",
      "1번 장면 흔들린 화면을 잡아 줘",
    ]);
  });

  // 고른 장면이 없어도 "어느 장면 말이야?"를 창작자가 되묻게 하지 않는다.
  it("falls back to the first scene that still needs work when nothing is selected", () => {
    const followUps = buildQualityFollowUps({
      view: view({ tracks: [narrationForBothScenes(), track("bgm", "seg-1"), track("sfx", "seg-1"), track("broll", "seg-1", { filter: { type: "warm" } })] as never }),
      selectedSegmentId: null,
    });

    // 1번은 다 채워져 있으므로 2번을 집는다.
    expect(followUps[0]).toBe("2번 장면에 어울리는 배경 음악을 넣어 줘");
  });

  it("says nothing at all when there is no timeline to talk about", () => {
    expect(buildQualityFollowUps({ view: view({ captions: [], tracks: [] }), selectedSegmentId: null })).toEqual([]);
  });

  // **누르면 실제로 되는 것만 권한다.** 유진이 말로 할 수 있는 편집은 여덟
  // 가지뿐이라, 그 밖의 것을 권하면 눌렀을 때 "그건 못 해요"가 돌아온다.
  it("only proposes edits that Yujin can actually carry out today", () => {
    const everything = [
      ...buildQualityFollowUps({ view: view({ tracks: [narrationForBothScenes(), track("broll", "seg-1")] as never }), selectedSegmentId: "seg-1" }),
      ...buildQualityFollowUps({
        view: view({ tracks: [narrationForBothScenes(), track("broll", "seg-1", { filter: { type: "warm" } }), track("bgm", "seg-1"), track("sfx", "seg-1")] as never }),
        selectedSegmentId: "seg-1",
      }),
    ].join(" ");

    // 아직 유진이 말로 못 하는 것은 권하지 않는다. 2026-09-02에 손떨림 보정과
    // 소리 정리가 의도 목록에 들어와서 목록에서 빠졌다 -- 남은 것은 여전히
    // 화면 패널 전용이다(변형의 숫자 칸, 음조 유지, 덕킹).
    for (const panelOnly of ["기울", "높낮이", "덕킹"]) {
      expect(everything).not.toContain(panelOnly);
    }
  });
});
