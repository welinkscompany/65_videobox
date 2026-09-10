import { timeToPixels, type TimelineScale } from "./time-scale";

export const TIMELINE_LANES = ["narration", "broll", "bgm", "sfx", "overlay", "caption"] as const;

export type TimelineLane = (typeof TIMELINE_LANES)[number];

export type TimelineClip = Readonly<{
  id: string;
  lane: TimelineLane;
  startSec: number;
  endSec: number;
  /** 어느 트랙 줄인가. 없으면 그 종류(`lane`)의 줄. 자유 멀티트랙 Phase 7. */
  trackId?: string;
}>;

/** 화면에 그릴 줄 목록(위에서 아래로). 안 주면 예전 고정 여섯 줄. */
export type TimelineRowKeys = readonly string[];

export type TimelineViewport = Readonly<{
  startSec: number;
  endSec: number;
}>;

export type TimelineGeometryViewport = TimelineViewport & Readonly<{
  topPx: number;
  heightPx: number;
}>;

export type ClipRect = Readonly<{
  clipId: string;
  lane: TimelineLane;
  x: number;
  y: number;
  width: number;
  height: number;
}>;

export type ClipNeighbors = Readonly<{
  previous?: TimelineClip;
  next?: TimelineClip;
}>;

function requireFinite(value: number, name: string): void {
  if (!Number.isFinite(value)) {
    throw new RangeError(`${name} must be finite`);
  }
}

function requireClip(clip: TimelineClip): void {
  if (!clip || typeof clip.id !== "string" || clip.id.trim().length === 0) {
    throw new RangeError("Clip id must be nonempty");
  }
  if (!(TIMELINE_LANES as readonly string[]).includes(clip.lane)) {
    throw new RangeError("Clip lane must be valid");
  }
  requireFinite(clip.startSec, "Clip startSec");
  requireFinite(clip.endSec, "Clip endSec");
  if (clip.endSec <= clip.startSec) {
    throw new RangeError("Clip endSec must be greater than startSec");
  }
}

function requireClips(clips: readonly TimelineClip[]): void {
  if (!Array.isArray(clips)) {
    throw new RangeError("Clips must be an array");
  }
  for (let index = 0; index < clips.length; index += 1) {
    const clip = clips[index];
    if (clip === undefined) {
      throw new RangeError("Clips must not contain empty slots");
    }
    requireClip(clip);
  }
}

function requireUniqueClipIds(clips: readonly TimelineClip[]): void {
  const ids = new Set<string>();
  for (const clip of clips) {
    if (ids.has(clip.id)) {
      throw new RangeError("Clip ids must be unique");
    }
    ids.add(clip.id);
  }
}

function requireViewport(viewport: TimelineViewport): void {
  if (!viewport) {
    throw new RangeError("Viewport is required");
  }
  requireFinite(viewport.startSec, "Viewport startSec");
  requireFinite(viewport.endSec, "Viewport endSec");
  if (viewport.endSec < viewport.startSec) {
    throw new RangeError("Viewport endSec must not be before startSec");
  }
}

function requireGeometryViewport(viewport: TimelineGeometryViewport): void {
  requireViewport(viewport);
  requireFinite(viewport.topPx, "Viewport topPx");
  requireFinite(viewport.heightPx, "Viewport heightPx");
  if (viewport.topPx < 0 || viewport.heightPx <= 0) {
    throw new RangeError("Viewport topPx must be nonnegative and heightPx must be positive");
  }
}

function requireLaneHeight(laneHeightPx: number): void {
  requireFinite(laneHeightPx, "Lane height");
  if (laneHeightPx <= 0) {
    throw new RangeError("Lane height must be positive");
  }
}

function requireScale(scale: TimelineScale): void {
  if (!scale || !Number.isFinite(scale.pixelsPerSecond) || scale.pixelsPerSecond <= 0 || !Number.isFinite(scale.originSec)) {
    throw new RangeError("Timeline scale must have positive finite pixelsPerSecond and finite originSec");
  }
}

export function selectVisibleClips(
  clips: readonly TimelineClip[],
  viewport: TimelineViewport,
): TimelineClip[] {
  requireClips(clips);
  requireViewport(viewport);
  if (viewport.startSec === viewport.endSec) {
    return [];
  }
  return clips.filter((clip) => clip.startSec < viewport.endSec && clip.endSec > viewport.startSec);
}

export function deriveClipRect(
  clip: TimelineClip,
  viewport: TimelineGeometryViewport,
  scale: TimelineScale,
  laneHeightPx: number,
  rows: TimelineRowKeys = TIMELINE_LANES,
): ClipRect | null {
  requireClip(clip);
  requireGeometryViewport(viewport);
  requireLaneHeight(laneHeightPx);
  requireScale(scale);

  const visibleStartSec = Math.max(clip.startSec, viewport.startSec);
  const visibleEndSec = Math.min(clip.endSec, viewport.endSec);
  if (visibleEndSec <= visibleStartSec) {
    return null;
  }

  // 트랙 이름표가 있으면 그 줄, 없거나 **모르는 이름표면 그 종류의 줄**로
  // 내린다. 지운 트랙의 이름표가 남아 있다는 이유만으로 작업판 전체가
  // 죽으면 안 된다(`requireClip`은 종류만 검사한다).
  const labelledIndex = clip.trackId === undefined ? -1 : rows.indexOf(clip.trackId);
  const laneIndex = labelledIndex === -1 ? rows.indexOf(clip.lane) : labelledIndex;
  if (laneIndex === -1) {
    return null;
  }
  const laneTopPx = laneIndex * laneHeightPx;
  const laneBottomPx = laneTopPx + laneHeightPx;
  const viewportBottomPx = viewport.topPx + viewport.heightPx;
  requireFinite(laneTopPx, "Lane topPx");
  requireFinite(laneBottomPx, "Lane bottomPx");
  requireFinite(viewportBottomPx, "Viewport bottomPx");

  const visibleTopPx = Math.max(laneTopPx, viewport.topPx);
  const visibleBottomPx = Math.min(laneBottomPx, viewportBottomPx);
  if (visibleBottomPx <= visibleTopPx) {
    return null;
  }

  const x = timeToPixels(visibleStartSec, scale);
  const endX = timeToPixels(visibleEndSec, scale);
  const width = endX - x;
  const height = visibleBottomPx - visibleTopPx;

  requireFinite(x, "Rectangle x");
  requireFinite(width, "Rectangle width");
  requireFinite(visibleTopPx, "Rectangle y");
  requireFinite(height, "Rectangle height");
  if (width <= 0 || height <= 0) {
    throw new RangeError("Rectangle width and height must be positive");
  }

  return {
    clipId: clip.id,
    lane: clip.lane,
    x,
    y: visibleTopPx,
    width,
    height,
  };
}

export function findClipNeighbors(
  clips: readonly TimelineClip[],
  clipId: string,
): ClipNeighbors {
  requireClips(clips);
  requireUniqueClipIds(clips);
  if (typeof clipId !== "string" || clipId.trim().length === 0) {
    throw new RangeError("Clip id must be nonempty");
  }

  const sortedClips = [...clips].sort((left, right) => {
    if (left.startSec !== right.startSec) {
      return left.startSec < right.startSec ? -1 : 1;
    }
    if (left.endSec !== right.endSec) {
      return left.endSec < right.endSec ? -1 : 1;
    }
    if (left.id === right.id) {
      return 0;
    }
    return left.id < right.id ? -1 : 1;
  });
  const index = sortedClips.findIndex((clip) => clip.id === clipId);
  if (index === -1) {
    throw new RangeError("Clip id was not found");
  }

  return {
    previous: sortedClips[index - 1],
    next: sortedClips[index + 1],
  };
}
