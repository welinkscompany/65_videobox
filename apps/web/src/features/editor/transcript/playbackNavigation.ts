export type TimedSegment = Readonly<{ segmentId: string; startSec: number; endSec: number }>;

function finite(value: number, name: string): void {
  if (!Number.isFinite(value)) throw new RangeError(`${name} must be finite`);
}

export function clampPlaybackSeconds(seconds: number, durationSec: number): number {
  finite(seconds, "Playback seconds"); finite(durationSec, "Duration");
  if (durationSec < 0) throw new RangeError("Duration must be nonnegative");
  return Math.min(durationSec, Math.max(0, seconds));
}

export function activeSegmentIdAt(segments: readonly TimedSegment[], seconds: number): string | null {
  finite(seconds, "Playback seconds");
  return segments.find((segment) => segment.startSec <= seconds && seconds < segment.endSec)?.segmentId ?? null;
}
