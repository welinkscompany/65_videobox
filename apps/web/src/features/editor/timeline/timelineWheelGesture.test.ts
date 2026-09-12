import { describe, expect, it } from "vitest";

import { timelineWheelGestureFor } from "./timelineWheelGesture";

function wheel(overrides: Partial<Parameters<typeof timelineWheelGestureFor>[0]> = {}) {
  return {
    deltaX: 0,
    deltaY: 0,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    ...overrides,
  };
}

describe("timelineWheelGestureFor", () => {
  it("늘린다 -- Ctrl과 바퀴를 위로", () => {
    expect(timelineWheelGestureFor(wheel({ ctrlKey: true, deltaY: -120 }), false)).toEqual({ kind: "zoom", command: "in" });
  });

  it("줄인다 -- Ctrl과 바퀴를 아래로", () => {
    expect(timelineWheelGestureFor(wheel({ ctrlKey: true, deltaY: 120 }), false)).toEqual({ kind: "zoom", command: "out" });
  });

  it("맥에서도 같다 -- Cmd와 바퀴", () => {
    expect(timelineWheelGestureFor(wheel({ metaKey: true, deltaY: -120 }), false)).toEqual({ kind: "zoom", command: "in" });
    expect(timelineWheelGestureFor(wheel({ metaKey: true, deltaY: 120 }), false)).toEqual({ kind: "zoom", command: "out" });
  });

  it("옆으로 미는 바퀴만 와도 Ctrl이면 늘리고 줄인다", () => {
    expect(timelineWheelGestureFor(wheel({ ctrlKey: true, deltaX: -40 }), false)).toEqual({ kind: "zoom", command: "in" });
    expect(timelineWheelGestureFor(wheel({ ctrlKey: true, deltaX: 40 }), false)).toEqual({ kind: "zoom", command: "out" });
  });

  it("Ctrl만 누르고 바퀴를 안 돌리면 아무 일도 없다", () => {
    expect(timelineWheelGestureFor(wheel({ ctrlKey: true }), false)).toBeNull();
  });

  it("Shift와 바퀴는 옆으로 민다 -- 세로 바퀴가 가로 이동이 된다", () => {
    expect(timelineWheelGestureFor(wheel({ shiftKey: true, deltaY: 120 }), false)).toEqual({ kind: "scroll", deltaPx: 120 });
    expect(timelineWheelGestureFor(wheel({ shiftKey: true, deltaY: -120 }), false)).toEqual({ kind: "scroll", deltaPx: -120 });
  });

  it("Shift와 바퀴인데 가로 값만 오면 그 값을 쓴다", () => {
    expect(timelineWheelGestureFor(wheel({ shiftKey: true, deltaX: 50 }), false)).toEqual({ kind: "scroll", deltaPx: 50 });
  });

  it("맨 바퀴의 가로 값은 예전 그대로 옆으로 민다", () => {
    expect(timelineWheelGestureFor(wheel({ deltaX: 50 }), false)).toEqual({ kind: "scroll", deltaPx: 50 });
  });

  it("맨 바퀴의 세로 값은 가로채지 않는다 -- 타임라인 칸이 위아래로 스크롤되던 것을 지킨다", () => {
    expect(timelineWheelGestureFor(wheel({ deltaY: 120 }), false)).toBeNull();
  });

  it("Alt가 눌린 조합은 다른 뜻이라 가로채지 않는다", () => {
    expect(timelineWheelGestureFor(wheel({ altKey: true, ctrlKey: true, deltaY: -120 }), false)).toBeNull();
    expect(timelineWheelGestureFor(wheel({ altKey: true, shiftKey: true, deltaY: 120 }), false)).toBeNull();
  });

  it("글을 쓰는 칸 위에서는 가로채지 않는다", () => {
    expect(timelineWheelGestureFor(wheel({ ctrlKey: true, deltaY: -120 }), true)).toBeNull();
    expect(timelineWheelGestureFor(wheel({ shiftKey: true, deltaY: 120 }), true)).toBeNull();
    expect(timelineWheelGestureFor(wheel({ deltaX: 50 }), true)).toBeNull();
  });

  it("Ctrl과 Shift가 같이 눌리면 늘리고 줄이는 쪽이 이긴다 -- 브라우저와 같다", () => {
    expect(timelineWheelGestureFor(wheel({ ctrlKey: true, shiftKey: true, deltaY: -120 }), false)).toEqual({ kind: "zoom", command: "in" });
  });
});
