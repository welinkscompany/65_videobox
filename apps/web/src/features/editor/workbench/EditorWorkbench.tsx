import { type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "../../../components/ui/resizable";
import type { PanelImperativeHandle } from "react-resizable-panels";
import type { EditorViewModel } from "../editorViewModel";
import { EditorWorkbenchReadOnlyAdapters } from "./editorWorkbenchReadOnlyAdapters";
import { resolveEditorWorkbenchLayout, type EditorWorkbenchPersistedState } from "./editorWorkbenchLayout";

const storageKey = "videobox.editor-workbench.ui";
const defaultUi: EditorWorkbenchPersistedState = { leftOpen: true, rightOpen: true, activeDrawer: null, leftSize: 280, rightSize: 320 };
function readUi(): EditorWorkbenchPersistedState { try { const stored = JSON.parse(window.localStorage.getItem(storageKey) ?? "null"); return typeof stored === "object" && stored ? { ...defaultUi, ...stored } : defaultUi; } catch { return defaultUi; } }

export function EditorWorkbench({ view }: { view: EditorViewModel }) {
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const [availableWorkbenchWidth, setAvailableWorkbenchWidth] = useState(() => window.innerWidth);
  const [ui, setUi] = useState<EditorWorkbenchPersistedState>(readUi);
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
  useEffect(() => { if (ui.activeDrawer) drawerRef.current?.focus(); }, [ui.activeDrawer]);
  useEffect(() => { const side = restoreFocusRef.current; if (!ui.activeDrawer && side) { restoreFocusRef.current = null; window.setTimeout(() => (side === "left" ? leftTriggerRef : rightTriggerRef).current?.focus(), 0); } }, [ui.activeDrawer]);
  const layout = resolveEditorWorkbenchLayout({ viewportWidth, availableWorkbenchWidth, persisted: ui });
  const openDrawer = (side: "left" | "right") => setUi((current) => ({ ...current, activeDrawer: side }));
  const closeDrawer = () => setUi((current) => ({ ...current, activeDrawer: null }));
  const closeAndRestore = () => { restoreFocusRef.current = ui.activeDrawer; closeDrawer(); };
  const dock = (side: "left" | "right") => <aside aria-label={side === "left" ? "자산과 대본" : "유진과 Inspector"} className={`vb-editor-workbench__dock vb-editor-workbench__dock--${side}`}><EditorWorkbenchReadOnlyAdapters view={view} dock={side} /></aside>;
  const resize = (side: "left" | "right", delta: number) => setUi((current) => { const key = side === "left" ? "leftSize" : "rightSize"; const value = Math.max(side === "left" ? 220 : 260, current[key] + delta); (side === "left" ? leftPanelRef : rightPanelRef).current?.resize(`${value}px`); return { ...current, [key]: value }; });
  const handleKey = (event: KeyboardEvent<HTMLDivElement>, side: "left" | "right") => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); resize(side, event.key === "ArrowRight" ? 20 : -20); } };
  const trapDrawerFocus = (event: KeyboardEvent<HTMLDivElement>) => { if (event.key === "Escape") { closeAndRestore(); return; } if (event.key !== "Tab") return; const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex="0"]')); if (!focusable.length) { event.preventDefault(); return; } const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } };
  const drawer = layout.activeDrawer && <div ref={drawerRef} role="dialog" aria-modal="true" aria-label={layout.activeDrawer === "left" ? "자산과 대본" : "유진과 Inspector"} className="vb-editor-workbench__drawer" onKeyDown={trapDrawerFocus} tabIndex={-1}>{dock(layout.activeDrawer)}<button type="button" onClick={closeAndRestore}>닫기</button></div>;
  const leftVisible = layout.mode === "desktop-both" || (layout.mode === "desktop-single" && layout.leftOpen);
  const rightVisible = layout.mode === "desktop-both" || (layout.mode === "desktop-single" && layout.rightOpen);
  return <section className="vb-editor-workbench" aria-label="편집 작업판" data-project-id={view.projectId} data-session-id={view.sessionId} data-editor-density={layout.mode} data-available-workbench-width={Math.round(availableWorkbenchWidth)}>
    <header className="vb-editor-workbench__toolbar"><strong>읽기 전용 편집 작업판</strong><span>{view.timelineId} · revision {view.expectedRevision}</span><div><button ref={leftTriggerRef} type="button" onClick={() => layout.mode === "drawer" ? openDrawer("left") : setUi((current) => ({ ...current, leftOpen: !current.leftOpen }))}>자산과 대본</button><button ref={rightTriggerRef} type="button" onClick={() => layout.mode === "drawer" ? openDrawer("right") : setUi((current) => ({ ...current, rightOpen: !current.rightOpen }))}>유진과 Inspector</button></div></header>
    <div ref={bodyRef} className="vb-editor-workbench__body">
      {layout.mode !== "drawer" ? <ResizablePanelGroup orientation="horizontal" className="vb-editor-workbench__panels">
        {leftVisible && <><ResizablePanel panelRef={leftPanelRef} defaultSize={`${ui.leftSize}px`} minSize="220px" onResize={(size) => setUi((current) => ({ ...current, leftSize: Math.round(Number.parseFloat(String(size))) || current.leftSize }))}>{dock("left")}</ResizablePanel><ResizableHandle aria-label="왼쪽 패널 크기 조절" onKeyDown={(event) => handleKey(event, "left")} /></>}
        <ResizablePanel minSize={layout.previewMinPx} className="vb-editor-workbench__stage-panel"><section aria-label="미리보기 자리" className="vb-editor-workbench__preview" data-preview-min-width={layout.previewMinPx}><p>미리보기 자리</p><span>{view.output.width} × {view.output.height} · {view.output.durationSec.toFixed(1)}초</span><small>정확한 미리보기와 재생은 다음 단계에서 준비합니다.</small></section></ResizablePanel>
        {rightVisible && <><ResizableHandle aria-label="오른쪽 패널 크기 조절" onKeyDown={(event) => handleKey(event, "right")} /><ResizablePanel panelRef={rightPanelRef} defaultSize={`${ui.rightSize}px`} minSize="260px" onResize={(size) => setUi((current) => ({ ...current, rightSize: Math.round(Number.parseFloat(String(size))) || current.rightSize }))}>{dock("right")}</ResizablePanel></>}
      </ResizablePanelGroup> : <><section aria-label="미리보기 자리" className="vb-editor-workbench__preview" data-preview-min-width="0"><p>미리보기 자리</p><span>{view.output.width} × {view.output.height}</span></section>{drawer}</>}
    </div>
    <section aria-label="타임라인" className="vb-editor-workbench__timeline"><h2>타임라인</h2><p>{view.tracks.length}개 트랙 · {view.captions.length}개 자막 · {view.gaps.length}개 자산 공백 · {view.source.status}</p></section>
  </section>;
}
