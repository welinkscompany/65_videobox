import { describe, expect, it } from "vitest";
import { snapDragProposal, type DragSnapInput } from "./dragSnap";

const base: Omit<DragSnapInput, "mode" | "proposedSec" | "durationSec"> = {
  originalSec: 100, // 후보와 멀리 떨어진 처음 자리
  candidates: [
    { kind: "neighbor-end", id: "clip:a:end", timeSec: 24 },
    { kind: "neighbor-start", id: "clip:self:start", timeSec: 10 },
  ],
  draggedClipIds: ["self"],
  scale: { pixelsPerSecond: 20, originSec: 0 },
  fps: { num: 30, den: 1 },
  thresholdPx: 8,
};

describe("끌기 붙기 (스파이크 H-d)", () => {
  it("옮기기: 시작이 24초 끝에서 5px 안이면 24로 붙는다", () => {
    const result = snapDragProposal({ ...base, mode: "move", proposedSec: 24.2, durationSec: 9.93 });
    expect(result.proposedSec).toBe(24);
    expect(result.snap?.id).toBe("clip:a:end");
  });

  it("옮기기: 시작은 멀고 끝이 24.1이면 끝이 24에 붙도록 시작을 당긴다", () => {
    const result = snapDragProposal({ ...base, mode: "move", proposedSec: 14.17, durationSec: 9.93 });
    expect(result.proposedSec).toBeCloseTo(24 - 9.93, 9);
    expect(result.snap?.id).toBe("clip:a:end");
  });

  it("옮기기: 시작과 끝이 둘 다 닿으면 더 가까운 쪽을 따른다", () => {
    const candidates = [
      { kind: "neighbor-end" as const, id: "clip:a:end", timeSec: 10 },
      { kind: "neighbor-start" as const, id: "clip:b:start", timeSec: 20 },
    ];
    // 시작 10.3(0.3초), 끝 19.9(0.1초) -> 끝이 이긴다.
    const result = snapDragProposal({ ...base, candidates, mode: "move", proposedSec: 10.3, durationSec: 9.6 });
    expect(result.snap?.id).toBe("clip:b:start");
    expect(result.proposedSec).toBeCloseTo(10.4, 9);
  });

  it("끝 가장자리 자르기: 23.8이 24로 붙는다", () => {
    const result = snapDragProposal({ ...base, mode: "end", proposedSec: 23.8, durationSec: 0 });
    expect(result.proposedSec).toBe(24);
    expect(result.snap?.timeSec).toBe(24);
  });

  it("끄는 클립 자신의 가장자리에는 붙지 않는다", () => {
    const result = snapDragProposal({ ...base, mode: "start", proposedSec: 10.1, durationSec: 0 });
    expect(result.proposedSec).toBe(10.1);
    expect(result.snap).toBeNull();
  });

  it("임계 8px(0.4초) 밖이면 그대로", () => {
    const result = snapDragProposal({ ...base, mode: "end", proposedSec: 25.0, durationSec: 0 });
    expect(result.proposedSec).toBe(25);
    expect(result.snap).toBeNull();
  });

  it("임계는 화면 배율로 환산한다: 100px/초에서는 8px = 0.08초", () => {
    const scale = { pixelsPerSecond: 100, originSec: 0 };
    expect(snapDragProposal({ ...base, scale, mode: "end", proposedSec: 23.9, durationSec: 0 }).snap).toBeNull();
    expect(snapDragProposal({ ...base, scale, mode: "end", proposedSec: 23.95, durationSec: 0 }).proposedSec).toBe(24);
  });

  it("재생줄 후보에도 붙는다", () => {
    const candidates = [{ kind: "playhead" as const, id: "playhead", timeSec: 5 }];
    const result = snapDragProposal({ ...base, candidates, mode: "start", proposedSec: 5.2, durationSec: 0 });
    expect(result.proposedSec).toBe(5);
    expect(result.snap?.kind).toBe("playhead");
  });

  it("재생줄이 클립 처음 시작에 있어도 끝 가장자리는 거기에 붙는다(처음 끝이 아니므로)", () => {
    const candidates = [{ kind: "playhead" as const, id: "playhead", timeSec: 10 }];
    const result = snapDragProposal({ ...base, candidates, mode: "end", proposedSec: 10.2, durationSec: 0, originalSec: 14 });
    expect(result.proposedSec).toBe(10);
    expect(result.snap?.kind).toBe("playhead");
  });

  it("옮기기도: 재생줄이 클립 처음 시작에 있으면 처음 끝이 아니므로 끝이 거기로 붙을 수 있다", () => {
    const candidates = [{ kind: "playhead" as const, id: "playhead", timeSec: 20 }];
    // 클립 10~14 -> 시작 16.1로 끌면 끝 20.1이 재생줄(20)에 붙는다.
    const result = snapDragProposal({ ...base, candidates, mode: "move", proposedSec: 16.1, durationSec: 4, originalSec: 10 });
    expect(result.proposedSec).toBeCloseTo(16, 9);
  });

  it("제자리로는 도로 붙지 않는다: 처음 시작에 있는 재생줄 8px 안쪽에서 시작 자르기가 그대로 간다", () => {
    const candidates = [{ kind: "playhead" as const, id: "playhead", timeSec: 10 }];
    const result = snapDragProposal({ ...base, candidates, mode: "start", proposedSec: 10.3, durationSec: 0, originalSec: 10 });
    expect(result.proposedSec).toBe(10.3);
    expect(result.snap).toBeNull();
  });

  it("옮기기도 처음 시작·처음 끝 자리로는 도로 붙지 않는다", () => {
    const candidates = [
      { kind: "neighbor-end" as const, id: "clip:a:end", timeSec: 10 },
      { kind: "neighbor-start" as const, id: "clip:b:start", timeSec: 14 },
    ];
    const result = snapDragProposal({ ...base, candidates, mode: "move", proposedSec: 10.2, durationSec: 4, originalSec: 10 });
    expect(result.proposedSec).toBe(10.2);
    expect(result.snap).toBeNull();
  });

  it("끄는 클립이 여럿이면 모두의 접두사를 뺀다", () => {
    const candidates = [
      { kind: "neighbor-end" as const, id: "clip:x:end", timeSec: 30 },
      { kind: "neighbor-end" as const, id: "clip:y:end", timeSec: 31 },
    ];
    const result = snapDragProposal({ ...base, candidates, draggedClipIds: ["x", "y"], mode: "end", proposedSec: 30.1, durationSec: 0 });
    expect(result.snap).toBeNull();
  });

  it("끄는 클립을 못 찾으면(id 없음·빈 목록) 자기 가장자리를 구별할 수 없으니 붙이지 않는다", () => {
    const candidates = [{ kind: "neighbor-end" as const, id: "clip:self:end", timeSec: 24 }];
    for (const draggedClipIds of [[], [undefined], ["x", undefined]] as const) {
      const result = snapDragProposal({ ...base, candidates, draggedClipIds, mode: "end", proposedSec: 24.1, durationSec: 0 });
      expect(result).toEqual({ proposedSec: 24.1, snap: null });
    }
  });
});
