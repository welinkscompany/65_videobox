/** 시각을 사람이 읽는 말로.
 *
 * 프로젝트 카드가 `2026-08-17T06:13:40.438824+00:00`을 그대로 보여 주고 있었다.
 * 카드 폭에서 줄바꿈돼 `+00:0 0`으로 잘리기까지 했다(2026-08-17 owner 지적).
 *
 * **읽을 수 없으면 아무 말도 하지 않는다**(`null`). 틀린 시각을 자신 있게
 * 보여 주는 것보다 안 보여 주는 것이 낫다.
 */
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export function readableMoment(iso: string, now: Date = new Date()): string | null {
  const at = new Date(iso);
  if (!iso || Number.isNaN(at.getTime())) return null;

  // 시계가 어긋나 미래로 보일 수 있다. `-3분 전`이라고 하지 않는다.
  const elapsed = Math.max(0, now.getTime() - at.getTime());
  if (elapsed < MINUTE) return "방금";
  if (elapsed < HOUR) return `${Math.floor(elapsed / MINUTE)}분 전`;
  if (elapsed < DAY) return `${Math.floor(elapsed / HOUR)}시간 전`;

  const days = Math.floor(elapsed / DAY);
  if (days === 1) return "어제";
  if (days < 7) return `${days}일 전`;

  const sameYear = at.getUTCFullYear() === now.getUTCFullYear();
  const month = at.getUTCMonth() + 1;
  const day = at.getUTCDate();
  return sameYear ? `${month}월 ${day}일` : `${at.getUTCFullYear()}년 ${month}월 ${day}일`;
}
