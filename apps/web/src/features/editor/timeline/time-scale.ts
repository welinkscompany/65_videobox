export type RationalFps = Readonly<{
  num: number;
  den: number;
}>;

export type TimelineScale = Readonly<{
  pixelsPerSecond: number;
  originSec: number;
}>;

export type TimeRange = Readonly<{
  startSec: number;
  endSec: number;
}>;

function requireFinite(value: number): void {
  if (!Number.isFinite(value)) {
    throw new RangeError("Expected a finite number");
  }
}

function requireFps(fps: RationalFps): void {
  if (!fps || !Number.isSafeInteger(fps.num) || fps.num <= 0 || !Number.isSafeInteger(fps.den) || fps.den <= 0) {
    throw new RangeError("FPS numerator and denominator must be positive safe integers");
  }
}

function requireScale(scale: TimelineScale): void {
  if (!scale || !Number.isFinite(scale.pixelsPerSecond) || scale.pixelsPerSecond <= 0 || !Number.isFinite(scale.originSec)) {
    throw new RangeError("Timeline scale must have positive finite pixelsPerSecond and finite originSec");
  }
}

export function frameToSeconds(frame: number, fps: RationalFps): number {
  if (!Number.isSafeInteger(frame) || frame < 0) {
    throw new RangeError("Frame must be a nonnegative safe integer");
  }
  requireFps(fps);
  const seconds = (frame * fps.den) / fps.num;
  requireFinite(seconds);
  return seconds;
}

export function secondsToFrameHalfUp(seconds: number, fps: RationalFps): number {
  requireFinite(seconds);
  if (seconds < 0) {
    throw new RangeError("Seconds must be nonnegative");
  }
  requireFps(fps);

  const rawFrames = (seconds * fps.num) / fps.den;
  requireFinite(rawFrames);
  if (rawFrames < 0) {
    throw new RangeError("Raw frame count must be nonnegative");
  }

  const wholeFrames = Math.trunc(rawFrames);
  if (!Number.isSafeInteger(wholeFrames)) {
    throw new RangeError("Whole frame count must be a safe integer");
  }
  const fractionalFrames = rawFrames - wholeFrames;
  const frame = fractionalFrames >= 0.5 ? wholeFrames + 1 : wholeFrames;
  if (!Number.isSafeInteger(frame)) {
    throw new RangeError("Rounded frame must be a safe integer");
  }
  return frame;
}

export function quantizeToFrame(seconds: number, fps: RationalFps): number {
  return frameToSeconds(secondsToFrameHalfUp(seconds, fps), fps);
}

export function timeToPixels(time: number, scale: TimelineScale): number {
  requireFinite(time);
  requireScale(scale);
  const pixels = (time - scale.originSec) * scale.pixelsPerSecond;
  requireFinite(pixels);
  return pixels;
}

export function pixelsToTime(pixel: number, scale: TimelineScale): number {
  requireFinite(pixel);
  requireScale(scale);
  const time = pixel / scale.pixelsPerSecond + scale.originSec;
  requireFinite(time);
  return time;
}

export function zoomAroundAnchor(
  scale: TimelineScale,
  anchorPixel: number,
  nextPixelsPerSecond: number,
): TimelineScale {
  requireScale(scale);
  requireFinite(anchorPixel);
  if (!Number.isFinite(nextPixelsPerSecond) || nextPixelsPerSecond <= 0) {
    throw new RangeError("Pixels per second must be positive and finite");
  }

  const oldAnchorTime = pixelsToTime(anchorPixel, scale);
  const originSec = oldAnchorTime - anchorPixel / nextPixelsPerSecond;
  requireFinite(originSec);
  return {
    pixelsPerSecond: nextPixelsPerSecond,
    originSec,
  };
}

export function clampTime(time: number, range: TimeRange): number {
  requireFinite(time);
  if (!range || !Number.isFinite(range.startSec) || !Number.isFinite(range.endSec) || range.startSec > range.endSec) {
    throw new RangeError("Time range must contain finite ordered bounds");
  }
  return Math.min(Math.max(time, range.startSec), range.endSec);
}
