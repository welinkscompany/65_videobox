import { describe, expect, it } from "vitest";

import { captionHead } from "./sceneNames";

describe("captionHead", () => {
  it("keeps the first sentence, short enough for one card line", () => {
    expect(captionHead("안녕하세요, 제주입니다")).toBe("안녕하세요, 제주입니다");
    expect(captionHead("오름에 올라 바다를 봅니다. 두 번째 문장은 잘립니다.")).toBe("오름에 올라 바다를 봅니다");
  });

  it("says nothing when the first sentence is only a list number", () => {
    // 실화면에서 나온 것: 대본을 번호 목록으로 붙여 넣으면 자막이 `1. 걷는 리듬…`이
    // 되고, 첫 문장만 자르면 카드에 `4번째 장면 · 1`이 남는다. 그건 장면 이름이 아니다.
    expect(captionHead("1. 걷는 리듬을 강조합니다")).toBe("걷는 리듬을 강조합니다");
    expect(captionHead("1")).toBe("");
    expect(captionHead("   ")).toBe("");
  });
});
