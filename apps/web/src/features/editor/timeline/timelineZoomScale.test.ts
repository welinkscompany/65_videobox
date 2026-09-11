import { describe, expect, it } from "vitest";

import {
  TIMELINE_FALLBACK_PIXELS_PER_SECOND,
  TIMELINE_INITIAL_VISIBLE_SECONDS,
  TIMELINE_MAX_PIXELS_PER_SECOND,
  initialPixelsPerSecond,
  pixelsPerSecondBounds,
} from "./timelineZoomScale";

describe("타임라인 처음 배율과 한계", () => {
  it("긴 영상과 짧은 영상에 같은 규칙을 쓴다 -- 한 화면에 60초, 영상이 더 짧으면 영상 전체", () => {
    // 대표님 실제 영상이 494.837초다. 예전 기본값 100px/초로는 49,483px이 되어
    // 1200px 타임라인에 12초만 보였다. 반대로 전체를 한 화면에 우겨넣으면
    // 2.4px/초라 5초짜리 장면이 12px이다 -- 잡을 수가 없다.
    expect(initialPixelsPerSecond({ durationSec: 494.837, viewportWidthPx: 1200 })).toBeCloseTo(20, 9);
    // 15초짜리는 60초를 채우지 못한다. 빈 자리를 그리는 대신 영상 전체가 화면을 채운다.
    expect(initialPixelsPerSecond({ durationSec: 15, viewportWidthPx: 1200 })).toBeCloseTo(80, 9);
    expect(TIMELINE_INITIAL_VISIBLE_SECONDS).toBe(60);
  });

  it("줄이기는 영상 전체가 한 화면에 들어온 자리에서 멈추고, 늘리기는 프레임이 보이는 자리에서 멈춘다", () => {
    const long = pixelsPerSecondBounds({ durationSec: 494.837, viewportWidthPx: 1200 });
    const short = pixelsPerSecondBounds({ durationSec: 15, viewportWidthPx: 1200 });

    expect(long.min).toBeCloseTo(1200 / 494.837, 9);
    expect(short.min).toBeCloseTo(80, 9);
    expect(long.max).toBe(TIMELINE_MAX_PIXELS_PER_SECOND);
    expect(short.max).toBe(TIMELINE_MAX_PIXELS_PER_SECOND);
  });

  it("아주 짧은 영상은 한계를 넘지 않는다 -- 바닥이 천장보다 위로 올라가지 않는다", () => {
    const bounds = pixelsPerSecondBounds({ durationSec: 1, viewportWidthPx: 1200 });

    expect(bounds.min).toBe(TIMELINE_MAX_PIXELS_PER_SECOND);
    expect(bounds.max).toBe(TIMELINE_MAX_PIXELS_PER_SECOND);
    expect(initialPixelsPerSecond({ durationSec: 1, viewportWidthPx: 1200 })).toBe(TIMELINE_MAX_PIXELS_PER_SECOND);
  });

  it("길이가 틀리게 와도 유한한 값을 준다 -- 길이 결함이 편집기를 못 열게 하면 안 된다", () => {
    // 대표님 494초 세션의 `output.duration_sec`이 5.0으로 온다(같은 계획의 다른 조각).
    // 그 값이 고쳐지기 전에도 배율은 유한하고 양수여야 한다 -- 0이나 Infinity가
    // `createTimelineNavigation`에 들어가면 RangeError가 나고 편집기가 통째로 안 열린다.
    const wrong = initialPixelsPerSecond({ durationSec: 5, viewportWidthPx: 1200 });
    expect(Number.isFinite(wrong)).toBe(true);
    expect(wrong).toBeGreaterThan(0);
    expect(wrong).toBeCloseTo(240, 9);

    for (const durationSec of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(initialPixelsPerSecond({ durationSec, viewportWidthPx: 1200 })).toBe(TIMELINE_FALLBACK_PIXELS_PER_SECOND);
    }
    for (const viewportWidthPx of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(initialPixelsPerSecond({ durationSec: 20, viewportWidthPx })).toBe(TIMELINE_FALLBACK_PIXELS_PER_SECOND);
    }
    const degenerate = pixelsPerSecondBounds({ durationSec: 0, viewportWidthPx: 0 });
    expect(degenerate.min).toBeGreaterThan(0);
    expect(degenerate.min).toBeLessThanOrEqual(degenerate.max);
  });
});
