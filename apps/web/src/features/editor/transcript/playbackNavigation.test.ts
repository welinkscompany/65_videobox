import { describe, expect, it } from "vitest";
import { activeSegmentIdAt, clampPlaybackSeconds, frameDurationSec, resolvePlaybackSelection } from "./playbackNavigation";

const entries = [{ segmentId: "s-1", startSec: 0, endSec: 2 }, { segmentId: "s-2", startSec: 2, endSec: 4 }];

describe("playback navigation", () => {
  it("clamps nonnegative playback seconds to the output duration", () => {
    expect(clampPlaybackSeconds(-1, 4)).toBe(0);
    expect(clampPlaybackSeconds(9, 4)).toBe(4);
  });
  it("uses half-open segment ranges so a boundary activates the next row", () => {
    expect(activeSegmentIdAt(entries, 2)).toBe("s-2");
    expect(activeSegmentIdAt(entries, 4)).toBeNull();
  });
});

// 0907-b26195af 실측(2026-10-08 점검 §3-1, 스파이크 §3(나)): 경계와 재생기가 알려 온 시각.
const scenes0907 = [
  { segmentId: "scene-1", startSec: 0, endSec: 1.3324 },
  { segmentId: "scene-2", startSec: 1.3324, endSec: 1.8990646 },
  { segmentId: "scene-3", startSec: 1.8990646, endSec: 2.9281 },
  { segmentId: "scene-4", startSec: 2.9281, endSec: 3.7512 },
];
const playerReported = 1.899064;
const frame = frameDurationSec({ num: 30, den: 1 });

describe("재생 시각으로 장면 고르기 -- 누른 장면이 먼저 (2026-10-08)", () => {
  it("옛 규칙은 재생기가 알려 온 시각에서 앞 장면을 고른다 -- 결함의 정체", () => {
    expect(activeSegmentIdAt(scenes0907, playerReported)).toBe("scene-2");
  });
  it("방금 누른 장면은 재생기가 시작 바로 앞을 알려 와도 그대로다", () => {
    expect(resolvePlaybackSelection(scenes0907, playerReported, { pinnedSegmentId: "scene-3", frameSec: frame })).toBe("scene-3");
  });
  it("누른 장면이 없어도 경계 반 프레임 안은 뒤 장면이다", () => {
    expect(resolvePlaybackSelection(scenes0907, playerReported, { pinnedSegmentId: null, frameSec: frame })).toBe("scene-3");
  });
  it("재생이 누른 장면 끝을 지나면 다음 장면으로 넘어간다", () => {
    expect(resolvePlaybackSelection(scenes0907, 2.9281 + 0.001, { pinnedSegmentId: "scene-3", frameSec: frame })).toBe("scene-4");
  });
  it("다른 곳으로 크게 옮기면 그 자리 장면이다", () => {
    expect(resolvePlaybackSelection(scenes0907, 0.5, { pinnedSegmentId: "scene-3", frameSec: frame })).toBe("scene-1");
  });
  it("마지막 장면 끝 반 프레임 안도 마지막 장면이고, 그 뒤는 없다", () => {
    expect(resolvePlaybackSelection(scenes0907, 3.7512 - frame / 4, { pinnedSegmentId: null, frameSec: frame })).toBe("scene-4");
    expect(resolvePlaybackSelection(scenes0907, 3.9, { pinnedSegmentId: null, frameSec: frame })).toBeNull();
  });
  it("모든 이웃 클립을 하나씩 눌러도 재생기가 시작 한 프레임 안쪽 아래를 알려 오면 누른 장면이다", () => {
    for (const scene of scenes0907) {
      for (const offset of [0, 1e-6, frame / 2, frame - 1e-6]) {
        const t = Math.max(0, scene.startSec - offset);
        expect(resolvePlaybackSelection(scenes0907, t, { pinnedSegmentId: scene.segmentId, frameSec: frame })).toBe(scene.segmentId);
      }
    }
  });
  it("재생이 흘러가는 동안(고정 없음/옛 장면 고정) 시각대로 장면이 넘어간다", () => {
    const expected = [[0.1, "scene-1"], [1.0, "scene-1"], [1.4, "scene-2"], [1.8, "scene-2"], [1.95, "scene-3"], [2.5, "scene-3"], [3.0, "scene-4"], [3.7, "scene-4"]] as const;
    for (const [t, id] of expected) {
      expect(resolvePlaybackSelection(scenes0907, t, { pinnedSegmentId: null, frameSec: frame })).toBe(id);
      expect(resolvePlaybackSelection(scenes0907, t, { pinnedSegmentId: "scene-1", frameSec: frame })).toBe(id);
    }
  });
  it("모르는 고정 id는 무시하고, 프레임 길이는 den/num이다", () => {
    expect(resolvePlaybackSelection(scenes0907, 2.0, { pinnedSegmentId: "nope", frameSec: frame })).toBe("scene-3");
    expect(frameDurationSec({ num: 30000, den: 1001 })).toBeCloseTo(1001 / 30000, 9);
    expect(() => frameDurationSec({ num: 0, den: 1 })).toThrow(RangeError);
  });
});
