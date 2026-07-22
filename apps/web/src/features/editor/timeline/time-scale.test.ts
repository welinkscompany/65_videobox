import { describe, expect, it } from "vitest";
import {
  clampTime,
  frameToSeconds,
  pixelsToTime,
  quantizeToFrame,
  secondsToFrameHalfUp,
  timeToPixels,
  zoomAroundAnchor,
} from "./time-scale";

describe("time scale", () => {
  it("uses rational 30000/1001 half-up frame quantization", () => {
    const fps = { num: 30000, den: 1001 };
    const halfFrame = 1001 / 60000;

    expect(secondsToFrameHalfUp(halfFrame, fps)).toBe(1);
    expect(secondsToFrameHalfUp(halfFrame - Number.EPSILON, fps)).toBe(0);
    expect(frameToSeconds(1, fps)).toBe(1001 / 30000);
  });

  it("keeps half-up boundaries below one half-frame and at the largest safe frame", () => {
    const fps = { num: 1, den: 1 };

    expect(secondsToFrameHalfUp(0.49999999999999994, fps)).toBe(0);
    expect(secondsToFrameHalfUp(0.5, fps)).toBe(1);
    expect(secondsToFrameHalfUp(Number.MAX_SAFE_INTEGER, fps)).toBe(Number.MAX_SAFE_INTEGER);
  });

  it("converts 24fps frames and seconds without rounding", () => {
    const fps = { num: 24, den: 1 };

    expect(frameToSeconds(12, fps)).toBe(0.5);
    expect(secondsToFrameHalfUp(0.5, fps)).toBe(12);
    expect(secondsToFrameHalfUp(0.51, fps)).toBe(12);
  });

  it("rejects invalid frame, second, and frame-rate inputs", () => {
    const validFps = { num: 24, den: 1 };

    expect(() => frameToSeconds(-1, validFps)).toThrow(RangeError);
    expect(() => frameToSeconds(1.5, validFps)).toThrow(RangeError);
    expect(() => frameToSeconds(Number.MAX_SAFE_INTEGER + 1, validFps)).toThrow(RangeError);
    expect(() => frameToSeconds(1, { num: 0, den: 1 })).toThrow(RangeError);
    expect(() => frameToSeconds(1, { num: 24, den: 1.5 })).toThrow(RangeError);
    expect(() => secondsToFrameHalfUp(-0.01, validFps)).toThrow(RangeError);
    expect(() => secondsToFrameHalfUp(Number.POSITIVE_INFINITY, validFps)).toThrow(RangeError);
    expect(() => secondsToFrameHalfUp(Number.MAX_VALUE, validFps)).toThrow(RangeError);
  });

  it("keeps repeated frame quantization drift-free", () => {
    const fps = { num: 30000, den: 1001 };
    const once = quantizeToFrame(1.234567, fps);

    expect(quantizeToFrame(once, fps)).toBe(once);
    expect(quantizeToFrame(quantizeToFrame(once, fps), fps)).toBe(once);
  });

  it("round-trips timeline pixels and time", () => {
    const scale = { pixelsPerSecond: 80, originSec: -1.25 };
    const time = 2.75;
    const pixel = timeToPixels(time, scale);

    expect(pixelsToTime(pixel, scale)).toBeCloseTo(time, 12);
  });

  it("preserves the anchor time while zooming", () => {
    const scale = { pixelsPerSecond: 100, originSec: 2 };
    const anchorPixel = 250;
    const oldAnchorTime = pixelsToTime(anchorPixel, scale);
    const zoomed = zoomAroundAnchor(scale, anchorPixel, 160);

    expect(pixelsToTime(anchorPixel, zoomed)).toBeCloseTo(oldAnchorTime, 12);
    expect(zoomed.pixelsPerSecond).toBe(160);
  });

  it("rejects nonfinite transform results from finite inputs", () => {
    expect(() => zoomAroundAnchor(
      { pixelsPerSecond: Number.MAX_VALUE, originSec: 0 },
      Number.MAX_VALUE,
      Number.MIN_VALUE,
    )).toThrow(RangeError);
    expect(() => timeToPixels(Number.MAX_VALUE, { pixelsPerSecond: 1, originSec: -Number.MAX_VALUE })).toThrow(RangeError);
    expect(() => pixelsToTime(Number.MAX_VALUE, { pixelsPerSecond: Number.MIN_VALUE, originSec: 0 })).toThrow(RangeError);
  });

  it("allows finite zoom-origin cancellation", () => {
    const zoomed = zoomAroundAnchor(
      { pixelsPerSecond: 1, originSec: 0 },
      Number.MAX_VALUE,
      1,
    );

    expect(zoomed.originSec).toBe(0);
    expect(Number.isFinite(zoomed.originSec)).toBe(true);
  });

  it("rejects invalid timeline scale, coordinates, and ranges", () => {
    const validScale = { pixelsPerSecond: 100, originSec: 0 };

    expect(() => timeToPixels(Number.NaN, validScale)).toThrow(RangeError);
    expect(() => timeToPixels(1, { pixelsPerSecond: 0, originSec: 0 })).toThrow(RangeError);
    expect(() => pixelsToTime(Number.NEGATIVE_INFINITY, validScale)).toThrow(RangeError);
    expect(() => pixelsToTime(1, { pixelsPerSecond: 100, originSec: Number.NaN })).toThrow(RangeError);
    expect(() => zoomAroundAnchor(validScale, Number.NaN, 200)).toThrow(RangeError);
    expect(() => zoomAroundAnchor(validScale, 1, 0)).toThrow(RangeError);
    expect(() => clampTime(Number.NaN, { startSec: 0, endSec: 1 })).toThrow(RangeError);
    expect(() => clampTime(0, { startSec: 2, endSec: 1 })).toThrow(RangeError);
    expect(() => clampTime(0, { startSec: 0, endSec: Number.POSITIVE_INFINITY })).toThrow(RangeError);
  });

  it("clamps time to finite ordered bounds", () => {
    const range = { startSec: 2, endSec: 5 };

    expect(clampTime(1, range)).toBe(2);
    expect(clampTime(3, range)).toBe(3);
    expect(clampTime(6, range)).toBe(5);
  });
});
