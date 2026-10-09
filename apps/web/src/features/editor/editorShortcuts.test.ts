import { describe, expect, it } from "vitest";
import { EDITOR_SHORTCUTS, editorShortcutFor, isSwallowedRepeat, type EditorKeyEvent, type EditorShortcutId } from "./editorShortcuts";

const ALL_IDS: EditorShortcutId[] = ["toggle-play", "pause", "faster", "slower", "frame-back", "frame-forward", "split", "delete", "undo", "redo", "zoom-in", "zoom-out", "zoom-fit"];

function el(html: string): HTMLElement {
  const host = document.createElement("div");
  host.innerHTML = html;
  document.body.appendChild(host);
  return host.querySelector("#t") as HTMLElement;
}
const ev = (o: Partial<EditorKeyEvent> & { key: string }): EditorKeyEvent => ({
  ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, isComposing: false, defaultPrevented: false, target: document.body, ...o,
});

describe("표 모양", () => {
  it("id는 겹치지 않고, 모든 명령이 정확히 한 줄이다", () => {
    const ids = EDITOR_SHORTCUTS.map((row) => row.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect([...ids].sort()).toEqual([...ALL_IDS].sort());
  });
  it("owner는 셋 중 하나다", () => {
    for (const row of EDITOR_SHORTCUTS) expect(["preview", "workbench", "timeline"]).toContain(row.owner);
  });
  it("줄마다 부르는 키 견본이 있다", () => {
    for (const row of EDITOR_SHORTCUTS) expect(row.samples.length).toBeGreaterThan(0);
  });
});

describe("표의 키가 그 줄을 부른다", () => {
  it.each(EDITOR_SHORTCUTS.flatMap((row) => row.samples.map((sample) => [row.id, sample] as const)))("%s", (id, sample) => {
    expect(editorShortcutFor(ev(sample))).toBe(id);
  });
});

describe("문지기 규칙", () => {
  const modal = () => el("<div aria-modal='true'><div id=t></div></div>");
  it.each([
    ["글칸 input에서 Delete", () => ev({ key: "Delete", target: el("<input id=t>") }), null],
    ["글칸 textarea에서 Ctrl+B", () => ev({ key: "b", ctrlKey: true, target: el("<textarea id=t></textarea>") }), null],
    ["글칸 input에서 Ctrl+Z", () => ev({ key: "z", ctrlKey: true, target: el("<input id=t>") }), null],
    ["글칸 input에서 l", () => ev({ key: "l", target: el("<input id=t>") }), null],
    ["서랍 안에서 Delete는 안 지운다(의도된 변경)", () => ev({ key: "Delete", target: modal() }), null],
    ["서랍 안에서 Backspace도", () => ev({ key: "Backspace", target: modal() }), null],
    ["서랍 안에서 Ctrl+Z는 받는다", () => ev({ key: "z", ctrlKey: true, target: modal() }), "undo"],
    ["서랍 안에서 Ctrl+=는 받는다", () => ev({ key: "=", ctrlKey: true, target: modal() }), "zoom-in"],
    ["꾹 누른 Delete", () => ev({ key: "Delete", repeat: true }), null],
    ["꾹 누른 Ctrl+B", () => ev({ key: "b", ctrlKey: true, repeat: true }), null],
    ["꾹 누른 Ctrl+=는 계속", () => ev({ key: "=", ctrlKey: true, repeat: true }), "zoom-in"],
    ["꾹 누른 Ctrl+Z는 계속", () => ev({ key: "z", ctrlKey: true, repeat: true }), "undo"],
    ["Alt", () => ev({ key: "Delete", altKey: true }), null],
    ["Ctrl+Alt+Z", () => ev({ key: "z", ctrlKey: true, altKey: true }), null],
    ["한글 조합 중", () => ev({ key: "Delete", isComposing: true }), null],
    ["이미 막힌 키", () => ev({ key: " ", defaultPrevented: true }), null],
    ["Ctrl+Shift+B도 나누기(지금 그대로)", () => ev({ key: "B", ctrlKey: true, shiftKey: true }), "split"],
    ["Ctrl+Shift+Y는 아무것도 아니다(지금 그대로)", () => ev({ key: "Y", ctrlKey: true, shiftKey: true }), null],
    ["Ctrl+스페이스", () => ev({ key: " ", ctrlKey: true }), null],
    ["타임라인 안 스페이스 단추", () => ev({ key: " ", target: el("<div data-timeline-surface='true'><button id=t></button></div>") }), "toggle-play"],
    ["단추 위 스페이스는 단추 몫", () => ev({ key: " ", target: el("<button id=t></button>") }), null],
    ["슬라이더 위 화살표는 슬라이더 몫", () => ev({ key: "ArrowLeft", target: el("<div role='slider' id=t></div>") }), null],
    ["타임라인 면 안 화살표는 타임라인 몫", () => ev({ key: "ArrowRight", target: el("<div data-timeline-surface='true'><i id=t></i></div>") }), null],
    ["Shift+화살표", () => ev({ key: "ArrowRight", shiftKey: true }), null],
    ["대상이 창", () => ev({ key: " ", target: window }), "toggle-play"],
    ...["m", "n", "p", "v", "a", "[", "]"].map((k) => [`캡컷에만 있는 ${k}`, () => ev({ key: k }), null] as const),
    ...["c", "v", "d", "r", "g"].map((k) => [`Ctrl+${k}`, () => ev({ key: k, ctrlKey: true }), null] as const),
    ["Alt+k", () => ev({ key: "k", altKey: true }), null],
  ] as const)("%s", (_name, make, expected) => {
    expect(editorShortcutFor(make())).toBe(expected);
  });

  it("isSwallowedRepeat: 꾹 누른 스페이스는 삼키고 단추 위 스페이스는 안 삼킨다", () => {
    expect(isSwallowedRepeat(ev({ key: " ", repeat: true }))).toBe(true);
    expect(isSwallowedRepeat(ev({ key: " ", repeat: true, target: el("<button id=t></button>") }))).toBe(false);
    expect(isSwallowedRepeat(ev({ key: " " }))).toBe(false);
  });
});

describe("표 문구", () => {
  const FORBIDDEN = /revision|provider|runtime|job|pipeline|model|fallback/i;
  const KEY_NAMES = ["Ctrl", "Shift", "Delete", "Backspace", "Home", "End", "Q", "W", "J", "K", "L", "Z", "B", "Y", "0"];
  it("내부 용어가 없고, 한글 아닌 낱말은 키 이름뿐이다", () => {
    for (const row of EDITOR_SHORTCUTS) {
      for (const text of [row.keys, row.label, row.note ?? ""]) {
        expect(text).not.toMatch(FORBIDDEN);
        for (const word of text.match(/[A-Za-z0-9]+/g) ?? []) expect(KEY_NAMES).toContain(word);
      }
    }
  });
});

describe("진짜 KeyboardEvent", () => {
  it("펼침(...) 없이 필드를 읽어서, 꾹 누른 스페이스를 삼킨다", () => {
    const real = new KeyboardEvent("keydown", { key: " ", repeat: true });
    Object.defineProperty(real, "target", { value: document.body });
    expect(isSwallowedRepeat(real)).toBe(true);
    expect(editorShortcutFor(new KeyboardEvent("keydown", { key: "j" }))).toBe("slower");
  });
});
