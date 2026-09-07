/** 리플 배속을 걸면 장면이 몇 초가 되는지.
 *
 *  엔진과 같은 식이다 -- `set_segment_ripple_playback_rate`가
 *  `display_duration = source_duration / rate`로 `end_sec`를 바꾸고 뒤 장면을
 *  당긴다(`editing_session.py:630`).
 *
 *  **`endSec - startSec`를 그냥 나누면 틀린다.** 그 값은 이미 지금 배속이 걸린
 *  **표시 길이**라 원본이 아니다. 원본으로 되돌린 뒤(`표시 × 지금배속`) 새
 *  배속으로 나눈다. 지금 배속이 1인 장면에서는 두 식이 같은 값을 내서 이 차이가
 *  안 보인다 -- 2026-09-04에 그래서 한 번 틀렸다.
 */
export function rippleDisplayDurationSec({
  displayedSec,
  currentRate,
  nextRate,
}: Readonly<{ displayedSec: number; currentRate: number; nextRate: number }>): number | null {
  if (!(displayedSec > 0) || !(currentRate > 0) || !(nextRate > 0)) return null;
  const sourceSec = displayedSec * currentRate;
  return sourceSec / nextRate;
}
