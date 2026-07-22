import { type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "../../../components/ui/resizable";
import type { PanelImperativeHandle, PanelSize } from "react-resizable-panels";
import type { EditorViewModel } from "../editorViewModel";
import { PreviewStage, type AuditionSource } from "../preview/preview-stage";
import { TimelineDock } from "../timeline/TimelineDock";
import { activeSegmentIdAt, clampPlaybackSeconds } from "../transcript/playbackNavigation";
import { EditorWorkbenchReadOnlyAdapters } from "./editorWorkbenchReadOnlyAdapters";
import { resolveEditorWorkbenchLayout, type EditorWorkbenchPersistedState } from "./editorWorkbenchLayout";

const storageKey = "videobox.editor-workbench.ui";
const eugeneDraftStorageKey = "videobox.editor-workbench.eugene-draft";
const defaultUi: EditorWorkbenchPersistedState = { leftOpen: true, rightOpen: true, activeDrawer: null, leftSize: 280, rightSize: 320 };
function readUi(): EditorWorkbenchPersistedState { try { const stored = JSON.parse(window.localStorage.getItem(storageKey) ?? "null"); return typeof stored === "object" && stored ? { ...defaultUi, ...stored } : defaultUi; } catch { return defaultUi; } }
function readEugeneDraft() { try { return window.localStorage.getItem(eugeneDraftStorageKey) ?? ""; } catch { return ""; } }
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
  onPreviewRefresh?: () => void | Promise<void>;
  onTrimNarration?: (input: NarrationTrim) => void | Promise<void>;
  onReorderNarration?: (input: NarrationReorder) => void | Promise<void>;
  onUpdatePlacements?: (input: TimelinePlacements) => void | Promise<void>;
  onUpdateCaption?: (input: CaptionText) => void | Promise<void>;
  isSavingTimeline?: boolean;
  timelineMutationMessage?: string;
}>;

export function EditorWorkbench({
  view,
  onPreviewRefresh,
  onTrimNarration,
  onReorderNarration,
  onUpdatePlacements,
  onUpdateCaption,
  isSavingTimeline = false,
  timelineMutationMessage,
}: EditorWorkbenchProps) {
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const [availableWorkbenchWidth, setAvailableWorkbenchWidth] = useState(() => window.innerWidth);
  const [ui, setUi] = useState<EditorWorkbenchPersistedState>(readUi);
  const [eugeneDraft, setEugeneDraft] = useState(readEugeneDraft);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(view.local.selectedSegmentId);
  const [playbackSec, setPlaybackSec] = useState(view.local.seekSec);
  const bodyRef = useRef<HTMLDivElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<"left" | "right" | null>(null);
  const leftPanelRef = useRef<PanelImperativeHandle>(null);
  const rightPanelRef = useRef<PanelImperativeHandle>(null);
  const leftTriggerRef = useRef<HTMLButtonElement>(null);
  const rightTriggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { const update = () => setViewportWidth(window.innerWidth); window.addEventListener("resize", update); return () => window.removeEventListener("resize", update); }, []);
  useLayoutEffect(() => {
    const measure = () => setAvailableWorkbenchWidth(bodyRef.current?.getBoundingClientRect().width || window.innerWidth);
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    if (bodyRef.current) observer?.observe(bodyRef.current);
    window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, []);
  useEffect(() => { window.localStorage.setItem(storageKey, JSON.stringify({ leftOpen: ui.leftOpen, rightOpen: ui.rightOpen, activeDrawer: ui.activeDrawer, leftSize: ui.leftSize, rightSize: ui.rightSize })); }, [ui]);
  useEffect(() => { window.localStorage.setItem(eugeneDraftStorageKey, eugeneDraft); }, [eugeneDraft]);
  useEffect(() => { if (ui.activeDrawer) drawerRef.current?.focus(); }, [ui.activeDrawer]);
  useEffect(() => {
    const segmentIds = new Set(view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips.map((clip) => clip.segmentId)));
    setSelectedSegmentId((current) => current && segmentIds.has(current) ? current : segmentIds.has(view.local.selectedSegmentId ?? "") ? view.local.selectedSegmentId : null);
    setPlaybackSec((current) => clampPlaybackSeconds(current, view.output.durationSec));
  }, [view.expectedRevision, view.local.selectedSegmentId, view.output.durationSec, view.projectId, view.sessionId, view.tracks]);
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
      view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips.map((clip) => ({ segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec }))),
      nextSeconds,
    );
    setSelectedSegmentId(activeSegmentId);
  };
  const dock = (side: "left" | "right") => <aside aria-label={side === "left" ? "자산과 대본" : "유진과 Inspector"} className={`vb-editor-workbench__dock vb-editor-workbench__dock--${side}`}><EditorWorkbenchReadOnlyAdapters view={view} dock={side} eugeneDraft={eugeneDraft} isSavingCaption={isSavingTimeline} onEugeneDraftChange={setEugeneDraft} onSaveCaption={onUpdateCaption} onSeek={seekPlayback} onSelectSegment={selectSegment} playbackSec={playbackSec} selectedSegmentId={selectedSegmentId} /></aside>;
  const resize = (side: "left" | "right", delta: number) => setUi((current) => { const key = side === "left" ? "leftSize" : "rightSize"; const value = Math.max(side === "left" ? 220 : 260, current[key] + delta); (side === "left" ? leftPanelRef : rightPanelRef).current?.resize(`${value}px`); return { ...current, [key]: value }; });
  const handleKey = (event: KeyboardEvent<HTMLDivElement>, side: "left" | "right") => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); resize(side, event.key === "ArrowRight" ? 20 : -20); } };
  const trapDrawerFocus = (event: KeyboardEvent<HTMLDivElement>) => { if (event.key === "Escape") { closeAndRestore(); return; } if (event.key !== "Tab") return; const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex="0"]')); if (!focusable.length) { event.preventDefault(); return; } const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } };
  const drawer = layout.activeDrawer && <div ref={drawerRef} role="dialog" aria-modal="true" aria-label={layout.activeDrawer === "left" ? "자산과 대본" : "유진과 Inspector"} className="vb-editor-workbench__drawer" onKeyDown={trapDrawerFocus} tabIndex={-1}>{dock(layout.activeDrawer)}<button type="button" onClick={closeAndRestore}>닫기</button></div>;
  const leftVisible = layout.mode === "desktop-both" || (layout.mode === "desktop-single" && layout.leftOpen);
  const rightVisible = layout.mode === "desktop-both" || (layout.mode === "desktop-single" && layout.rightOpen);
  const sources: AuditionSource[] = view.tracks.flatMap((track) => track.clips.flatMap((clip) => {
    if (!clip.assetId) return [];
    const url = view.playback.auditionUrls[clip.assetId];
    if (!url) return [];
    const mediaKind = auditionMediaKind(track.role, clip.overlayType);
    return mediaKind ? [{ id: clip.clipId, label: `${track.role === "broll" ? "B-roll" : track.role.toUpperCase()} · ${clip.segmentId}`, url, mediaKind, timelineRange: { startSec: clip.startSec, endSec: clip.endSec } }] : [];
  }));
  const stage = <PreviewStage expectedRevision={view.expectedRevision} exactPreview={view.playback.exactPreview} captions={view.captions} onPlaybackTimeChange={seekPlayback} playbackSec={playbackSec} sources={sources} onRefresh={onPreviewRefresh} />;
  return <section className="vb-editor-workbench" aria-label="편집 작업판" data-project-id={view.projectId} data-session-id={view.sessionId} data-editor-density={layout.mode} data-available-workbench-width={Math.round(availableWorkbenchWidth)}>
    <header className="vb-editor-workbench__toolbar"><strong>편집 작업판</strong><span>{view.timelineId} · revision {view.expectedRevision}</span><div><button ref={leftTriggerRef} type="button" onClick={() => layout.mode === "drawer" ? openDrawer("left") : setUi((current) => ({ ...current, leftOpen: !current.leftOpen }))}>자산과 대본</button><button ref={rightTriggerRef} type="button" onClick={() => layout.mode === "drawer" ? openDrawer("right") : setUi((current) => ({ ...current, rightOpen: !current.rightOpen }))}>유진과 Inspector</button></div></header>
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
      selectedSegmentId={selectedSegmentId}
      view={view}
      viewportWidthPx={Math.max(1, Math.round(availableWorkbenchWidth))}
    />
  </section>;
}

function auditionMediaKind(role: EditorViewModel["tracks"][number]["role"], overlayType: EditorViewModel["tracks"][number]["clips"][number]["overlayType"]): AuditionSource["mediaKind"] | null {
  if (role === "narration" || role === "bgm" || role === "sfx") return "audio";
  if (role === "broll") return "video";
  return overlayType === "image_overlay" ? null : "video";
}
