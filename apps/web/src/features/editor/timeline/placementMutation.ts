import { frameToSeconds, secondsToFrameHalfUp, type RationalFps } from "./time-scale";

export type TimelinePlacementKind = "broll" | "bgm" | "sfx" | "overlay" | "caption";
export type TimelinePlacement = Readonly<{ placementId: string; kind: TimelinePlacementKind; startSec: number; endSec: number }>;
export type TimelinePlacementBounds = Readonly<{ startSec: number; endSec: number }>;

function finite(value: number, name: string): void {
  if (!Number.isFinite(value)) throw new RangeError(`${name} must be finite`);
}

function validated(input: TimelinePlacement, durationSec: number): void {
  if (!input || !input.placementId.trim()) throw new RangeError("Placement id is required");
  finite(input.startSec, "Placement start"); finite(input.endSec, "Placement end"); finite(durationSec, "Timeline duration");
  if (input.startSec < 0 || input.endSec <= input.startSec || input.endSec > durationSec || durationSec <= 0) throw new RangeError("Placement bounds are invalid");
}

function boundedFrame(seconds: number, durationSec: number, fps: RationalFps): number {
  return Math.min(secondsToFrameHalfUp(durationSec, fps), Math.max(0, secondsToFrameHalfUp(seconds, fps)));
}

/** UI-only clamping; the server independently rejects malformed raw requests. */
export function derivePlacementMove(input: Readonly<{ placement: TimelinePlacement; proposedStartSec: number; durationSec: number; fps: RationalFps }>): TimelinePlacementBounds {
  validated(input.placement, input.durationSec); finite(input.proposedStartSec, "Proposed start");
  const spanFrames = secondsToFrameHalfUp(input.placement.endSec, input.fps) - secondsToFrameHalfUp(input.placement.startSec, input.fps);
  const maxStart = Math.max(0, secondsToFrameHalfUp(input.durationSec, input.fps) - spanFrames);
  const startFrame = Math.min(maxStart, Math.max(0, boundedFrame(input.proposedStartSec, input.durationSec, input.fps)));
  return { startSec: frameToSeconds(startFrame, input.fps), endSec: frameToSeconds(startFrame + spanFrames, input.fps) };
}

export function derivePlacementTrim(input: Readonly<{ placement: TimelinePlacement; edge: "start" | "end"; proposedSec: number; durationSec: number; fps: RationalFps }>): TimelinePlacementBounds {
  validated(input.placement, input.durationSec); finite(input.proposedSec, "Proposed trim");
  const startFrame = secondsToFrameHalfUp(input.placement.startSec, input.fps);
  const endFrame = secondsToFrameHalfUp(input.placement.endSec, input.fps);
  const proposed = boundedFrame(input.proposedSec, input.durationSec, input.fps);
  if (input.edge === "start") {
    return { startSec: frameToSeconds(Math.min(endFrame - 1, Math.max(0, proposed)), input.fps), endSec: frameToSeconds(endFrame, input.fps) };
  }
  return { startSec: frameToSeconds(startFrame, input.fps), endSec: frameToSeconds(Math.max(startFrame + 1, Math.min(secondsToFrameHalfUp(input.durationSec, input.fps), proposed)), input.fps) };
}
