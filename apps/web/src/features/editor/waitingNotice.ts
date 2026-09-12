import { useEffect, useState } from "react";

/** 기다림을 화면에 남기는 공용 문구·시계.
 *
 *  **왜 있는가.** 완성본 만들기는 2026-09-11에 스스로 다시 읽으면서 단추 글씨까지
 *  바꿨지만(`app/OutputsPage.tsx`), 편집 저장과 유진 대화는 여전히 문장 하나를
 *  띄운 채 몇 분을 흘려보냈다. 장면 나누기는 93번째가 실측 298초였고, 유진의
 *  숏폼 판단은 437초와 605초였다. 회색으로 잠긴 단추와 안 바뀌는 문장은
 *  "멈췄다"로 읽힌다(대표님 상시 지시 2026-09-12).
 *
 *  **백분율은 만들지 않는다.** 근거가 되는 데이터가 없다 -- 완성본 만들기도
 *  네 지점밖에 몰라서 일부러 숫자를 안 보여 준다. 흘러간 시간은 정직하고,
 *  가짜 진행바는 아니다.
 */

/** 시계를 다시 읽는 간격. 완성본 재확인(`OutputsPage.tsx`)과 같은 5초다. */
export const WAIT_CLOCK_TICK_MS = 5000;

/** 이 시간을 넘기면 "오래 걸릴 수 있다"고 덧붙인다. 몇 초에 끝나는 편집에는
 *  아무 말도 더하지 않는다 -- 빠른 일에 기다림 안내를 붙이면 그게 더 불안하다. */
export const LONG_WAIT_SEC = 10;

/** 흘러간 시간을 사람이 읽는 말로. 내부 단위(ms)는 화면에 쓰지 않는다(§10.13). */
export function waitElapsedLabel(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  if (whole < 60) return `${whole}초`;
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  return rest === 0 ? `${minutes}분` : `${minutes}분 ${rest}초`;
}

/** 오래 걸리는 중이라고 **정직하게** 말한다. 짧으면 `null`이라 아무 줄도 안 생긴다. */
export function longWaitNotice(seconds: number): string | null {
  if (seconds < LONG_WAIT_SEC) return null;
  return `${waitElapsedLabel(seconds)} 지났어요. 오래 걸릴 수 있어요. 이 화면을 열어 둔 채 기다려 주세요.`;
}

/** 기다리는 동안 몇 초 지났는지 세는 시계.
 *
 *  **멈추는 조건은 `active`가 거짓이 되는 것 하나다.** 기다릴 것이 없으면 다음
 *  한 번을 걸지 않고, 화면을 떠나면 cleanup의 `clearTimeout`이 거둔다. 모양은
 *  완성본 재확인 효과(`OutputsPage.tsx`의 `finalPollTick`)를 그대로 따른다 --
 *  `tick`을 의존값에 넣어 스스로 다음 한 번만 건다. 이 저장소에서 가장 나쁜
 *  결과가 안 멈추는 타이머라, 시험이 시간을 한참 넘겨 보고 `getTimerCount`가
 *  0인지 확인한다.
 */
export function useWaitElapsedSeconds(active: boolean): number {
  const [startedAtMs, setStartedAtMs] = useState<number | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!active) {
      // 다음 기다림이 0초부터 세도록 거둔다. 이미 비어 있으면 React가 알아서
      // 다시 그리지 않으므로 무한 루프가 되지 않는다.
      setStartedAtMs(null);
      setTick(0);
      return;
    }
    if (startedAtMs === null) {
      setStartedAtMs(Date.now());
      return;
    }
    const timer = window.setTimeout(() => setTick((current) => current + 1), WAIT_CLOCK_TICK_MS);
    return () => window.clearTimeout(timer);
  }, [active, startedAtMs, tick]);
  if (!active || startedAtMs === null) return 0;
  return Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000));
}
