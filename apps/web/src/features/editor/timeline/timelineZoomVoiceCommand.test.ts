import { describe, expect, it } from "vitest";

import { timelineZoomCommandFromInstruction } from "./timelineZoomVoiceCommand";

describe("유진 채팅으로 타임라인 늘리기·줄이기", () => {
  it("대표님 예시 문장을 그대로 받는다", () => {
    // 브리프(task-3-brief.md)의 예시 두 문장.
    expect(timelineZoomCommandFromInstruction("타임라인 좀 늘려줘")).toBe("in");
    expect(timelineZoomCommandFromInstruction("전체가 보이게 해줘")).toBe("fit");
  });

  it("줄이기·확대·축소·줌 표현도 받는다", () => {
    expect(timelineZoomCommandFromInstruction("타임라인 좀 줄여줘")).toBe("out");
    expect(timelineZoomCommandFromInstruction("타임라인 확대해줘")).toBe("in");
    expect(timelineZoomCommandFromInstruction("타임라인 축소해줘")).toBe("out");
    expect(timelineZoomCommandFromInstruction("타임라인 전체 보기")).toBe("fit");
    expect(timelineZoomCommandFromInstruction("줌인 해줘")).toBe("in");
    expect(timelineZoomCommandFromInstruction("줌 아웃 해줘")).toBe("out");
  });

  it("타임라인을 말하지 않은 다른 편집 요청은 건드리지 않는다", () => {
    // "늘려줘"·"확대해줘"만으로 잡으면 장면 길이(`set_segment_bounds`)나
    // 장면 화면 자체의 확대(`set_scene_transform`)를 가로챈다 -- 둘 다
    // `타임라인`이라는 말을 쓰지 않는다.
    expect(timelineZoomCommandFromInstruction("이 장면 3초까지 늘려줘")).toBeNull();
    expect(timelineZoomCommandFromInstruction("화면 확대해줘")).toBeNull();
    expect(timelineZoomCommandFromInstruction("두 번째 장면을 빠르게")).toBeNull();
  });

  it("빈 말이나 잘못된 입력은 조용히 흘려보낸다", () => {
    expect(timelineZoomCommandFromInstruction("")).toBeNull();
    expect(timelineZoomCommandFromInstruction("   ")).toBeNull();
    expect(timelineZoomCommandFromInstruction(null as unknown as string)).toBeNull();
  });
});
