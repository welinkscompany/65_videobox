import { describe, expect, it } from "vitest";

import { extractTitleSuggestions } from "./titleSuggestions";

describe("유진의 답에서 고를 수 있는 제목만 골라내기", () => {
  it("번호가 붙은 줄만 후보로 삼고 앞뒤 인사말은 버린다", () => {
    const answer = [
      "좋아요! 이런 제목은 어떠세요?",
      "",
      "1. 출근길에 만난 작은 행복",
      "2. 매일 아침 같은 길 다른 이야기",
      "3) 5분이면 끝나는 아침 준비",
      "",
      "마음에 드는 게 있으면 말씀해 주세요.",
    ].join("\n");

    expect(extractTitleSuggestions(answer)).toEqual([
      "출근길에 만난 작은 행복",
      "매일 아침 같은 길 다른 이야기",
      "5분이면 끝나는 아침 준비",
    ]);
  });

  it("가운뎃점이나 하이픈으로 나열한 목록도 읽는다", () => {
    const answer = ["- 겨울 바다 혼자 걷기", "• 아무도 없는 새벽 바다"].join("\n");

    expect(extractTitleSuggestions(answer)).toEqual(["겨울 바다 혼자 걷기", "아무도 없는 새벽 바다"]);
  });

  it("따옴표로 감싼 제목은 따옴표를 벗겨서 돌려준다", () => {
    const answer = ['1. "출근길 브이로그"', "2. 「조용한 아침」"].join("\n");

    expect(extractTitleSuggestions(answer)).toEqual(["출근길 브이로그", "조용한 아침"]);
  });

  it("목록이 아예 없으면 따옴표 안의 문구를 후보로 본다", () => {
    const answer = '제목은 "출근길 브이로그" 정도가 어울릴 것 같아요.';

    expect(extractTitleSuggestions(answer)).toEqual(["출근길 브이로그"]);
  });

  it("같은 제목이 두 번 나와도 한 번만 보여 준다", () => {
    const answer = ["1. 같은 제목", "2. 같은 제목", "3. 다른 제목"].join("\n");

    expect(extractTitleSuggestions(answer)).toEqual(["같은 제목", "다른 제목"]);
  });

  it("제목이라기엔 너무 긴 설명 문장은 후보에서 뺀다", () => {
    const long = "가".repeat(80);
    const answer = [`1. ${long}`, "2. 짧은 제목"].join("\n");

    expect(extractTitleSuggestions(answer)).toEqual(["짧은 제목"]);
  });

  it("고를 것이 없으면 빈 목록을 돌려준다", () => {
    expect(extractTitleSuggestions("지금은 답하기 어려워요.")).toEqual([]);
    expect(extractTitleSuggestions("")).toEqual([]);
  });

  it("너무 많이 나열해도 여섯 개까지만 보여 준다", () => {
    const answer = Array.from({ length: 12 }, (_, index) => `${index + 1}. 제목 ${index + 1}`).join("\n");

    expect(extractTitleSuggestions(answer)).toHaveLength(6);
  });
});
