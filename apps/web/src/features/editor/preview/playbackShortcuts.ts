import { editorShortcutFor, isSwallowedRepeat as swallowed, isTypingTarget as typing, type EditorKeyEvent } from "../editorShortcuts";

// 재생 키 포장 -- 판정은 `editorShortcutFor` 한 곳이다(표: editorShortcuts.ts).
export type PlaybackCommand =
  | Readonly<{ type: "toggle" }>
  | Readonly<{ type: "pause" }>
  | Readonly<{ type: "faster" }>
  | Readonly<{ type: "slower" }>
  | Readonly<{ type: "step"; frames: -1 | 1 }>;

export type PlaybackKeyEvent = EditorKeyEvent;

/** 글을 쓰는 자리인가 -- 정의는 editorShortcuts.ts. */
export const isTypingTarget = typing;

/** 꾹 누른 스페이스가 가로챌 자리에서 눌렸나. */
export const isSwallowedRepeat = swallowed;

/** 키 하나 → 재생 명령. 가로채면 안 되는 자리면 null. */
export function playbackShortcutFor(event: PlaybackKeyEvent): PlaybackCommand | null {
  switch (editorShortcutFor(event)) {
    case "toggle-play": return { type: "toggle" };
    case "pause": return { type: "pause" };
    case "faster": return { type: "faster" };
    case "slower": return { type: "slower" };
    case "frame-back": return { type: "step", frames: -1 };
    case "frame-forward": return { type: "step", frames: 1 };
    default: return null;
  }
}
