/** 타임라인을 처음 얼마나 늘려 둘지, 그리고 어디까지 늘리고 줄일 수 있는지.
 *
 * 대표님 지시(2026-09-12): "처음에 디폴트 값을 어느정도는 길게 하고 이걸 단축키로
 * 쉽게 늘리고 줄이고를 할수 있어야지".
 *
 * 예전에는 100px/초로 못박혀 있었다. 대표님 실제 영상(494.837초)이면 49,483px이고,
 * 1200px짜리 타임라인에 **12초**만 보인다 -- 장면 두 개다. 그렇다고 반대로 영상
 * 전체를 한 화면에 우겨넣으면 2.4px/초라 5초짜리 장면이 12px이 되어 눈으로 찾을
 * 수도, 손으로 잡을 수도 없다. 어느 쪽도 "어느정도는 길게"가 아니다.
 *
 * 그래서 규칙을 **한 화면에 몇 초**로 잡는다. 긴 영상과 짧은 영상에 같은 문장이
 * 그대로 통하는 유일한 형태다 -- 고정된 px/초는 긴 영상에서, 전체 맞춤은 짧은
 * 영상에서 각각 말이 안 된다.
 */

/** 처음 열었을 때 한 화면에 담는 시간. 대표님 영상은 장면 하나가 5초 안팎이라
 *  60초면 장면 열 개 남짓이 한눈에 들어오면서도 하나를 잡을 만큼은 넓다. */
export const TIMELINE_INITIAL_VISIBLE_SECONDS = 60;

/** 길이나 화면 폭을 못 믿을 때 돌아오는 자리. 예전 기본값 그대로다.
 *  0이나 Infinity가 `createTimelineNavigation`에 들어가면 RangeError가 나고
 *  편집기가 **통째로** 안 열린다 -- 배율 하나 때문에 화면을 잃지 않는다. */
export const TIMELINE_FALLBACK_PIXELS_PER_SECOND = 100;

/** 가장 크게 늘렸을 때. 25fps에서 한 프레임이 16px, 30fps에서 13.3px이다 --
 *  프레임 하나를 눈으로 보고 찍을 수 있는 자리까지가 끝이고, 더 늘려도 같은
 *  프레임이 넓어질 뿐 새로 보이는 것이 없다(편집은 전부 프레임에 맞춰 반올림된다). */
export const TIMELINE_MAX_PIXELS_PER_SECOND = 400;

/** 절대 바닥. 길이가 터무니없이 크게 들어와도 배율이 0에 닿지 않게 한다. */
const ABSOLUTE_MIN_PIXELS_PER_SECOND = 0.1;

export type TimelineZoomScaleInput = Readonly<{ durationSec: number; viewportWidthPx: number }>;

export type TimelineZoomBounds = Readonly<{ min: number; max: number }>;

/** 영상 전체가 한 화면에 들어오는 배율. 길이나 폭을 믿을 수 없으면 `null`이다 --
 *  "모른다"와 "0이다"를 섞으면 나눗셈이 Infinity를 뱉는다. */
export function fitPixelsPerSecond(input: TimelineZoomScaleInput): number | null {
  if (!input) return null;
  const { durationSec, viewportWidthPx } = input;
  if (!Number.isFinite(durationSec) || durationSec <= 0) return null;
  if (!Number.isFinite(viewportWidthPx) || viewportWidthPx <= 0) return null;
  const fit = viewportWidthPx / durationSec;
  return Number.isFinite(fit) && fit > 0 ? fit : null;
}

export function pixelsPerSecondBounds(input: TimelineZoomScaleInput): TimelineZoomBounds {
  const fit = fitPixelsPerSecond(input);
  const max = TIMELINE_MAX_PIXELS_PER_SECOND;
  // **줄이기는 영상 전체가 한 화면에 들어온 순간 멈춘다.** 그 너머는 빈 자리뿐이라
  // 더 줄일 이유가 없고, 이렇게 두면 줄이기를 계속 누른 자리와 `전체 보기`가
  // 정확히 같은 자리가 된다. 15초짜리를 2px/초까지 줄일 수 있게 두는 것은
  // 기능이 아니라 길 잃기다.
  if (fit === null) return { min: ABSOLUTE_MIN_PIXELS_PER_SECOND, max };
  return { min: Math.min(max, Math.max(ABSOLUTE_MIN_PIXELS_PER_SECOND, fit)), max };
}

export function initialPixelsPerSecond(input: TimelineZoomScaleInput): number {
  if (fitPixelsPerSecond(input) === null) return TIMELINE_FALLBACK_PIXELS_PER_SECOND;
  // 영상이 60초보다 짧으면 60초를 그리지 않는다. 뒤쪽 빈 자리를 보여 주는 대신
  // 영상 전체가 화면을 채운다.
  const visibleSec = Math.min(input.durationSec, TIMELINE_INITIAL_VISIBLE_SECONDS);
  const bounds = pixelsPerSecondBounds(input);
  return Math.min(bounds.max, Math.max(bounds.min, input.viewportWidthPx / visibleSec));
}
