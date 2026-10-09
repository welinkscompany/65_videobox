import { describe, expect, it } from "vitest";
import { isSwallowedRepeat, isTypingTarget, playbackShortcutFor, type PlaybackKeyEvent } from "./playbackShortcuts";

function el(html: string, pick: string): HTMLElement {
  const host = document.createElement("div");
  host.innerHTML = html;
  document.body.appendChild(host);
  return host.querySelector(pick) as HTMLElement;
}
const key = (target: EventTarget | null, o: Partial<PlaybackKeyEvent> = {}): PlaybackKeyEvent => ({
  key: " ", ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, isComposing: false, defaultPrevented: false, target, ...o,
});

describe("playbackShortcutFor", () => {
  const toggle = { type: "toggle" };
  it.each([
    ["규칙1 ctrl", () => key(el("<i id=t></i>", "#t"), { ctrlKey: true }), null],
    ["규칙1 meta", () => key(el("<i id=t></i>", "#t"), { metaKey: true }), null],
    ["규칙1 alt", () => key(el("<i id=t></i>", "#t"), { altKey: true }), null],
    ["규칙1 한글 조합 중", () => key(el("<i id=t></i>", "#t"), { isComposing: true }), null],
    ["규칙1 이미 막힘", () => key(el("<i id=t></i>", "#t"), { defaultPrevented: true }), null],
    ["규칙2 꾹 누름", () => key(el("<i id=t></i>", "#t"), { repeat: true }), null],
    ["규칙3 input", () => key(el("<input id=t>", "#t")), null],
    ["규칙3 textarea", () => key(el("<textarea id=t></textarea>", "#t")), null],
    ["규칙3 select", () => key(el("<select id=t></select>", "#t")), null],
    ["규칙3 contenteditable 안", () => key(el("<div contenteditable='true'><b id=t></b></div>", "#t")), null],
    ["규칙4 aria-modal 안", () => key(el("<div aria-modal='true'><div id=t></div></div>", "#t")), null],
    ["규칙4 aria-modal 안 단추", () => key(el("<div aria-modal='true' data-timeline-surface='true'><button id=t></button></div>", "#t")), null],
    ["규칙5 타임라인 안 button", () => key(el("<div data-timeline-surface='true'><button id=t></button></div>", "#t")), toggle],
    ["규칙5 타임라인 안 입력칸은 규칙3이 먼저", () => key(el("<div data-timeline-surface='true'><input id=t></div>", "#t")), null],
    ["규칙6 음소거 button(타임라인 밖)", () => key(el("<button id=t>음소거</button>", "#t")), null],
    ["규칙6 role=slider", () => key(el("<div role='slider' id=t></div>", "#t")), null],
    ["규칙6 a[href]", () => key(el("<a href='#x' id=t></a>", "#t")), null],
    ["규칙6 summary", () => key(el("<details><summary id=t></summary></details>", "#t")), null],
    ["규칙6 단추 안 글자", () => key(el("<button><span id=t></span></button>", "#t")), null],
    ["규칙7 section[tabindex=0] 미리보기 판", () => key(el("<section tabindex='0' id=t></section>", "#t")), toggle],
    ["규칙7 body", () => key(document.body), toggle],
    ["규칙7 대상이 창", () => key(window), toggle],
    ["다른 키", () => key(document.body, { key: "a" }), null],
  ] as const)("%s", (_name, make, expected) => {
    expect(playbackShortcutFor(make())).toEqual(expected);
  });

  it("꾹 누름은 가로챌 자리에서만 preventDefault 대상", () => {
    expect(isSwallowedRepeat(key(document.body, { repeat: true }))).toBe(true);
    expect(isSwallowedRepeat(key(el("<input id=t>", "#t"), { repeat: true }))).toBe(false);
    expect(isSwallowedRepeat(key(el("<button id=t></button>", "#t"), { repeat: true }))).toBe(false);
    expect(isSwallowedRepeat(key(document.body, { repeat: false }))).toBe(false);
  });
  it("isTypingTarget", () => {
    expect(isTypingTarget(el("<input id=t>", "#t"))).toBe(true);
    expect(isTypingTarget(el("<button id=t></button>", "#t"))).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
});
