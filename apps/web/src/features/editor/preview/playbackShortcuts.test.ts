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

describe("playbackShortcutFor J/K/L와 화살표", () => {
  const body = () => document.body;
  const inTimeline = () => el("<div data-timeline-surface='true'><button id=t></button></div>", "#t");
  it.each([
    ["k -> 멈춤", () => key(body(), { key: "k" }), { type: "pause" }],
    ["l -> 빠르게", () => key(body(), { key: "l" }), { type: "faster" }],
    ["j -> 느리게", () => key(body(), { key: "j" }), { type: "slower" }],
    ["L(shift) -> 빠르게", () => key(body(), { key: "L", shiftKey: true }), { type: "faster" }],
    ["J(shift) -> 느리게", () => key(body(), { key: "J", shiftKey: true }), { type: "slower" }],
    ["K(대문자) -> 멈춤", () => key(body(), { key: "K" }), { type: "pause" }],
    ["l 단추 위에서도 받는다", () => key(el("<button id=t></button>", "#t"), { key: "l" }), { type: "faster" }],
    ["l 타임라인 안 단추", () => key(inTimeline(), { key: "l" }), { type: "faster" }],
    ["l 입력칸 -> null", () => key(el("<input id=t>", "#t"), { key: "l" }), null],
    ["l select -> null", () => key(el("<select id=t></select>", "#t"), { key: "l" }), null],
    ["l ctrl -> null", () => key(body(), { key: "l", ctrlKey: true }), null],
    ["l 꾹 누름 -> null", () => key(body(), { key: "l", repeat: true }), null],
    ["l 모달 안 -> null", () => key(el("<div aria-modal='true'><button id=t></button></div>", "#t"), { key: "l" }), null],
    ["ArrowRight 본문 -> +1", () => key(body(), { key: "ArrowRight" }), { type: "step", frames: 1 }],
    ["ArrowLeft 본문 -> -1", () => key(body(), { key: "ArrowLeft" }), { type: "step", frames: -1 }],
    ["ArrowRight 단추 위 -> +1", () => key(el("<button id=t></button>", "#t"), { key: "ArrowRight" }), { type: "step", frames: 1 }],
    ["ArrowRight 미리보기 판 -> +1", () => key(el("<section tabindex='0' id=t></section>", "#t"), { key: "ArrowRight" }), { type: "step", frames: 1 }],
    ["ArrowRight 타임라인 면 안 -> null", () => key(inTimeline(), { key: "ArrowRight" }), null],
    ["ArrowLeft slider -> null", () => key(el("<div role='slider' id=t></div>", "#t"), { key: "ArrowLeft" }), null],
    ["ArrowRight separator -> null", () => key(el("<div role='separator' id=t></div>", "#t"), { key: "ArrowRight" }), null],
    ["ArrowRight spinbutton -> null", () => key(el("<div role='spinbutton' id=t></div>", "#t"), { key: "ArrowRight" }), null],
    ["ArrowRight radio -> null", () => key(el("<div role='radio' id=t></div>", "#t"), { key: "ArrowRight" }), null],
    ["ArrowRight tab -> null", () => key(el("<div role='tab' id=t></div>", "#t"), { key: "ArrowRight" }), null],
    ["ArrowRight menuitem -> null", () => key(el("<div role='menuitem' id=t></div>", "#t"), { key: "ArrowRight" }), null],
    ["ArrowRight option -> null", () => key(el("<div role='option' id=t></div>", "#t"), { key: "ArrowRight" }), null],
    ["ArrowRight select -> null", () => key(el("<select id=t></select>", "#t"), { key: "ArrowRight" }), null],
    ["ArrowRight 입력칸 -> null", () => key(el("<input id=t>", "#t"), { key: "ArrowRight" }), null],
    ["Shift+ArrowRight -> null", () => key(body(), { key: "ArrowRight", shiftKey: true }), null],
    ["ArrowRight ctrl -> null", () => key(body(), { key: "ArrowRight", ctrlKey: true }), null],
    ["ArrowRight 이미 막힘 -> null", () => key(body(), { key: "ArrowRight", defaultPrevented: true }), null],
  ] as const)("%s", (_name, make, expected) => {
    expect(playbackShortcutFor(make())).toEqual(expected);
  });
});
