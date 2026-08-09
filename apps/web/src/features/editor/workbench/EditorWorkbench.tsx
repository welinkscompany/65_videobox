import { type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";

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
import type { RightDockCandidate, RightDockDirector } from "./rightDockTypes";

const storageKey = "videobox.editor-workbench.ui";
const defaultUi: EditorWorkbenchPersistedState = { leftOpen: true, rightOpen: true, activeDrawer: null, leftSize: 280, rightSize: 320 };
function readUi(): EditorWorkbenchPersistedState { try { const stored = JSON.parse(window.localStorage.getItem(storageKey) ?? "null"); return typeof stored === "object" && stored ? { ...defaultUi, ...stored } : defaultUi; } catch { return defaultUi; } }
export function persistedPanelPixels(size: PanelSize, minPx: number, fallback: number) {
  const pixels = Number(size.inPixels);
  return Number.isFinite(pixels) ? Math.max(minPx, Math.round(pixels)) : fallback;
}

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
}: EditorWorkbenchProps) {
  const viewRouteKey = `${view.projectId}:${view.sessionId}`;
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const [availableWorkbenchWidth, setAvailableWorkbenchWidth] = useState(() => window.innerWidth);
  const [ui, setUi] = useState<EditorWorkbenchPersistedState>(readUi);
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
  // Undo from the keyboard. Ctrl/Cmd+Z is what hands already do; Alt+Z is
  // accepted too because that is what the owner reaches for. Never while a
  // text field has focus -- undoing the whole edit mid-sentence would throw
  // away the typing and a real edit at once, and the browser's own text undo
  // is the right thing there.
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "z" && event.key !== "Z") return;
      const target = event.target as HTMLElement | null;
      if (target?.isContentEditable) return;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const redo = (event.ctrlKey || event.metaKey) && event.shiftKey;
      const undo = !event.shiftKey && (event.ctrlKey || event.metaKey || event.altKey);
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
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({
        leftOpen: ui.leftOpen,
        rightOpen: ui.rightOpen,
        activeDrawer: ui.activeDrawer,
        leftSize: ui.leftSize,
        rightSize: ui.rightSize,
      }));
    } catch {
      // Panel persistence is best effort; storage denial must not block editing.
    }
  }, [ui]);
  useEffect(() => { if (ui.activeDrawer) drawerRef.current?.focus(); }, [ui.activeDrawer]);
  useEffect(() => {
    if (viewRouteKeyRef.current !== viewRouteKey) {
      viewRouteKeyRef.current = viewRouteKey;
      activeRequestedSegmentKey.current = null;
      setSelectedSegmentId(view.local.selectedSegmentId);
      setPlaybackSec(clampPlaybackSeconds(view.local.seekSec, view.output.durationSec));
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
  const openDrawer = (side: "left" | "right") => setUi((current) => ({ ...current, activeDrawer: side }));
  const closeDrawer = () => setUi((current) => ({ ...current, activeDrawer: null }));
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
  const openManualEditing = () => setUi((current) => layout.mode === "drawer" ? { ...current, activeDrawer: "left" } : { ...current, leftOpen: true });
  const rightDirector = director ? { ...director, onManualEdit: () => { director.onManualEdit(); openManualEditing(); }, onPreviewCandidate: previewDirectorCandidate } : undefined;
  const dock = (side: "left" | "right") => <aside aria-label={side === "left" ? "자산과 대본" : "유진과 편집 항목"} className={`vb-editor-workbench__dock vb-editor-workbench__dock--${side}`}><EditorWorkbenchReadOnlyAdapters assetCards={assetCards} assetPreviewStates={assetPreviewStates} assetTarget={assetTarget} director={rightDirector} dock={side} eugeneDraft={rightDirector?.draft ?? ""} isSavingCaption={isSavingTimeline} loadApprovedTtsCandidates={loadApprovedTtsCandidates} onApplyAssetCard={onApplyAssetCard} onEugeneDraftChange={rightDirector?.onDraftChange ?? (() => undefined)} onInspectorAction={onInspectorAction} onPreviewAsset={previewAssetCard} onRefreshExactPreview={onPreviewRefresh} onSaveCaption={onUpdateCaption} onSeek={seekPlayback} onSelectSegment={selectSegment} partialRegeneration={partialRegeneration} playbackSec={playbackSec} selectedSegmentId={selectedSegmentId} session={session} ttsCandidateScopeKey={ttsCandidateScopeKey} view={view} /></aside>;
  const resize = (side: "left" | "right", delta: number) => setUi((current) => { const key = side === "left" ? "leftSize" : "rightSize"; const value = Math.max(side === "left" ? 220 : 260, current[key] + delta); (side === "left" ? leftPanelRef : rightPanelRef).current?.resize(`${value}px`); return { ...current, [key]: value }; });
  const handleKey = (event: KeyboardEvent<HTMLDivElement>, side: "left" | "right") => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); resize(side, event.key === "ArrowRight" ? 20 : -20); } };
  const trapDrawerFocus = (event: KeyboardEvent<HTMLDivElement>) => { if (event.key === "Escape") { closeAndRestore(); return; } if (event.key !== "Tab") return; const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex="0"]')); if (!focusable.length) { event.preventDefault(); return; } const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } };
  const drawer = layout.activeDrawer && <div ref={drawerRef} role="dialog" aria-modal="true" aria-label={layout.activeDrawer === "left" ? "자산과 대본" : "유진과 편집 항목"} className="vb-editor-workbench__drawer" onKeyDown={trapDrawerFocus} tabIndex={-1}>{dock(layout.activeDrawer)}<Button type="button" onClick={closeAndRestore}>닫기</Button></div>;
  const leftVisible = layout.mode === "desktop-both" || (layout.mode === "desktop-single" && layout.leftOpen);
  const rightVisible = layout.mode === "desktop-both" || (layout.mode === "desktop-single" && layout.rightOpen);
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
  const stage = <PreviewStage key={`${view.projectId}:${view.sessionId}`} auditionRequest={auditionRequest} expectedRevision={view.expectedRevision} exactPreview={view.playback.exactPreview} captions={view.captions} onPlaybackTimeChange={seekPlayback} playbackSec={playbackSec} sources={sources} onRefresh={onPreviewRefresh} />;
  return <section className="vb-editor-workbench" aria-label="편집 작업판" data-project-id={view.projectId} data-session-id={view.sessionId} data-editor-revision={view.expectedRevision} data-editor-density={layout.mode} data-available-workbench-width={Math.round(availableWorkbenchWidth)}>
    <header className="vb-editor-workbench__toolbar"><strong>편집 작업판</strong><span>현재 편집본</span><div><Button type="button" title="Alt+Z 또는 Ctrl+Z" disabled={isSavingTimeline || !onUndo || !session?.undoCount} onClick={() => void onUndo?.()}>실행 취소</Button><Button type="button" title="Ctrl+Shift+Z" disabled={isSavingTimeline || !onRedo || !session?.redoCount} onClick={() => void onRedo?.()}>다시 실행</Button><Button ref={leftTriggerRef} type="button" onClick={() => layout.mode === "drawer" ? openDrawer("left") : setUi((current) => ({ ...current, leftOpen: !current.leftOpen }))}>자산과 대본</Button><Button ref={rightTriggerRef} type="button" onClick={() => layout.mode === "drawer" ? openDrawer("right") : setUi((current) => ({ ...current, rightOpen: !current.rightOpen }))}>유진과 편집 항목</Button></div></header>
    <div ref={bodyRef} className="vb-editor-workbench__body">
      {layout.mode !== "drawer" ? <ResizablePanelGroup orientation="horizontal" className="vb-editor-workbench__panels">
        {leftVisible && <><ResizablePanel panelRef={leftPanelRef} defaultSize={`${ui.leftSize}px`} minSize="220px" onResize={(size) => setUi((current) => ({ ...current, leftSize: persistedPanelPixels(size, 220, current.leftSize) }))}>{dock("left")}</ResizablePanel><ResizableHandle aria-label="왼쪽 패널 크기 조절" onKeyDown={(event) => handleKey(event, "left")} /></>}
        <ResizablePanel minSize={layout.previewMinPx} className="vb-editor-workbench__stage-panel"><div className="vb-editor-workbench__preview" data-preview-min-width={layout.previewMinPx}>{stage}</div></ResizablePanel>
        {rightVisible && <><ResizableHandle aria-label="오른쪽 패널 크기 조절" onKeyDown={(event) => handleKey(event, "right")} /><ResizablePanel panelRef={rightPanelRef} defaultSize={`${ui.rightSize}px`} minSize="260px" onResize={(size) => setUi((current) => ({ ...current, rightSize: persistedPanelPixels(size, 260, current.rightSize) }))}>{dock("right")}</ResizablePanel></>}
      </ResizablePanelGroup> : <><div className="vb-editor-workbench__preview" data-preview-min-width="0">{stage}</div>{drawer}</>}
    </div>
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
