import { type CSSProperties, type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";

import { api, type OutputVariant, type OutputVariantPatch } from "../../../api";
import { ChevronsLeftRight, Copy, PanelLeft, PanelRight, Redo2, Scissors, Trash2, Undo2 } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "../../../components/ui/resizable";
import type { PanelImperativeHandle, PanelSize } from "react-resizable-panels";
import type { EditorViewModel } from "../editorViewModel";
import type { EditorSessionSnapshot } from "../editorSnapshot";
import type { EditorAssetCard } from "../assets/editorAssetProjection";
import type { EditorAssetPreviewState } from "../assets/EditorAssetBrowser";
import type { ApprovedTtsCandidate, InspectorAction, PartialRegenerationControls } from "../inspector/InspectorControls";
import { PreviewStage, type AuditionRequest, type AuditionSource } from "../preview/preview-stage";
import { sceneNumbersBySegmentId } from "../sceneNames";
import { TimelineDock } from "../timeline/TimelineDock";
import { activeSegmentIdAt, clampPlaybackSeconds } from "../transcript/playbackNavigation";
import { EditorWorkbenchReadOnlyAdapters } from "./editorWorkbenchReadOnlyAdapters";
import { resolveEditorWorkbenchLayout, timelineHeightLimitsRem, type EditorWorkbenchPersistedState } from "./editorWorkbenchLayout";
import { hasLegacyEditorUiState, readEditorUiState, readVariantsCollapsed, writeEditorUiState, writeVariantsCollapsed } from "./editorUiState";
import type { RightDockCandidate, RightDockDirector } from "./rightDockTypes";
import { VariantCompare } from "../variants/VariantCompare";
import { cutToolbarState, EMPTY_CUT_TOOLS, type CutToolbarState } from "./cutToolbar";
import { cutShortcutFor } from "./cutShortcuts";
import { VariantConflictPanel } from "../variants/VariantConflictPanel";
import { VariantSelector } from "../variants/VariantSelector";
import { projectServerVariant, projectVariant, type VariantKind } from "../variants/variantProjection";
import { VariantServerControls } from "../variants/VariantServerControls";
import { usePublishShellCanvas } from "../../shell/shellCanvas";

export function persistedPanelPixels(size: PanelSize, minPx: number, fallback: number) {
  const pixels = Number(size.inPixels);
  return Number.isFinite(pixels) ? Math.max(minPx, Math.round(pixels)) : fallback;
}

const activeDrawerStorageKey = "videobox.editor-workbench.active-drawer";
type ActiveDrawer = "left" | "right" | null;
function readActiveDrawer(): ActiveDrawer {
  try {
    const value = window.localStorage.getItem(activeDrawerStorageKey);
    return value === "left" || value === "right" ? value : null;
  } catch {
    return null;
  }
}
function writeActiveDrawer(value: ActiveDrawer): void {
  try {
    if (value) window.localStorage.setItem(activeDrawerStorageKey, value);
    else window.localStorage.removeItem(activeDrawerStorageKey);
  } catch {
    // Drawer visibility is UI-only and best effort.
  }
}
let lastActiveDrawer: ActiveDrawer = null;

type NarrationTrim = Readonly<{ segmentId: string; startSec: number; endSec: number }>;
type NarrationReorder = Readonly<{
  segmentIds: string[];
  boundsById: Record<string, { startSec: number; endSec: number }>;
}>;
type TimelinePlacements = Readonly<{ changes: Array<{ placementId: string; kind: "broll" | "bgm" | "sfx" | "overlay" | "caption"; startSec: number; endSec: number }> }>;
type CaptionText = Readonly<{ segmentId: string; text: string }>;
type EditorWorkbenchProps = Readonly<{
  view: EditorViewModel;
  session?: EditorSessionSnapshot | null;
  onPreviewRefresh?: () => void | Promise<void>;
  onUndo?: () => void | Promise<void>;
  onRedo?: () => void | Promise<void>;
  onTrimNarration?: (input: NarrationTrim) => void | Promise<void>;
  onReorderNarration?: (input: NarrationReorder) => void | Promise<void>;
  onUpdatePlacements?: (input: TimelinePlacements) => void | Promise<void>;
  onUpdateCaption?: (input: CaptionText) => void | Promise<void>;
  onInspectorAction?: (action: InspectorAction) => void | Promise<void>;
  loadApprovedTtsCandidates?: (segmentId: string) => Promise<readonly ApprovedTtsCandidate[]>;
  ttsCandidateScopeKey?: string;
  partialRegeneration?: PartialRegenerationControls;
  assetCards?: readonly EditorAssetCard[];
  onApplyAssetCard?: (card: EditorAssetCard, segmentId: string) => void | Promise<void>;
  onApplyImageOverlay?: (card: EditorAssetCard, segmentId: string) => void | Promise<void>;
  onPrepareAssetPreview?: (card: EditorAssetCard) => Promise<string>;
  isSavingTimeline?: boolean;
  timelineMutationMessage?: string;
  director?: RightDockDirector;
  requestedSegmentId?: string | null;
  serverVariants?: readonly OutputVariant[];
  onVariantMaterialize?: (variant: OutputVariant) => void | Promise<void>;
  onVariantPatch?: (variant: OutputVariant, patch: OutputVariantPatch) => void | Promise<void>;
  onVariantCreateHighlight?: () => void | Promise<void>;
  variantBusy?: boolean;
}>;

export function EditorWorkbench(props: EditorWorkbenchProps) {
  const routeKey = `${props.view.projectId}:${props.view.sessionId}`;
  return <EditorWorkbenchInstance key={routeKey} {...props} />;
}

function EditorWorkbenchInstance({
  view,
  session,
  onPreviewRefresh,
  onUndo,
  onRedo,
  onTrimNarration,
  onReorderNarration,
  onUpdatePlacements,
  onUpdateCaption,
  onInspectorAction,
  loadApprovedTtsCandidates,
  ttsCandidateScopeKey,
  partialRegeneration,
  assetCards = [],
  onApplyAssetCard,
  onApplyImageOverlay,
  onPrepareAssetPreview,
  isSavingTimeline = false,
  timelineMutationMessage,
  director,
  requestedSegmentId = null,
  serverVariants = [],
  onVariantMaterialize,
  onVariantPatch,
  onVariantCreateHighlight,
  variantBusy = false,
}: EditorWorkbenchProps) {
  const viewRouteKey = `${view.projectId}:${view.sessionId}`;
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const [availableWorkbenchWidth, setAvailableWorkbenchWidth] = useState(() => window.innerWidth);
  const [ui, setUi] = useState<EditorWorkbenchPersistedState>(() => {
    const scoped = readEditorUiState(view.projectId, view.sessionId);
    const useLegacy = hasLegacyEditorUiState();
    return { ...scoped, activeDrawer: useLegacy ? scoped.activeDrawer : (lastActiveDrawer ?? readActiveDrawer() ?? scoped.activeDrawer) };
  });
  const [variantMode, setVariantMode] = useState<VariantKind | "side_by_side">("master");
  const [variantsCollapsed, setVariantsCollapsed] = useState(() => readVariantsCollapsed(view.projectId));
  // 위 띠의 화면 비율 자리는 **이 줄이 채운다**(`features/shell/shellCanvas.tsx`).
  // 껍데기가 직접 물어보게 하지 않는 이유는 그쪽 주석에 적었다. 편집기를 떠나면
  // 저절로 지워지므로, 다른 화면에서 남은 값이 보일 일은 없다.
  usePublishShellCanvas(view.output);
  // **타임라인 높이는 편집자가 정한다.** 컷을 딸 때는 타임라인을 키우고 화면을 볼
  // 때는 미리보기를 키우는 것이 편집자가 실제로 하는 일이다. 좌우 도크는 이미
  // 끌어서 폭을 바꾸는데 위아래만 내가 CSS로 정해 놓고 있었다.
  //
  // 손대기 전에는 `null`이고, 그동안은 화면 높이에 맞춘 CSS 기본값이 그대로 쓰인다.
  // 높이는 좌우 도크 폭과 같은 자리(`editorUiState`)에 저장돼 새로고침을 넘긴다.
  const setTimelineRem = (nextRem: number) => setUi((current) => ({
    ...current,
    timelineRem: Math.min(timelineHeightLimitsRem.max, Math.max(timelineHeightLimitsRem.min, nextRem)),
  }));
  const resizeTimeline = (deltaRem: number) => setTimelineRem((ui.timelineRem ?? 20) + deltaRem);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(view.local.selectedSegmentId);
  const [playbackSec, setPlaybackSec] = useState(view.local.seekSec);
  const [requestedSegmentFocusEpoch, setRequestedSegmentFocusEpoch] = useState(0);
  const [auditionState, setAuditionState] = useState<Readonly<{
    routeKey: string;
    request: AuditionRequest | null;
  }>>({ routeKey: viewRouteKey, request: null });
  const [assetPreviewStates, setAssetPreviewStates] = useState<Readonly<Record<string, EditorAssetPreviewState>>>({});
  const assetPreviewRequestId = useRef(0);
  const auditionRequest = auditionState.routeKey === viewRouteKey
    ? auditionState.request
    : null;
  const bodyRef = useRef<HTMLDivElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<"left" | "right" | null>(null);
  const leftPanelRef = useRef<PanelImperativeHandle>(null);
  const rightPanelRef = useRef<PanelImperativeHandle>(null);
  const leftTriggerRef = useRef<HTMLButtonElement>(null);
  const rightTriggerRef = useRef<HTMLButtonElement>(null);
  const viewRouteKeyRef = useRef(viewRouteKey);
  const activeRequestedSegmentKey = useRef<string | null>(null);
  useEffect(() => { const update = () => setViewportWidth(window.innerWidth); window.addEventListener("resize", update); return () => window.removeEventListener("resize", update); }, []);
  // Undo from the keyboard, standard bindings only. Ctrl/Cmd+Z undoes. Redo
  // has two conventions in the wild -- Ctrl+Shift+Z in creative apps, Ctrl+Y
  // in Office-style ones -- so both are accepted; taking only one would leave
  // the other silently doing nothing. Alt+Z is deliberately not bound: it
  // means undo nowhere, so binding it invites pressing it for redo and getting
  // a second undo. Never while a text field has focus -- undoing the whole
  // edit mid-sentence would throw away the typing and a real edit at once, and
  // the browser's own text undo is the right thing there.
  // 컷 도구는 이 아래에서 계산된다. ref로 들고 있어야 키 처리기를 매번 다시 붙이지
  // 않으면서도 늘 최신 상태를 본다.
  const cutToolsRef = useRef<CutToolbarState>(EMPTY_CUT_TOOLS);
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      const key = event.key.toLowerCase();
      const target = event.target as HTMLElement | null;
      if (target?.isContentEditable) return;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      // 캡컷 컷 단축키. 무엇을 할 수 있는지는 툴바가 이미 정했으므로 그것을 그대로
      // 쓴다 -- 여기서 다시 계산하면 단추와 키가 서로 다른 판단을 하게 된다.
      const cutAction = cutShortcutFor(event, cutToolsRef.current);
      if (cutAction) {
        if (isSavingTimeline || !onInspectorAction) return;
        event.preventDefault();
        void onInspectorAction(cutAction);
        return;
      }
      if (key !== "z" && key !== "y") return;
      const chord = (event.ctrlKey || event.metaKey) && !event.altKey;
      const redo = chord && ((key === "z" && event.shiftKey) || (key === "y" && !event.shiftKey));
      const undo = chord && key === "z" && !event.shiftKey;
      if (redo) {
        if (isSavingTimeline || !onRedo || !session?.redoCount) return;
        event.preventDefault();
        void onRedo();
        return;
      }
      if (!undo) return;
      if (isSavingTimeline || !onUndo || !session?.undoCount) return;
      event.preventDefault();
      void onUndo();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isSavingTimeline, onUndo, onRedo, onInspectorAction, session?.undoCount, session?.redoCount]);
  useLayoutEffect(() => {
    const measure = () => setAvailableWorkbenchWidth(bodyRef.current?.getBoundingClientRect().width || window.innerWidth);
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    if (bodyRef.current) observer?.observe(bodyRef.current);
    window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, []);
  useEffect(() => {
    if (viewRouteKeyRef.current !== viewRouteKey) {
      viewRouteKeyRef.current = viewRouteKey;
      activeRequestedSegmentKey.current = null;
      setSelectedSegmentId(view.local.selectedSegmentId);
      setPlaybackSec(clampPlaybackSeconds(view.local.seekSec, view.output.durationSec));
      const scoped = readEditorUiState(view.projectId, view.sessionId);
      const useLegacy = hasLegacyEditorUiState();
      setUi({ ...scoped, activeDrawer: useLegacy ? scoped.activeDrawer : (lastActiveDrawer ?? readActiveDrawer() ?? scoped.activeDrawer) });
      setVariantsCollapsed(readVariantsCollapsed(view.projectId));
      setAuditionState({ routeKey: viewRouteKey, request: null });
      assetPreviewRequestId.current += 1;
      setAssetPreviewStates({});
      return;
    }
    const segmentIds = new Set([
      ...view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips.map((clip) => clip.segmentId)),
      ...view.captions.map((caption) => caption.segmentId),
    ]);
    setSelectedSegmentId((current) => current && segmentIds.has(current) ? current : segmentIds.has(view.local.selectedSegmentId ?? "") ? view.local.selectedSegmentId : null);
    setPlaybackSec((current) => clampPlaybackSeconds(current, view.output.durationSec));
  }, [view.captions, view.expectedRevision, view.local.selectedSegmentId, view.output.durationSec, view.projectId, view.sessionId, view.tracks, viewRouteKey]);
  useEffect(() => {
    if (viewRouteKeyRef.current === viewRouteKey) {
      writeEditorUiState(view.projectId, view.sessionId, ui);
    }
  }, [ui, view.projectId, view.sessionId, viewRouteKey]);
  useEffect(() => { if (ui.activeDrawer) drawerRef.current?.focus(); }, [ui.activeDrawer]);
  useEffect(() => {
    const normalizedRequestedSegmentId = requestedSegmentId?.trim() || null;
    if (!normalizedRequestedSegmentId) {
      activeRequestedSegmentKey.current = null;
      return;
    }
    const key = `${view.sessionId}:${normalizedRequestedSegmentId}`;
    if (activeRequestedSegmentKey.current === key) return;
    const requestedNarration = view.tracks
      .filter((track) => track.role === "narration")
      .flatMap((track) => track.clips)
      .find((clip) => clip.segmentId === normalizedRequestedSegmentId)
      ?? view.captions.find((caption) => caption.segmentId === normalizedRequestedSegmentId);
    if (!requestedNarration) {
      activeRequestedSegmentKey.current = null;
      return;
    }
    activeRequestedSegmentKey.current = key;
    setRequestedSegmentFocusEpoch((current) => current + 1);
    setSelectedSegmentId(requestedNarration.segmentId);
    setPlaybackSec(clampPlaybackSeconds(requestedNarration.startSec, view.output.durationSec));
  }, [requestedSegmentId, view.captions, view.output.durationSec, view.sessionId, view.tracks]);
  useEffect(() => { const side = restoreFocusRef.current; if (!ui.activeDrawer && side) { restoreFocusRef.current = null; window.setTimeout(() => (side === "left" ? leftTriggerRef : rightTriggerRef).current?.focus(), 0); } }, [ui.activeDrawer]);
  const layout = resolveEditorWorkbenchLayout({ viewportWidth, availableWorkbenchWidth, persisted: ui });
  /** 도크 단추. **방금 누른 쪽이 이긴다.**
   *
   * 좁은 데스크톱은 도크를 하나만 보여 주는데, 어느 쪽을 보일지는 `leftOpen`이
   * 먼저 정했다. 그래서 왼쪽이 열려 있으면 `세부 정보`을 눌러도 **아무 일도
   * 없는 것처럼** 보였다 -- 왼쪽을 먼저 닫아야 나왔다(2026-08-19 배포 화면에서 확인).
   * 처음 쓰는 사람은 그것을 고장으로 읽는다.
   *
   * 넓은 화면(`desktop-both`)에서는 둘 다 열리므로 여는 동작만 하고 상대를 닫지
   * 않는다. 닫는 것은 어느 폭에서나 그대로 닫는다.
   */
  /** 저장된 값이 아니라 **지금 화면에 실제로 보이는지**를 돌려준다.
   *  좁은 화면에서는 둘 다 열려 있어도 하나만 보인다. */
  const resolvedVisible = (state: EditorWorkbenchPersistedState) => {
    const resolved = resolveEditorWorkbenchLayout({ viewportWidth, availableWorkbenchWidth, persisted: state });
    const both = resolved.mode === "desktop-both";
    return { left: both || resolved.leftOpen, right: both || resolved.rightOpen };
  };
  const toggleDock = (side: "left" | "right") => setUi((current) => {
    // **누르는 사람이 보는 것을 기준으로 정한다. 저장된 값이 아니라.**
    //
    // 2026-08-22에 기본값을 `양쪽 다 열림`으로 바꾸자 이 자리가 다시 죽었다.
    // 좁은 데스크톱에서는 둘 다 못 들어가서 왼쪽이 이기는데, 저장된 값으로는
    // 오른쪽도 `열림`이다. 그래서 `세부 정보`를 누르면 **닫기**로 읽혀 아무 일도
    // 일어나지 않았다 -- 화면에는 처음부터 안 보이는데.
    //
    // 이건 2026-08-19에 고쳤던 그 결함과 같은 것이고,
    // `shows the dock the creator just asked for`가 다시 잡아 줬다.
    const showing = side === "left"
      ? resolvedVisible(current).left
      : resolvedVisible(current).right;
    const opening = !showing;
    if (!opening) return { ...current, [side === "left" ? "leftOpen" : "rightOpen"]: false };
    // **지금 어느 모드인가가 아니라 "둘 다 들어가는가"로 정한다.** 앞엣것으로
    // 재면 왼쪽이 열린 상태는 늘 `desktop-single`이라, 1920 화면처럼 자리가
    // 남는데도 상대를 닫았다 -- 누른 사람은 열린 줄 모르고 한 번 더 누른다.
    // 자리를 물어보는 곳은 레이아웃 계산 한 군데뿐이니 그것에게 그대로 묻는다.
    const bothWouldFit = resolveEditorWorkbenchLayout({
      viewportWidth,
      availableWorkbenchWidth,
      persisted: { ...current, leftOpen: true, rightOpen: true },
    }).mode === "desktop-both";
    const closesTheOther = opening && !bothWouldFit;
    return {
      ...current,
      leftOpen: side === "left" ? true : closesTheOther ? false : current.leftOpen,
      rightOpen: side === "right" ? true : closesTheOther ? false : current.rightOpen,
    };
  });
  const openDrawer = (side: "left" | "right") => { lastActiveDrawer = side; writeActiveDrawer(side); setUi((current) => ({ ...current, activeDrawer: side })); };
  const closeDrawer = () => { lastActiveDrawer = null; writeActiveDrawer(null); setUi((current) => ({ ...current, activeDrawer: null })); };
  const closeAndRestore = () => { restoreFocusRef.current = ui.activeDrawer; closeDrawer(); };
  const selectSegment = (segmentId: string) => setSelectedSegmentId(segmentId);
  const seekPlayback = (seconds: number) => {
    const nextSeconds = clampPlaybackSeconds(seconds, view.output.durationSec);
    setPlaybackSec(nextSeconds);
    // **장면(내레이션 클립)이 먼저다.** 예전에는 자막이 있으면 자막에서 골랐는데,
    // 장면을 나누고 나면 자막 구간과 장면 구간이 어긋난다. 그래서 7초를 눌렀는데
    // 5~7초 장면이 골라지고 `나누기`가 영영 잠겼다(2026-08-17 실제 앱에서 확인).
    // 컷 도구가 다루는 단위는 장면이므로, 고를 것도 장면이어야 한다.
    const narrationSpans = view.tracks
      .filter((track) => track.role === "narration")
      .flatMap((track) => track.clips.map((clip) => ({ segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec })));
    // 다만 내레이션이 **긴 통짜 하나**일 때는(원본 영상 소리로 만든 초안) 장면이
    // 하나뿐이라 아무것도 구분하지 못한다. 그때는 자막이 의미 단위다.
    const activeSegmentId = activeSegmentIdAt(narrationSpans.length > 1 ? narrationSpans : view.captions.length ? view.captions : narrationSpans, nextSeconds);
    setSelectedSegmentId(activeSegmentId);
  };
  const selectedNarration = selectedSegmentId === null ? null : view.tracks
    .filter((track) => track.role === "narration")
    .flatMap((track) => track.clips)
    .find((clip) => clip.segmentId === selectedSegmentId)
    ?? view.captions.find((caption) => caption.segmentId === selectedSegmentId)
    ?? null;
  const assetTarget = selectedNarration === null ? null : { segmentId: selectedNarration.segmentId, startSec: selectedNarration.startSec, endSec: selectedNarration.endSec };
  // 캡컷처럼 컷 도구를 타임라인 위에 둔다. 2026-08-17까지 이 툴바에는 편집하는
  // 단추가 하나도 없었고, 나누기·붙이기는 `선택 구간 편집`이라는 이름 뒤에 있어
  // 컷편집을 찾는 사람은 만나지 못했다. 실제 변경은 기존 InspectorAction 경로가 한다.
  const cutTools = cutToolbarState({
    clips: view.tracks
      .filter((track) => track.role === "narration")
      .flatMap((track) => track.clips)
      .map((clip) => ({
        segmentId: clip.segmentId,
        startSec: clip.startSec,
        endSec: clip.endSec,
        // 뺀 장면인지는 타임라인 클립이 아니라 편집 세션이 안다.
        cutAction: session?.segments?.find((segment) => segment.segmentId === clip.segmentId)?.cutAction,
      })),
    // 장면에 붙어 있는 재료. `다음 장면에도`가 그대로 옮길 대상이다.
    media: view.tracks
      .filter((track) => track.role === "broll" || track.role === "bgm" || track.role === "sfx")
      .flatMap((track) => track.clips.flatMap((clip) => clip.assetId
        ? [{ segmentId: clip.segmentId, mediaKind: track.role as "broll" | "bgm" | "sfx", assetId: clip.assetId, controls: clip.controls }]
        : [])),
    selectedSegmentId,
    playheadSec: playbackSec,
  });
  // 잠긴 단추는 마우스 이벤트를 받지 않아 자기 title을 못 띄운다. 감싸는 자리에
  // 걸어야 **왜 잠겼는지**가 보인다 -- 이유 없이 회색인 단추는 고장으로 읽힌다.
  cutToolsRef.current = cutTools;
  const cutButton = (tool: typeof cutTools.split, Icon: typeof Scissors) => (
    <span title={tool.hint} className="vb-cut-tool">
      <Button
        type="button"
        variant="outline"
        aria-description={tool.hint}
        disabled={!tool.enabled || isSavingTimeline || !onInspectorAction}
        onClick={() => { if (tool.action) void onInspectorAction?.(tool.action); }}
      >
        <Icon aria-hidden="true" />
        {tool.label}
      </Button>
    </span>
  );
  const playAssetCard = (card: EditorAssetCard, previewUrl: string) => {
    const mediaKind = card.previewKind ?? (card.kind === "broll" ? "video" : "audio");
    setAuditionState((current) => {
      const currentRequest = current.routeKey === viewRouteKey ? current.request : null;
      return {
        routeKey: viewRouteKey,
        request: {
          requestId: (currentRequest?.requestId ?? 0) + 1,
          source: { id: card.id, label: card.title, url: previewUrl, mediaKind, timelineRange: assetTarget ?? { startSec: 0, endSec: view.output.durationSec } },
        },
      };
    });
  };
  const previewAssetCard = (card: EditorAssetCard) => {
    const requestId = assetPreviewRequestId.current + 1;
    assetPreviewRequestId.current = requestId;
    if (!card.requiresBrowserPreviewPreparation || !onPrepareAssetPreview) {
      setAssetPreviewStates({});
      playAssetCard(card, card.previewUrl);
      return;
    }
    setAssetPreviewStates({ [card.id]: { status: "preparing" } });
    void onPrepareAssetPreview(card).then((previewUrl) => {
      if (assetPreviewRequestId.current !== requestId || viewRouteKeyRef.current !== viewRouteKey) return;
      setAssetPreviewStates({});
      playAssetCard(card, previewUrl);
    }).catch(() => {
      if (assetPreviewRequestId.current !== requestId || viewRouteKeyRef.current !== viewRouteKey) return;
      setAssetPreviewStates({ [card.id]: { status: "failed" } });
    });
  };
  const previewDirectorCandidate = (candidate: RightDockCandidate) => {
    const previewUrl = candidate.previewUrl;
    if (!previewUrl) return;
    setAuditionState((current) => {
      const currentRequest = current.routeKey === viewRouteKey ? current.request : null;
      return {
        routeKey: viewRouteKey,
        request: {
          requestId: (currentRequest?.requestId ?? 0) + 1,
          source: { id: `director:${candidate.candidateId}`, label: candidate.visibleReferenceCode, url: previewUrl, mediaKind: candidate.mediaType === "broll" || candidate.mediaType === "video" ? "video" : "audio", timelineRange: assetTarget ?? { startSec: 0, endSec: view.output.durationSec } },
        },
      };
    });
  };
  const toggleVariantsCollapsed = () => setVariantsCollapsed((current) => { const next = !current; writeVariantsCollapsed(view.projectId, next); return next; });
  const openManualEditing = () => setUi((current) => layout.mode === "drawer" ? { ...current, activeDrawer: "left" } : { ...current, leftOpen: true });
  const rightDirector = director ? { ...director, onManualEdit: () => { director.onManualEdit(); openManualEditing(); }, onPreviewCandidate: previewDirectorCandidate } : undefined;
  // §10.13: this label is read aloud by screen readers and shown on screen, so
  // it must not carry a raw role name or an internal segment id. Scene numbers
  // follow timeline order, matching how the review screen counts them.
  // 세는 규칙은 `sceneNames`에 하나만 둔다 -- 추천 카드도 같은 번호로 장면을
  // 부르므로, 여기서 따로 세면 같은 장면이 화면마다 다른 번호가 된다.
  const sceneNumbers = sceneNumbersBySegmentId(view);
  const sources: AuditionSource[] = view.tracks.flatMap((track) => track.clips.flatMap((clip) => {
    if (!clip.assetId) return [];
    const url = view.playback.auditionUrls[clip.assetId];
    if (!url) return [];
    const mediaKind = auditionMediaKind(track.role, clip.overlayType);
    const scene = sceneNumbers.get(clip.segmentId);
    const label = `${auditionRoleLabel(track.role)} · ${scene ? `${scene}번째 장면` : "선택한 장면"}`;
    return mediaKind ? [{ id: clip.clipId, label, url, mediaKind, timelineRange: { startSec: clip.startSec, endSec: clip.endSec } }] : [];
  }));
  // Review is a reference action, not part of the applied edit, so it opens
  // the same shell as an asset-card preview rather than one of its own.
  const previewTimelineSource = (source: AuditionSource) => {
    setAuditionState((current) => {
      const currentRequest = current.routeKey === viewRouteKey ? current.request : null;
      return { routeKey: viewRouteKey, request: { requestId: (currentRequest?.requestId ?? 0) + 1, source } };
    });
  };
  const dock = (side: "left" | "right") => <aside aria-label={side === "left" ? "소재" : "세부 정보"} className={`vb-editor-workbench__dock vb-editor-workbench__dock--${side}`}><EditorWorkbenchReadOnlyAdapters assetCards={assetCards} assetPreviewStates={assetPreviewStates} assetTarget={assetTarget} director={rightDirector} dock={side} eugeneDraft={rightDirector?.draft ?? ""} isSavingCaption={isSavingTimeline} loadApprovedTtsCandidates={loadApprovedTtsCandidates} onApplyAssetCard={onApplyAssetCard} onApplyImageOverlay={onApplyImageOverlay} onEugeneDraftChange={rightDirector?.onDraftChange ?? (() => undefined)} onInspectorAction={onInspectorAction} onPreviewAsset={previewAssetCard} onPreviewSource={previewTimelineSource} onRefreshExactPreview={onPreviewRefresh} onSaveCaption={onUpdateCaption} onSeek={seekPlayback} onSelectSegment={selectSegment} partialRegeneration={partialRegeneration} playbackSec={playbackSec} selectedSegmentId={selectedSegmentId} session={session} sources={sources} ttsCandidateScopeKey={ttsCandidateScopeKey} view={view} /></aside>;
  const resize = (side: "left" | "right", delta: number) => setUi((current) => { const key = side === "left" ? "leftSize" : "rightSize"; const value = Math.max(side === "left" ? 220 : 260, current[key] + delta); (side === "left" ? leftPanelRef : rightPanelRef).current?.resize(`${value}px`); return { ...current, [key]: value }; });
  const handleKey = (event: KeyboardEvent<HTMLDivElement>, side: "left" | "right") => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); resize(side, event.key === "ArrowRight" ? 20 : -20); } };
  const trapDrawerFocus = (event: KeyboardEvent<HTMLDivElement>) => { if (event.key === "Escape") { closeAndRestore(); return; } if (event.key !== "Tab") return; const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex="0"]')); if (!focusable.length) { event.preventDefault(); return; } const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } };
  const drawer = layout.activeDrawer && <div ref={drawerRef} role="dialog" aria-modal="true" aria-label={layout.activeDrawer === "left" ? "소재" : "세부 정보"} className="vb-editor-workbench__drawer" onKeyDown={trapDrawerFocus} tabIndex={-1}>{dock(layout.activeDrawer)}<Button type="button" onClick={closeAndRestore}>닫기</Button></div>;
  const leftVisible = layout.mode === "desktop-both" || (layout.mode === "desktop-single" && layout.leftOpen);
  const rightVisible = layout.mode === "desktop-both" || (layout.mode === "desktop-single" && layout.rightOpen);
  // 지금 그 도크가 **실제로 보이는가**. 넓은 화면이면 펴져 있는지, 좁은 화면이면
  // 그 서랍이 열려 있는지 -- 두 모드가 다른 상태를 쓰므로 한 자리에서 합친다.
  const leftShowing = layout.mode === "drawer" ? layout.activeDrawer === "left" : leftVisible;
  const rightShowing = layout.mode === "drawer" ? layout.activeDrawer === "right" : rightVisible;
  // 반복 구간은 새로 만들지 않는다. 화면이 이미 `적용 구간`으로 보여 주는 그 구간이다 --
  // 같은 개념이 두 벌이 되면 하나가 조용히 낡는다.
  // 클립 위에 깔 그림. **주소를 아는 것은 여기의 일**이다 -- 타임라인은 서버를
  // 알지 않는다(`test_editor_ui_source_provenance`가 그 경계를 지킨다).
  //
  // 그림은 새로 만들지 않는다: 영상은 자산 카드가 이미 쓰는 썸네일, 소리는
  // 라이브러리 자산이 이미 쓰던 파형이다. 자산이 없는 클립은 넣지 않는다 --
  // 넣으면 클립마다 404가 나간다.
  const clipPictures = new Map<string, string>(
    view.tracks.flatMap((track) => track.clips.flatMap((clip) => clip.assetId
      ? [[clip.placementId ?? clip.clipId, track.role === "narration" || track.role === "bgm" || track.role === "sfx"
        ? api.assetWaveformUrl(view.projectId, clip.assetId)
        : api.assetThumbnailUrl(view.projectId, clip.assetId)] as const]
      : [])),
  );
  const stage = <PreviewStage key={`${view.projectId}:${view.sessionId}`} auditionRequest={auditionRequest} expectedRevision={view.expectedRevision} exactPreview={view.playback.exactPreview} captions={view.captions} fps={view.fps} loopRange={assetTarget} onPlaybackTimeChange={seekPlayback} playbackSec={playbackSec} sources={sources} onRefresh={onPreviewRefresh} />;
  const variantMaster = {
    variantId: "master",
    label: "마스터" as const,
    kind: "master" as const,
    aspectRatio: "16:9" as const,
    playheadSec: playbackSec,
    durationSec: view.output.durationSec,
    safeArea: "표시 안 함",
    crop: "전체 화면",
    focalPoint: { x: 0.5, y: 0.5 },
    captionLayout: "마스터 자막",
    lockedFields: [],
    conflicts: [],
    ownsAudio: true,
  };
  const serverVariant = serverVariants.find((variant) => variant.kind === (variantMode === "horizontal" ? "horizontal" : "vertical_full"));
  const variantPreview = serverVariant
    ? projectServerVariant({ variant: serverVariant, source: variantMaster })
    : variantMode === "horizontal"
      ? projectVariant({ variantId: "horizontal", kind: "horizontal", source: variantMaster })
      : projectVariant({ variantId: "vertical-full", kind: "vertical_full", source: variantMaster });
  const showVariantCompare = variantMode !== "master";
  const masterSegmentIds = Array.from(new Set([
    ...view.tracks.flatMap((track) => track.clips.map((clip) => clip.segmentId)),
    ...view.captions.map((caption) => caption.segmentId),
  ]));
  const highlightVariant = serverVariants.find((variant) => variant.kind === "vertical_highlight");
  const resolveConflict = (field: string, decision: "keep_local" | "rebase_master") => {
    if (!serverVariant || !onVariantPatch) return;
    void onVariantPatch(serverVariant, { resolve_conflicts: { [field]: decision } });
  };
  return <section className="vb-editor-workbench" aria-label="편집 작업판" data-editor-viewport="bounded" data-project-id={view.projectId} data-session-id={view.sessionId} data-editor-revision={view.expectedRevision} data-editor-density={layout.mode} data-available-workbench-width={Math.round(availableWorkbenchWidth)} style={ui.timelineRem === null ? undefined : ({ "--vb-timeline-height": `${ui.timelineRem}rem` } as CSSProperties)}>
    {/* `현재 편집본`을 뺐다(owner 지시 2026-08-22: 설명 문장을 키워드로).
        늘 같은 글자라 아무것도 말해 주지 않으면서 툴바 자리만 먹었다.
        캡컷 편집기 툴바에는 이런 이름표가 없다 -- 연장만 있다. */}
    <header className="vb-editor-workbench__toolbar"><strong>편집 작업판</strong><div>
      {/* 승인 기록 2026-08-20 항목 2: 큰 주황 알약 여덟 개가 줄지어 있던 자리다.
          채운 주황은 이 저장소에서 **강조**를 뜻하므로(활성 메뉴·선택된 항목·주요 단추)
          도구가 전부 그 색이면 강조가 강조를 못 한다. 도구는 조용한 `outline`으로 내리고,
          강조는 **지금 열려 있는 도크**만 가져간다. 이름은 지우지 않는다 -- 아이콘만
          두면 캡컷을 안 써 본 사람은 무엇인지 알 수 없다.

          **`ghost`를 쓰지 않는다.** 이 앱은 Tailwind preflight 없이 `utilities`만
          불러와서, 배경을 지정하지 않는 `ghost`는 브라우저 기본 단추색이 남는다 --
          어두운 편집 화면에서 실측하니 투명이 아니라 `rgb(107,107,107)` 회색
          상자였다. `outline`은 `bg-background`를 직접 깔아서 그 틈에 안 걸린다. */}
      <Button type="button" variant="outline" title="Ctrl+Z" disabled={isSavingTimeline || !onUndo || !session?.undoCount} onClick={() => void onUndo?.()}><Undo2 aria-hidden="true" />실행 취소</Button>
      <Button type="button" variant="outline" title="Ctrl+Shift+Z 또는 Ctrl+Y" disabled={isSavingTimeline || !onRedo || !session?.redoCount} onClick={() => void onRedo?.()}><Redo2 aria-hidden="true" />다시 실행</Button>
      {cutButton(cutTools.split, Scissors)}{cutButton(cutTools.join, ChevronsLeftRight)}{cutButton(cutTools.drop, Trash2)}{cutButton(cutTools.copyToNext, Copy)}
      {/* **이름을 캡컷 길이로 줄였다(owner 지시 2026-08-22).**
          > "자산과대본. 이라는 것도 말도 안되고 유진과편집항목. 이런메뉴가 어딨어"

          맞는 지적이다. 둘 다 메뉴 이름이 아니라 **안에 뭐가 들었는지 설명하는
          문장**이었다. 캡컷은 같은 자리를 `소재`, `세부 정보`라고 부른다.
          이름이 길면 단추가 커지고, 단추가 크면 툴바가 화면을 먹는다. */}
      <Button ref={leftTriggerRef} type="button" variant={leftShowing ? "default" : "outline"} aria-pressed={leftShowing} onClick={() => layout.mode === "drawer" ? openDrawer("left") : toggleDock("left")}><PanelLeft aria-hidden="true" />소재</Button>
      <Button ref={rightTriggerRef} type="button" variant={rightShowing ? "default" : "outline"} aria-pressed={rightShowing} onClick={() => layout.mode === "drawer" ? openDrawer("right") : toggleDock("right")}><PanelRight aria-hidden="true" />세부 정보</Button>
    </div></header>
    <div ref={bodyRef} className="vb-editor-workbench__body" data-scroll-owner="panels">
      {layout.mode !== "drawer" ? <ResizablePanelGroup orientation="horizontal" className="vb-editor-workbench__panels">
        {leftVisible && <><ResizablePanel panelRef={leftPanelRef} defaultSize={`${ui.leftSize}px`} minSize="220px" onResize={(size) => setUi((current) => ({ ...current, leftSize: persistedPanelPixels(size, 220, current.leftSize) }))}>{dock("left")}</ResizablePanel><ResizableHandle aria-label="왼쪽 패널 크기 조절" onKeyDown={(event) => handleKey(event, "left")} /></>}
        <ResizablePanel minSize={layout.previewMinPx} className="vb-editor-workbench__stage-panel"><div className="vb-editor-workbench__preview" data-scroll-owner="preview" data-preview-min-width={layout.previewMinPx}>{stage}</div></ResizablePanel>
        {rightVisible && <><ResizableHandle aria-label="오른쪽 패널 크기 조절" onKeyDown={(event) => handleKey(event, "right")} /><ResizablePanel panelRef={rightPanelRef} defaultSize={`${ui.rightSize}px`} minSize="260px" onResize={(size) => setUi((current) => ({ ...current, rightSize: persistedPanelPixels(size, 260, current.rightSize) }))}>{dock("right")}</ResizablePanel></>}
      </ResizablePanelGroup> : <><div className="vb-editor-workbench__preview" data-scroll-owner="preview" data-preview-min-width="0">{stage}</div>{drawer}</>}
    </div>
    <section className="vb-editor-variants" aria-label="출력 변형" data-collapsed={variantsCollapsed}>
      <div className="vb-editor-variants__header"><div><h2>가로·세로 비교</h2></div><Button type="button" variant="outline" aria-expanded={!variantsCollapsed} onClick={toggleVariantsCollapsed}>{variantsCollapsed ? "출력 변형 펼치기" : "출력 변형 접기"}</Button></div>
      {!variantsCollapsed ? <><span className="vb-editor-variants__hint">마스터 편집은 하나, 출력은 안전하게 분기</span>
      <VariantSelector selected={variantMode} onSelect={setVariantMode} />
      {variantMode === "master" ? <p className="vb-editor-variants__master-note">현재 마스터 편집본을 기준으로 출력 변형을 확인합니다.</p> : <>
        <VariantCompare master={variantMaster} variant={variantPreview} onSeek={seekPlayback} />
        {serverVariant && onVariantMaterialize && onVariantPatch ? <VariantServerControls variant={serverVariant} busy={variantBusy} onMaterialize={onVariantMaterialize} onPatch={onVariantPatch} onCreateHighlight={onVariantCreateHighlight} /> : null}
      </>}
      {showVariantCompare ? <VariantConflictPanel conflicts={variantPreview.conflicts} onKeep={(field) => resolveConflict(field, "keep_local")} onRebase={(field) => resolveConflict(field, "rebase_master")} /> : null}
      {highlightVariant && onVariantMaterialize && onVariantPatch ? <VariantServerControls variant={highlightVariant} masterSegmentIds={masterSegmentIds} busy={variantBusy} onMaterialize={onVariantMaterialize} onPatch={onVariantPatch} /> : null}</> : null}
    </section>
    <div
      role="separator"
      aria-label="타임라인 높이 조절"
      aria-orientation="horizontal"
      className="vb-editor-workbench__timeline-handle"
      tabIndex={0}
      title="위·아래 화살표로 조절"
      onKeyDown={(event) => {
        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
        event.preventDefault();
        resizeTimeline(event.key === "ArrowUp" ? 1 : -1);
      }}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        const startY = event.clientY;
        const startRem = ui.timelineRem ?? 20;
        const move = (moveEvent: PointerEvent) => {
          // 위로 끌면 타임라인이 커진다. 1rem = 16px. 한계는 setTimelineRem이 잡는다.
          setTimelineRem(startRem + (startY - moveEvent.clientY) / 16);
        };
        const stop = () => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", stop);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", stop);
      }}
    />
    <TimelineDock
      clipPictures={clipPictures}
      isSaving={isSavingTimeline}
      mutationMessage={timelineMutationMessage}
      // 끌어다 놓기는 **이미 있는 `적용` 경로**를 그대로 탄다. 같은 편집이 두 경로를
      // 갖지 않게 -- 하나만 고치면 다른 하나가 조용히 옛 동작으로 남는다.
      onDropAsset={onApplyAssetCard ? ({ cardId, segmentId }) => {
        const card = assetCards.find((item) => item.id === cardId);
        if (card) void onApplyAssetCard(card, segmentId);
      } : undefined}
      onReorderNarration={onReorderNarration}
      onUpdatePlacements={onUpdatePlacements}
      onTrimNarration={onTrimNarration}
      onPlaybackSeek={seekPlayback}
      onSelectSegment={selectSegment}
      playbackSec={playbackSec}
      selectionResetKey={requestedSegmentFocusEpoch}
      selectedSegmentId={selectedSegmentId}
      view={view}
      viewportWidthPx={Math.max(1, Math.round(availableWorkbenchWidth))}
    />
  </section>;
}

function auditionRoleLabel(role: EditorViewModel["tracks"][number]["role"]): string {
  const labels: Record<string, string> = {
    narration: "내레이션",
    broll: "B-roll",
    bgm: "배경 음악",
    sfx: "효과음",
    overlay: "화면 표시",
  };
  return labels[role] ?? "미디어";
}

function auditionMediaKind(role: EditorViewModel["tracks"][number]["role"], overlayType: EditorViewModel["tracks"][number]["clips"][number]["overlayType"]): AuditionSource["mediaKind"] | null {
  if (role === "narration" || role === "bgm" || role === "sfx") return "audio";
  if (role === "broll") return "video";
  return overlayType === "image_overlay" ? null : "video";
}
