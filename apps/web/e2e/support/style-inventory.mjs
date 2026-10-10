// 계산 스타일 수집 도우미 (계획 I Task 0). 화면을 누르지 않고 읽기만 한다.
// 기준선(Task 0)·계산 스타일 게이트(Task 12)·무반응 스모크(Task 13)·클릭 지도(Task 14)가 같은 함수를 쓴다.

export const CONTROL_SELECTOR = [
  "button",
  "[role=tab]",
  "[role=menuitem]",
  "[role=option]",
  "select",
  "input:not([type=hidden]):not([type=range]):not([type=checkbox]):not([type=radio]):not([type=file])",
  "textarea",
].join(", ");

/**
 * 브라우저 안에서 도는 수집 본문. 따로 export 해서 내장 브라우저(javascript_tool)에 그대로 붙여 넣을 수도 있다.
 * @param {string} controlSelector
 */
export function inventoryInPage(controlSelector) {
  const firstFont = (value) => (value.split(",")[0] ?? "").trim().replace(/^["']|["']$/g, "");
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none";
  };
  const selectorOf = (el) => {
    const parts = [];
    let node = el;
    for (let depth = 0; node && node.nodeType === 1 && depth < 3; depth += 1) {
      const slot = node.getAttribute("data-slot");
      const cls = [...node.classList].filter((c) => c.startsWith("vb-")).slice(0, 2).join(".");
      parts.unshift(node.tagName.toLowerCase() + (slot ? `[data-slot=${slot}]` : "") + (cls ? `.${cls}` : ""));
      node = node.parentElement;
    }
    return parts.join(" > ");
  };
  const nameOf = (el) => {
    const label = el.getAttribute("aria-label") || el.getAttribute("title");
    if (label) return label.trim();
    const text = (el.innerText || el.value || el.getAttribute("placeholder") || "").replace(/\s+/g, " ").trim();
    return text.slice(0, 60);
  };

  const controls = [];
  for (const el of document.querySelectorAll(controlSelector)) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    controls.push({
      name: nameOf(el),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role"),
      h: Math.round(r.height * 10) / 10,
      w: Math.round(r.width * 10) / 10,
      fontFamily: firstFont(s.fontFamily),
      fontSize: parseFloat(s.fontSize),
      fontWeight: Number(s.fontWeight),
      radius: s.borderTopLeftRadius,
      variant: el.getAttribute("data-variant"),
      size: el.getAttribute("data-size"),
      disabled: el.disabled === true || el.getAttribute("aria-disabled") === "true",
      hasReason: el.hasAttribute("title") || el.hasAttribute("aria-describedby"),
      primary: el.hasAttribute("data-primary-action"),
      selector: selectorOf(el),
    });
  }

  // 글자 칸: 자기 직속 글자 노드가 있는 보이는 요소의 계산 글자 크기.
  const texts = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const parent = node.parentElement;
    if (!parent || seen.has(parent)) continue;
    if (parent.closest("script, style, noscript")) continue;
    const sample = (node.nodeValue || "").replace(/\s+/g, " ").trim();
    if (!sample) continue;
    if (!visible(parent)) continue;
    seen.add(parent);
    const s = getComputedStyle(parent);
    texts.push({ fontSize: parseFloat(s.fontSize), fontWeight: Number(s.fontWeight), fontFamily: firstFont(s.fontFamily), sample: sample.slice(0, 40) });
  }

  return {
    path: location.pathname + location.search,
    viewport: { w: window.innerWidth, h: window.innerHeight },
    docScrollWidth: document.documentElement.scrollWidth,
    docClientWidth: document.documentElement.clientWidth,
    controls,
    texts,
  };
}

/** @param {import("@playwright/test").Page} page @returns {Promise<StyleInventory>} */
export async function collectStyleInventory(page) {
  return page.evaluate(inventoryInPage, CONTROL_SELECTOR);
}

/** 사람이 읽는 요약: 값별 개수. 기준선 표와 게이트가 같은 모양을 쓴다. */
export function summarizeInventory(inventory) {
  const tally = (values) => {
    const out = {};
    for (const value of values) out[value] = (out[value] ?? 0) + 1;
    return out;
  };
  const { controls, texts } = inventory;
  return {
    path: inventory.path,
    viewport: inventory.viewport,
    overflowX: inventory.docScrollWidth - inventory.docClientWidth,
    controlCount: controls.length,
    controlHeights: tally(controls.map((c) => Math.round(c.h))),
    controlFonts: tally(controls.map((c) => c.fontFamily)),
    controlFontSizes: tally(controls.map((c) => c.fontSize)),
    controlRadii: tally(controls.map((c) => c.radius)),
    filledPrimaryButtons: controls.filter((c) => c.variant === "default").length,
    disabledWithoutReason: controls.filter((c) => c.disabled && !c.hasReason).length,
    textFontSizes: tally(texts.map((t) => t.fontSize)),
    textFontWeights: tally(texts.map((t) => t.fontWeight)),
    textFontFamilies: tally(texts.map((t) => t.fontFamily)),
  };
}
