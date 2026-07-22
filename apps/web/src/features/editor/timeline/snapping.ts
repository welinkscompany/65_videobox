import {
  frameToSeconds,
  pixelsToTime,
  secondsToFrameHalfUp,
  type RationalFps,
  type TimelineScale,
} from "./time-scale";

export type SnapCandidateKind = "playhead" | "selected-start" | "selected-end" | "neighbor-start" | "neighbor-end";

export type SnapCandidate = Readonly<{
  kind: SnapCandidateKind;
  id: string;
  timeSec: number;
}>;

export type TimelineSnapRequest = Readonly<{
  candidates: readonly SnapCandidate[];
  proposedSec: number;
  thresholdPx: number;
  scale: TimelineScale;
  fps: RationalFps;
}>;

export type TimelineSnap = Readonly<{
  timeSec: number;
  kind: SnapCandidateKind;
  id: string;
  frame: number;
}>;

type QuantizedCandidate = Readonly<{
  kind: SnapCandidateKind;
  id: string;
  rawTimeSec: number;
  timeSec: number;
  frame: number;
}>;

const KIND_RANK: Readonly<Record<SnapCandidateKind, number>> = {
  playhead: 0,
  "selected-start": 1,
  "selected-end": 2,
  "neighbor-start": 3,
  "neighbor-end": 4,
};

function compareNumbers(left: number, right: number): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function compareCodeUnits(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function isSnapCandidateKind(value: unknown): value is SnapCandidateKind {
  return typeof value === "string" && Object.prototype.hasOwnProperty.call(KIND_RANK, value);
}

function requireCandidate(candidate: unknown): asserts candidate is SnapCandidate {
  if (!candidate || typeof candidate !== "object") {
    throw new RangeError("Snap candidate must be an object");
  }

  const { kind, id, timeSec } = candidate as SnapCandidate;
  if (!isSnapCandidateKind(kind) || typeof id !== "string" || id.length === 0 || !Number.isFinite(timeSec) || timeSec < 0) {
    throw new RangeError("Snap candidate must have a known kind, nonempty string ID, and nonnegative finite time");
  }
}

function requireRequest(request: TimelineSnapRequest): number {
  if (!request || typeof request !== "object" || !Array.isArray(request.candidates)) {
    throw new RangeError("Snap request must include a candidate array");
  }
  if (!Number.isFinite(request.proposedSec) || request.proposedSec < 0) {
    throw new RangeError("Proposed time must be nonnegative and finite");
  }
  if (!Number.isFinite(request.thresholdPx) || request.thresholdPx < 0) {
    throw new RangeError("Snap threshold must be nonnegative and finite");
  }
  if (!request.scale || typeof request.scale !== "object") {
    throw new RangeError("Snap request must include a timeline scale");
  }

  secondsToFrameHalfUp(request.proposedSec, request.fps);
  return pixelsToTime(request.thresholdPx, {
    pixelsPerSecond: request.scale.pixelsPerSecond,
    originSec: 0,
  });
}

function compareDuplicateFrame(left: QuantizedCandidate, right: QuantizedCandidate): number {
  return compareNumbers(KIND_RANK[left.kind], KIND_RANK[right.kind])
    || compareCodeUnits(left.id, right.id)
    || compareNumbers(left.rawTimeSec, right.rawTimeSec);
}

function compareSnapCandidates(
  left: QuantizedCandidate,
  right: QuantizedCandidate,
  proposedFrame: number,
): number {
  return compareNumbers(Math.abs(left.frame - proposedFrame), Math.abs(right.frame - proposedFrame))
    || compareNumbers(KIND_RANK[left.kind], KIND_RANK[right.kind])
    || compareCodeUnits(left.id, right.id)
    || compareNumbers(left.timeSec, right.timeSec);
}

export function findTimelineSnap(request: TimelineSnapRequest): TimelineSnap | null {
  const thresholdSec = requireRequest(request);
  const candidatesByFrame = new Map<number, QuantizedCandidate>();

  for (const candidate of request.candidates) {
    requireCandidate(candidate);
    const frame = secondsToFrameHalfUp(candidate.timeSec, request.fps);
    const quantizedCandidate: QuantizedCandidate = {
      kind: candidate.kind,
      id: candidate.id,
      rawTimeSec: candidate.timeSec,
      timeSec: frameToSeconds(frame, request.fps),
      frame,
    };
    const existing = candidatesByFrame.get(frame);
    if (!existing || compareDuplicateFrame(quantizedCandidate, existing) < 0) {
      candidatesByFrame.set(frame, quantizedCandidate);
    }
  }

  const proposedFrame = (request.proposedSec * request.fps.num) / request.fps.den;
  let winner: QuantizedCandidate | null = null;
  for (const candidate of candidatesByFrame.values()) {
    const distanceSec = Math.abs(candidate.timeSec - request.proposedSec);
    if (request.thresholdPx === 0 && distanceSec !== 0) {
      continue;
    }
    const comparisonTolerance = Number.EPSILON * Math.max(1, candidate.timeSec, request.proposedSec, thresholdSec);
    if (request.thresholdPx > 0 && distanceSec > thresholdSec + comparisonTolerance) {
      continue;
    }
    if (!winner || compareSnapCandidates(candidate, winner, proposedFrame) < 0) {
      winner = candidate;
    }
  }

  return winner === null
    ? null
    : { timeSec: winner.timeSec, kind: winner.kind, id: winner.id, frame: winner.frame };
}
