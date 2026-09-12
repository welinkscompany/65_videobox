import { describe, expect, it } from "vitest";

import { shortFormPickNotice } from "./shortFormNotice";

/** 2026-09-12: 유진이 댄 **"왜 퍼질까"** 한 줄이 화면 문구까지 가야 한다.
 *
 * 값만 만들고 아무도 안 읽으면 배선이 아니다. 이 문구를 만드는 자리가 하나이고
 * (`shortFormNotice.ts`), 숏폼 만들기·다시 만들기·유진에게 말해서 다시 만들기
 * 셋이 전부 이 함수를 지난다.
 */
describe("shortFormPickNotice", () => {
  it("유진이 댄 퍼질 이유를 문구에 싣는다", () => {
    const notice = shortFormPickNotice(
      {
        judged_by: "yujin",
        notice: "유진이 전사의 말을 전 구간 읽고 퍼질 만한 대목으로 숏폼을 골랐어요.",
        scenes_total: 94,
        scenes_read_by_yujin: 94,
        spread_reason: "대놓고 솔직한 한마디로 시작해서 매출 결과로 닫혀요",
      },
      { remade: false },
    );

    expect(notice).toContain("대놓고 솔직한 한마디로 시작해서 매출 결과로 닫혀요");
    expect(notice).toContain("퍼질");
  });

  it("이유가 없으면 지어내지 않는다", () => {
    const notice = shortFormPickNotice(
      {
        judged_by: "caption_density",
        notice: "유진이 지금 도와줄 수 없어서, 자막이 많은 장면 위주로 골랐어요.",
        scenes_total: 3,
        scenes_read_by_yujin: 0,
        spread_reason: null,
      },
      { remade: false },
    );

    expect(notice).not.toContain("퍼질 이유");
    expect(notice).toContain("자막이 많은 장면");
  });

  it("옛 서버 응답(이유 칸이 없음)에도 유진을 들먹이지 않는다", () => {
    const notice = shortFormPickNotice(undefined, { remade: true });

    expect(notice).toContain("숏폼을 다시 만들었어요");
    expect(notice).not.toContain("유진");
  });
});
