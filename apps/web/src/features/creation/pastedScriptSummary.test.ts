import { describe, expect, it } from "vitest";

import { pastedScriptSummary } from "./pastedScriptSummary";

describe("pastedScriptSummary", () => {
  it("uses the opening line, because that is what the creator already wrote", () => {
    // 대본을 이미 가진 사람에게 "요약을 한 줄 쓰세요"를 다시 묻지 않는다.
    // 지어내지도 않는다 -- 첫 문장은 창작자가 쓴 말 그대로다.
    expect(pastedScriptSummary("제주 바다는 아침이 가장 좋습니다.\n해가 뜨면 물빛이 바뀝니다."))
      .toBe("제주 바다는 아침이 가장 좋습니다.");
  });

  it("keeps a long opening readable instead of pasting a wall of text", () => {
    const long = "가".repeat(200);
    const summary = pastedScriptSummary(long);
    expect(summary.length).toBeLessThanOrEqual(80);
    expect(summary.endsWith("…")).toBe(true);
  });

  it("falls back to a plain label when there is nothing to read", () => {
    // 확정 화면이 빈 요약으로 막히면 안 된다. 사람이 고쳐 쓸 자리를 준다.
    expect(pastedScriptSummary("   ")).toBe("붙여넣은 대본");
    expect(pastedScriptSummary("")).toBe("붙여넣은 대본");
  });
});
