import { describe, expect, it } from "vitest";

import { cutToolbarState } from "./cutToolbar";

const clips = [
  { segmentId: "s1", startSec: 0, endSec: 5 },
  { segmentId: "s2", startSec: 5, endSec: 11 },
];

describe("cut toolbar", () => {
  it("splits the selected clip at the playhead", () => {
    // 캡컷은 재생 위치에서 나눈다. 우리는 이 기능을 갖고도 화면에 자리가 없어
    // owner가 "컷편집이 되는지 모르겠다"고 했다.
    const state = cutToolbarState({ clips, selectedSegmentId: "s2", playheadSec: 8 });

    expect(state.split.enabled).toBe(true);
    expect(state.split.action).toEqual({ kind: "split-narration", segmentId: "s2", splitSec: 8 });
  });

  it("will not split where there is nothing to cut", () => {
    // 장면 경계에서 나누면 길이 0짜리가 생긴다.
    expect(cutToolbarState({ clips, selectedSegmentId: "s2", playheadSec: 5 }).split.enabled).toBe(false);
    expect(cutToolbarState({ clips, selectedSegmentId: "s2", playheadSec: 11 }).split.enabled).toBe(false);
    // 재생 위치가 선택한 장면 밖이면 무엇을 나누는지 알 수 없다.
    expect(cutToolbarState({ clips, selectedSegmentId: "s1", playheadSec: 8 }).split.enabled).toBe(false);
  });

  it("joins the selected clip with the one before it", () => {
    const state = cutToolbarState({ clips, selectedSegmentId: "s2", playheadSec: 8 });

    expect(state.join.enabled).toBe(true);
    expect(state.join.action).toEqual({ kind: "merge-narration", leftSegmentId: "s1", rightSegmentId: "s2" });
  });

  it("cannot join the first clip with nothing", () => {
    expect(cutToolbarState({ clips, selectedSegmentId: "s1", playheadSec: 2 }).join.enabled).toBe(false);
  });

  it("drops the selected clip from the video", () => {
    const state = cutToolbarState({ clips, selectedSegmentId: "s2", playheadSec: 8 });

    expect(state.drop.enabled).toBe(true);
    expect(state.drop.label).toBe("빼기");
    expect(state.drop.action).toEqual({ kind: "set-cut-action", segmentId: "s2", cutAction: "remove" });
  });

  it("never pretends it can put a dropped clip back", () => {
    // 실제 앱에서 확인: 뺀 장면은 타임라인에서 사라져 다시 고를 수 없다. 처음에는
    // 같은 단추가 `다시 넣기`로 바뀌게 만들었는데, 누를 수 있는 상황이 오지 않았다.
    // 되돌리기는 `실행 취소`가, 다시 넣기는 인스펙터의 `유지`가 맡는다.
    const dropped = cutToolbarState({
      clips: [clips[0], { ...clips[1], cutAction: "remove" }], selectedSegmentId: "s2", playheadSec: 8,
    });

    expect(dropped.drop.label).toBe("빼기");
  });

  it("says why a tool is locked instead of just greying out", () => {
    // 실제 앱에서 장면을 고르고도 `나누기`가 회색이었다. 이유는 재생 위치가 그 장면
    // 밖이라는 것이었는데 화면은 아무 말도 하지 않아 고장으로 보였다.
    const outside = cutToolbarState({ clips, selectedSegmentId: "s2", playheadSec: 1 });
    expect(outside.split.hint).toContain("재생 위치");

    const nothingPicked = cutToolbarState({ clips, selectedSegmentId: null, playheadSec: 3 });
    expect(nothingPicked.split.hint).toContain("고르세요");

    expect(cutToolbarState({ clips, selectedSegmentId: "s1", playheadSec: 2 }).join.hint).toContain("첫 장면");
  });

  it("offers nothing while no clip is selected", () => {
    const state = cutToolbarState({ clips, selectedSegmentId: null, playheadSec: 3 });

    expect([state.split.enabled, state.join.enabled, state.drop.enabled]).toEqual([false, false, false]);
  });
});
