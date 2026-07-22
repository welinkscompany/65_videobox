import { useMemo, useReducer, type KeyboardEvent, type MouseEvent, type WheelEvent } from "react";

import type { EditorViewModel } from "../editorViewModel";
import { classifyTimelineHit } from "./hit-testing";
import { findTimelineSnap, type SnapCandidate, type SnapCandidateKind } from "./snapping";
import { pixelsToTime } from "./time-scale";
import { TIMELINE_LANES, type ClipRect, type TimelineLane } from "./timeline-geometry";
import {
  createTimelineNavigation,
  navigationKeyAction,
  projectVisibleTimelineClips,
  reduceTimelineNavigation,
  type TimelineNavigationAction,
  type TimelineNavigationState,
} from "./timelineNavigation";

const LANE_HEIGHT_PX = 32;
const SNAP_THRESHOLD_PX = 8;

const laneLabel: Readonly<Record<TimelineLane, string>> = {
  narration: "내레이션",
  broll: "B-roll",
  bgm: "BGM",
  sfx: "효과음",
  overlay: "오버레이",
};

type Props = Readonly<{ view: EditorViewModel; viewportWidthPx: number }>;

function formatSeconds(seconds: number): string {
  return String(Number(seconds.toFixed(6)));
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || target.closest("input, textarea, select, [contenteditable='true']") !== null;
}

function clipSources(view: EditorViewModel) {
  return view.tracks.flatMap((track) => track.clips.map((clip) => ({
    id: clip.clipId,
    role: track.role,
    startSec: clip.startSec,
    endSec: clip.endSec,
  })));
}

const snapKindLabel: Readonly<Record<SnapCandidateKind, string>> = {
  playhead: "재생 위치",
  "selected-start": "선택 항목 시작",
  "selected-end": "선택 항목 끝",
  "neighbor-start": "항목 시작",
  "neighbor-end": "항목 끝",
};

function sourceSnapCandidates(view: EditorViewModel): readonly SnapCandidate[] {
  return Object.freeze([
    ...view.tracks.flatMap((track) => track.clips.flatMap((clip) => [
      Object.freeze({ kind: "neighbor-start" as const, id: `clip:${clip.clipId}:start`, timeSec: clip.startSec }),
      Object.freeze({ kind: "neighbor-end" as const, id: `clip:${clip.clipId}:end`, timeSec: clip.endSec }),
    ])),
    ...view.gaps.flatMap((gap) => [
      Object.freeze({ kind: "neighbor-start" as const, id: `gap:${gap.gapId}:start`, timeSec: gap.startSec }),
      Object.freeze({ kind: "neighbor-end" as const, id: `gap:${gap.gapId}:end`, timeSec: gap.endSec }),
    ]),
    ...view.captions.flatMap((caption) => [
      Object.freeze({ kind: "neighbor-start" as const, id: `caption:${caption.segmentId}:start`, timeSec: caption.startSec }),
      Object.freeze({ kind: "neighbor-end" as const, id: `caption:${caption.segmentId}:end`, timeSec: caption.endSec }),
    ]),
  ]);
}

function resolveViewportEnd(state: TimelineNavigationState, durationSec: number, viewportWidthPx: number): number {
  return Math.min(durationSec, pixelsToTime(viewportWidthPx, {
    pixelsPerSecond: state.pixelsPerSecond,
    originSec: state.viewportStartSec,
  }));
}

function navigationReducer(
  state: TimelineNavigationState,
  action: TimelineNavigationAction,
  options: Readonly<{ durationSec: number; viewportWidthPx: number; fps: EditorViewModel["fps"] }>,
): TimelineNavigationState {
  return reduceTimelineNavigation(state, action, options);
}

export function TimelineDock({ view, viewportWidthPx }: Props) {
  const options = { durationSec: view.output.durationSec, viewportWidthPx, fps: view.fps };
  const [state, dispatch] = useReducer(
    (current: TimelineNavigationState, action: TimelineNavigationAction) => navigationReducer(current, action, options),
    options,
    (initial) => createTimelineNavigation({ durationSec: initial.durationSec, pixelsPerSecond: 100 }),
  );
  const viewportEndSec = resolveViewportEnd(state, view.output.durationSec, viewportWidthPx);
  const rects = useMemo(() => projectVisibleTimelineClips({
    clips: clipSources(view),
    viewport: { startSec: state.viewportStartSec, endSec: viewportEndSec, topPx: 0, heightPx: TIMELINE_LANES.length * LANE_HEIGHT_PX },
    pixelsPerSecond: state.pixelsPerSecond,
    originSec: state.viewportStartSec,
    laneHeightPx: LANE_HEIGHT_PX,
  }), [state.pixelsPerSecond, state.viewportStartSec, view, viewportEndSec]);
  const visibleGaps = view.gaps.filter((gap) => gap.startSec < viewportEndSec && gap.endSec > state.viewportStartSec);
  const caption = view.captions.find((item) => state.playheadSec >= item.startSec && state.playheadSec < item.endSec) ?? null;
  const snapCandidates = useMemo(() => sourceSnapCandidates(view), [view]);
  const snap = findTimelineSnap({
    candidates: snapCandidates,
    proposedSec: state.playheadSec,
    thresholdPx: SNAP_THRESHOLD_PX,
    scale: { pixelsPerSecond: state.pixelsPerSecond, originSec: state.viewportStartSec },
    fps: view.fps,
  });
  const rulerMarks = useMemo(() => {
    const first = Math.ceil(state.viewportStartSec);
    const last = Math.floor(viewportEndSec);
    return Array.from({ length: Math.max(0, last - first + 1) }, (_, index) => first + index);
  }, [state.viewportStartSec, viewportEndSec]);

  const handleClick = (event: MouseEvent<HTMLElement>) => {
    if (event.target instanceof Element && event.target.closest("button")) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    dispatch({ type: "seek", seconds: pixelsToTime(event.clientX - bounds.left, {
      pixelsPerSecond: state.pixelsPerSecond,
      originSec: state.viewportStartSec,
    }) });
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const action = navigationKeyAction(event.key, isEditableTarget(event.target), { state, fps: view.fps });
    if (!action) return;
    event.preventDefault();
    dispatch(action);
  };
  const handleWheel = (event: WheelEvent<HTMLElement>) => {
    if (event.deltaX === 0) return;
    event.preventDefault();
    const deltaSec = pixelsToTime(event.deltaX, { pixelsPerSecond: state.pixelsPerSecond, originSec: 0 });
    dispatch({ type: "scroll", seconds: state.viewportStartSec + deltaSec });
  };
  const selectClip = (rect: ClipRect) => {
    const hit = classifyTimelineHit({
      point: { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 },
      lane: rect.lane,
      edgeHandlePx: 1,
      rects: rects.map((item) => ({ ...item, zIndex: 0 })),
    });
    if (hit.kind === "body") dispatch({ type: "select", clipId: hit.clipId });
  };

  return <section
    aria-label="타임라인"
    className="vb-editor-workbench__timeline"
    data-pixels-per-second={formatSeconds(state.pixelsPerSecond)}
    data-viewport-start-seconds={formatSeconds(state.viewportStartSec)}
    onClick={handleClick}
    onKeyDown={handleKeyDown}
    onWheel={handleWheel}
    tabIndex={0}
  >
    <h2>타임라인</h2>
    <p>{view.tracks.length}개 트랙 · {view.captions.length}개 자막 · {view.gaps.length}개 자산 공백 · {view.source.status}</p>
    <p>클릭으로 재생 위치를 보고, 화살표·Home·End·+·- 키로 탐색합니다.</p>
    <div aria-label="시간 눈금" role="list" style={{ display: "flex", minHeight: "1.5rem", overflow: "hidden" }}>
      {rulerMarks.map((seconds) => <span key={seconds} aria-label={`눈금 ${seconds}초`} role="listitem" style={{ minWidth: `${state.pixelsPerSecond}px` }}>{seconds}s</span>)}
    </div>
    <div aria-label="고정 트랙" role="list" style={{ position: "relative" }}>
      {TIMELINE_LANES.map((lane) => <div key={lane} aria-label={laneLabel[lane]} role="listitem" style={{ height: `${LANE_HEIGHT_PX}px`, borderTop: "1px solid currentColor", position: "relative" }}>
        <span>{laneLabel[lane]}</span>
      </div>)}
      {rects.map((rect) => <button
        aria-label={`${laneLabel[rect.lane]} 클립 ${rect.clipId}`}
        data-clip-id={rect.clipId}
        data-selected={state.selectedClipId === rect.clipId ? "true" : "false"}
        data-testid="timeline-clip"
        key={rect.clipId}
        onClick={(event) => { event.stopPropagation(); selectClip(rect); }}
        style={{ left: `${rect.x}px`, position: "absolute", top: `${rect.y}px`, width: `${rect.width}px`, height: `${rect.height}px` }}
        type="button"
      >{rect.clipId}</button>)}
    </div>
    {visibleGaps.map((gap) => <p key={gap.gapId}>자산 공백: {gap.reason}</p>)}
    {caption ? <p>현재 자막: {caption.text}</p> : <p>현재 자막 없음</p>}
    {snap ? <p>스냅: {snapKindLabel[snap.kind]} ({snap.id}, {formatSeconds(snap.timeSec)}초)</p> : <p>스냅 없음</p>}
    <output aria-label="재생 위치" data-seconds={formatSeconds(state.playheadSec)}>{formatSeconds(state.playheadSec)}초</output>
    {rects.length === 0 && visibleGaps.length === 0 ? <p>표시할 타임라인 항목이 없습니다.</p> : null}
  </section>;
}
