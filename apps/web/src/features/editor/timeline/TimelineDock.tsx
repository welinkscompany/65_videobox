import { useEffect, useMemo, useReducer, useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent, type WheelEvent } from "react";

import type { EditorViewModel } from "../editorViewModel";
import { classifyTimelineHit } from "./hit-testing";
import { findTimelineSnap, type SnapCandidate, type SnapCandidateKind } from "./snapping";
import { frameToSeconds, pixelsToTime, secondsToFrameHalfUp } from "./time-scale";
import { TIMELINE_LANES, type ClipRect, type TimelineLane } from "./timeline-geometry";
import { deriveNarrationTrim, reorderNarrationLayout, type NarrationSegment, type NarrationReorderLayout } from "./narrationMutation";
import { derivePlacementMove, derivePlacementTrim, type TimelinePlacement, type TimelinePlacementKind } from "./placementMutation";
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
  caption: "자막",
};

type TrimNarration = Readonly<{ segmentId: string; startSec: number; endSec: number }>;
type ReorderNarration = Readonly<{ segmentIds: string[]; boundsById: NarrationReorderLayout["boundsById"] }>;
type UpdatePlacements = Readonly<{ changes: TimelinePlacement[] }>;

type Props = Readonly<{
  view: EditorViewModel;
  viewportWidthPx: number;
  onTrimNarration?: (input: TrimNarration) => void;
  onReorderNarration?: (input: ReorderNarration) => void;
  onUpdatePlacements?: (input: UpdatePlacements) => void;
  onSelectSegment?: (segmentId: string) => void;
  onPlaybackSeek?: (seconds: number) => void;
  selectedSegmentId?: string | null;
  playbackSec?: number;
  isSaving?: boolean;
  mutationMessage?: string;
}>;

type PointerDraft = Readonly<{
  pointerId: number;
  kind: "trim";
  downClientX: number;
  hasMoved: boolean;
  clip: NarrationSegment;
  edge: "start" | "end";
  bounds: TrimNarration;
}> | Readonly<{
  pointerId: number;
  kind: "reorder";
  downClientX: number;
  hasMoved: boolean;
  movingId: string;
  originalIndex: number;
  targetIndex: number;
  layout: NarrationReorderLayout;
}>;
type PlacementMoveDraft = Readonly<{ pointerId: number; kind: "placement-move"; downClientX: number; hasMoved: boolean; placement: TimelinePlacement; placements: readonly TimelinePlacement[]; bounds: Readonly<{ startSec: number; endSec: number }> }>;
type PlacementTrimDraft = Readonly<{ pointerId: number; kind: "placement-trim"; downClientX: number; hasMoved: boolean; placement: TimelinePlacement; edge: "start" | "end"; bounds: Readonly<{ startSec: number; endSec: number }> }>;
type TimelinePointerDraft = PointerDraft | PlacementMoveDraft | PlacementTrimDraft;

function formatSeconds(seconds: number): string {
  return String(Number(seconds.toFixed(6)));
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || target.closest("input, textarea, select, [contenteditable='true']") !== null;
}

function clipSources(view: EditorViewModel) {
  return [
    ...view.tracks.flatMap((track) => track.clips.map((clip) => ({
    id: clip.placementId ?? clip.clipId,
    role: track.role,
    startSec: clip.startSec,
    endSec: clip.endSec,
    }))),
    ...view.captions.flatMap((caption) => caption.placementId ? [{ id: caption.placementId, role: "caption" as const, startSec: caption.startSec, endSec: caption.endSec }] : []),
  ];
}

function narrationSegments(view: EditorViewModel): NarrationSegment[] {
  return view.tracks
    .filter((track) => track.role === "narration")
    .flatMap((track) => track.clips.map((clip) => ({ segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec })))
    .sort((a, b) => a.startSec - b.startSec || a.segmentId.localeCompare(b.segmentId));
}

function releasePointerCapture(target: HTMLElement, pointerId: number): void {
  try {
    if (target.hasPointerCapture(pointerId)) target.releasePointerCapture(pointerId);
  } catch {
    // Pointer capture is unavailable in some DOM environments.
  }
}

function capturePointer(target: HTMLElement, pointerId: number): void {
  try {
    target.setPointerCapture(pointerId);
  } catch {
    // Pointer capture is unavailable in some DOM environments.
  }
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

export function TimelineDock({ view, viewportWidthPx, onTrimNarration, onReorderNarration, onUpdatePlacements, onSelectSegment, onPlaybackSeek, selectedSegmentId = null, playbackSec, isSaving = false, mutationMessage }: Props) {
  const options = { durationSec: view.output.durationSec, viewportWidthPx, fps: view.fps };
  const [state, dispatch] = useReducer(
    (current: TimelineNavigationState, action: TimelineNavigationAction) => navigationReducer(current, action, options),
    { ...options, playbackSec },
    (initial) => {
      const navigation = createTimelineNavigation({ durationSec: initial.durationSec, pixelsPerSecond: 100 });
      return initial.playbackSec === undefined || !Number.isFinite(initial.playbackSec)
        ? navigation
        : reduceTimelineNavigation(navigation, { type: "seek", seconds: initial.playbackSec }, initial);
    },
  );
  const [pointerDraft, setPointerDraft] = useState<TimelinePointerDraft | null>(null);
  const [selectedPlacementIds, setSelectedPlacementIds] = useState<readonly string[]>([]);
  const onPlaybackSeekRef = useRef(onPlaybackSeek);
  useEffect(() => { onPlaybackSeekRef.current = onPlaybackSeek; }, [onPlaybackSeek]);
  useEffect(() => { onPlaybackSeekRef.current?.(state.playheadSec); }, [state.playheadSec]);
  useEffect(() => {
    if (playbackSec === undefined || !Number.isFinite(playbackSec) || playbackSec === state.playheadSec) return;
    dispatch({ type: "seek", seconds: playbackSec });
  }, [playbackSec, state.playheadSec]);
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
  const selectClip = (rect: ClipRect, additive = false) => {
    const hit = classifyTimelineHit({
      point: { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 },
      lane: rect.lane,
      edgeHandlePx: 1,
      rects: rects.map((item) => ({ ...item, zIndex: 0 })),
    });
    if (hit.kind === "body") {
      dispatch({ type: "select", clipId: hit.clipId });
      const narrationClip = narrationByClipId.get(hit.clipId);
      const caption = captionsByPlacementId.get(hit.clipId);
      const segmentId = narrationClip?.segmentId ?? caption?.segmentId;
      if (segmentId) onSelectSegment?.(segmentId);
      const segmentStartSec = narrationClip?.startSec ?? caption?.startSec;
      if (segmentStartSec !== undefined) onPlaybackSeek?.(segmentStartSec);
      const placement = placementsByClipId.get(hit.clipId);
      if (placement) setSelectedPlacementIds((current) => additive ? (current.includes(placement.placementId) ? current.filter((id) => id !== placement.placementId) : [...current, placement.placementId]) : [placement.placementId]);
      else if (!additive) setSelectedPlacementIds([]);
    }
  };
  const narration = useMemo(() => narrationSegments(view), [view]);
  const narrationByClipId = useMemo(() => new Map(
    view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips.map((clip) => [clip.clipId, {
      segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec,
    }] as const)),
  ), [view]);
  const placementsByClipId = useMemo(() => new Map<string, TimelinePlacement>([
    ...view.tracks.flatMap((track) => track.clips.flatMap((clip) => clip.placementId ? [[clip.placementId, { placementId: clip.placementId, kind: track.role as TimelinePlacementKind, startSec: clip.startSec, endSec: clip.endSec } as TimelinePlacement] as const] : [])),
  ]), [view]);
  const captionsByPlacementId = useMemo(() => new Map(view.captions.flatMap((caption) => caption.placementId ? [[caption.placementId, caption] as const] : [])), [view]);
  const draftProjection = useMemo(() => {
    const boundsByClipId = new Map<string, Readonly<{ startSec: number; endSec: number }>>();
    const sources = clipSources(view).map((source) => {
      const narrationClip = narrationByClipId.get(source.id);
      let bounds = { startSec: source.startSec, endSec: source.endSec };
      if (narrationClip && pointerDraft?.kind === "trim" && pointerDraft.clip.segmentId === narrationClip.segmentId) {
        bounds = pointerDraft.bounds;
      } else if (narrationClip && pointerDraft?.kind === "reorder") {
        bounds = pointerDraft.layout.boundsById[narrationClip.segmentId] ?? bounds;
      } else if ((pointerDraft?.kind === "placement-move" || pointerDraft?.kind === "placement-trim") && pointerDraft.placement.placementId === source.id) {
        bounds = pointerDraft.bounds;
      }
      boundsByClipId.set(source.id, bounds);
      return { ...source, ...bounds };
    });
    const projectedRects = projectVisibleTimelineClips({
      clips: sources,
      viewport: { startSec: state.viewportStartSec, endSec: viewportEndSec, topPx: 0, heightPx: TIMELINE_LANES.length * LANE_HEIGHT_PX },
      pixelsPerSecond: state.pixelsPerSecond,
      originSec: state.viewportStartSec,
      laneHeightPx: LANE_HEIGHT_PX,
    }).sort((left, right) => left.y - right.y || left.x - right.x || left.clipId.localeCompare(right.clipId));
    return { boundsByClipId, rects: projectedRects };
  }, [narrationByClipId, pointerDraft, state.pixelsPerSecond, state.viewportStartSec, view, viewportEndSec]);
  const pointerTimelineX = (event: PointerEvent<HTMLElement>): number => {
    const timelineTrack = event.currentTarget.closest<HTMLElement>("[data-timeline-track]");
    const clientX = Number.isFinite(event.clientX) ? event.clientX : 0;
    return clientX - (timelineTrack?.getBoundingClientRect().left ?? 0);
  };
  const pointerClientX = (event: PointerEvent<HTMLElement>): number => {
    return Number.isFinite(event.clientX) ? event.clientX : 0;
  };
  const trimSecondsAtPointer = (draft: Extract<PointerDraft, { kind: "trim" }>, event: PointerEvent<HTMLElement>): number => {
    const originalBoundarySec = draft.edge === "start" ? draft.clip.startSec : draft.clip.endSec;
    const deltaSec = pixelsToTime(pointerClientX(event) - draft.downClientX, {
      pixelsPerSecond: state.pixelsPerSecond,
      originSec: 0,
    });
    return originalBoundarySec + deltaSec;
  };
  const startTrim = (event: PointerEvent<HTMLButtonElement>, clip: NarrationSegment, edge: "start" | "end") => {
    if (isSaving) return;
    event.preventDefault();
    event.stopPropagation();
    const timelineTrack = event.currentTarget.closest<HTMLElement>("[data-timeline-track]");
    if (timelineTrack) capturePointer(timelineTrack, event.pointerId);
    setPointerDraft({
      pointerId: event.pointerId,
      kind: "trim",
      downClientX: pointerClientX(event),
      hasMoved: false,
      clip,
      edge,
      bounds: { segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec },
    });
  };
  const moveTrim = (event: PointerEvent<HTMLElement>) => {
    const draft = pointerDraft;
    if (!draft || draft.kind !== "trim" || draft.pointerId !== event.pointerId) return;
    event.preventDefault();
    const bounds = deriveNarrationTrim({
      clip: draft.clip,
      edge: draft.edge,
      proposedSec: trimSecondsAtPointer(draft, event),
      narration,
      durationSec: view.output.durationSec,
      fps: view.fps,
    });
    setPointerDraft({
      ...draft,
      hasMoved: draft.hasMoved || pointerClientX(event) !== draft.downClientX,
      bounds: { segmentId: draft.clip.segmentId, ...bounds },
    });
  };
  const endTrim = (event: PointerEvent<HTMLElement>) => {
    const draft = pointerDraft;
    if (!draft || draft.kind !== "trim" || draft.pointerId !== event.pointerId) return;
    event.preventDefault();
    releasePointerCapture(event.currentTarget, event.pointerId);
    setPointerDraft(null);
    const hasMoved = draft.hasMoved || pointerClientX(event) !== draft.downClientX;
    if (!hasMoved) return;
    const bounds = deriveNarrationTrim({
      clip: draft.clip,
      edge: draft.edge,
      proposedSec: trimSecondsAtPointer(draft, event),
      narration,
      durationSec: view.output.durationSec,
      fps: view.fps,
    });
    const result = { segmentId: draft.clip.segmentId, ...bounds };
    if (result.startSec !== draft.clip.startSec || result.endSec !== draft.clip.endSec) onTrimNarration?.(result);
  };
  const startReorder = (event: PointerEvent<HTMLButtonElement>, clip: NarrationSegment) => {
    if (isSaving) return;
    event.preventDefault();
    event.stopPropagation();
    const originalIndex = narration.findIndex((segment) => segment.segmentId === clip.segmentId);
    if (originalIndex === -1) return;
    const timelineTrack = event.currentTarget.closest<HTMLElement>("[data-timeline-track]");
    if (timelineTrack) capturePointer(timelineTrack, event.pointerId);
    setPointerDraft({
      pointerId: event.pointerId,
      kind: "reorder",
      downClientX: pointerClientX(event),
      hasMoved: false,
      movingId: clip.segmentId,
      originalIndex,
      targetIndex: originalIndex,
      layout: reorderNarrationLayout({ narration, movingId: clip.segmentId, targetIndex: originalIndex }),
    });
  };
  const reorderAtPointer = (draft: Extract<PointerDraft, { kind: "reorder" }>, event: PointerEvent<HTMLElement>) => {
    const remaining = narration.filter((segment) => segment.segmentId !== draft.movingId);
    const targetIndex = remaining.findIndex((segment) => {
      const clipId = [...narrationByClipId.entries()].find(([, value]) => value.segmentId === segment.segmentId)?.[0];
      const rect = rects.find((item) => item.clipId === clipId);
      return rect ? pointerTimelineX(event) < rect.x + rect.width / 2 : false;
    });
    const insertionIndex = targetIndex === -1 ? remaining.length : targetIndex;
    return {
      ...draft,
      hasMoved: draft.hasMoved || pointerClientX(event) !== draft.downClientX,
      targetIndex: insertionIndex,
      layout: reorderNarrationLayout({ narration, movingId: draft.movingId, targetIndex: insertionIndex }),
    };
  };
  const moveReorder = (event: PointerEvent<HTMLElement>) => {
    const draft = pointerDraft;
    if (!draft || draft.kind !== "reorder" || draft.pointerId !== event.pointerId) return;
    event.preventDefault();
    setPointerDraft(reorderAtPointer(draft, event));
  };
  const endReorder = (event: PointerEvent<HTMLElement>) => {
    const draft = pointerDraft;
    if (!draft || draft.kind !== "reorder" || draft.pointerId !== event.pointerId) return;
    event.preventDefault();
    releasePointerCapture(event.currentTarget, event.pointerId);
    setPointerDraft(null);
    const hasMoved = draft.hasMoved || pointerClientX(event) !== draft.downClientX;
    if (!hasMoved) return;
    const result = reorderAtPointer(draft, event);
    if (result.targetIndex !== result.originalIndex) onReorderNarration?.(result.layout);
  };
  const placementBoundsAtPointer = (draft: PlacementMoveDraft | PlacementTrimDraft, event: PointerEvent<HTMLElement>) => {
    const deltaSec = pixelsToTime(pointerClientX(event) - draft.downClientX, { pixelsPerSecond: state.pixelsPerSecond, originSec: 0 });
    return draft.kind === "placement-move"
      ? derivePlacementMove({ placement: draft.placement, proposedStartSec: draft.placement.startSec + deltaSec, durationSec: view.output.durationSec, fps: view.fps })
      : derivePlacementTrim({ placement: draft.placement, edge: draft.edge, proposedSec: (draft.edge === "start" ? draft.placement.startSec : draft.placement.endSec) + deltaSec, durationSec: view.output.durationSec, fps: view.fps });
  };
  const startPlacement = (event: PointerEvent<HTMLButtonElement>, placement: TimelinePlacement, operation: "move" | "trim", edge?: "start" | "end") => {
    if (isSaving) return;
    event.preventDefault(); event.stopPropagation();
    const timelineTrack = event.currentTarget.closest<HTMLElement>("[data-timeline-track]");
    if (timelineTrack) capturePointer(timelineTrack, event.pointerId);
    const movePlacements = selectedPlacementIds.length > 1
      ? selectedPlacementIds.map((id) => placementsByClipId.get(id)).filter((item): item is TimelinePlacement => Boolean(item))
      : [placement];
    setPointerDraft(operation === "move"
      ? { pointerId: event.pointerId, kind: "placement-move", downClientX: pointerClientX(event), hasMoved: false, placement, placements: movePlacements, bounds: { startSec: placement.startSec, endSec: placement.endSec } }
      : { pointerId: event.pointerId, kind: "placement-trim", downClientX: pointerClientX(event), hasMoved: false, placement, edge: edge!, bounds: { startSec: placement.startSec, endSec: placement.endSec } });
  };
  const movePlacement = (event: PointerEvent<HTMLElement>) => {
    const draft = pointerDraft;
    if (!draft || (draft.kind !== "placement-move" && draft.kind !== "placement-trim") || draft.pointerId !== event.pointerId) return;
    event.preventDefault();
    setPointerDraft({ ...draft, hasMoved: draft.hasMoved || pointerClientX(event) !== draft.downClientX, bounds: placementBoundsAtPointer(draft, event) });
  };
  const endPlacement = (event: PointerEvent<HTMLElement>) => {
    const draft = pointerDraft;
    if (!draft || (draft.kind !== "placement-move" && draft.kind !== "placement-trim") || draft.pointerId !== event.pointerId) return;
    event.preventDefault(); releasePointerCapture(event.currentTarget, event.pointerId); setPointerDraft(null);
    if (draft.hasMoved || pointerClientX(event) !== draft.downClientX) {
      const bounds = placementBoundsAtPointer(draft, event);
      if (draft.kind === "placement-move" && draft.placements.length > 1) {
        const deltaSec = bounds.startSec - draft.placement.startSec;
        onUpdatePlacements?.({ changes: draft.placements.map((placement) => ({ ...placement, ...derivePlacementMove({ placement, proposedStartSec: placement.startSec + deltaSec, durationSec: view.output.durationSec, fps: view.fps }) })) });
      } else updatePlacement(draft.placement, bounds);
    }
  };
  const cancelPointerDraft = (event: PointerEvent<HTMLElement>) => {
    if (pointerDraft?.pointerId !== event.pointerId) return;
    releasePointerCapture(event.currentTarget, event.pointerId);
    setPointerDraft(null);
  };
  const movePointerDraft = (event: PointerEvent<HTMLElement>) => {
    if (pointerDraft?.kind === "trim") moveTrim(event);
    else if (pointerDraft?.kind === "reorder") moveReorder(event);
    else movePlacement(event);
  };
  const endPointerDraft = (event: PointerEvent<HTMLElement>) => {
    if (pointerDraft?.kind === "trim") endTrim(event);
    else if (pointerDraft?.kind === "reorder") endReorder(event);
    else endPlacement(event);
  };
  const keyboardTrim = (event: KeyboardEvent<HTMLButtonElement>, clip: NarrationSegment, edge: "start" | "end") => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    if (isSaving) return;
    const direction = event.key === "ArrowLeft" ? -1 : 1;
    const currentSec = edge === "start" ? clip.startSec : clip.endSec;
    const currentFrame = secondsToFrameHalfUp(currentSec, view.fps);
    const proposedSec = frameToSeconds(Math.max(0, currentFrame + direction), view.fps);
    const bounds = deriveNarrationTrim({ clip, edge, proposedSec, narration, durationSec: view.output.durationSec, fps: view.fps });
    const result = { segmentId: clip.segmentId, ...bounds };
    if (result.startSec !== clip.startSec || result.endSec !== clip.endSec) onTrimNarration?.(result);
  };
  const keyboardReorder = (event: KeyboardEvent<HTMLButtonElement>, clip: NarrationSegment) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    if (isSaving) return;
    const originalIndex = narration.findIndex((segment) => segment.segmentId === clip.segmentId);
    if (originalIndex === -1) return;
    const direction = event.key === "ArrowLeft" ? -1 : 1;
    const targetIndex = Math.min(narration.length - 1, Math.max(0, originalIndex + direction));
    if (targetIndex === originalIndex) return;
    onReorderNarration?.(reorderNarrationLayout({ narration, movingId: clip.segmentId, targetIndex }));
  };
  const updatePlacement = (placement: TimelinePlacement, bounds: Readonly<{ startSec: number; endSec: number }>) => {
    if (bounds.startSec !== placement.startSec || bounds.endSec !== placement.endSec) onUpdatePlacements?.({ changes: [{ ...placement, ...bounds }] });
  };
  const keyboardPlacementMove = (event: KeyboardEvent<HTMLButtonElement>, placement: TimelinePlacement) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault(); event.stopPropagation(); if (isSaving) return;
    const direction = event.key === "ArrowLeft" ? -1 : 1;
    updatePlacement(placement, derivePlacementMove({ placement, proposedStartSec: frameToSeconds(Math.max(0, secondsToFrameHalfUp(placement.startSec, view.fps) + direction), view.fps), durationSec: view.output.durationSec, fps: view.fps }));
  };
  const keyboardPlacementTrim = (event: KeyboardEvent<HTMLButtonElement>, placement: TimelinePlacement, edge: "start" | "end") => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault(); event.stopPropagation(); if (isSaving) return;
    const direction = event.key === "ArrowLeft" ? -1 : 1;
    const current = edge === "start" ? placement.startSec : placement.endSec;
    updatePlacement(placement, derivePlacementTrim({ placement, edge, proposedSec: frameToSeconds(Math.max(0, secondsToFrameHalfUp(current, view.fps) + direction), view.fps), durationSec: view.output.durationSec, fps: view.fps }));
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
    <div data-timeline-track data-testid="timeline-track" onPointerCancel={cancelPointerDraft} onPointerMove={movePointerDraft} onPointerUp={endPointerDraft} style={{ position: "relative" }}>
      <div aria-label="고정 트랙" role="list">
        {TIMELINE_LANES.map((lane) => <div key={lane} aria-label={laneLabel[lane]} role="listitem" style={{ height: `${LANE_HEIGHT_PX}px`, borderTop: "1px solid currentColor", position: "relative" }}>
          <span>{laneLabel[lane]}</span>
        </div>)}
      </div>
      <div aria-label="타임라인 클립" role="group" style={{ inset: 0, position: "absolute" }}>
        {draftProjection.rects.map((rect) => {
        const narrationClip = rect.lane === "narration" ? narrationByClipId.get(rect.clipId) : undefined;
        const placement = placementsByClipId.get(rect.clipId);
        const displayBounds = draftProjection.boundsByClipId.get(rect.clipId);
        const isTranscriptSelected = narrationClip?.segmentId === selectedSegmentId || captionsByPlacementId.get(rect.clipId)?.segmentId === selectedSegmentId;
        const isSelected = state.selectedClipId === rect.clipId;
        return <div
        aria-label={`${laneLabel[rect.lane]} 클립 ${rect.clipId}`}
        data-clip-id={rect.clipId}
        data-end-seconds={displayBounds ? formatSeconds(displayBounds.endSec) : undefined}
        data-selected={isSelected || isTranscriptSelected ? "true" : "false"}
        data-start-seconds={displayBounds ? formatSeconds(displayBounds.startSec) : undefined}
        data-testid="timeline-clip"
        key={rect.clipId}
        role="group"
        style={{ left: `${rect.x}px`, overflow: "hidden", position: "absolute", top: `${rect.y}px`, width: `${rect.width}px`, height: `${rect.height}px` }}
      ><button
        aria-label={`${rect.clipId} 클립 선택`}
        aria-pressed={isSelected || isTranscriptSelected}
        onClick={(event) => { event.stopPropagation(); selectClip(rect, event.shiftKey); }}
        onKeyDown={(event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          event.stopPropagation();
          selectClip(rect, event.shiftKey);
        }}
        style={{ height: "100%", width: "100%" }}
        type="button"
      >{rect.clipId}</button>{narrationClip && isSelected ? <span data-mutation-controls="true" onClick={(event) => event.stopPropagation()} style={{ inset: 0, overflow: "hidden", pointerEvents: "none", position: "absolute" }}>
        <button aria-label={`${rect.clipId} 시작 자르기`} data-trim-edge="start" disabled={isSaving} onKeyDown={(event) => keyboardTrim(event, narrationClip, "start")} onPointerDown={(event) => startTrim(event, narrationClip, "start")} style={{ bottom: 0, left: 0, maxWidth: "33.333%", overflow: "hidden", padding: 0, pointerEvents: "auto", position: "absolute", top: 0, width: "33.333%" }} title="왼쪽·오른쪽 화살표로 한 프레임씩 조절" type="button">시작</button>
        <button aria-label={`${rect.clipId} 끝 자르기`} data-trim-edge="end" disabled={isSaving} onKeyDown={(event) => keyboardTrim(event, narrationClip, "end")} onPointerDown={(event) => startTrim(event, narrationClip, "end")} style={{ bottom: 0, maxWidth: "33.333%", overflow: "hidden", padding: 0, pointerEvents: "auto", position: "absolute", right: 0, top: 0, width: "33.333%" }} title="왼쪽·오른쪽 화살표로 한 프레임씩 조절" type="button">끝</button>
        <button aria-label={`${rect.clipId} 순서 바꾸기`} data-reorder-control="true" disabled={isSaving} onKeyDown={(event) => keyboardReorder(event, narrationClip)} onPointerDown={(event) => startReorder(event, narrationClip)} style={{ bottom: 0, left: "33.333%", maxWidth: "33.334%", overflow: "hidden", padding: 0, pointerEvents: "auto", position: "absolute", top: 0, width: "33.334%" }} title="왼쪽·오른쪽 화살표로 한 칸씩 이동" type="button">순서</button>
      </span> : null}{placement && isSelected ? <span data-placement-controls="true" onClick={(event) => event.stopPropagation()} style={{ display: "flex", gap: 2, inset: 0, pointerEvents: "none", position: "absolute" }}>
        <button aria-label={`${rect.clipId} 시작 자르기`} disabled={isSaving} onKeyDown={(event) => keyboardPlacementTrim(event, placement, "start")} onPointerDown={(event) => startPlacement(event, placement, "trim", "start")} style={{ pointerEvents: "auto" }} title="드래그하거나 왼쪽·오른쪽 화살표로 한 프레임씩 조절" type="button">시작</button>
        <button aria-label={`${rect.clipId} 이동`} disabled={isSaving} onKeyDown={(event) => keyboardPlacementMove(event, placement)} onPointerDown={(event) => startPlacement(event, placement, "move")} style={{ pointerEvents: "auto" }} title="드래그하거나 왼쪽·오른쪽 화살표로 한 프레임씩 이동" type="button">이동</button>
        <button aria-label={`${rect.clipId} 끝 자르기`} disabled={isSaving} onKeyDown={(event) => keyboardPlacementTrim(event, placement, "end")} onPointerDown={(event) => startPlacement(event, placement, "trim", "end")} style={{ pointerEvents: "auto" }} title="드래그하거나 왼쪽·오른쪽 화살표로 한 프레임씩 조절" type="button">끝</button>
      </span> : null}</div>;
        })}
      </div>
    </div>
    {visibleGaps.map((gap) => <p key={gap.gapId}>자산 공백: {gap.reason}</p>)}
    {caption ? <p>현재 자막: {caption.text}</p> : <p>현재 자막 없음</p>}
    {selectedPlacementIds.length > 1 ? <p>선택한 독립 항목: {selectedPlacementIds.length}개</p> : null}
    {snap ? <p>스냅: {snapKindLabel[snap.kind]} ({snap.id}, {formatSeconds(snap.timeSec)}초)</p> : <p>스냅 없음</p>}
    {mutationMessage ? <p role="status">{mutationMessage}</p> : null}
    <output aria-label="재생 위치" data-seconds={formatSeconds(state.playheadSec)}>{formatSeconds(state.playheadSec)}초</output>
    {draftProjection.rects.length === 0 && visibleGaps.length === 0 ? <p>표시할 타임라인 항목이 없습니다.</p> : null}
  </section>;
}
