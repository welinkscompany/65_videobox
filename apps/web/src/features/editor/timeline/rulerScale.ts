// opencut-classic(cf5e79e9) apps/web/src/timeline/ruler-utils.ts의 "확대 정도에 따라 간격을 고른다"는 생각만 보고
// 다시 썼다. 코드는 옮기지 않았다(2026-10-08 채택 스파이크).
import type { RationalFps } from "./time-scale";

/** 초 단위 후보. 1시간 영상 전체 보기(0.37px/초)에서도 글자 사이가 벌어지도록 30분·1시간까지 둔다. */
const SECOND_STEPS = [1, 2, 3, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600] as const;
/** 프레임 단위 후보. 아주 크게 늘렸을 때 프레임 경계를 읽을 수 있게 한다. */
const FRAME_STEPS = [2, 3, 5, 10, 15] as const;
/** 잔눈금 하나가 최소 이만큼(큰 눈금 글자 간격의 1/5) 벌어져야 눈에 잡힌다. */
const MINOR_TICK_FRACTION = 1 / 5;
const EPSILON = 1e-9;

export type RulerIntervals = Readonly<{ majorSec: number; minorSec: number }>;

function candidateSteps(fps: RationalFps): readonly number[] {
  const frameSec = fps.den / fps.num;
  return [...FRAME_STEPS.map((frames) => frames * frameSec), ...SECOND_STEPS].sort((a, b) => a - b);
}

function dividesEvenly(whole: number, part: number): boolean {
  const ratio = whole / part;
  return Math.abs(ratio - Math.round(ratio)) < EPSILON * Math.max(1, ratio);
}

/**
 * 큰 눈금(글자가 붙는 눈금)은 글자 사이가 `minLabelGapPx` 이상인 가장 작은 간격,
 * 잔눈금은 그 간격을 똑 떨어지게 나누는 후보 중 `minLabelGapPx / 5` 이상 벌어지는 가장 작은 것이다.
 * 어느 후보도 모자라면(극단적으로 줄인 화면) 가장 큰 후보에 머문다.
 */
export function rulerIntervals(pixelsPerSecond: number, fps: RationalFps, minLabelGapPx: number): RulerIntervals {
  const steps = candidateSteps(fps);
  const widest = steps[steps.length - 1]!;
  if (!(pixelsPerSecond > 0) || !Number.isFinite(pixelsPerSecond)) return { majorSec: widest, minorSec: widest };
  const majorSec = steps.find((step) => step * pixelsPerSecond >= minLabelGapPx - EPSILON) ?? widest;
  const minorSec = steps.find((step) => step < majorSec
    && dividesEvenly(majorSec, step)
    && step * pixelsPerSecond >= minLabelGapPx * MINOR_TICK_FRACTION - EPSILON) ?? majorSec;
  return { majorSec, minorSec };
}

function cleanSeconds(seconds: number): number {
  return Number(seconds.toFixed(9));
}

/** `[startSec, endSec]` 안에서 `majorSec`의 배수 위에 있는 시각들. */
export function rulerMarks(input: Readonly<{ startSec: number; endSec: number; majorSec: number }>): readonly number[] {
  const { startSec, endSec, majorSec } = input;
  if (!(majorSec > 0) || !Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec < startSec) return [];
  const first = Math.ceil(Math.max(0, startSec) / majorSec - EPSILON);
  const last = Math.floor(endSec / majorSec + EPSILON);
  return Array.from({ length: Math.max(0, last - first + 1) }, (_, index) => cleanSeconds((first + index) * majorSec));
}

/** 1초 미만 간격이면 `0.5s`, 60초 이상이면 `1:30`, 그 밖은 `15s`. */
export function formatRulerLabel(seconds: number, majorSec: number): string {
  if (majorSec < 1) return `${Number(seconds.toFixed(3))}s`;
  if (seconds >= 60) {
    const whole = Math.round(seconds);
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
  }
  return `${Math.round(seconds)}s`;
}

/**
 * 칸 오른쪽 끝에 너무 가까워 글자가 잘릴 눈금인가. 그렇다면 글자를 선 왼쪽에 얹는다(시각은 그대로).
 * `labelRoomPx`는 글자 하나가 차지하는 폭의 넉넉한 어림값이다.
 */
export function rulerLabelAlignsEnd(input: Readonly<{ seconds: number; viewportEndSec: number; pixelsPerSecond: number; labelRoomPx: number }>): boolean {
  const { seconds, viewportEndSec, pixelsPerSecond, labelRoomPx } = input;
  if (!(seconds > 0) || !(pixelsPerSecond > 0)) return false;
  return (viewportEndSec - seconds) * pixelsPerSecond < labelRoomPx;
}
