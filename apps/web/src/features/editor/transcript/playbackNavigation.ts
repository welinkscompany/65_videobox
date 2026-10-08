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

/** 한 프레임의 길이(초). */
export function frameDurationSec(fps: Readonly<{ num: number; den: number }>): number {
  if (!(fps.num > 0) || !(fps.den > 0)) throw new RangeError("fps must be positive");
  return fps.den / fps.num;
}

/** 화면 클릭 처리기용: 잘못된 fps여도 던지지 않고 30fps 한 프레임으로 본다. */
export function safeFrameDurationSec(fps: Readonly<{ num: number; den: number }>, fallbackSec = 1 / 30): number {
  try { return frameDurationSec(fps); } catch { return fallbackSec; }
}

/**
 * 재생 시각에서 고를 장면. **방금 누른 장면이 먼저다**(2026-10-08 점검 §3-1).
 * 재생기는 장면 시작으로 옮겨도 그보다 아주 조금 작은 시각(백만분의 1초·프레임 버림)을
 * 알려 온다. 그 시각으로 다시 찾으면 앞 장면이 잡혀 속도가 엉뚱한 장면에 들어갔다.
 */
export function resolvePlaybackSelection(
  segments: readonly TimedSegment[],
  seconds: number,
  options: Readonly<{ pinnedSegmentId: string | null; frameSec: number }>,
): string | null {
  finite(seconds, "Playback seconds");
  const { pinnedSegmentId, frameSec } = options;
  const pinned = pinnedSegmentId === null ? undefined : segments.find((segment) => segment.segmentId === pinnedSegmentId);
  if (pinned && pinned.startSec - frameSec <= seconds && seconds < pinned.endSec) return pinned.segmentId;
  const half = frameSec / 2;
  return segments.find((segment) => segment.startSec - half <= seconds && seconds < segment.endSec - half)?.segmentId
    ?? activeSegmentIdAt(segments, seconds);
}
