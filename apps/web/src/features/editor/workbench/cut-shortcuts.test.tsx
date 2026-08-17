import { describe, expect, it } from "vitest";

import { cutShortcutFor } from "./cutShortcuts";

const tools = {
  split: { enabled: true, label: "나누기", hint: "", action: { kind: "split-narration", segmentId: "s2", splitSec: 8 } },
  join: { enabled: true, label: "앞과 붙이기", hint: "", action: { kind: "merge-narration", leftSegmentId: "s1", rightSegmentId: "s2" } },
  drop: { enabled: true, label: "빼기", hint: "", action: { kind: "set-cut-action", segmentId: "s2", cutAction: "remove" } },
} as const;

const locked = {
  split: { enabled: false, label: "나누기", hint: "", action: null },
  join: { enabled: false, label: "앞과 붙이기", hint: "", action: null },
  drop: { enabled: false, label: "빼기", hint: "", action: null },
} as const;

const press = (key: string, extra: Partial<{ ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }> = {}) =>
  ({ key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...extra });

describe("cut shortcuts", () => {
  it("splits at the playhead with Ctrl+B, the way CapCut does", () => {
    expect(cutShortcutFor(press("b", { ctrlKey: true }), tools)).toEqual(tools.split.action);
    // 맥에서는 Cmd다. 하나만 받으면 나머지 절반은 조용히 아무 일도 안 한다.
    expect(cutShortcutFor(press("B", { metaKey: true }), tools)).toEqual(tools.split.action);
  });

  it("drops the selected clip with Delete or Backspace", () => {
    expect(cutShortcutFor(press("Delete"), tools)).toEqual(tools.drop.action);
    expect(cutShortcutFor(press("Backspace"), tools)).toEqual(tools.drop.action);
  });

  it("does nothing when the tool itself is locked", () => {
    // 단추가 잠겨 있는데 키로는 통하면, 화면이 말한 것과 다른 일이 일어난다.
    expect(cutShortcutFor(press("b", { ctrlKey: true }), locked)).toBeNull();
    expect(cutShortcutFor(press("Delete"), locked)).toBeNull();
  });

  it("leaves keys we did not claim alone", () => {
    expect(cutShortcutFor(press("b"), tools)).toBeNull();          // 그냥 b는 글자다
    expect(cutShortcutFor(press("z", { ctrlKey: true }), tools)).toBeNull();  // 실행 취소는 따로 있다
    expect(cutShortcutFor(press("b", { ctrlKey: true, altKey: true }), tools)).toBeNull();
  });
});
