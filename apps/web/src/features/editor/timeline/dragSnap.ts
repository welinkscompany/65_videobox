import { findTimelineSnap, type SnapCandidate, type TimelineSnap } from "./snapping";
import type { RationalFps, TimelineScale } from "./time-scale";

export type DragSnapInput = Readonly<{
  mode: "move" | "start" | "end";
  /** move면 새 시작, start/end면 그 가장자리. */
  proposedSec: number;
  /** move에서만 쓴다(클립 길이). */
  durationSec: number;
  candidates: readonly SnapCandidate[];
  /** 끄는 클립들의 id. 그 클립 자신의 후보(`clip:${clipId}:…`)에는 붙지 않는다.
   *  비었거나 하나라도 못 찾았으면(undefined) 자기 가장자리를 구별할 수 없으니 붙이지 않는다. */
  draggedClipIds: readonly (string | undefined)[];
  /** 끄는 가장자리의 **처음 자리**(move·start는 처음 시작, end는 처음 끝). 거기 있는 후보는 뺀다 --
   *  제자리로 도로 붙으면 8px 안쪽 미세 조정이 안 된다. 끄는 가장자리가 아닌 쪽은 보지 않는다. */
  originalSec: number;
  scale: TimelineScale;
  fps: RationalFps;
  thresholdPx: number;
}>;

export type DragSnapResult = Readonly<{ proposedSec: number; snap: TimelineSnap | null }>;

/**
 * 끌거나 자르는 중의 제안 시각을 옆 클립의 시작·끝, 재생줄에 붙인다.
 * 옮길 때는 클립의 시작과 끝을 둘 다 대어 보고 더 가까운 쪽으로 시작을 옮긴다.
 * 붙지 않으면 제안을 그대로 돌려준다.
 */
export function snapDragProposal(input: DragSnapInput): DragSnapResult {
  const ids = input.draggedClipIds.filter((id): id is string => Boolean(id));
  if (ids.length === 0 || ids.length !== input.draggedClipIds.length) return { proposedSec: input.proposedSec, snap: null };
  const prefixes = ids.map((id) => `clip:${id}:`);
  const notOwn = input.candidates.filter((candidate) => !prefixes.some((prefix) => candidate.id.startsWith(prefix)));
  const halfFrameSec = input.fps.den / input.fps.num / 2;
  const find = (proposedSec: number, originalSec: number) => findTimelineSnap({
    candidates: notOwn.filter((candidate) => Math.abs(candidate.timeSec - originalSec) > halfFrameSec),
    proposedSec,
    thresholdPx: input.thresholdPx,
    scale: input.scale,
    fps: input.fps,
  });
  if (input.proposedSec < 0) return { proposedSec: input.proposedSec, snap: null };

  if (input.mode !== "move") {
    const snap = find(input.proposedSec, input.originalSec);
    return snap ? { proposedSec: snap.timeSec, snap } : { proposedSec: input.proposedSec, snap: null };
  }

  const startSnap = find(input.proposedSec, input.originalSec);
  const endSnap = find(input.proposedSec + input.durationSec, input.originalSec + input.durationSec);
  const startGap = startSnap ? Math.abs(startSnap.timeSec - input.proposedSec) : Infinity;
  const endGap = endSnap ? Math.abs(endSnap.timeSec - (input.proposedSec + input.durationSec)) : Infinity;
  if (endSnap && endGap < startGap) {
    return { proposedSec: Math.max(0, endSnap.timeSec - input.durationSec), snap: endSnap };
  }
  if (startSnap) return { proposedSec: startSnap.timeSec, snap: startSnap };
  return { proposedSec: input.proposedSec, snap: null };
}
