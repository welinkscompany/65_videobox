import { useEffect, useMemo, useReducer, useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent, type ReactNode, type WheelEvent } from "react";
import { Eye, EyeOff, Lock, Unlock, Volume2, VolumeX } from "lucide-react";
import { clipContentLabel } from "./clipNames";

import type { EditorViewModel } from "../editorViewModel";
import { classifyTimelineHit } from "./hit-testing";
import { carriesAsset, readAssetDrag } from "../assets/assetDragPayload";
import { findTimelineSnap, type SnapCandidate, type SnapCandidateKind } from "./snapping";
import { frameToSeconds, pixelsToTime, secondsToFrameHalfUp, timeToPixels } from "./time-scale";
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
/** 눈·음소거를 그릴 트랙. 서버(`track_states.py`)가 받는 것과 같은 갈래이고,
 *  두 벌이 어긋나면 눌러도 422로 거절되는 단추가 생긴다. */
const HIDEABLE_LANES = new Set<TimelineLane>(["broll", "overlay", "caption"]);
const MUTABLE_LANES = new Set<TimelineLane>(["narration", "broll", "bgm", "sfx"]);
const SNAP_THRESHOLD_PX = 8;

// Source status describes base-timeline provenance. Session edits are already
// materialized in this view, so the label must not imply that they are absent.
const sourceStatusLabel: Readonly<Record<string, string>> = {
  current: "원본과 편집본 일치",
  stale: "현재 편집본 기준",
};

const laneLabel: Readonly<Record<TimelineLane, string>> = {
  narration: "내레이션",
  broll: "영상",
  bgm: "배경 음악",
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
  /** 클립 id → 그 클립 위에 깔 그림 주소. 소유자가 정해서 넘긴다. */
  clipPictures?: ReadonlyMap<string, string>;
  onTrimNarration?: (input: TrimNarration) => void;
  onReorderNarration?: (input: ReorderNarration) => void;
  onUpdatePlacements?: (input: UpdatePlacements) => void;
  /** 트랙 눈·음소거를 저장한다. 없으면 그 단추들이 꺼진 채로 보인다 --
   *  숨기지 않는다. 있는데 안 되는 것과 아예 없는 것은 다르다. */
  onUpdateTrackStates?: (states: Record<string, { hidden?: boolean; muted?: boolean }>) => void | Promise<void>;
  onSelectSegment?: (segmentId: string) => void;
  onPlaybackSeek?: (seconds: number) => void;
  selectedSegmentId?: string | null;
  selectionResetKey?: string | number | null;
  playbackSec?: number;
  /** 캡컷처럼 재료를 장면 위로 끌어다 놓았을 때. 없으면 클립은 드래그를 받지 않는다. */
  onDropAsset?: (input: Readonly<{ cardId: string; segmentId: string }>) => void;
  isSaving?: boolean;
  mutationMessage?: string;
  /** 되돌리기·자르기 같은 편집 동작 단추 묶음. 캡컷 참조(2026-08-30 버튼
   *  단위 벤치마킹 승인) -- 이 동작들은 상단 도구줄이 아니라 타임라인
   *  바로 위, 확대·축소와 같은 줄에 있다. 그 버튼들의 상태·핸들러는
   *  전부 `EditorWorkbench`가 갖고 있으므로 여기서는 다시 짜지 않고
   *  그린 결과만 받는다. */
  editToolbar?: ReactNode;
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
type ScrubDraft = Readonly<{ pointerId: number; kind: "scrub"; downClientX: number; hasMoved: boolean; originSec: number }>;
type TimelinePointerDraft = PointerDraft | PlacementMoveDraft | PlacementTrimDraft | ScrubDraft;

function formatSeconds(seconds: number): string {
  return String(Number(seconds.toFixed(6)));
}

// Display-only name: selection/mutation logic keeps using rect.clipId
// (data-clip-id, onClick handlers) unchanged. Never mix the identifier into
// what the creator reads (F-3: internal IDs like
// "broll:session-broll-segment_draft_1726b9574a-0" were leaking into the
// clip selection button's accessible name and visible text).
function formatClipDisplayName(lane: TimelineLane, ordinalInLane: number, startSec: number, content: string | null): string {
  // 보이는 이름이 앞부분이어야 한다(아래 주석). 내용이 붙은 막대에까지
  // `번째 장면`을 끼우면 `자막 1 · 요즘 영상…번째 장면`처럼 읽힌다.
  const stem = formatClipShortName(lane, ordinalInLane, content);
  return content ? `${stem}, ${Math.round(startSec)}초부터` : `${stem}번째 장면, ${Math.round(startSec)}초부터`;
}

// 막대 위에 실제로 보이는 이름. 전체 이름이 막대를 가로질러 깔리면 썸네일·파형을
// 덮는다(캡컷은 짧은 이름을 왼쪽 위에만 둔다). 반드시 전체 이름(aria-label)의
// 앞부분이어야 한다 -- 보이는 글자와 접근 이름이 다르면 음성으로 부를 수 없다.
function formatClipShortName(lane: TimelineLane, ordinalInLane: number, content: string | null): string {
  // 내용이 있으면 그것까지가 보이는 이름이다. 없으면 예전 그대로 -- 영상·음악
  // 막대에는 여기서 읽을 내용이 없고, 없는 이름을 지어 붙이지 않는다.
  return content ? `${laneLabel[lane]} ${ordinalInLane} · ${content}` : `${laneLabel[lane]} ${ordinalInLane}`;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || target.closest("input, textarea, select, [contenteditable='true']") !== null;
}

function clipSources(view: EditorViewModel) {
  return [
    ...view.tracks.flatMap((track) => track.clips.map((clip) => ({
    id: clip.placementId ?? clip.clipId,
    segmentId: clip.segmentId,
    role: track.role,
    startSec: clip.startSec,
    endSec: clip.endSec,
    }))),
    ...view.captions.flatMap((caption) => caption.placementId ? [{ id: caption.placementId, segmentId: caption.segmentId, role: "caption" as const, startSec: caption.startSec, endSec: caption.endSec }] : []),
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

export function TimelineDock({ clipPictures = new Map(), view, viewportWidthPx, onTrimNarration, onReorderNarration, onUpdatePlacements, onUpdateTrackStates, onSelectSegment, onPlaybackSeek, onDropAsset, selectedSegmentId = null, selectionResetKey = null, playbackSec, isSaving = false, mutationMessage, editToolbar }: Props) {
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
  // 지금 어느 장면 위에 떠 있는지. 받을 자리를 보여 주지 않으면 어디에 놓이는지 모른다.
  const [dragOverClipId, setDragOverClipId] = useState<string | null>(null);
  const [selectedPlacementIds, setSelectedPlacementIds] = useState<readonly string[]>([]);
  // **트랙 잠금**(owner 지시 2026-08-22, `capcut-observed` 기록 §2: "트랙마다
  // 왼쪽에 잠금·눈·음소거"). 우리는 **음소거만 만들지 않는다** -- 미리보기가
  // 서버가 미리 렌더링한 파일 하나라 트랙을 눌러도 그 순간 아무것도 안 바뀌고,
  // 반영하려면 렌더 파이프라인을 새로 만져야 한다(따로 계획 잡을 일).
  //
  // 잠금은 **다르다.** 우리 자산·음악·효과음·오버레이·자막 트랙은 이미 드래그로
  // 이동·자르기가 된다(`startPlacement`) -- 옆 트랙을 실수로 밀리게 하는 일을
  // 잠금이 그 자리에서 막아 준다. 새 백엔드가 필요 없다.
  //
  // 세션에서만 기억한다(새로고침하면 풀린다) -- 편집 도중 실수를 막는 것이
  // 목적이지 프로젝트에 영구히 남길 상태가 아니다.
  const [lockedLanes, setLockedLanes] = useState<ReadonlySet<TimelineLane>>(new Set());
  const toggleLaneLock = (lane: TimelineLane) => setLockedLanes((current) => {
    const next = new Set(current);
    if (next.has(lane)) next.delete(lane); else next.add(lane);
    return next;
  });
  // **눈·음소거는 잠금과 달리 여기 상태가 아니다.** 결과물이 달라지는
  // 편집이라 세션이 원본이고(`track_states.py`), 화면은 그것을 그릴 뿐이다.
  // 여기에 따로 들고 있으면 저장이 실패해도 켜진 것처럼 보인다.
  // 트랙마다 붙은 값이 아니라 `trackStates` 한자리에서 읽는다 -- 자막 트랙은
  // 재생 목록의 `tracks`에 아예 안 실려서(자기 필드가 따로 있다) 트랙 쪽만
  // 보면 자막 숨김을 되읽지 못한다.
  const trackStates = view.trackStates ?? {};
  const hiddenLanes = useMemo(
    () => new Set(TIMELINE_LANES.filter((lane) => trackStates[lane]?.hidden)),
    [trackStates],
  );
  const mutedLanes = useMemo(
    () => new Set(TIMELINE_LANES.filter((lane) => trackStates[lane]?.muted)),
    [trackStates],
  );
  const toggleTrackState = (lane: TimelineLane, field: "hidden" | "muted") => {
    if (!onUpdateTrackStates || isSaving) return;
    // **보낸 것이 곧 전체 상태다.** 지금 켜져 있는 것 전부를 다시 실어 보내고
    // 누른 것 하나만 뒤집는다 -- 조각만 보내면 서버가 나머지를 지운다.
    const next: Record<string, { hidden?: boolean; muted?: boolean }> = {};
    for (const other of TIMELINE_LANES) {
      const hidden = other === lane && field === "hidden" ? !hiddenLanes.has(other) : hiddenLanes.has(other);
      const muted = other === lane && field === "muted" ? !mutedLanes.has(other) : mutedLanes.has(other);
      const state: { hidden?: boolean; muted?: boolean } = {};
      if (HIDEABLE_LANES.has(other) && hidden) state.hidden = true;
      if (MUTABLE_LANES.has(other) && muted) state.muted = true;
      if (Object.keys(state).length) next[other] = state;
    }
    void onUpdateTrackStates(next);
  };
  const previousSelectionResetKey = useRef(selectionResetKey);
  const onPlaybackSeekRef = useRef(onPlaybackSeek);
  useEffect(() => { onPlaybackSeekRef.current = onPlaybackSeek; }, [onPlaybackSeek]);
  // 우리가 방금 소유자에게 올려보낸 위치. 그것이 `playbackSec`으로 되돌아왔을 때
  // 다시 seek하지 않기 위한 표식이다.
  const reportedPlayheadRef = useRef<number | null>(null);
  useEffect(() => {
    reportedPlayheadRef.current = state.playheadSec;
    onPlaybackSeekRef.current?.(state.playheadSec);
  }, [state.playheadSec]);
  useEffect(() => {
    if (previousSelectionResetKey.current === selectionResetKey) return;
    previousSelectionResetKey.current = selectionResetKey;
    dispatch({ type: "select", clipId: null });
    setSelectedPlacementIds([]);
    setPointerDraft(null);
  }, [selectionResetKey]);
  // **밖에서 온 위치만** 따라간다. 예전에는 `state.playheadSec`도 이 effect의 deps에
  // 있어서, 우리가 타임라인을 눌러 위치를 옮기면 아직 갱신되지 않은 옛 `playbackSec`이
  // 우리를 도로 끌어당겼다. 그 둘이 서로를 되돌리는 고리가 되어 재생 위치가 첫 클릭
  // 자리에 붙박였고, 그 때문에 `나누기`를 쓸 수 없었다(2026-08-17 실제 앱에서 확인).
  useEffect(() => {
    if (playbackSec === undefined || !Number.isFinite(playbackSec)) return;
    if (playbackSec === reportedPlayheadRef.current) return;
    dispatch({ type: "seek", seconds: playbackSec });
  }, [playbackSec]);
  // 재생 머리가 보이는 구간을 벗어나면 뷰포트를 그 자리로 넘긴다. 확대해 놓고
  // 재생하면 머리가 오른쪽 끝을 지나가 버리는데, 타임라인이 따라가지 않으면
  // 편집자는 지금 어디를 지나는지 볼 수 없다.
  //
  // deps는 **재생 위치 하나뿐**이다. viewportStartSec까지 넣으면 편집자가 다른
  // 구간을 보려고 옆으로 밀어 둔 뷰포트를 재생 위치가 도로 끌어당긴다.
  useEffect(() => {
    const followEndSec = resolveViewportEnd(state, view.output.durationSec, viewportWidthPx);
    if (state.playheadSec >= state.viewportStartSec && state.playheadSec <= followEndSec) return;
    dispatch({ type: "scroll", seconds: state.playheadSec });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.playheadSec]);
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
  // 클립과 **같은 좌표계**로 재생 위치 선을 놓는다. 다른 식으로 계산하면 확대하거나
  // 옆으로 밀었을 때 선만 어긋난다.
  const playheadX = timeToPixels(state.playheadSec, {
    pixelsPerSecond: state.pixelsPerSecond,
    originSec: state.viewportStartSec,
  });
  const rulerMarks = useMemo(() => {
    const first = Math.ceil(state.viewportStartSec);
    const last = Math.floor(viewportEndSec);
    return Array.from({ length: Math.max(0, last - first + 1) }, (_, index) => first + index);
  }, [state.viewportStartSec, viewportEndSec]);

  const handleClick = (event: MouseEvent<HTMLElement>) => {
    if (event.target instanceof Element && event.target.closest("button")) return;
    // 클립·재생 머리와 **같은 좌표계**(트랙 원점)로 잰다. 섹션 원점으로 재면
    // 섹션 안쪽 여백만큼 옆으로 어긋난 자리로 seek한다.
    const track = event.currentTarget.querySelector<HTMLElement>("[data-timeline-track]");
    const bounds = (track ?? event.currentTarget).getBoundingClientRect();
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
  // 단추도 키와 **같은 경로**를 탄다. 확대 계산을 여기서 다시 쓰면 같은 동작이 두
  // 벌이 되고, 그중 하나가 조용히 낡는다.
  const zoom = (key: "+" | "-") => {
    const action = navigationKeyAction(key, false, { state, fps: view.fps });
    if (action) dispatch(action);
  };
  // 전체 맞춤. 축소를 열 번 누르는 대신 한 번에 처음으로 돌아온다. 확대와 같은
  // reducer를 타므로 배율 계산이 두 벌이 되지 않는다. 길이가 0이면 나눌 수 없어
  // 아무 일도 하지 않는다.
  const fitAll = () => {
    if (!(view.output.durationSec > 0) || !(viewportWidthPx > 0)) return;
    dispatch({ type: "zoom", pixelsPerSecond: viewportWidthPx / view.output.durationSec, anchorPx: 0 });
    dispatch({ type: "scroll", seconds: 0 });
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
      const timelineClip = timelineClipById.get(hit.clipId);
      const segmentId = narrationClip?.segmentId ?? caption?.segmentId ?? timelineClip?.segmentId;
      // 재생 위치를 먼저 옮기고 **그 다음에** 고른다. 순서가 반대면, seek이 재생
      // 위치에서 장면을 다시 유도하면서 방금 고른 클립을 덮어쓴다(경계에서는 앞
      // 장면이 잡힌다). 2026-08-17 실제 앱에서 두 클립이 함께 골라져 있었다.
      const segmentStartSec = narrationClip?.startSec ?? caption?.startSec ?? timelineClip?.startSec;
      if (segmentStartSec !== undefined) onPlaybackSeek?.(segmentStartSec);
      if (segmentId) onSelectSegment?.(segmentId);
      const placement = placementsByClipId.get(hit.clipId);
      if (placement) setSelectedPlacementIds((current) => additive ? (current.includes(placement.placementId) ? current.filter((id) => id !== placement.placementId) : [...current, placement.placementId]) : [placement.placementId]);
      else if (!additive) setSelectedPlacementIds([]);
    }
  };
  /** 끌어다 놓은 자리가 어느 장면인지. 클립 id는 표시용이고 편집은 장면 단위다. */
  const segmentIdForClip = (clipId: string): string | null =>
    narrationByClipId.get(clipId)?.segmentId
    ?? captionsByPlacementId.get(clipId)?.segmentId
    ?? timelineClipById.get(clipId)?.segmentId
    ?? null;
  const narration = useMemo(() => narrationSegments(view), [view]);
  const narrationByClipId = useMemo(() => new Map(
    view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips.map((clip) => [clip.clipId, {
      segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec,
    }] as const)),
  ), [view]);
  const placementsByClipId = useMemo(() => new Map<string, TimelinePlacement>([
    ...view.tracks.flatMap((track) => track.clips.flatMap((clip) => clip.placementId ? [[clip.placementId, { placementId: clip.placementId, kind: track.role as TimelinePlacementKind, startSec: clip.startSec, endSec: clip.endSec } as TimelinePlacement] as const] : [])),
  ]), [view]);
  // 막대가 자기를 부르는 이름은 `placement_id`다(`overlay:session-…`). `clip_id`로
  // 열쇠를 삼으면 앞의 `overlay:`가 없어서 영영 안 맞는다 -- 실측으로 확인했다.
  const overlayByPlacementId = useMemo(() => new Map(view.tracks.flatMap((track) => track.clips.map((clip) => [clip.placementId ?? clip.clipId, clip] as const))), [view]);
  const captionsByPlacementId = useMemo(() => new Map(view.captions.flatMap((caption) => caption.placementId ? [[caption.placementId, caption] as const] : [])), [view]);
  const timelineClipById = useMemo(() => new Map(clipSources(view).map((clip) => [clip.id, clip] as const)), [view]);
  // 클립 위에 그 클립의 **그림**을 그린다. 주소는 **받는다** -- 이 컴포넌트는
  // 서버를 알지 않는다(`test_editor_ui_source_provenance`가 그 경계를 지킨다).
  // 무엇을 그릴지 고르는 것은 소유자(`EditorWorkbench`)의 일이다.
  const clipPictureByClipId = clipPictures;
  // 그림이 없는 것과 **고장난 것처럼 보이는 것**은 다르다. 그 자산에 파형·썸네일이
  // 없으면(ffmpeg가 없거나 404) 클립 위에 깨진 이미지 아이콘이 그대로 떴다 --
  // 스냅샷을 보고 찾았다. 한 번 실패한 주소는 다시 걸지 않는다.
  const [brokenPictures, setBrokenPictures] = useState<ReadonlySet<string>>(new Set());
  // Computed over the full (unfiltered) clip list, not the viewport-visible
  // subset draftProjection.rects renders -- otherwise scrolling or zooming
  // the timeline would renumber/rename the same physical clip, undermining
  // the whole point of a stable human-readable identity (F-3/Task 7).
  const laneOrdinalByClipId = useMemo(() => {
    const counters: Partial<Record<TimelineLane, number>> = {};
    const map = new Map<string, number>();
    for (const source of clipSources(view)) {
      const lane = source.role as TimelineLane;
      counters[lane] = (counters[lane] ?? 0) + 1;
      map.set(source.id, counters[lane]!);
    }
    return map;
  }, [view]);
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
    if (isSaving || lockedLanes.has("narration")) return;
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
    if (isSaving || lockedLanes.has("narration")) return;
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
    if (isSaving || lockedLanes.has(placement.kind)) return;
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
  // 재생 머리를 끌어서 문지른다(스크럽). 트림 손잡이와 같은 상대 이동 방식이다 --
  // 절대 좌표로 계산하면 눈금 원점과 어긋났을 때 머리가 튄다. 이동량만 초로 바꾼다.
  const scrubSecondsAtPointer = (draft: ScrubDraft, event: PointerEvent<HTMLElement>): number => {
    const deltaSec = pixelsToTime(pointerClientX(event) - draft.downClientX, {
      pixelsPerSecond: state.pixelsPerSecond,
      originSec: 0,
    });
    return frameToSeconds(Math.max(0, secondsToFrameHalfUp(draft.originSec + deltaSec, view.fps)), view.fps);
  };
  const startScrub = (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    capturePointer(event.currentTarget, event.pointerId);
    setPointerDraft({
      pointerId: event.pointerId,
      kind: "scrub",
      downClientX: pointerClientX(event),
      hasMoved: false,
      originSec: state.playheadSec,
    });
  };
  const moveScrub = (event: PointerEvent<HTMLElement>) => {
    const draft = pointerDraft;
    if (!draft || draft.kind !== "scrub" || draft.pointerId !== event.pointerId) return;
    event.preventDefault();
    setPointerDraft({ ...draft, hasMoved: draft.hasMoved || pointerClientX(event) !== draft.downClientX });
    // 문지르는 동안 계속 seek한다. 미리보기가 그 자리를 바로 보여 주는 것이 목적이다.
    dispatch({ type: "seek", seconds: scrubSecondsAtPointer(draft, event) });
  };
  const endScrub = (event: PointerEvent<HTMLElement>) => {
    const draft = pointerDraft;
    if (!draft || draft.kind !== "scrub" || draft.pointerId !== event.pointerId) return;
    event.preventDefault();
    releasePointerCapture(event.currentTarget, event.pointerId);
    setPointerDraft(null);
    // 움직이지 않은 채 놓았으면 seek할 것도 없다. 머리는 이미 그 자리에 있다.
    // (드래그 끝의 click은 handleClick이 button을 무시하므로 중복 seek이 없다.)
    if (draft.hasMoved || pointerClientX(event) !== draft.downClientX) {
      dispatch({ type: "seek", seconds: scrubSecondsAtPointer(draft, event) });
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
    if (lockedLanes.has("narration")) return;
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
    if (lockedLanes.has("narration")) return;
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
    if (lockedLanes.has(placement.kind)) return;
    event.preventDefault(); event.stopPropagation(); if (isSaving) return;
    const direction = event.key === "ArrowLeft" ? -1 : 1;
    updatePlacement(placement, derivePlacementMove({ placement, proposedStartSec: frameToSeconds(Math.max(0, secondsToFrameHalfUp(placement.startSec, view.fps) + direction), view.fps), durationSec: view.output.durationSec, fps: view.fps }));
  };
  const keyboardPlacementTrim = (event: KeyboardEvent<HTMLButtonElement>, placement: TimelinePlacement, edge: "start" | "end") => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    if (lockedLanes.has(placement.kind)) return;
    event.preventDefault(); event.stopPropagation(); if (isSaving) return;
    const direction = event.key === "ArrowLeft" ? -1 : 1;
    const current = edge === "start" ? placement.startSec : placement.endSec;
    updatePlacement(placement, derivePlacementTrim({ placement, edge, proposedSec: frameToSeconds(Math.max(0, secondsToFrameHalfUp(current, view.fps) + direction), view.fps), durationSec: view.output.durationSec, fps: view.fps }));
  };

  return <section
    aria-label="타임라인"
    className="vb-editor-workbench__timeline"
    data-scroll-owner="timeline"
    data-pixels-per-second={formatSeconds(state.pixelsPerSecond)}
    data-viewport-start-seconds={formatSeconds(state.viewportStartSec)}
    onClick={handleClick}
    onKeyDown={handleKeyDown}
    onWheel={handleWheel}
    tabIndex={0}
  >
    {/* 안내는 지우지 않고 **한 줄로 모은다.** 재 보니 타임라인이 필요로 하는 449px
        가운데 눈금과 트랙은 222px뿐이고 나머지는 이렇게 한 줄씩 차지한 글자였다.
        그래서 owner가 승인한 "타임라인을 아래쪽으로 넉넉히"가 자리를 더 줘도 계속
        스크롤 안에 숨어 있었다 -- 자리가 모자란 게 아니라 글자가 먹고 있었다. */}
    <div className="vb-editor-workbench__timeline-head">
      <h2>타임라인</h2>
      <p>{view.tracks.length}개 트랙 · {view.captions.length}개 자막 · {view.gaps.length}개 미디어 공백 · {sourceStatusLabel[view.source.status] ?? "최신 여부 확인 중"}</p>
      {/* 조작 설명 한 줄을 뺐다(owner 지시 2026-08-22: 설명 문장을 키워드로).
          클릭해서 재생 위치를 보는 것은 타임라인이면 다 그렇고, 화살표·Home·End는
          눌러 보면 안다. 캡컷 타임라인에도 이런 안내가 없다. */}
      {/* 확대·축소는 `+`/`-` 키로만 됐다. 안내에 적어 두어도 **눈에 보이는 단추가
          없으면 안 쓰는 기능**이다 -- 2026-08-17에 컷 도구가 정확히 그랬다. */}
      {editToolbar}
      <span className="vb-editor-workbench__timeline-zoom">
        <button data-native-control="timeline-zoom-out" type="button" aria-label="타임라인 축소" title="- 키" onClick={() => zoom("-")}>−</button>
        <button data-native-control="timeline-zoom-in" type="button" aria-label="타임라인 확대" title="+ 키" onClick={() => zoom("+")}>+</button>
        <button data-native-control="timeline-fit" type="button" aria-label="타임라인 전체 보기" title="영상 전체가 한 화면에 들어오게" onClick={fitAll}>전체</button>
      </span>
    </div>
    {/* 캡컷처럼 눈금과 트랙을 한 좌표계에 놓고, 그 위에 재생 위치 선을 관통시킨다.
        예전에는 맨 아래 숫자뿐이라 어디서 나뉘는지 눈으로 찾을 수 없었다. */}
    <div className="vb-timeline-scale" style={{ position: "relative" }}>
      <div aria-label="시간 눈금" role="list" style={{ display: "flex", minHeight: "1.5rem", overflow: "hidden" }}>
        {rulerMarks.map((seconds) => <span key={seconds} aria-label={`눈금 ${seconds}초`} role="listitem" style={{ minWidth: `${state.pixelsPerSecond}px` }}>{seconds}s</span>)}
      </div>
      <div data-timeline-track data-testid="timeline-track" onPointerCancel={cancelPointerDraft} onPointerMove={movePointerDraft} onPointerUp={endPointerDraft} style={{ position: "relative" }}>
      <div aria-label="고정 트랙" role="list">
        {TIMELINE_LANES.map((lane) => <div key={lane} aria-label={laneLabel[lane]} role="listitem" style={{ height: `${LANE_HEIGHT_PX}px`, borderTop: "1px solid currentColor", position: "relative" }}>
          <span>{laneLabel[lane]}</span>
          {/* **잠금 · 눈 · 음소거**(`capcut-observed` 기록 §2: "트랙마다 왼쪽에
              잠금 · 눈 · 음소거 · `···`"). 셋의 성격이 다르다 --
              **잠금**은 화면 안에서만 쓰는 것이라 여기 상태로 끝나고(새로고침하면
              풀린다), **눈·음소거는 결과물이 달라지는 편집**이라 세션에 남고
              렌더까지 간다(`track_states.py`). `···`는 기록에 메뉴 내용이
              없어 만들지 않는다 -- 만들면 지어내는 것이다. */}
          <button
            type="button"
            data-native-control="timeline-lane-lock"
            aria-label={`${laneLabel[lane]} 트랙 잠금`}
            aria-pressed={lockedLanes.has(lane)}
            onClick={() => toggleLaneLock(lane)}
          >
            {lockedLanes.has(lane) ? <Lock aria-hidden="true" size={14} /> : <Unlock aria-hidden="true" size={14} />}
          </button>
          {/* 트랙마다 **뜻이 있는 것만** 그린다. 자막 트랙 음소거처럼 눌러도
              아무 일도 안 일어날 단추는 두지 않는다(기록 §4). */}
          {HIDEABLE_LANES.has(lane) ? <button
            type="button"
            data-native-control="timeline-lane-hidden"
            aria-label={`${laneLabel[lane]} 트랙 숨기기`}
            aria-pressed={hiddenLanes.has(lane)}
            disabled={!onUpdateTrackStates || isSaving}
            onClick={() => toggleTrackState(lane, "hidden")}
          >
            {hiddenLanes.has(lane) ? <EyeOff aria-hidden="true" size={14} /> : <Eye aria-hidden="true" size={14} />}
          </button> : null}
          {MUTABLE_LANES.has(lane) ? <button
            type="button"
            data-native-control="timeline-lane-muted"
            aria-label={`${laneLabel[lane]} 트랙 음소거`}
            aria-pressed={mutedLanes.has(lane)}
            disabled={!onUpdateTrackStates || isSaving}
            onClick={() => toggleTrackState(lane, "muted")}
          >
            {mutedLanes.has(lane) ? <VolumeX aria-hidden="true" size={14} /> : <Volume2 aria-hidden="true" size={14} />}
          </button> : null}
        </div>)}
      </div>
      <div aria-label="타임라인 클립" role="group" style={{ inset: 0, position: "absolute" }}>
        {draftProjection.rects.map((rect) => {
        const ordinalInLane = laneOrdinalByClipId.get(rect.clipId) ?? 1;
        const narrationClip = rect.lane === "narration" ? narrationByClipId.get(rect.clipId) : undefined;
        const placement = placementsByClipId.get(rect.clipId);
        const displayBounds = draftProjection.boundsByClipId.get(rect.clipId);
        const isTranscriptSelected = narrationClip?.segmentId === selectedSegmentId || captionsByPlacementId.get(rect.clipId)?.segmentId === selectedSegmentId;
        const isSelected = state.selectedClipId === rect.clipId;
        const clipContent = clipContentLabel({
          captionText: captionsByPlacementId.get(rect.clipId)?.text,
          overlayType: overlayByPlacementId.get(rect.clipId)?.overlayType,
          overlayPayload: overlayByPlacementId.get(rect.clipId)?.overlayPayload,
        });
        const clipDisplayName = formatClipDisplayName(rect.lane, ordinalInLane, displayBounds?.startSec ?? 0, clipContent);
        const clipShortName = formatClipShortName(rect.lane, ordinalInLane, clipContent);
        return <div
        aria-label={`${clipDisplayName} 클립`}
        data-clip-id={rect.clipId}
        data-end-seconds={displayBounds ? formatSeconds(displayBounds.endSec) : undefined}
        data-selected={isSelected || isTranscriptSelected ? "true" : "false"}
        data-start-seconds={displayBounds ? formatSeconds(displayBounds.startSec) : undefined}
        data-testid="timeline-clip"
        key={rect.clipId}
        role="group"
        // 캡컷처럼 재료를 장면 위로 끌어다 놓는다. **우리가 실은 짐일 때만** 받는다 --
        // 파일 탐색기에서 끌어온 것에 커서를 바꾸면 받을 것처럼 보이는 거짓말이 된다.
        data-drop-target={dragOverClipId === rect.clipId ? "true" : undefined}
        onDragOver={(event) => {
          const segmentId = segmentIdForClip(rect.clipId);
          if (!onDropAsset || !segmentId || !carriesAsset(event.dataTransfer)) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
          if (dragOverClipId !== rect.clipId) setDragOverClipId(rect.clipId);
        }}
        onDragLeave={() => { if (dragOverClipId === rect.clipId) setDragOverClipId(null); }}
        onDrop={(event) => {
          const segmentId = segmentIdForClip(rect.clipId);
          const cardId = readAssetDrag(event.dataTransfer);
          setDragOverClipId(null);
          if (!onDropAsset || !segmentId || !cardId) return;
          event.preventDefault();
          onDropAsset({ cardId, segmentId });
        }}
        style={{ left: `${rect.x}px`, overflow: "hidden", position: "absolute", top: `${rect.y}px`, width: `${rect.width}px`, height: `${rect.height}px` }}
      >{clipPictureByClipId.get(rect.clipId) && !brokenPictures.has(rect.clipId) ? <img
        data-clip-picture="true"
        alt=""
        aria-hidden="true"
        loading="lazy"
        onError={() => setBrokenPictures((current) => new Set(current).add(rect.clipId))}
        src={clipPictureByClipId.get(rect.clipId)}
        style={{ height: "100%", inset: 0, objectFit: "cover", opacity: 0.55, pointerEvents: "none", position: "absolute", width: "100%" }}
      /> : null}<button data-native-control="timeline-clip-select"
        aria-label={clipDisplayName}
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
      >{/* 보이는 이름은 짧게 왼쪽 위에만. 전체 이름이 막대를 가로질러 깔리면
          썸네일·파형을 덮는다. 시작 시각까지 담은 전체 이름은 aria-label에 있고,
          이 짧은 이름은 그 앞부분이라 음성으로 불러도 어긋나지 않는다. */}
        <span aria-hidden="true" className="vb-timeline-clip__name">{clipShortName}</span></button>{narrationClip && isSelected ? <span data-mutation-controls="true" onClick={(event) => event.stopPropagation()} style={{ inset: 0, overflow: "hidden", pointerEvents: "none", position: "absolute" }}>
        <button data-native-control="timeline-trim-start" aria-label={`${clipDisplayName} 시작 자르기`} data-trim-edge="start" disabled={isSaving || lockedLanes.has("narration")} onKeyDown={(event) => keyboardTrim(event, narrationClip, "start")} onPointerDown={(event) => startTrim(event, narrationClip, "start")} style={{ bottom: 0, left: 0, maxWidth: "33.333%", overflow: "hidden", padding: 0, pointerEvents: "auto", position: "absolute", top: 0, width: "33.333%" }} title="왼쪽·오른쪽 화살표로 한 프레임씩 조절" type="button">시작</button>
        <button data-native-control="timeline-trim-end" aria-label={`${clipDisplayName} 끝 자르기`} data-trim-edge="end" disabled={isSaving || lockedLanes.has("narration")} onKeyDown={(event) => keyboardTrim(event, narrationClip, "end")} onPointerDown={(event) => startTrim(event, narrationClip, "end")} style={{ bottom: 0, maxWidth: "33.333%", overflow: "hidden", padding: 0, pointerEvents: "auto", position: "absolute", right: 0, top: 0, width: "33.333%" }} title="왼쪽·오른쪽 화살표로 한 프레임씩 조절" type="button">끝</button>
        <button data-native-control="timeline-reorder" aria-label={`${clipDisplayName} 순서 바꾸기`} data-reorder-control="true" disabled={isSaving || lockedLanes.has("narration")} onKeyDown={(event) => keyboardReorder(event, narrationClip)} onPointerDown={(event) => startReorder(event, narrationClip)} style={{ bottom: 0, left: "33.333%", maxWidth: "33.334%", overflow: "hidden", padding: 0, pointerEvents: "auto", position: "absolute", top: 0, width: "33.334%" }} title="왼쪽·오른쪽 화살표로 한 칸씩 이동" type="button">순서</button>
      </span> : null}{placement && isSelected ? <span data-placement-controls="true" onClick={(event) => event.stopPropagation()} style={{ display: "flex", gap: 2, inset: 0, pointerEvents: "none", position: "absolute" }}>
        <button data-native-control="placement-trim-start" aria-label={`${clipDisplayName} 시작 자르기`} disabled={isSaving || lockedLanes.has(placement.kind)} onKeyDown={(event) => keyboardPlacementTrim(event, placement, "start")} onPointerDown={(event) => startPlacement(event, placement, "trim", "start")} style={{ pointerEvents: "auto" }} title="드래그하거나 왼쪽·오른쪽 화살표로 한 프레임씩 조절" type="button">시작</button>
        <button data-native-control="placement-move" aria-label={`${clipDisplayName} 이동`} disabled={isSaving || lockedLanes.has(placement.kind)} onKeyDown={(event) => keyboardPlacementMove(event, placement)} onPointerDown={(event) => startPlacement(event, placement, "move")} style={{ pointerEvents: "auto" }} title="드래그하거나 왼쪽·오른쪽 화살표로 한 프레임씩 이동" type="button">이동</button>
        <button data-native-control="placement-trim-end" aria-label={`${clipDisplayName} 끝 자르기`} disabled={isSaving || lockedLanes.has(placement.kind)} onKeyDown={(event) => keyboardPlacementTrim(event, placement, "end")} onPointerDown={(event) => startPlacement(event, placement, "trim", "end")} style={{ pointerEvents: "auto" }} title="드래그하거나 왼쪽·오른쪽 화살표로 한 프레임씩 조절" type="button">끝</button>
      </span> : null}</div>;
        })}
      </div>
      </div>
      <div
        className="vb-timeline-playhead"
        data-seconds={formatSeconds(state.playheadSec)}
        data-testid="timeline-playhead"
        style={{ left: `${playheadX}px` }}
      ><span aria-hidden="true" className="vb-timeline-playhead__grip" />{/*
        캡컷처럼 재생 머리를 잡고 문지른다. 클릭만 되던 때는 자를 자리를 찾으려면
        찍고 확인하고 다시 찍기를 반복해야 했다. 선은 2px뿐이라 잡을 수 없으므로
        이 단추가 선 위에 넓은 손자리를 겹쳐 둔다. 화살표 키는 타임라인의 기존
        키 경로가 그대로 받는다.
      */}<button
        aria-label="재생 위치 끌기"
        className="vb-timeline-playhead__handle"
        data-native-control="timeline-scrub"
        onPointerCancel={cancelPointerDraft}
        onPointerDown={startScrub}
        onPointerMove={moveScrub}
        onPointerUp={endScrub}
        title="끌어서 재생 위치를 훑고, 왼쪽·오른쪽 화살표로 한 프레임씩"
        type="button"
      /></div>
    </div>
    {/* 아래 상태 줄들도 같은 이유로 한 줄에 모은다. 하나하나는 짧은 조각인데
        한 줄씩 차지하면 눈금과 트랙이 밀려 스크롤 안으로 들어간다. */}
    <div className="vb-editor-workbench__timeline-foot">
      {visibleGaps.map((gap) => <p key={gap.gapId}>미디어 공백: {gap.reason}</p>)}
      {caption ? <p>현재 자막: {caption.text}</p> : <p>현재 자막 없음</p>}
      {selectedPlacementIds.length > 1 ? <p>선택한 독립 항목: {selectedPlacementIds.length}개</p> : null}
      {/* §10.13: the snap target id is an internal key (caption:<segment>:start)
          and meant nothing to the owner. The kind and the time are the parts that
          actually tell them where the playhead landed. */}
      {snap ? <p>스냅: {snapKindLabel[snap.kind]} ({formatSeconds(snap.timeSec)}초)</p> : <p>스냅 없음</p>}
      {mutationMessage ? <p role="status" aria-label="편집 저장 상태">{mutationMessage}</p> : null}
      <output aria-label="재생 위치" data-seconds={formatSeconds(state.playheadSec)}>{formatSeconds(state.playheadSec)}초</output>
      {draftProjection.rects.length === 0 && visibleGaps.length === 0 ? <p>표시할 타임라인 항목이 없습니다.</p> : null}
    </div>
  </section>;
}
