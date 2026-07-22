import {
  frameToSeconds,
  secondsToFrameHalfUp,
  type RationalFps,
} from "./time-scale";

export type NarrationSegment = Readonly<{
  segmentId: string;
  startSec: number;
  endSec: number;
}>;

export type NarrationBounds = Readonly<{
  startSec: number;
  endSec: number;
}>;

export type NarrationTrimInput = Readonly<{
  clip: NarrationSegment;
  edge: "start" | "end";
  proposedSec: number;
  narration: readonly NarrationSegment[];
  durationSec: number;
  fps: RationalFps;
}>;

export type NarrationReorderInput = Readonly<{
  narration: readonly NarrationSegment[];
  movingId: string;
  targetIndex: number;
}>;

export type NarrationReorderLayout = Readonly<{
  segmentIds: string[];
  boundsById: Record<string, NarrationBounds>;
}>;

function requireSegmentId(value: string, name: string): void {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new RangeError(`${name} must be a nonempty string`);
  }
}

function requireFinite(value: number, name: string): void {
  if (!Number.isFinite(value)) {
    throw new RangeError(`${name} must be finite`);
  }
}

function compareNarration(a: NarrationSegment, b: NarrationSegment): number {
  if (a.startSec !== b.startSec) {
    return a.startSec - b.startSec;
  }
  return a.segmentId < b.segmentId ? -1 : a.segmentId > b.segmentId ? 1 : 0;
}

function frameAtOrAfter(seconds: number, fps: RationalFps): number {
  const nearestFrame = secondsToFrameHalfUp(seconds, fps);
  const frame = frameToSeconds(nearestFrame, fps) < seconds ? nearestFrame + 1 : nearestFrame;
  if (!Number.isSafeInteger(frame)) {
    throw new RangeError("Frame must be a nonnegative safe integer");
  }
  return frame;
}

function frameAtOrBefore(seconds: number, fps: RationalFps): number {
  const nearestFrame = secondsToFrameHalfUp(seconds, fps);
  const frame = frameToSeconds(nearestFrame, fps) > seconds ? nearestFrame - 1 : nearestFrame;
  if (!Number.isSafeInteger(frame) || frame < 0) {
    throw new RangeError("Frame must be a nonnegative safe integer");
  }
  return frame;
}

function validateNarration(narration: readonly NarrationSegment[]): NarrationSegment[] {
  if (!Array.isArray(narration) || narration.length === 0) {
    throw new RangeError("Narration must be a nonempty array");
  }
  for (let index = 0; index < narration.length; index += 1) {
    if (!(index in narration)) {
      throw new RangeError("Narration must not contain sparse entries");
    }
  }

  const seen = new Set<string>();
  const copied = narration.map((segment) => {
    if (!segment) {
      throw new RangeError("Narration segment is required");
    }
    requireSegmentId(segment.segmentId, "Narration segment id");
    requireFinite(segment.startSec, "Narration start");
    requireFinite(segment.endSec, "Narration end");
    if (segment.startSec < 0 || segment.endSec <= segment.startSec || seen.has(segment.segmentId)) {
      throw new RangeError("Narration segments must have unique nonempty ids and positive finite durations");
    }
    seen.add(segment.segmentId);
    return { ...segment };
  });

  copied.sort(compareNarration);
  for (let index = 1; index < copied.length; index += 1) {
    if (copied[index - 1].endSec > copied[index].startSec) {
      throw new RangeError("Narration segments must not overlap");
    }
  }
  return copied;
}

export function deriveNarrationTrim(input: NarrationTrimInput): NarrationBounds {
  if (!input || !input.clip || (input.edge !== "start" && input.edge !== "end")) {
    throw new RangeError("Narration trim input is invalid");
  }
  requireSegmentId(input.clip.segmentId, "Clip id");
  requireFinite(input.clip.startSec, "Clip start");
  requireFinite(input.clip.endSec, "Clip end");
  requireFinite(input.proposedSec, "Proposed trim");
  requireFinite(input.durationSec, "Timeline duration");
  if (input.durationSec <= 0) {
    throw new RangeError("Timeline duration must be positive");
  }

  const sorted = validateNarration(input.narration);
  if (sorted.some((segment) => segment.endSec > input.durationSec)) {
    throw new RangeError("Narration segments must be within the timeline duration");
  }
  const clipIndex = sorted.findIndex((segment) => segment.segmentId === input.clip.segmentId);
  if (clipIndex === -1) {
    throw new RangeError("Clip id must exist in narration");
  }
  const clip = sorted[clipIndex];
  if (clip.startSec !== input.clip.startSec || clip.endSec !== input.clip.endSec) {
    throw new RangeError("Clip bounds must match narration");
  }

  const proposedFrame = secondsToFrameHalfUp(
    Math.min(Math.max(input.proposedSec, 0), input.durationSec),
    input.fps,
  );

  if (input.edge === "start") {
    const minimumStartFrame = clipIndex === 0
      ? 0
      : frameAtOrAfter(sorted[clipIndex - 1].endSec, input.fps);
    const endFrame = frameAtOrBefore(clip.endSec, input.fps);
    const maximumStartFrame = endFrame - 1;
    if (minimumStartFrame > maximumStartFrame) {
      throw new RangeError("Narration clip cannot retain one frame within its neighbours");
    }
    return {
      startSec: frameToSeconds(Math.min(Math.max(proposedFrame, minimumStartFrame), maximumStartFrame), input.fps),
      endSec: frameToSeconds(endFrame, input.fps),
    };
  }

  const startFrame = frameAtOrAfter(clip.startSec, input.fps);
  const minimumEndFrame = startFrame + 1;
  const maximumEndFrame = clipIndex === sorted.length - 1
    ? frameAtOrBefore(input.durationSec, input.fps)
    : frameAtOrBefore(sorted[clipIndex + 1].startSec, input.fps);
  if (minimumEndFrame > maximumEndFrame) {
    throw new RangeError("Narration clip cannot retain one frame within its neighbours");
  }
  return {
    startSec: frameToSeconds(startFrame, input.fps),
    endSec: frameToSeconds(Math.min(Math.max(proposedFrame, minimumEndFrame), maximumEndFrame), input.fps),
  };
}

export function reorderNarrationLayout(input: NarrationReorderInput): NarrationReorderLayout {
  if (!input) {
    throw new RangeError("Narration reorder input is required");
  }
  requireSegmentId(input.movingId, "Moving segment id");
  if (!Number.isSafeInteger(input.targetIndex)) {
    throw new RangeError("Target index must be a safe integer");
  }

  const sorted = validateNarration(input.narration);
  if (input.targetIndex < 0 || input.targetIndex >= sorted.length) {
    throw new RangeError("Target index must be within narration");
  }
  const movingIndex = sorted.findIndex((segment) => segment.segmentId === input.movingId);
  if (movingIndex === -1) {
    throw new RangeError("Moving segment id must exist in narration");
  }

  const [moving] = sorted.splice(movingIndex, 1);
  sorted.splice(input.targetIndex, 0, moving);

  let cursorSec = Math.min(...input.narration.map((segment) => segment.startSec));
  const boundsById: Record<string, NarrationBounds> = {};
  for (const segment of sorted) {
    const durationSec = segment.endSec - segment.startSec;
    const endSec = cursorSec + durationSec;
    if (!Number.isFinite(endSec)) {
      throw new RangeError("Reordered narration bounds must be finite");
    }
    boundsById[segment.segmentId] = { startSec: cursorSec, endSec };
    cursorSec = endSec;
  }

  return {
    segmentIds: sorted.map((segment) => segment.segmentId),
    boundsById,
  };
}
