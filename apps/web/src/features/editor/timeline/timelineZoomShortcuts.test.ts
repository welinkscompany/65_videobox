import { describe, expect, it } from "vitest";

import { cutShortcutFor } from "../workbench/cutShortcuts";
import { timelineZoomShortcutFor } from "./timelineZoomShortcuts";

const press = (key: string, extra: Partial<{ ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }> = {}) =>
  ({ key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...extra });

const cutTools = {
  split: { enabled: true, label: "분할", hint: "", action: { kind: "split-narration", segmentId: "s2", splitSec: 8 } },
  join: { enabled: true, label: "앞과 붙이기", hint: "", action: { kind: "merge-narration", leftSegmentId: "s1", rightSegmentId: "s2" } },
  drop: { enabled: true, label: "빼기", hint: "", action: { kind: "set-cut-action", segmentId: "s2", cutAction: "remove" } },
} as const;

describe("타임라인 늘리기·줄이기 단축키", () => {
  it("Ctrl과 = / - 로 늘리고 줄이고, Ctrl과 0으로 전체를 본다", () => {
    expect(timelineZoomShortcutFor(press("=", { ctrlKey: true }), false)).toBe("in");
    expect(timelineZoomShortcutFor(press("-", { ctrlKey: true }), false)).toBe("out");
    expect(timelineZoomShortcutFor(press("0", { ctrlKey: true }), false)).toBe("fit");
  });

  it("자판이 같은 키를 다른 글자로 보내는 경우를 다 받는다", () => {
    // `Ctrl+Shift+=`와 숫자판 `+`는 key가 `+`로 온다. `=`만 받으면 대표님이 늘리려고
    // Shift를 같이 눌렀을 때 조용히 아무 일도 안 한다.
    expect(timelineZoomShortcutFor(press("+", { ctrlKey: true, shiftKey: true }), false)).toBe("in");
    expect(timelineZoomShortcutFor(press("_", { ctrlKey: true, shiftKey: true }), false)).toBe("out");
    // 맥에는 Ctrl이 아니라 Cmd다. `cutShortcuts.ts`가 Delete/Backspace를 둘 다 받는
    // 것과 같은 이유 -- 하나만 받으면 나머지 절반이 못 쓴다.
    expect(timelineZoomShortcutFor(press("=", { metaKey: true }), false)).toBe("in");
    expect(timelineZoomShortcutFor(press("-", { metaKey: true }), false)).toBe("out");
    expect(timelineZoomShortcutFor(press("0", { metaKey: true }), false)).toBe("fit");
  });

  it("이미 쓰고 있는 키와 부딪히지 않는다", () => {
    // 편집기가 이미 쓰는 키: Ctrl+Z(되돌리기)·Ctrl+Shift+Z/Ctrl+Y(다시)·Ctrl+B(나누기)·
    // Delete/Backspace(빼기). 우리 키는 그 어느 것도 물지 않는다.
    for (const chord of [
      press("z", { ctrlKey: true }),
      press("z", { ctrlKey: true, shiftKey: true }),
      press("y", { ctrlKey: true }),
      press("b", { ctrlKey: true }),
      press("B", { metaKey: true }),
      press("Delete"),
      press("Backspace"),
    ]) {
      expect(timelineZoomShortcutFor(chord, false)).toBeNull();
    }
    // 반대 방향도 본다. 우리 키를 컷 도구가 집어가면 늘리려다 장면이 잘린다.
    for (const chord of [
      press("=", { ctrlKey: true }),
      press("+", { ctrlKey: true, shiftKey: true }),
      press("-", { ctrlKey: true }),
      press("_", { ctrlKey: true, shiftKey: true }),
      press("0", { ctrlKey: true }),
      press("=", { metaKey: true }),
    ]) {
      expect(cutShortcutFor(chord, cutTools)).toBeNull();
    }
  });

  it("안 집은 키는 그대로 둔다", () => {
    expect(timelineZoomShortcutFor(press("="), false)).toBeNull();      // 그냥 =는 글자다
    expect(timelineZoomShortcutFor(press("0"), false)).toBeNull();
    expect(timelineZoomShortcutFor(press("1", { ctrlKey: true }), false)).toBeNull();
    // Alt가 눌린 조합은 다른 뜻이다. `cutShortcuts.ts`와 같은 규약.
    expect(timelineZoomShortcutFor(press("=", { ctrlKey: true, altKey: true }), false)).toBeNull();
  });

  it("글을 쓰는 중에는 가로채지 않는다", () => {
    // 자막을 고쳐 쓰는 칸에서 Ctrl+-를 누르는 일은 없겠지만, 가로채는 순간 브라우저가
    // 원래 하던 일까지 같이 막힌다.
    expect(timelineZoomShortcutFor(press("=", { ctrlKey: true }), true)).toBeNull();
    expect(timelineZoomShortcutFor(press("-", { ctrlKey: true }), true)).toBeNull();
  });
});
