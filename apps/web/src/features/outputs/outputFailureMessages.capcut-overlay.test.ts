import { describe, expect, it } from "vitest";

import { capcutDraftFailureMessage } from "./outputFailureMessages";

describe("CapCut으로 넘길 때 얹은 영상이 막힌 이유", () => {
  it("투명 모션은 할 수 있는 일을 알려 준다", () => {
    const message = capcutDraftFailureMessage("capcut_transparent_motion_unsupported");
    expect(message).toContain("투명 모션은 아직 캡컷으로 넘길 수 없어요");
    expect(message).toContain("얹기를 빼고");
  });
  it("얹는 구간이 영상보다 길 때도 코드를 그대로 띄우지 않는다", () => {
    const message = capcutDraftFailureMessage("capcut_overlay_shorter_than_window");
    expect(message).toContain("얹은 영상이 얹는 구간보다 짧아요");
    expect(message).not.toContain("capcut_");
  });
});
