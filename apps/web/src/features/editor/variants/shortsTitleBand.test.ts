import { describe, expect, it } from "vitest";

import type { OutputVariant } from "../../../api";
import { shortsTitleBand, shortsTitleBandPatch } from "./shortsTitleBand";

function variant(layout: Record<string, unknown> | null): OutputVariant {
  return {
    variant_id: "v1",
    kind: "vertical_highlight",
    source_session_id: "s1",
    source_session_revision: 1,
    variant_revision: 1,
    overrides: { crop: null, focal: null, caption: null, safe_area: null, audio: null, layout },
    locks: [],
    conflicts: [],
  } as unknown as OutputVariant;
}

describe("숏폼 첫 화면 제목 띠", () => {
  it("아직 제목이 없으면 지어내지 않는다", () => {
    expect(shortsTitleBand(variant(null))).toBeNull();
    expect(shortsTitleBand(variant({ title_lines: [] }))).toBeNull();
    expect(shortsTitleBand(variant({ hidden: true }))).toBeNull();
  });

  it("껐어도 문구는 남아 있다 -- 지우면 다시 켤 때 되돌릴 것이 없다", () => {
    const band = shortsTitleBand(variant({
      title_lines: ["10년 팔아 본 사람이 말하는", "재고가 안 남는 이유"],
      highlight: "재고",
      hidden: true,
    }));
    expect(band).toEqual({
      lines: ["10년 팔아 본 사람이 말하는", "재고가 안 남는 이유"],
      highlight: "재고",
      hidden: true,
    });
  });

  it("끄기·켜기 patch가 문구를 그대로 싣는다", () => {
    const band = shortsTitleBand(variant({ title_lines: ["훅", "결과"], highlight: "결과" }))!;

    expect(shortsTitleBandPatch(band, { hidden: true })).toEqual({
      overrides: { layout: { title_lines: ["훅", "결과"], highlight: "결과", hidden: true } },
    });
    expect(shortsTitleBandPatch({ ...band, hidden: true }, { hidden: false })).toEqual({
      overrides: { layout: { title_lines: ["훅", "결과"], highlight: "결과", hidden: false } },
    });
  });
});
