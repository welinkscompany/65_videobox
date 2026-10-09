import { describe, expect, it } from "vitest";

import {
  TIMELINE_FALLBACK_PIXELS_PER_SECOND,
  TIMELINE_INITIAL_VISIBLE_SECONDS,
  TIMELINE_MAX_PIXELS_PER_SECOND,
  TIMELINE_MIN_VISIBLE_SECONDS,
  fitPixelsPerSecond,
  initialPixelsPerSecond,
  pixelsPerSecondBounds,
} from "./timelineZoomScale";

describe("타임라인 처음 배율과 한계", () => {
  it("짧은 영상도 적어도 20초 창으로 연다 -- 1초가 화면 절반을 쓰지 않게(2026-10-09 대표님)", () => {
    expect(TIMELINE_MIN_VISIBLE_SECONDS).toBe(20);
    expect(initialPixelsPerSecond({ durationSec: 7.75, viewportWidthPx: 1200 })).toBeCloseTo(60, 9);
    expect(initialPixelsPerSecond({ durationSec: 15, viewportWidthPx: 1200 })).toBeCloseTo(60, 9);
    expect(initialPixelsPerSecond({ durationSec: 30, viewportWidthPx: 1200 })).toBeCloseTo(40, 9);
    expect(initialPixelsPerSecond({ durationSec: 494.837, viewportWidthPx: 1200 })).toBeCloseTo(20, 9);
    expect(pixelsPerSecondBounds({ durationSec: 7.75, viewportWidthPx: 1200 }).min).toBeCloseTo(60, 9);
    expect(pixelsPerSecondBounds({ durationSec: 494.837, viewportWidthPx: 1200 }).min).toBeCloseTo(1200 / 494.837, 9);
  });

  it("길이 0·1·7.75·20·30·60·120·3600초와 폭 0·NaN에서 바닥·처음·맞춤이 유한하고 순서가 맞다", () => {
    for (const durationSec of [0, 1, 7.75, 20, 30, 60, 120, 3600]) {
      for (const viewportWidthPx of [0, Number.NaN, 1200]) {
        const input = { durationSec, viewportWidthPx };
        const bounds = pixelsPerSecondBounds(input);
        const initial = initialPixelsPerSecond(input);
        expect(Number.isFinite(bounds.min) && bounds.min > 0).toBe(true);
        expect(bounds.min).toBeLessThanOrEqual(bounds.max);
        expect(Number.isFinite(initial) && initial > 0).toBe(true);
        if (durationSec > 0 && viewportWidthPx === 1200) {
          expect(initial).toBeGreaterThanOrEqual(bounds.min);
          expect(initial).toBeLessThanOrEqual(bounds.max);
          // 맞춤은 영상 전체가 칸을 채우는 배율 -- 바닥보다 작을 수 없다(20초 아래에선 바닥보다 크다).
          expect(fitPixelsPerSecond(input)!).toBeGreaterThanOrEqual(1200 / Math.max(durationSec, 20) - 1e-9);
        }
      }
    }
    expect(fitPixelsPerSecond({ durationSec: 7.75, viewportWidthPx: 1200 })).toBeCloseTo(1200 / 7.75, 9);
    expect(pixelsPerSecondBounds({ durationSec: 20, viewportWidthPx: 1200 }).min).toBeCloseTo(60, 9);
    expect(pixelsPerSecondBounds({ durationSec: 3600, viewportWidthPx: 1200 }).min).toBeCloseTo(1200 / 3600, 9);
  });

  it("긴 영상과 짧은 영상에 같은 규칙을 쓴다 -- 한 화면에 60초, 영상이 더 짧으면 영상 전체", () => {
    // 대표님 실제 영상이 494.837초다. 예전 기본값 100px/초로는 49,483px이 되어
    // 1200px 타임라인에 12초만 보였다. 반대로 전체를 한 화면에 우겨넣으면
    // 2.4px/초라 5초짜리 장면이 12px이다 -- 잡을 수가 없다.
    expect(initialPixelsPerSecond({ durationSec: 494.837, viewportWidthPx: 1200 })).toBeCloseTo(20, 9);
    // P2(2026-10-09): 20초보다 짧은 영상도 20초 창으로 연다 -- 15초는 1200/20 = 60 (옛 기대: 영상 전체 = 80).
    expect(initialPixelsPerSecond({ durationSec: 15, viewportWidthPx: 1200 })).toBeCloseTo(60, 9);
    expect(TIMELINE_INITIAL_VISIBLE_SECONDS).toBe(60);
  });

  it("줄이기는 영상 전체가 한 화면에 들어온 자리에서 멈추고, 늘리기는 프레임이 보이는 자리에서 멈춘다", () => {
    const long = pixelsPerSecondBounds({ durationSec: 494.837, viewportWidthPx: 1200 });
    const short = pixelsPerSecondBounds({ durationSec: 15, viewportWidthPx: 1200 });

    expect(long.min).toBeCloseTo(1200 / 494.837, 9);
    // P2: 줄이기 바닥 = 칸 ÷ max(길이, 20초) -- 15초도 20초 창까지 줄인다 (옛 기대 80).
    expect(short.min).toBeCloseTo(60, 9);
    expect(long.max).toBe(TIMELINE_MAX_PIXELS_PER_SECOND);
    expect(short.max).toBe(TIMELINE_MAX_PIXELS_PER_SECOND);
  });

  it("아주 짧은 영상은 한계를 넘지 않는다 -- 바닥이 천장보다 위로 올라가지 않는다", () => {
    // P2: 1초 영상의 바닥은 이제 1200/20 = 60 (옛 기대: 400으로 천장과 같았다). 맞춤(1200)은 천장 400을 넘지 않게 접힌다.
    const bounds = pixelsPerSecondBounds({ durationSec: 1, viewportWidthPx: 1200 });

    expect(bounds.min).toBeCloseTo(60, 9);
    expect(bounds.max).toBe(TIMELINE_MAX_PIXELS_PER_SECOND);
    expect(initialPixelsPerSecond({ durationSec: 1, viewportWidthPx: 1200 })).toBeCloseTo(60, 9);
    // 바닥이 천장을 넘는 폭(칸이 아주 넓다)에서도 뒤집히지 않는다.
    const wide = pixelsPerSecondBounds({ durationSec: 1, viewportWidthPx: 100000 });
    expect(wide.min).toBe(TIMELINE_MAX_PIXELS_PER_SECOND);
    expect(wide.max).toBe(TIMELINE_MAX_PIXELS_PER_SECOND);
  });

  it("길이가 틀리게 와도 유한한 값을 준다 -- 길이 결함이 편집기를 못 열게 하면 안 된다", () => {
    // 대표님 494초 세션의 `output.duration_sec`이 5.0으로 온다(같은 계획의 다른 조각).
    // 그 값이 고쳐지기 전에도 배율은 유한하고 양수여야 한다 -- 0이나 Infinity가
    // `createTimelineNavigation`에 들어가면 RangeError가 나고 편집기가 통째로 안 열린다.
    const wrong = initialPixelsPerSecond({ durationSec: 5, viewportWidthPx: 1200 });
    expect(Number.isFinite(wrong)).toBe(true);
    expect(wrong).toBeGreaterThan(0);
    // P2: 5초도 20초 창 = 1200/20 = 60 (옛 기대 240 = 영상 전체). 요지(유한·양수)는 그대로.
    expect(wrong).toBeCloseTo(60, 9);

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
