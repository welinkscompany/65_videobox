import { type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";

import type { OutputVariant, OutputVariantPatch } from "../../../api";
import { Button } from "../../../components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "../../../components/ui/resizable";
import type { PanelImperativeHandle, PanelSize } from "react-resizable-panels";
import type { EditorViewModel } from "../editorViewModel";
import type { EditorSessionSnapshot } from "../editorSnapshot";
import type { EditorAssetCard } from "../assets/editorAssetProjection";
import type { EditorAssetPreviewState } from "../assets/EditorAssetBrowser";
import type { ApprovedTtsCandidate, InspectorAction, PartialRegenerationControls } from "../inspector/InspectorControls";
import { PreviewStage, type AuditionRequest, type AuditionSource } from "../preview/preview-stage";
import { TimelineDock } from "../timeline/TimelineDock";
import { activeSegmentIdAt, clampPlaybackSeconds } from "../transcript/playbackNavigation";
import { EditorWorkbenchReadOnlyAdapters } from "./editorWorkbenchReadOnlyAdapters";
import { resolveEditorWorkbenchLayout, type EditorWorkbenchPersistedState } from "./editorWorkbenchLayout";
import { hasLegacyEditorUiState, readEditorUiState, readVariantsCollapsed, writeEditorUiState, writeVariantsCollapsed } from "./editorUiState";
import type { RightDockCandidate, RightDockDirector } from "./rightDockTypes";
import { VariantCompare } from "../variants/VariantCompare";
import { VariantConflictPanel } from "../variants/VariantConflictPanel";
import { VariantSelector } from "../variants/VariantSelector";
import { projectServerVariant, projectVariant, type VariantKind } from "../variants/variantProjection";
import { VariantServerControls } from "../variants/VariantServerControls";

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
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      const key = event.key.toLowerCase();
      if (key !== "z" && key !== "y") return;
      const target = event.target as HTMLElement | null;
      if (target?.isContentEditable) return;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
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
  }, [isSavingTimeline, onUndo, onRedo, session?.undoCount, session?.redoCount]);
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
  const openDrawer = (side: "left" | "right") => { lastActiveDrawer = side; writeActiveDrawer(side); setUi((current) => ({ ...current, activeDrawer: side })); };
  const closeDrawer = () => { lastActiveDrawer = null; writeActiveDrawer(null); setUi((current) => ({ ...current, activeDrawer: null })); };
  const closeAndRestore = () => { restoreFocusRef.current = ui.activeDrawer; closeDrawer(); };
  const selectSegment = (segmentId: string) => setSelectedSegmentId(segmentId);
  const seekPlayback = (seconds: number) => {
    const nextSeconds = clampPlaybackSeconds(seconds, view.output.durationSec);
    setPlaybackSec(nextSeconds);
    const activeSegmentId = activeSegmentIdAt(
      view.captions.length
        ? view.captions
        : view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips.map((clip) => ({ segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec }))),
      nextSeconds,
    );
    setSelectedSegmentId(activeSegmentId);
  };
  const selectedNarration = selectedSegmentId === null ? null : view.tracks
    .filter((track) => track.role === "narration")
    .flatMap((track) => track.clips)
    .find((clip) => clip.segmentId === selectedSegmentId)
    ?? view.captions.find((caption) => caption.segmentId === selectedSegmentId)
    ?? null;
  const assetTarget = selectedNarration === null ? null : { segmentId: selectedNarration.segmentId, startSec: selectedNarration.startSec, endSec: selectedNarration.endSec };
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
  const sceneNumbers = new Map<string, number>();
  view.tracks
    .flatMap((track) => track.clips)
    .slice()
    .sort((left, right) => left.startSec - right.startSec)
    .forEach((clip) => {
      if (clip.segmentId && !sceneNumbers.has(clip.segmentId)) sceneNumbers.set(clip.segmentId, sceneNumbers.size + 1);
    });
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
  const dock = (side: "left" | "right") => <aside aria-label={side === "left" ? "자산과 대본" : "유진과 편집 항목"} className={`vb-editor-workbench__dock vb-editor-workbench__dock--${side}`}><EditorWorkbenchReadOnlyAdapters assetCards={assetCards} assetPreviewStates={assetPreviewStates} assetTarget={assetTarget} director={rightDirector} dock={side} eugeneDraft={rightDirector?.draft ?? ""} isSavingCaption={isSavingTimeline} loadApprovedTtsCandidates={loadApprovedTtsCandidates} onApplyAssetCard={onApplyAssetCard} onEugeneDraftChange={rightDirector?.onDraftChange ?? (() => undefined)} onInspectorAction={onInspectorAction} onPreviewAsset={previewAssetCard} onPreviewSource={previewTimelineSource} onRefreshExactPreview={onPreviewRefresh} onSaveCaption={onUpdateCaption} onSeek={seekPlayback} onSelectSegment={selectSegment} partialRegeneration={partialRegeneration} playbackSec={playbackSec} selectedSegmentId={selectedSegmentId} session={session} sources={sources} ttsCandidateScopeKey={ttsCandidateScopeKey} view={view} /></aside>;
  const resize = (side: "left" | "right", delta: number) => setUi((current) => { const key = side === "left" ? "leftSize" : "rightSize"; const value = Math.max(side === "left" ? 220 : 260, current[key] + delta); (side === "left" ? leftPanelRef : rightPanelRef).current?.resize(`${value}px`); return { ...current, [key]: value }; });
  const handleKey = (event: KeyboardEvent<HTMLDivElement>, side: "left" | "right") => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); resize(side, event.key === "ArrowRight" ? 20 : -20); } };
  const trapDrawerFocus = (event: KeyboardEvent<HTMLDivElement>) => { if (event.key === "Escape") { closeAndRestore(); return; } if (event.key !== "Tab") return; const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex="0"]')); if (!focusable.length) { event.preventDefault(); return; } const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } };
  const drawer = layout.activeDrawer && <div ref={drawerRef} role="dialog" aria-modal="true" aria-label={layout.activeDrawer === "left" ? "자산과 대본" : "유진과 편집 항목"} className="vb-editor-workbench__drawer" onKeyDown={trapDrawerFocus} tabIndex={-1}>{dock(layout.activeDrawer)}<Button type="button" onClick={closeAndRestore}>닫기</Button></div>;
  const leftVisible = layout.mode === "desktop-both" || (layout.mode === "desktop-single" && layout.leftOpen);
  const rightVisible = layout.mode === "desktop-both" || (layout.mode === "desktop-single" && layout.rightOpen);
  const stage = <PreviewStage key={`${view.projectId}:${view.sessionId}`} auditionRequest={auditionRequest} expectedRevision={view.expectedRevision} exactPreview={view.playback.exactPreview} captions={view.captions} onPlaybackTimeChange={seekPlayback} playbackSec={playbackSec} sources={sources} onRefresh={onPreviewRefresh} />;
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
  return <section className="vb-editor-workbench" aria-label="편집 작업판" data-editor-viewport="bounded" data-project-id={view.projectId} data-session-id={view.sessionId} data-editor-revision={view.expectedRevision} data-editor-density={layout.mode} data-available-workbench-width={Math.round(availableWorkbenchWidth)}>
    <header className="vb-editor-workbench__toolbar"><strong>편집 작업판</strong><span>현재 편집본</span><div><Button type="button" title="Ctrl+Z" disabled={isSavingTimeline || !onUndo || !session?.undoCount} onClick={() => void onUndo?.()}>실행 취소</Button><Button type="button" title="Ctrl+Shift+Z 또는 Ctrl+Y" disabled={isSavingTimeline || !onRedo || !session?.redoCount} onClick={() => void onRedo?.()}>다시 실행</Button><Button ref={leftTriggerRef} type="button" onClick={() => layout.mode === "drawer" ? openDrawer("left") : setUi((current) => ({ ...current, leftOpen: !current.leftOpen }))}>자산과 대본</Button><Button ref={rightTriggerRef} type="button" onClick={() => layout.mode === "drawer" ? openDrawer("right") : setUi((current) => ({ ...current, rightOpen: !current.rightOpen }))}>유진과 편집 항목</Button></div></header>
    <div ref={bodyRef} className="vb-editor-workbench__body" data-scroll-owner="panels">
      {layout.mode !== "drawer" ? <ResizablePanelGroup orientation="horizontal" className="vb-editor-workbench__panels">
        {leftVisible && <><ResizablePanel panelRef={leftPanelRef} defaultSize={`${ui.leftSize}px`} minSize="220px" onResize={(size) => setUi((current) => ({ ...current, leftSize: persistedPanelPixels(size, 220, current.leftSize) }))}>{dock("left")}</ResizablePanel><ResizableHandle aria-label="왼쪽 패널 크기 조절" onKeyDown={(event) => handleKey(event, "left")} /></>}
        <ResizablePanel minSize={layout.previewMinPx} className="vb-editor-workbench__stage-panel"><div className="vb-editor-workbench__preview" data-scroll-owner="preview" data-preview-min-width={layout.previewMinPx}>{stage}</div></ResizablePanel>
        {rightVisible && <><ResizableHandle aria-label="오른쪽 패널 크기 조절" onKeyDown={(event) => handleKey(event, "right")} /><ResizablePanel panelRef={rightPanelRef} defaultSize={`${ui.rightSize}px`} minSize="260px" onResize={(size) => setUi((current) => ({ ...current, rightSize: persistedPanelPixels(size, 260, current.rightSize) }))}>{dock("right")}</ResizablePanel></>}
      </ResizablePanelGroup> : <><div className="vb-editor-workbench__preview" data-scroll-owner="preview" data-preview-min-width="0">{stage}</div>{drawer}</>}
    </div>
    <section className="vb-editor-variants" aria-label="출력 변형" data-collapsed={variantsCollapsed}>
      <div className="vb-editor-variants__header"><div><p className="vb-editor-variants__eyebrow">연결된 출력</p><h2>가로·세로 결과를 한 박자에 비교</h2></div><Button type="button" variant="outline" aria-expanded={!variantsCollapsed} onClick={toggleVariantsCollapsed}>{variantsCollapsed ? "출력 변형 펼치기" : "출력 변형 접기"}</Button></div>
      {!variantsCollapsed ? <><span className="vb-editor-variants__hint">마스터 편집은 하나, 출력은 안전하게 분기</span>
      <VariantSelector selected={variantMode} onSelect={setVariantMode} />
      {variantMode === "master" ? <p className="vb-editor-variants__master-note">현재 마스터 편집본을 기준으로 출력 변형을 확인합니다.</p> : <>
        <VariantCompare master={variantMaster} variant={variantPreview} onSeek={seekPlayback} />
        {serverVariant && onVariantMaterialize && onVariantPatch ? <VariantServerControls variant={serverVariant} busy={variantBusy} onMaterialize={onVariantMaterialize} onPatch={onVariantPatch} onCreateHighlight={onVariantCreateHighlight} /> : null}
      </>}
      {showVariantCompare ? <VariantConflictPanel conflicts={variantPreview.conflicts} onKeep={(field) => resolveConflict(field, "keep_local")} onRebase={(field) => resolveConflict(field, "rebase_master")} /> : null}
      {highlightVariant && onVariantMaterialize && onVariantPatch ? <VariantServerControls variant={highlightVariant} masterSegmentIds={masterSegmentIds} busy={variantBusy} onMaterialize={onVariantMaterialize} onPatch={onVariantPatch} /> : null}</> : null}
    </section>
    <TimelineDock
      isSaving={isSavingTimeline}
      mutationMessage={timelineMutationMessage}
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
