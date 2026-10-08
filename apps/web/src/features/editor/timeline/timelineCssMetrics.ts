/** **값은 px여야 한다**(`32px`). rem·calc·% 같은 값은 숫자로 못 읽어 fallback으로 돌아간다.
 *  CSS 사용자 변수(`--vb-timeline-lane-h` 같은 `NNpx` 값)를 숫자로 읽는다.
 *  크기를 CSS 변수로만 정해 두면 밀도를 바꿀 때 로직을 안 건드려도 되는데,
 *  좌표 계산은 숫자가 필요해서 마운트 뒤에 한 번 읽는다. 읽을 수 없으면
 *  (요소 없음·jsdom·`rem` 등 px가 아닌 값) fallback이다. */
export function readCssPixels(element: Element | null, name: string, fallbackPx: number): number {
  if (!element) return fallbackPx;
  const raw = window.getComputedStyle(element).getPropertyValue(name).trim();
  // `2rem`을 parseFloat하면 2가 나오므로 단위까지 확인한다.
  const match = /^(\d*\.?\d+)px$/.exec(raw);
  const parsed = match ? Number.parseFloat(match[1]) : Number.NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallbackPx;
}
