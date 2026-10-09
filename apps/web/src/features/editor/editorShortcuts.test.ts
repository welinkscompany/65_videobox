import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { EDITOR_SHORTCUTS, editorShortcutFor, isSwallowedRepeat, type EditorKeyEvent, type EditorShortcutId } from "./editorShortcuts";

const ALL_IDS: EditorShortcutId[] = ["toggle-play", "pause", "faster", "slower", "frame-back", "frame-forward", "split", "delete", "undo", "redo", "zoom-in", "zoom-out", "zoom-fit", "trim-left", "trim-right", "prev-cut", "next-cut", "go-start", "go-end"];

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
    ["Q 키는 왼쪽 자르기", () => ev({ key: "q" }), "trim-left"],
    ["W 키는 오른쪽 자르기", () => ev({ key: "w" }), "trim-right"],
    ["Shift+Q는 아니다", () => ev({ key: "Q", shiftKey: true }), null],
    ["Shift+W는 아니다", () => ev({ key: "W", shiftKey: true }), null],
    ["Ctrl+Q·Ctrl+W는 브라우저 몫", () => ev({ key: "q", ctrlKey: true }), null],
    ["Ctrl+W(탭 닫기)", () => ev({ key: "w", ctrlKey: true }), null],
    ["Alt+Q", () => ev({ key: "q", altKey: true }), null],
    ["글칸 textarea 안의 q는 글자다", () => ev({ key: "q", target: el("<textarea id=t></textarea>") }), null],
    ["글칸 input 안의 w는 글자다", () => ev({ key: "w", target: el("<input id=t>") }), null],
    ["contenteditable 안의 q", () => ev({ key: "q", target: el("<div contenteditable='true'><b id=t></b></div>") }), null],
    ["서랍(aria-modal) 안의 q", () => ev({ key: "q", target: modal() }), null],
    ["꾹 누른 q는 한 번만", () => ev({ key: "q", repeat: true }), null],
    ["한글 조합 중 q", () => ev({ key: "q", isComposing: true }), null],
    ["이미 막힌 w", () => ev({ key: "w", defaultPrevented: true }), null],
    ["단추 위의 q도 받는다(글자는 단추 몫이 아니다)", () => ev({ key: "q", target: el("<button id=t></button>") }), "trim-left"],
    ["타임라인 면 안의 w도 받는다", () => ev({ key: "w", target: el("<div data-timeline-surface='true'><button id=t></button></div>") }), "trim-right"],
    ["ArrowUp은 앞 자른 자리", () => ev({ key: "ArrowUp" }), "prev-cut"],
    ["ArrowDown은 뒤 자른 자리", () => ev({ key: "ArrowDown" }), "next-cut"],
    ["타임라인 면 안의 ArrowUp도 받는다", () => ev({ key: "ArrowUp", target: el("<div data-timeline-surface='true'><i id=t></i></div>") }), "prev-cut"],
    ["높이 손잡이(separator) 위 ArrowUp은 손잡이 몫", () => ev({ key: "ArrowUp", target: el("<div role='separator' id=t></div>") }), null],
    ["슬라이더 위 ArrowDown", () => ev({ key: "ArrowDown", target: el("<div role='slider' id=t></div>") }), null],
    ["목록 항목 위 ArrowDown", () => ev({ key: "ArrowDown", target: el("<div role='option' id=t></div>") }), null],
    ["Shift+ArrowUp", () => ev({ key: "ArrowUp", shiftKey: true }), null],
    ["Ctrl+ArrowDown", () => ev({ key: "ArrowDown", ctrlKey: true }), null],
    ["글칸 안의 ArrowUp", () => ev({ key: "ArrowUp", target: el("<textarea id=t></textarea>") }), null],
    ["꾹 누른 ArrowDown", () => ev({ key: "ArrowDown", repeat: true }), null],
    ["서랍 안의 ArrowUp", () => ev({ key: "ArrowUp", target: modal() }), null],
    ["본문의 Home은 처음으로", () => ev({ key: "Home" }), "go-start"],
    ["본문의 End는 끝으로", () => ev({ key: "End" }), "go-end"],
    ["타임라인 면 안 Home은 타임라인이 이미 받는다", () => ev({ key: "Home", target: el("<div data-timeline-surface='true'><i id=t></i></div>") }), null],
    ["타임라인 면 안 End", () => ev({ key: "End", target: el("<div data-timeline-surface='true'><button id=t></button></div>") }), null],
    ["슬라이더 위 Home은 슬라이더 몫", () => ev({ key: "Home", target: el("<div role='slider' id=t></div>") }), null],
    ["높이 손잡이 위 End", () => ev({ key: "End", target: el("<div role='separator' id=t></div>") }), null],
    ["글칸 안의 Home", () => ev({ key: "Home", target: el("<input id=t>") }), null],
    ["서랍 안의 End", () => ev({ key: "End", target: modal() }), null],
    ["Shift+Home", () => ev({ key: "Home", shiftKey: true }), null],
    ["Ctrl+End", () => ev({ key: "End", ctrlKey: true }), null],
    ["꾹 누른 Home", () => ev({ key: "Home", repeat: true }), null],
    ["Shift+Z는 영상 전체 보기", () => ev({ key: "Z", shiftKey: true }), "zoom-fit"],
    ["맨 z는 아니다", () => ev({ key: "z" }), null],
    ["글칸 안의 Shift+Z", () => ev({ key: "Z", shiftKey: true, target: el("<textarea id=t></textarea>") }), null],
    ["Ctrl+Shift+Z는 여전히 다시 하기", () => ev({ key: "Z", ctrlKey: true, shiftKey: true }), "redo"],
    ["Alt+Shift+Z", () => ev({ key: "Z", shiftKey: true, altKey: true }), null],
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

describe("진짜 Chromium 덮개", () => {
  // 표에 줄을 더하면서 진짜 브라우저 시험을 안 더하면 여기서 빨개진다. 시험 머리의 `// covers: <id>` 주석이 열쇠다.
  const specs = ["capcut-shortcuts.spec.mjs", "playback-smoothness.spec.mjs"];
  const covered = new Set<string>();
  for (const name of specs) {
    const source = readFileSync(resolve(import.meta.dirname, "../../../e2e-real", name), "utf-8");
    for (const match of source.matchAll(/\/\/ covers: ([a-z-]+)/g)) covered.add(match[1]);
  }
  it("모든 단축키 줄이 진짜 Chromium 시험을 가진다", () => {
    const missing = EDITOR_SHORTCUTS.map((row) => row.id).filter((id) => !covered.has(id));
    expect(missing).toEqual([]);
  });
  it("덮개 주석이 표에 없는 id를 가리키지 않는다(오타·지운 줄 방지)", () => {
    const known = new Set<string>(EDITOR_SHORTCUTS.map((row) => row.id));
    expect([...covered].filter((id) => !known.has(id))).toEqual([]);
  });
});
