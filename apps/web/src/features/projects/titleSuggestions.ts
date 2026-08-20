/** 유진의 답에서 **고를 수 있는 제목만** 골라낸다.
 *
 * 승인된 사람 게이트는 `제목 추천 -> [사람: 선택]`이다
 * (`docs/decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md`).
 * 그래서 여기가 하는 일은 후보를 **보여 줄 수 있게 다듬는 것**까지다. 고르는
 * 것도, 저장하는 것도 사람이 누른다.
 *
 * 답은 자유 문장이라 완벽히 읽어 낼 수 없다. 그래서 **덜 잡는 쪽**으로 기울인다 --
 * 번호나 기호로 나열한 줄만 후보로 본다. 인사말까지 제목이라고 내밀면 owner는
 * 목록 전체를 믿지 않게 된다.
 */

const LIST_MARKER = /^\s*(?:\d{1,2}\s*[.)\]、]|[-*•·–—])\s*(.+)$/;
const QUOTED_ANYWHERE = /[“"'「『]([^”"'」』\n]{2,60})[”"'」』]/g;
const QUOTE_PAIRS: readonly (readonly [string, string])[] = [
  ['"', '"'],
  ["'", "'"],
  ["“", "”"],
  ["‘", "’"],
  ["「", "」"],
  ["『", "』"],
];

const MAX_SUGGESTIONS = 6;
const MAX_TITLE_LENGTH = 60;
const MIN_TITLE_LENGTH = 2;

function unwrapQuotes(value: string): string {
  let current = value.trim();
  for (;;) {
    const pair = QUOTE_PAIRS.find(([open, close]) =>
      current.length > open.length + close.length && current.startsWith(open) && current.endsWith(close));
    if (!pair) return current;
    current = current.slice(pair[0].length, current.length - pair[1].length).trim();
  }
}

function usable(value: string): boolean {
  return value.length >= MIN_TITLE_LENGTH && value.length <= MAX_TITLE_LENGTH;
}

export function extractTitleSuggestions(answer: string): readonly string[] {
  const listed: string[] = [];
  for (const line of answer.split(/\r?\n/)) {
    const match = LIST_MARKER.exec(line);
    if (!match) continue;
    const candidate = unwrapQuotes(match[1]);
    if (usable(candidate)) listed.push(candidate);
  }

  // 목록이 아예 없을 때만 따옴표로 내려간다. 목록이 있는데도 본문의 따옴표를
  // 함께 담으면 설명 문구가 제목 사이에 섞여 들어간다.
  const found = listed.length > 0
    ? listed
    : Array.from(answer.matchAll(QUOTED_ANYWHERE), (match) => match[1].trim()).filter(usable);

  return Array.from(new Set(found)).slice(0, MAX_SUGGESTIONS);
}
