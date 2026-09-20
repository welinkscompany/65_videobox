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

  /** 2026-09-20 코드리뷰 후속(altitude): `find_audio_matches`/
   *  `find_footage_matches`가 이제 값이 태어나는 자리에서 관련도를 매겨
   *  보낸다(유진의 추천 경로도 같은 함수를 쓰므로 같은 신호를 받는다).
   *  화면은 그 값을 다시 계산하지 않고 그대로 믿는다 -- 두 곳에서 같은
   *  계산을 하면 나중에 갈라질 수 있다. */
  it("백엔드가 이미 매긴 relevance_percent가 있으면 다시 계산하지 않고 그대로 믿는다", () => {
    const result = withRelevance([
      // score만 보면 33%지만, 백엔드가 이미 자기 색인 안에서 100%라고
      // 매겨 보냈다 -- 화면은 이 값을 그대로 따라야 한다.
      match({ library_asset_id: "backend-said-100", media_type: "sfx", score: 0.3, semantic_match: true, relevance_percent: 100 }),
      match({ library_asset_id: "video-top", media_type: "broll", score: 0.9, semantic_match: true, relevance_percent: 100 }),
    ]);

    expect(result.map((item) => item.library_asset_id)).toEqual(["backend-said-100", "video-top"]);
    expect(result.find((item) => item.library_asset_id === "backend-said-100")?.relevance_percent).toBe(100);
  });

  /** 2026-09-20 코드리뷰 실측: 영상·그림(`find_footage_matches`)과
   *  음악·효과음(`find_audio_matches`)은 서로 다른 임베딩 색인을 쓴다 --
   *  코사인 점수 규모가 같다는 보장이 없다. "전체" 탭처럼 네 종류를 한 번에
   *  섞을 때, 한쪽 색인이 원래 더 높은 점수를 낸다는 이유만으로 다른 쪽
   *  전체가 조용히 사라지면 안 된다. */
  it("영상·그림과 음악·효과음은 서로 다른 임베딩 색인이라 관련도를 따로 잰다", () => {
    const result = withRelevance([
      match({ library_asset_id: "video-top", media_type: "broll", score: 0.9, semantic_match: true }),
      // sfx 0.3은 sfx 안에서는 최고점이다. 영상의 0.9와 비교해 33%로 접히면
      // 안 된다 -- 실제로는 정답이었을 수 있다.
      match({ library_asset_id: "sfx-top", media_type: "sfx", score: 0.3, semantic_match: true }),
    ]);

    expect(result.map((item) => item.library_asset_id)).toEqual(["video-top", "sfx-top"]);
    expect(result.find((item) => item.library_asset_id === "video-top")?.relevance_percent).toBe(100);
    expect(result.find((item) => item.library_asset_id === "sfx-top")?.relevance_percent).toBe(100);
  });

  it("음악과 효과음은 같은 색인을 쓰므로 서로 대비해서 관련도를 잰다", () => {
    const result = withRelevance([
      match({ library_asset_id: "music-top", media_type: "music", score: 0.5, semantic_match: true }),
      match({ library_asset_id: "sfx-far", media_type: "sfx", score: 0.05, semantic_match: true }),
    ]);

    expect(result.map((item) => item.library_asset_id)).toEqual(["music-top"]);
  });
});
