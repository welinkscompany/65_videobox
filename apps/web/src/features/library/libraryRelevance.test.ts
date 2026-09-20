import { describe, expect, it } from "vitest";

import type { LibraryAsset } from "../../api";
import { RELEVANCE_CUTOFF_PERCENT, withRelevance } from "./libraryRelevance";

function match(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  return {
    library_asset_id: "asset_1",
    media_type: "broll",
    origin: "user",
    lifecycle: "ready",
    ...overrides,
  };
}

describe("withRelevance", () => {
  /** 2026-08-31 실측: "공원" 검색에서 관련 있는 것과 없는 것이 전부
   *  0.44~0.49 사이에 몰려 있었다 -- 코사인 유사도는 "몇 % 확신"을 절대값으로
   *  말할 수 없다. 그래서 이번 검색의 최고점 대비 상대 퍼센트로 매긴다. */
  it("최고점을 100으로 두고 나머지를 그 대비 퍼센트로 매긴다 (컷오프 위)", () => {
    const result = withRelevance([
      match({ library_asset_id: "top", score: 0.49, semantic_match: true }),
      match({ library_asset_id: "seventy", score: 0.343, semantic_match: true }),
    ]);

    expect(result.find((item) => item.library_asset_id === "top")?.relevance_percent).toBe(100);
    expect(result.find((item) => item.library_asset_id === "seventy")?.relevance_percent).toBe(70);
  });

  it(`최고점 대비 ${RELEVANCE_CUTOFF_PERCENT}% 밑으로 떨어지는 결과는 접는다`, () => {
    const result = withRelevance([
      match({ library_asset_id: "top", score: 1, semantic_match: true }),
      match({ library_asset_id: "far", score: 0.1, semantic_match: true }),
    ]);

    expect(result.map((item) => item.library_asset_id)).toEqual(["top"]);
  });

  it("최고점 자신은 항상 남는다 -- 검색 결과가 0건이 되지 않는다", () => {
    const result = withRelevance([
      match({ library_asset_id: "only", score: 0.01, semantic_match: true }),
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].relevance_percent).toBe(100);
  });

  it("단어 매칭 행은 손대지 않는다 -- 비교할 점수 척도가 다르다", () => {
    const result = withRelevance([
      match({ library_asset_id: "semantic-top", score: 1, semantic_match: true }),
      match({ library_asset_id: "word-only", score: 0.5, semantic_match: false }),
    ]);

    expect(result.map((item) => item.library_asset_id)).toEqual(["semantic-top", "word-only"]);
    expect(result.find((item) => item.library_asset_id === "word-only")?.relevance_percent).toBeUndefined();
  });

  it("의미검색 행이 하나도 없으면 통째로 그대로 돌려준다", () => {
    const input = [match({ library_asset_id: "a", score: 0.9 }), match({ library_asset_id: "b", score: 0.1 })];
    expect(withRelevance(input)).toEqual(input);
  });
});
