import { TIMELINE_LANES, type TimelineLane } from "./timeline-geometry";

export type HitRect = Readonly<{
  clipId: string;
  lane: TimelineLane;
  x: number;
  y: number;
  width: number;
  height: number;
  zIndex: number;
}>;

export type TimelineHit =
  | Readonly<{ kind: "edge"; edge: "start" | "end"; clipId: string }>
  | Readonly<{ kind: "body"; clipId: string }>
  | Readonly<{ kind: "gap"; lane: TimelineLane }>
  | Readonly<{ kind: "empty" }>;

export type TimelineHitInput = Readonly<{
  point: Readonly<{ x: number; y: number }>;
  lane?: TimelineLane;
  edgeHandlePx: number;
  selectedClipId?: string;
  rects: readonly HitRect[];
}>;

function requireFinite(value: number, name: string): void {
  if (!Number.isFinite(value)) {
    throw new RangeError(`${name} must be finite`);
  }
}

function isTimelineLane(value: unknown): value is TimelineLane {
  return typeof value === "string" && (TIMELINE_LANES as readonly string[]).includes(value);
}

function requireInput(input: TimelineHitInput): void {
  if (!input || !input.point) {
    throw new RangeError("Hit input and point are required");
  }
  requireFinite(input.point.x, "Point x");
  requireFinite(input.point.y, "Point y");
  requireFinite(input.edgeHandlePx, "Edge handle size");
  if (input.edgeHandlePx <= 0) {
    throw new RangeError("Edge handle size must be positive");
  }
  if (input.lane !== undefined && !isTimelineLane(input.lane)) {
    throw new RangeError("Hit lane must be valid");
  }
  if (input.selectedClipId !== undefined
    && (typeof input.selectedClipId !== "string" || input.selectedClipId.trim().length === 0)) {
    throw new RangeError("Selected clipId must be nonempty");
  }
  if (!Array.isArray(input.rects)) {
    throw new RangeError("Rects must be an array");
  }

  const clipIds = new Set<string>();
  for (const rect of input.rects) {
    if (!rect || typeof rect.clipId !== "string" || rect.clipId.length === 0) {
      throw new RangeError("Rect clipId must be nonempty");
    }
    if (!isTimelineLane(rect.lane)) {
      throw new RangeError("Rect lane must be valid");
    }
    if (clipIds.has(rect.clipId)) {
      throw new RangeError("Rect clipIds must be unique");
    }
    clipIds.add(rect.clipId);
    requireFinite(rect.x, "Rect x");
    requireFinite(rect.y, "Rect y");
    requireFinite(rect.width, "Rect width");
    requireFinite(rect.height, "Rect height");
    requireFinite(rect.zIndex, "Rect zIndex");
    if (rect.width <= 0 || rect.height <= 0) {
      throw new RangeError("Rect width and height must be positive");
    }
  }
}

function containsPoint(rect: HitRect, point: TimelineHitInput["point"]): boolean {
  return point.x >= rect.x
    && point.x <= rect.x + rect.width
    && point.y >= rect.y
    && point.y <= rect.y + rect.height;
}

function compareBodyPriority(left: HitRect, right: HitRect): number {
  if (left.zIndex !== right.zIndex) {
    return right.zIndex - left.zIndex;
  }
  if (left.clipId < right.clipId) {
    return -1;
  }
  if (left.clipId > right.clipId) {
    return 1;
  }
  return 0;
}

export function classifyTimelineHit(input: TimelineHitInput): TimelineHit {
  requireInput(input);

  const selectedRect = input.selectedClipId === undefined
    ? undefined
    : input.rects.find((rect) => rect.clipId === input.selectedClipId);
  if (selectedRect
    && (input.lane === undefined || selectedRect.lane === input.lane)
    && containsPoint(selectedRect, input.point)) {
    const edgeWidth = Math.min(input.edgeHandlePx, selectedRect.width);
    if (input.point.x <= selectedRect.x + edgeWidth) {
      return { kind: "edge", edge: "start", clipId: selectedRect.clipId };
    }
    if (input.point.x >= selectedRect.x + selectedRect.width - edgeWidth) {
      return { kind: "edge", edge: "end", clipId: selectedRect.clipId };
    }
  }

  if (input.lane !== undefined) {
    const body = input.rects
      .filter((rect) => rect.lane === input.lane && containsPoint(rect, input.point))
      .sort(compareBodyPriority)[0];
    if (body) {
      return { kind: "body", clipId: body.clipId };
    }
    return { kind: "gap", lane: input.lane };
  }

  return { kind: "empty" };
}
