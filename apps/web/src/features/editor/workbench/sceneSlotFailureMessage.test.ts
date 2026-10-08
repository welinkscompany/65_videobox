import { describe, expect, it } from "vitest";

import { ApiRequestError } from "../../../api";
import { sceneSlotFailureMessage } from "./sceneSlotFailureMessage";

describe("되살릴 자리가 막혔을 때 안내", () => {
  it("서버 사유 코드를 창작자 말로 옮긴다", () => {
    const error = new ApiRequestError("segment_restore_overlaps_neighbour", 400, "/cut-action");
    expect(sceneSlotFailureMessage(error)).toBe("옆 장면이 이 자리를 쓰고 있어요. 옆 장면을 줄이거나 되돌리기를 눌러 주세요.");
    expect(sceneSlotFailureMessage("segment_restore_overlaps_neighbour")).toContain("옆 장면");
  });

  it("다른 오류는 null이라 일반 안내로 간다", () => {
    expect(sceneSlotFailureMessage(new ApiRequestError("boom", 500, "/x"))).toBeNull();
    expect(sceneSlotFailureMessage(null)).toBeNull();
  });
});
