import { describe, expect, it } from "vitest";
import golden from "./editorShortcuts.golden.json";
import { editorShortcutFor } from "./editorShortcuts";
import { eventFor, goldenCases, makeTarget, type GoldenCase } from "./editorShortcutsGoldenMatrix";

// editorShortcuts.golden.json = 합치기 전 옛 처리기 셋(재생·자르기/되돌리기·줌)이 이 입력 그물에서 낸 결과.
// 키 "키|조합|자리|상태" -> 명령, 표에 없는 칸은 null. 옛 처리기에서 시험으로 뽑아 그대로 굳혔다.
const expected = golden as Record<string, string>;

/** 합치면서 일부러 바뀐 칸 -- 전부 "예전엔 했는데 이제 안 한다" 방향이다(null로만 바뀐다). */
function intendedChange(c: GoldenCase, was: string): string | null {
  // 1) 서랍(aria-modal) 안에서 Delete/Backspace가 장면을 지우던 것 (Plan P2 C1, 의도).
  if (was === "delete" && (c.target === "modal" || c.target === "modalButton")) return "서랍 안 Delete";
  // 2) 꾹 누른 Delete/Ctrl+B는 반복하지 않는다 (예전 자르기 처리기에는 repeat 검사가 없었다).
  if ((was === "delete" || was === "split") && c.flags === "repeat") return "꾹 누름 반복 안 함";
  // 3) 한글 조합 중·이미 막힌 키는 모두 비킨다 (예전엔 재생 처리기만 그랬다).
  if (c.flags === "composing" || c.flags === "prevented") return "조합 중·이미 막힘";
  // 4) 시험 환경(jsdom)에는 isContentEditable이 없어 옛 작업판 가드가 글칸으로 못 알아봤다. 브라우저에서는 옛 가드도 막았다.
  if (c.target === "editable") return "jsdom 글칸 가짜 허용";
  return null;
}

/** 계획 P2 Task 4가 **새로 더한** 캡컷 키들 -- 옛 처리기에는 없던 키라 옛 표에서는 null이었다. 이 여섯 명령 말고는 늘어나면 안 된다. */
const ADDED_IDS = new Set(["trim-left", "trim-right", "prev-cut", "next-cut", "go-start", "go-end"]);
function addedKey(c: GoldenCase, now: string): string | null {
  if (ADDED_IDS.has(now)) return "새 캡컷 키";
  // 맨 Shift+Z -> 전체 보기 (Ctrl+0은 옛 표에도 있었다).
  if (now === "zoom-fit" && c.key.toLowerCase() === "z" && c.mods === "shift") return "새 캡컷 키";
  return null;
}

describe("옛 동작 골든 표", () => {
  it("그물의 모든 칸이 옛 동작과 같다 (의도된 차이는 이름을 달아 허용)", () => {
    const unexplained: string[] = [];
    const explained: Record<string, number> = {};
    let total = 0;
    for (const c of goldenCases()) {
      total += 1;
      const now = editorShortcutFor(eventFor(c, makeTarget(c.target)));
      const was = expected[c.id] ?? null;
      if (now === was) continue;
      const reason = was !== null && now === null ? intendedChange(c, was) : was === null && now !== null ? addedKey(c, now) : null;
      if (reason) explained[reason] = (explained[reason] ?? 0) + 1;
      else unexplained.push(`${c.id}: ${was} -> ${now}`);
    }
    expect(total).toBeGreaterThan(10000);
    expect(unexplained).toEqual([]);
    // 허용 사유 넷이 실제로 닿아야 한다(헛 허용 방지).
    expect(Object.keys(explained).sort()).toEqual(["jsdom 글칸 가짜 허용", "꾹 누름 반복 안 함", "서랍 안 Delete", "조합 중·이미 막힘", "새 캡컷 키"].sort());
  });
});
