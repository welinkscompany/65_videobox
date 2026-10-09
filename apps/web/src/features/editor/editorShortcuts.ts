// 편집기 단축키 -- 표 하나, 문지기 하나.
// 재생(미리보기)·자르기/되돌리기(작업판)·줌(타임라인)이 따로 판정하던 것을 여기로 모았다.
// 누가 실행하는지(owner)는 표에 적고, 어느 자리에서 가로채도 되는지는 `editorShortcutFor` 하나가 정한다.
// (2026-10-09 실측: 미리보기 판과 창 전체가 둘 다 스페이스를 받아 서로 상쇄했다 -- 같은 종류의 사고를 막는 자리다.)
export type EditorShortcutId =
  | "toggle-play" | "pause" | "faster" | "slower" | "frame-back" | "frame-forward"
  | "split" | "delete" | "undo" | "redo"
  | "zoom-in" | "zoom-out" | "zoom-fit"
  | "trim-left" | "trim-right" | "prev-cut" | "next-cut" | "go-start" | "go-end";

export type EditorKeyEvent = Readonly<{
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

export type ShortcutOwner = "preview" | "workbench" | "timeline";
export type CapcutParity = "same" | "differs";

export type EditorShortcut = Readonly<{
  id: EditorShortcutId;
  owner: ShortcutOwner;
  group: "재생" | "이동" | "자르기" | "되돌리기" | "타임라인 보기";
  keys: string;
  label: string;
  capcut: CapcutParity;
  note?: string;
  samples: readonly Readonly<Partial<EditorKeyEvent> & { key: string }>[];
}>;

export const EDITOR_SHORTCUTS: readonly EditorShortcut[] = [
  { id: "toggle-play", owner: "preview", group: "재생", keys: "스페이스바", label: "재생 / 일시정지", capcut: "same", samples: [{ key: " " }] },
  { id: "pause", owner: "preview", group: "재생", keys: "K 키", label: "멈춤", capcut: "differs", samples: [{ key: "k" }, { key: "K", shiftKey: true }] },
  { id: "faster", owner: "preview", group: "재생", keys: "L 키", label: "재생, 누를수록 빠르게", capcut: "differs", samples: [{ key: "l" }] },
  { id: "slower", owner: "preview", group: "재생", keys: "J 키", label: "느리게", capcut: "differs", samples: [{ key: "j" }] },
  { id: "frame-back", owner: "preview", group: "이동", keys: "←", label: "한 프레임 뒤로", capcut: "same", samples: [{ key: "ArrowLeft" }] },
  { id: "frame-forward", owner: "preview", group: "이동", keys: "→", label: "한 프레임 앞으로", capcut: "same", samples: [{ key: "ArrowRight" }] },
  { id: "split", owner: "workbench", group: "자르기", keys: "Ctrl + B", label: "재생 위치에서 나누기", capcut: "same", samples: [{ key: "b", ctrlKey: true }, { key: "B", metaKey: true, shiftKey: true }] },
  { id: "delete", owner: "workbench", group: "자르기", keys: "Delete", label: "고른 장면 빼기", capcut: "same", samples: [{ key: "Delete" }, { key: "Backspace" }] },
  { id: "undo", owner: "workbench", group: "되돌리기", keys: "Ctrl + Z", label: "되돌리기", capcut: "same", samples: [{ key: "z", ctrlKey: true }, { key: "z", metaKey: true }] },
  { id: "redo", owner: "workbench", group: "되돌리기", keys: "Ctrl + Shift + Z", label: "다시 하기", capcut: "same", samples: [{ key: "Z", ctrlKey: true, shiftKey: true }, { key: "y", ctrlKey: true }] },
  { id: "zoom-in", owner: "timeline", group: "타임라인 보기", keys: "Ctrl + =", label: "타임라인 늘리기", capcut: "same", samples: [{ key: "=", ctrlKey: true }, { key: "+", ctrlKey: true, shiftKey: true }] },
  { id: "zoom-out", owner: "timeline", group: "타임라인 보기", keys: "Ctrl + -", label: "타임라인 줄이기", capcut: "same", samples: [{ key: "-", ctrlKey: true }, { key: "_", metaKey: true }] },
  { id: "zoom-fit", owner: "timeline", group: "타임라인 보기", keys: "Shift + Z (또는 Ctrl + 0)", label: "영상 전체 보기", capcut: "same", samples: [{ key: "0", ctrlKey: true }, { key: "Z", shiftKey: true }] },
  { id: "trim-left", owner: "timeline", group: "자르기", keys: "Q 키", label: "재생 위치 왼쪽 잘라 내기", capcut: "same", note: "빈자리는 그대로 둬요", samples: [{ key: "q" }, { key: "Q" }] },
  { id: "trim-right", owner: "timeline", group: "자르기", keys: "W 키", label: "재생 위치 오른쪽 잘라 내기", capcut: "same", note: "빈자리는 그대로 둬요", samples: [{ key: "w" }] },
  { id: "prev-cut", owner: "timeline", group: "이동", keys: "↑", label: "앞 자른 자리로", capcut: "same", samples: [{ key: "ArrowUp" }] },
  { id: "next-cut", owner: "timeline", group: "이동", keys: "↓", label: "뒤 자른 자리로", capcut: "same", samples: [{ key: "ArrowDown" }] },
  { id: "go-start", owner: "timeline", group: "이동", keys: "Home 키", label: "처음으로", capcut: "same", samples: [{ key: "Home" }] },
  { id: "go-end", owner: "timeline", group: "이동", keys: "End 키", label: "끝으로", capcut: "same", samples: [{ key: "End" }] },
];

/** 이 명령을 누가 실행하나(표의 owner 칸). */
export function ownerOf(id: EditorShortcutId): ShortcutOwner {
  return (EDITOR_SHORTCUTS.find((row) => row.id === id) as EditorShortcut).owner;
}

const TYPING = "input, textarea, select, [contenteditable='true']";
const SELF_SPACE = "button, [role='button'], [role='menuitem'], [role='menuitemradio'], [role='option'], [role='slider'], [role='checkbox'], [role='switch'], [role='tab'], [role='radio'], summary, a[href]";
// 화살표를 스스로 쓰는 조작(목록·슬라이더·탭·도크 크기 손잡이 ...). 거기서는 한 프레임 이동을 가로채지 않는다.
const SELF_ARROWS = "[role='slider'], [role='spinbutton'], [role='radio'], [role='tab'], [role='menuitem'], [role='menuitemradio'], [role='option'], [role='separator']";

/** 글을 쓰는 자리인가(input·textarea·select·contenteditable). */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || target.closest(TYPING) !== null;
}

/** 키 하나 → 명령 id. 가로채면 안 되는 자리면 null. 규칙은 위에서부터 먼저 걸리는 것이 이긴다. */
export function editorShortcutFor(event: EditorKeyEvent): EditorShortcutId | null {
  if (!event || typeof event.key !== "string") return null;
  if (event.isComposing || event.defaultPrevented || event.altKey) return null; // 1
  const target = event.target instanceof HTMLElement ? event.target : null;
  if (isTypingTarget(target)) return null; // 2
  const letter = event.key.length === 1 ? event.key.toLowerCase() : event.key;

  if (event.ctrlKey || event.metaKey) { // 3
    // 꾹 누르면 나누기만 막는다. 줌·되돌리기는 반복이 맞다.
    if (letter === "z") return event.shiftKey ? "redo" : "undo";
    if (letter === "y") return event.shiftKey ? null : "redo";
    if (letter === "b") return event.repeat ? null : "split";
    if (event.key === "=" || event.key === "+") return "zoom-in";
    if (event.key === "-" || event.key === "_") return "zoom-out";
    if (event.key === "0") return "zoom-fit";
    return null;
  }

  if (event.repeat) return null; // 4
  if (target?.closest("[aria-modal='true']")) return null;

  if (event.key === "Delete" || event.key === "Backspace") return "delete"; // 5

  if (event.key === "ArrowUp" || event.key === "ArrowDown") { // 5-a: 앞/뒤 자른 자리 (타임라인 면 안에서도 받는다 -- 거기서는 위아래를 쓰지 않는다)
    if (event.shiftKey || target?.closest(SELF_ARROWS)) return null;
    return event.key === "ArrowUp" ? "prev-cut" : "next-cut";
  }

  if (event.key === "Home" || event.key === "End") { // 5-b: 타임라인 면 안은 타임라인이 이미 받는다(둘이 받으면 두 번 간다)
    if (event.shiftKey || target?.closest("[data-timeline-surface='true']") || target?.closest(SELF_ARROWS)) return null;
    return event.key === "Home" ? "go-start" : "go-end";
  }

  if (event.key === "ArrowLeft" || event.key === "ArrowRight") { // 6
    // Shift+화살표는 이번 범위 밖. 타임라인 면 안은 타임라인이 이미 받는다(둘이 받으면 두 프레임 간다).
    if (event.shiftKey) return null;
    if (target?.closest("[data-timeline-surface='true']") || target?.closest(SELF_ARROWS)) return null;
    return event.key === "ArrowLeft" ? "frame-back" : "frame-forward";
  }

  if (event.key === " ") { // 7
    if (target?.closest("[data-timeline-surface='true']")) return "toggle-play";
    if (target?.closest(SELF_SPACE)) return null;
    return "toggle-play";
  }

  // 8 -- 글자 키는 단추 위에서도 받는다. 단추는 글자를 쓰지 않는다.
  if (letter === "k") return "pause";
  if (letter === "l") return "faster";
  if (letter === "j") return "slower";
  // 캡컷 Q·W(재생 위치 왼쪽·오른쪽 잘라 내기)와 Shift+Z(전체 보기). Shift+Q·Shift+W와 맨 z는 아니다.
  if (letter === "q") return event.shiftKey ? null : "trim-left";
  if (letter === "w") return event.shiftKey ? null : "trim-right";
  if (letter === "z") return event.shiftKey ? "zoom-fit" : null;
  return null;
}

// 진짜 KeyboardEvent는 `{...event}`로 펼치면 key 같은 속성이 하나도 안 따라온다 -- 필드를 하나씩 옮긴다.
/** 꾹 누른 키가 가로챌 자리에서 눌렸나 -- 호출하는 쪽이 preventDefault만 하도록(페이지가 굴러가지 않게). */
export function isSwallowedRepeat(event: EditorKeyEvent): boolean {
  return event.repeat && editorShortcutFor({ key: event.key, ctrlKey: event.ctrlKey, metaKey: event.metaKey, altKey: event.altKey, shiftKey: event.shiftKey, isComposing: event.isComposing, defaultPrevented: event.defaultPrevented, target: event.target, repeat: false }) !== null;
}
