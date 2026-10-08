import { findTimelineSnap, type SnapCandidate, type TimelineSnap } from "./snapping";
import type { RationalFps, TimelineScale } from "./time-scale";

export type DragSnapInput = Readonly<{
  mode: "move" | "start" | "end";
  /** move면 새 시작, start/end면 그 가장자리. */
  proposedSec: number;
  /** move에서만 쓴다(클립 길이). */
  durationSec: number;
  candidates: readonly SnapCandidate[];
  /** 끄는 클립 자신의 후보(`clip:${clipId}:`)를 뺀다. 빈 문자열이면 거르지 않는다. */
  excludeIdPrefix: string;
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
  const candidates = input.excludeIdPrefix
    ? input.candidates.filter((candidate) => !candidate.id.startsWith(input.excludeIdPrefix))
    : input.candidates;
  const find = (proposedSec: number) => findTimelineSnap({
    candidates,
    proposedSec,
    thresholdPx: input.thresholdPx,
    scale: input.scale,
    fps: input.fps,
  });
  if (input.proposedSec < 0) return { proposedSec: input.proposedSec, snap: null };

  if (input.mode !== "move") {
    const snap = find(input.proposedSec);
    return snap ? { proposedSec: snap.timeSec, snap } : { proposedSec: input.proposedSec, snap: null };
  }

  const startSnap = find(input.proposedSec);
  const endSnap = find(input.proposedSec + input.durationSec);
  const startGap = startSnap ? Math.abs(startSnap.timeSec - input.proposedSec) : Infinity;
  const endGap = endSnap ? Math.abs(endSnap.timeSec - (input.proposedSec + input.durationSec)) : Infinity;
  if (endSnap && endGap < startGap) {
    return { proposedSec: Math.max(0, endSnap.timeSec - input.durationSec), snap: endSnap };
  }
  if (startSnap) return { proposedSec: startSnap.timeSec, snap: startSnap };
  return { proposedSec: input.proposedSec, snap: null };
}
