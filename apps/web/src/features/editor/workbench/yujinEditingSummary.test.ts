import { describe, expect, it } from "vitest";

import { yujinEditingOperationSummary } from "./yujinEditingSummary";

const summary = (operation: Record<string, unknown>) =>
  yujinEditingOperationSummary(operation as never);

describe("유진이 한 일 한 줄", () => {
  it("사진을 얹으면 고른 것까지 말한다", () => {
    expect(summary({
      intent: "set_image_overlay", segment_id: "s1", asset_id: "a1",
      vertical: "top", horizontal: "right", size: "small", motion: "fade_in",
    })).toBe("사진을 화면 위에 얹어요 (위 · 오른쪽 · 작게 · 천천히 나타나기).");
  });

  it("안 고른 것은 말하지 않는다", () => {
    expect(summary({ intent: "set_image_overlay", segment_id: "s1", asset_id: "a1" }))
      .toBe("사진을 화면 위에 얹어요.");
  });

  it("빼는 것과 넣는 것을 구별한다", () => {
    expect(summary({ intent: "remove_image_overlay", segment_id: "s1" }))
      .toBe("화면 위에 얹은 사진을 빼요.");
  });

  it("장면 넘기기는 화면에 쓰는 이름으로 말한다", () => {
    expect(summary({ intent: "set_scene_transition", segment_id: "s1", transition: { type: "wipeleft" } }))
      .toBe("장면 넘기기를 왼쪽으로 쓸어내기(으)로 바꿔요.");
  });

  it("다듬기와 화면 맞춤도 제 이름이 있다", () => {
    expect(summary({ intent: "set_picture_cleanup", segment_id: "s1" })).toBe("화면을 다듬어요.");
    expect(summary({ intent: "set_sound_cleanup", segment_id: "s1" })).toBe("소리를 다듬어요.");
    expect(summary({ intent: "set_scene_transform", segment_id: "s1" })).toBe("화면 맞춤을 바꿔요.");
  });

  it("옛 명령들의 문구는 그대로다", () => {
    expect(summary({ intent: "set_scene_speed", segment_id: "s1", rate: 2 })).toBe("2배로 속도를 바꿔요.");
    expect(summary({ intent: "apply_media", segment_id: "s1", media_type: "sfx" })).toBe("골라 둔 효과음을 넣어요.");
    expect(summary({ intent: "remove_media", segment_id: "s1", media_type: "bgm" })).toBe("넣어 둔 배경 음악을 빼요.");
    expect(summary({ intent: "reorder_segments" })).toBe("장면 순서를 바꿔요.");
  });

  it("모르는 명령이 와도 화면이 멈추지 않는다", () => {
    expect(summary({ intent: "something_new" })).toBe("편집 항목을 바꿔요.");
  });
});
