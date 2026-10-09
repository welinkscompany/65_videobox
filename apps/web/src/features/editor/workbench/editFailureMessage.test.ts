import { describe, expect, it } from "vitest";

import { ApiRequestError } from "../../../api";
import { editFailureMessage } from "./editFailureMessage";

const fail = (detail: string | null, status = 400) => new ApiRequestError(detail, status, "/x", detail);

describe("editFailureMessage", () => {
  it("영상 길이 밖 자리는 그렇게 말한다", () => {
    expect(editFailureMessage(fail("timeline_placement_out_of_range"))).toBe("영상 길이 밖으로는 옮길 수 없어요.");
  });

  it("한 프레임보다 짧은 자르기", () => {
    expect(editFailureMessage(fail("timeline_placement_frame_span_invalid"))).toBe("한 프레임보다 짧게는 자를 수 없어요.");
  });

  it("그 밖의 자리 거절은 되돌리기를 안내한다", () => {
    expect(editFailureMessage(fail("timeline_placement_kind_mismatch"))).toBe("이 자리는 지금 저장할 수 없어요. 되돌리기를 누른 뒤 다시 해 주세요.");
  });

  it("같은 조각이 겹친 자리", () => {
    expect(editFailureMessage(fail("timeline_placement_duplicate"))).toContain("두 번");
  });

  it("장면 편집 거절 이유", () => {
    expect(editFailureMessage(fail("segment_restore_overlaps_neighbour"))).toContain("옆 장면");
    expect(editFailureMessage(fail("segment_split_ripple_removed"))).toContain("당겨서 뺀 장면");
    expect(editFailureMessage(fail("segment_ripple_playback_rate_below_minimum_duration"))).toContain("배속");
    expect(editFailureMessage(fail("Split must leave at least 0.2 seconds on both sides."))).toContain("0.2초");
    expect(editFailureMessage(fail("Segment duration must be at least 0.2 seconds."))).toContain("0.2초");
  });

  it("다른 곳이 먼저 저장한 충돌(409)", () => {
    expect(editFailureMessage(fail("stale", 409))).toBe("다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.");
  });

  it("모르는 이유는 null", () => {
    expect(editFailureMessage(fail("boom", 500))).toBeNull();
    expect(editFailureMessage(fail(null, 500))).toBeNull();
    expect(editFailureMessage(new Error("x"))).toBeNull();
    expect(editFailureMessage(null)).toBeNull();
  });
});
