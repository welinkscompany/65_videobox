// 단축키 골든 표의 입력 그물 -- 옛 처리기 셋(재생·자르기/되돌리기·줌)과 새 문지기가 같은 그물을 밟는다.
export type GoldenFlags = "none" | "repeat" | "composing" | "prevented";
export type GoldenCase = { id: string; key: string; mods: string; target: string; flags: GoldenFlags };

export const GOLDEN_KEYS = [" ", "ArrowLeft", "ArrowRight", "ArrowUp", "j", "k", "l", "J", "K", "L", "Delete", "Backspace", "b", "B", "z", "Z", "y", "Y", "=", "+", "-", "_", "0", "a", "Enter", "m", "n", "p", "v", "[", "]", "c", "d", "r", "g", "q", "w", "Home", "End"] as const;
export const GOLDEN_MODS = ["", "ctrl", "meta", "alt", "shift", "ctrl+shift", "ctrl+alt"] as const;
export const GOLDEN_FLAGS: GoldenFlags[] = ["none", "repeat", "composing", "prevented"];
export const GOLDEN_TARGETS: Record<string, string | null> = {
  body: null,
  window: null,
  input: "<input id=t>",
  textarea: "<textarea id=t></textarea>",
  select: "<select id=t></select>",
  editable: "<div contenteditable='true'><b id=t></b></div>",
  modal: "<div aria-modal='true'><div id=t></div></div>",
  modalButton: "<div aria-modal='true'><button id=t></button></div>",
  surface: "<div data-timeline-surface='true'><i id=t></i></div>",
  surfaceButton: "<div data-timeline-surface='true'><button id=t></button></div>",
  button: "<button id=t>x</button>",
  slider: "<div role='slider' id=t></div>",
  anchor: "<a href='#x' id=t></a>",
  section: "<section tabindex='0' id=t></section>",
};

export function makeTarget(name: string): EventTarget {
  if (name === "body") return document.body;
  if (name === "window") return window;
  const host = document.createElement("div");
  host.innerHTML = GOLDEN_TARGETS[name] as string;
  document.body.appendChild(host);
  return host.querySelector("#t") as HTMLElement;
}

export function* goldenCases(): Generator<GoldenCase> {
  for (const key of GOLDEN_KEYS) for (const mods of GOLDEN_MODS) for (const target of Object.keys(GOLDEN_TARGETS)) for (const flags of GOLDEN_FLAGS) {
    yield { id: `${key === " " ? "Space" : key}|${mods}|${target}|${flags}`, key, mods, target, flags };
  }
}

export function eventFor(c: GoldenCase, target: EventTarget) {
  const m = c.mods.split("+");
  return {
    key: c.key, ctrlKey: m.includes("ctrl"), metaKey: m.includes("meta"), altKey: m.includes("alt"), shiftKey: m.includes("shift"),
    repeat: c.flags === "repeat", isComposing: c.flags === "composing", defaultPrevented: c.flags === "prevented", target,
  };
}
