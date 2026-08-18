import {
  clampTime,
  frameToSeconds,
  pixelsToTime,
  secondsToFrameHalfUp,
  timeToPixels,
  zoomAroundAnchor,
  type RationalFps,
} from "./time-scale";
import {
  deriveClipRect,
  selectVisibleClips,
  type ClipRect,
  type TimelineGeometryViewport,
  type TimelineLane,
} from "./timeline-geometry";

export type TimelineNavigationState = Readonly<{
  viewportStartSec: number;
  pixelsPerSecond: number;
  playheadSec: number;
  selectedClipId: string | null;
}>;

export type TimelineNavigationAction =
  | Readonly<{ type: "seek"; seconds: number }>
  | Readonly<{ type: "seek"; bound: "start" | "end" }>
  | Readonly<{ type: "scroll"; seconds: number }>
  | Readonly<{ type: "zoom"; pixelsPerSecond: number; anchorPx: number }>
  // 배율 형태. **누가 계산하느냐**가 다르다 -- 이쪽은 reducer가 자기 상태에서
  // 곱한다. 절대값으로 보내면 한 묶음 안에서 두 번 누른 순간 둘 다 같은 옛
  // 상태를 보고 계산해 두 번째가 첫 번째를 덮어쓴다(실제로 그랬다).
  | Readonly<{ type: "zoom"; factor: number; anchorPx?: number }>
  | Readonly<{ type: "select"; clipId: string | null }>;

export type TimelineNavigationOptions = Readonly<{
  durationSec: number;
  viewportWidthPx: number;
  fps: RationalFps;
}>;

export type TimelineNavigationKeyboardContext = Readonly<{
  state: TimelineNavigationState;
  fps: RationalFps;
  zoomFactor?: number;
}>;

export type TimelineSourceClip = Readonly<{
  id: string;
  role: TimelineLane;
  startSec: number;
  endSec: number;
}>;

export type TimelineProjectionInput = Readonly<{
  clips: readonly TimelineSourceClip[];
  viewport: TimelineGeometryViewport;
  pixelsPerSecond: number;
  originSec: number;
  laneHeightPx: number;
}>;

function requireFinite(value: number, name: string): void {
  if (!Number.isFinite(value)) {
    throw new RangeError(`${name} must be finite`);
  }
}

function requirePositive(value: number, name: string): void {
  requireFinite(value, name);
  if (value <= 0) {
    throw new RangeError(`${name} must be positive`);
  }
}

function requireDuration(durationSec: number): void {
  requireFinite(durationSec, "Duration");
  if (durationSec < 0) {
    throw new RangeError("Duration must be nonnegative");
  }
}

function requireSelectedClipId(selectedClipId: string | null): void {
  if (selectedClipId !== null && (typeof selectedClipId !== "string" || selectedClipId.trim().length === 0)) {
    throw new RangeError("Selected clip id must be a nonempty string or null");
  }
}

function requireState(state: TimelineNavigationState): void {
  if (!state) {
    throw new RangeError("Navigation state is required");
  }
  requireFinite(state.viewportStartSec, "Viewport start");
  requirePositive(state.pixelsPerSecond, "Pixels per second");
  requireFinite(state.playheadSec, "Playhead");
  requireSelectedClipId(state.selectedClipId);
}

function requireOptions(options: TimelineNavigationOptions): void {
  if (!options) {
    throw new RangeError("Navigation options are required");
  }
  requireDuration(options.durationSec);
  requireFinite(options.viewportWidthPx, "Viewport width");
  if (options.viewportWidthPx < 0) {
    throw new RangeError("Viewport width must be nonnegative");
  }
  frameToSeconds(0, options.fps);
}

function maximumViewportStart(durationSec: number, viewportWidthPx: number, pixelsPerSecond: number): number {
  const visibleDurationSec = pixelsToTime(viewportWidthPx, { pixelsPerSecond, originSec: 0 });
  const maximum = Math.max(0, durationSec - visibleDurationSec);
  requireFinite(maximum, "Maximum viewport start");
  return maximum;
}

function clampViewportStart(
  viewportStartSec: number,
  durationSec: number,
  viewportWidthPx: number,
  pixelsPerSecond: number,
): number {
  requireFinite(viewportStartSec, "Viewport start");
  return clampTime(viewportStartSec, {
    startSec: 0,
    endSec: maximumViewportStart(durationSec, viewportWidthPx, pixelsPerSecond),
  });
}

function normalizedState(state: TimelineNavigationState, options: TimelineNavigationOptions): TimelineNavigationState {
  return {
    viewportStartSec: clampViewportStart(
      state.viewportStartSec,
      options.durationSec,
      options.viewportWidthPx,
      state.pixelsPerSecond,
    ),
    pixelsPerSecond: state.pixelsPerSecond,
    playheadSec: clampTime(state.playheadSec, { startSec: 0, endSec: options.durationSec }),
    selectedClipId: state.selectedClipId,
  };
}

export function createTimelineNavigation(
  input: Readonly<{ durationSec: number; pixelsPerSecond: number }>,
): TimelineNavigationState {
  if (!input) {
    throw new RangeError("Navigation input is required");
  }
  requireDuration(input.durationSec);
  requirePositive(input.pixelsPerSecond, "Pixels per second");
  return {
    viewportStartSec: 0,
    pixelsPerSecond: input.pixelsPerSecond,
    playheadSec: 0,
    selectedClipId: null,
  };
}

export function reduceTimelineNavigation(
  state: TimelineNavigationState,
  action: TimelineNavigationAction,
  options: TimelineNavigationOptions,
): TimelineNavigationState {
  requireState(state);
  requireOptions(options);
  if (!action) {
    throw new RangeError("Navigation action is required");
  }
  const current = normalizedState(state, options);

  switch (action.type) {
    case "seek": {
      let playheadSec: number;
      if ("bound" in action) {
        if (action.bound !== "start" && action.bound !== "end") {
          throw new RangeError("Seek bound must be start or end");
        }
        playheadSec = action.bound === "start" ? 0 : options.durationSec;
      } else {
        playheadSec = action.seconds;
      }
      requireFinite(playheadSec, "Seek time");
      return { ...current, playheadSec: clampTime(playheadSec, { startSec: 0, endSec: options.durationSec }) };
    }
    case "scroll": {
      requireFinite(action.seconds, "Scroll target");
      return {
        ...current,
        viewportStartSec: clampViewportStart(
          action.seconds,
          options.durationSec,
          options.viewportWidthPx,
          current.pixelsPerSecond,
        ),
      };
    }
    case "zoom": {
      const scale = { pixelsPerSecond: current.pixelsPerSecond, originSec: current.viewportStartSec };
      const target = "factor" in action
        ? (requirePositive(action.factor, "Zoom factor"), current.pixelsPerSecond * action.factor)
        : action.pixelsPerSecond;
      // 배율로 온 경우 기준점도 여기서 잡는다. 화면 쪽에서 미리 잡아 두면 그 값도
      // 같은 이유로 낡는다.
      const anchorPx = action.anchorPx ?? timeToPixels(current.playheadSec, scale);
      requirePositive(target, "Pixels per second");
      requireFinite(anchorPx, "Anchor pixel");
      const nextScale = zoomAroundAnchor(scale, anchorPx, target);
      return {
        ...current,
        pixelsPerSecond: nextScale.pixelsPerSecond,
        viewportStartSec: clampViewportStart(
          nextScale.originSec,
          options.durationSec,
          options.viewportWidthPx,
          nextScale.pixelsPerSecond,
        ),
      };
    }
    case "select":
      requireSelectedClipId(action.clipId);
      return { ...current, selectedClipId: action.clipId };
    default:
      throw new RangeError("Unknown navigation action");
  }
}

export function navigationKeyAction(
  key: string,
  targetIsEditable: boolean,
  context: TimelineNavigationKeyboardContext,
): TimelineNavigationAction | null {
  if (typeof key !== "string" || typeof targetIsEditable !== "boolean" || !context) {
    throw new RangeError("Keyboard navigation input is invalid");
  }
  if (targetIsEditable) {
    return null;
  }
  requireState(context.state);
  const currentFrame = secondsToFrameHalfUp(context.state.playheadSec, context.fps);
  const zoomFactor = context.zoomFactor ?? 1.25;
  requirePositive(zoomFactor, "Zoom factor");
  switch (key) {
    case "ArrowLeft":
      return { type: "seek", seconds: frameToSeconds(Math.max(0, currentFrame - 1), context.fps) };
    case "ArrowRight":
      return { type: "seek", seconds: frameToSeconds(currentFrame + 1, context.fps) };
    case "Home":
      return { type: "seek", bound: "start" };
    case "End":
      return { type: "seek", bound: "end" };
    case "+":
      return { type: "zoom", factor: zoomFactor };
    case "-":
      return { type: "zoom", factor: 1 / zoomFactor };
    default:
      return null;
  }
}

export function projectVisibleTimelineClips(input: TimelineProjectionInput): ClipRect[] {
  if (!input) {
    throw new RangeError("Timeline projection input is required");
  }
  const visibleClips = selectVisibleClips(
    input.clips.map((clip) => ({
      id: clip.id,
      lane: clip.role,
      startSec: clip.startSec,
      endSec: clip.endSec,
    })),
    input.viewport,
  );
  const rects: ClipRect[] = [];
  for (const clip of visibleClips) {
    const rect = deriveClipRect(
      clip,
      input.viewport,
      { pixelsPerSecond: input.pixelsPerSecond, originSec: input.originSec },
      input.laneHeightPx,
    );
    if (rect) {
      rects.push(rect);
    }
  }
  return rects;
}
