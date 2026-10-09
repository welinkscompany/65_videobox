// 재생 키 문지기 -- 스페이스가 재생/정지인지 아닌지를 정하는 곳은 여기 하나다.
// (2026-10-09 실측: 미리보기 판과 창 전체가 둘 다 스페이스를 받아 서로 상쇄했다.)
export type PlaybackCommand =
  | Readonly<{ type: "toggle" }>
  | Readonly<{ type: "pause" }>
  | Readonly<{ type: "faster" }>
  | Readonly<{ type: "slower" }>
  | Readonly<{ type: "step"; frames: -1 | 1 }>;

export type PlaybackKeyEvent = Readonly<{
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
  repeat: boolean;
  isComposing: boolean;
  defaultPrevented: boolean;
  target: EventTarget | null;
}>;

const TYPING = "input, textarea, select, [contenteditable='true']";
const SELF_SPACE = "button, [role='button'], [role='menuitem'], [role='menuitemradio'], [role='option'], [role='slider'], [role='checkbox'], [role='switch'], [role='tab'], [role='radio'], summary, a[href]";

/** 글을 쓰는 자리인가(input·textarea·select·contenteditable). */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || target.closest(TYPING) !== null;
}

/** 키 하나 → 재생 명령. 가로채면 안 되는 자리면 null. */
export function playbackShortcutFor(event: PlaybackKeyEvent): PlaybackCommand | null {
  if (event.key !== " ") return null;
  if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing || event.defaultPrevented) return null; // 1
  if (event.repeat) return null; // 2
  const target = event.target instanceof HTMLElement ? event.target : null;
  if (isTypingTarget(target)) return null; // 3
  if (target?.closest("[aria-modal='true']")) return null; // 4
  if (target?.closest("[data-timeline-surface='true']")) return { type: "toggle" }; // 5
  if (target?.closest(SELF_SPACE)) return null; // 6
  return { type: "toggle" }; // 7
}

/** 꾹 누른 스페이스가 가로챌 자리에서 눌렸나 -- 호출하는 쪽이 preventDefault만 하도록(페이지가 굴러가지 않게). */
export function isSwallowedRepeat(event: PlaybackKeyEvent): boolean {
  return event.repeat && playbackShortcutFor({ ...event, repeat: false }) !== null;
}
