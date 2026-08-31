import type { EditorViewModel } from "../editorViewModel";
import type { EditorSessionSnapshot } from "../editorSnapshot";
import { Button } from "../../../components/ui/button";
import { EditorAssetBrowser, type EditorAssetPreviewState, type LeftPane } from "../assets/EditorAssetBrowser";
import type { EditorAssetCard } from "../assets/editorAssetProjection";
import type { AuditionSource } from "../preview/preview-stage";
import { isAllowedLocalUrl } from "../../../lib/network-guard";
import { TranscriptPanel } from "../transcript/TranscriptPanel";
import { projectTranscriptEntries } from "../transcript/transcriptProjection";
import type { ApprovedTtsCandidate, InspectorAction, PartialRegenerationControls } from "../inspector/InspectorControls";
import { projectInspectorTargets } from "../inspector/inspectorRegistry";
import { RightDock } from "./RightDock";
import type { RightDockDirector } from "./rightDockTypes";


// `role`은 `narration | broll | bgm | sfx | overlay` 원값이다. 타임라인이 쓰는
// 어휘와 같아야 owner가 같은 것을 두 이름으로 보지 않는다.
const trackRoleLabels: Readonly<Record<string, string>> = {
  narration: "내레이션",
  broll: "영상",
  bgm: "배경 음악",
  sfx: "효과음",
  overlay: "오버레이",
  caption: "자막",
};

function trackRoleLabel(role: string): string {
  return trackRoleLabels[role] ?? "트랙";
}

export function EditorWorkbenchReadOnlyAdapters({ view, session, dock, director, selectedSegmentId, playbackSec, onSelectSegment, onSeek, onSaveCaption, isSavingCaption = false, assetCards = [], assetPreviewStates = {}, assetTarget, onPreviewAsset, onPreviewSource, sources = [], onRefreshExactPreview, onApplyAssetCard, onApplyImageOverlay, onInspectorAction, onSetSegmentRippleSpeed, onPreviewSelectedRange, partialRegeneration, loadApprovedTtsCandidates, ttsCandidateScopeKey, onMediaAdded, leftPane, onLeftPaneChange }: { view: EditorViewModel; session?: EditorSessionSnapshot | null; dock: "left" | "right"; director?: RightDockDirector; selectedSegmentId: string | null; playbackSec: number; onSelectSegment: (segmentId: string) => void; onSeek: (seconds: number) => void; onSaveCaption?: (input: { segmentId: string; text: string }) => void | Promise<void>; isSavingCaption?: boolean; assetCards?: readonly EditorAssetCard[]; assetPreviewStates?: Readonly<Record<string, EditorAssetPreviewState>>; assetTarget: Readonly<{ segmentId: string; startSec: number; endSec: number }> | null; onPreviewAsset: (card: EditorAssetCard) => void; onPreviewSource?: (source: AuditionSource) => void; sources?: readonly AuditionSource[]; onRefreshExactPreview?: () => void; onApplyAssetCard?: (card: EditorAssetCard, segmentId: string) => void | Promise<void>; onApplyImageOverlay?: (card: EditorAssetCard, segmentId: string) => void | Promise<void>; onInspectorAction?: (action: InspectorAction) => void | Promise<void>; onSetSegmentRippleSpeed?: (input: { segmentId: string; rate: 1 | 1.5 | 2 }) => void | Promise<void>; onPreviewSelectedRange?: (input: { segmentId: string; startSec: number; endSec: number }) => void | Promise<void>; partialRegeneration?: PartialRegenerationControls; loadApprovedTtsCandidates?: (segmentId: string) => Promise<readonly ApprovedTtsCandidate[]>; ttsCandidateScopeKey?: string; onMediaAdded?: () => void | Promise<void>; /** 최상위(편집기 맨 위)에서 관리하는 왼쪽 탭 -- 승인 2026-08-30(버튼 단위 벤치마킹 2단계). */ leftPane?: LeftPane; onLeftPaneChange?: (pane: LeftPane) => void }) {
  if (dock === "left") {
    const localSources = sources.filter((source) => isAllowedLocalUrl(source.url));
    // 캡컷은 전환을 왼쪽 패널 탭에서 고른다. 걸 대상은 오른쪽 속성 패널이 쓰는
    // 것과 **같은 계산**이다 -- 고른 장면과, 그 앞에 장면이 있는지.
    const leftSelectedIndex = selectedSegmentId === null
      ? -1
      : session?.segments.findIndex((segment) => segment.segmentId === selectedSegmentId) ?? -1;
    const transitionTarget = selectedSegmentId === null || leftSelectedIndex < 0
      ? null
      : { segmentId: selectedSegmentId, hasPrevious: leftSelectedIndex > 0 };
    // **한 번에 하나만 보여 준다(owner 지시 2026-08-27).**
    // 실측: 이 도크는 보이는 높이 137px인데 내용이 1,608px이었다 -- 11.7배 스크롤.
    // 미디어 아래에 `영상 구성 · 소스 확인 · 대본 · 자막`이 세로로 더 쌓여 있었다.
    //
    // `영상 구성`은 **없앴다.** 타임라인 머리말이 이미 같은 말을 한다
    // (`n개 트랙 · n개 자막 · n개 미디어 공백`)는 데다, 클립은 타임라인이 직접 보여 준다.
    // 나머지 둘은 탭 안으로 들어간다 -- 자막은 캡컷 `텍스트` 자리, 소스 확인은 미디어 안.
    return <EditorAssetBrowser
      cards={assetCards} target={assetTarget} isSaving={isSavingCaption}
      onPreview={onPreviewAsset} onApply={(card, segmentId) => void onApplyAssetCard?.(card, segmentId)}
      onApplyOverlay={onApplyImageOverlay ? (card, segmentId) => void onApplyImageOverlay(card, segmentId) : undefined}
      previewStates={assetPreviewStates} onRefreshExactPreview={onRefreshExactPreview}
      projectId={view.projectId} onMediaAdded={onMediaAdded}
      transitionTarget={transitionTarget} onInspectorAction={onInspectorAction}
      pane={leftPane} onPaneChange={onLeftPaneChange} renderPaneTabs={!onLeftPaneChange}
      sourceCheck={localSources.length > 0 ? <section aria-label="소스 확인" className="vb-editor-workbench__sources"><h2>소스 확인</h2><p>편집본에 적용하지 않고 원본만 확인합니다.</p><div>{localSources.map((source) => <Button key={source.id} type="button" variant="outline" onClick={() => onPreviewSource?.(source)} aria-label={`${source.label} 원본 열기`}>{source.label}</Button>)}</div></section> : null}
      transcript={<TranscriptPanel entries={projectTranscriptEntries({ narration: view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips.map((clip) => ({ segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec }))), captions: view.captions })} isSaving={isSavingCaption} onSaveCaption={onSaveCaption} onSeek={onSeek} onSelectSegment={onSelectSegment} playbackSec={playbackSec} selectedSegmentId={selectedSegmentId} />}
    />;
  }
  const narrationClips = view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips);
  const selectedRange = selectedSegmentId === null
    ? null
    : narrationClips.find((clip) => clip.segmentId === selectedSegmentId)
      ?? view.captions.find((caption) => caption.segmentId === selectedSegmentId)
      ?? null;
  const selectedSessionSegmentIndex = selectedSegmentId === null ? -1 : session?.segments.findIndex((segment) => segment.segmentId === selectedSegmentId) ?? -1;
  const selectedSessionSegment = selectedSessionSegmentIndex >= 0 ? session?.segments[selectedSessionSegmentIndex] ?? null : null;
  return <RightDock
    projectId={view.projectId}
    inspectorDisabled={isSavingCaption}
    loadApprovedTtsCandidates={loadApprovedTtsCandidates}
    onInspectorAction={onInspectorAction}
    onSetSegmentRippleSpeed={onSetSegmentRippleSpeed}
    onPreviewSelectedRange={onPreviewSelectedRange}
    partialRegeneration={partialRegeneration}
    selectedSegment={selectedRange ? {
      segmentId: selectedRange.segmentId,
      startSec: selectedRange.startSec,
      endSec: selectedRange.endSec,
      nextSegmentId: selectedSessionSegmentIndex >= 0 ? session?.segments[selectedSessionSegmentIndex + 1]?.segmentId ?? null : null,
      // 전환은 **앞 장면이 있어야** 고를 수 있다. 첫 장면이면 null이다.
      previousSegmentId: selectedSessionSegmentIndex > 0 ? session?.segments[selectedSessionSegmentIndex - 1]?.segmentId ?? null : null,
      cutAction: selectedSessionSegment?.cutAction ?? "keep",
      draftApplied: false,
      transitionIn: selectedSessionSegment?.transitionIn ?? null,
      ripplePlaybackRate: selectedSessionSegment?.ripplePlaybackRate ?? 1,
      ttsReplacement: selectedSessionSegment?.ttsReplacement ?? null,
    } : undefined}
    ttsCandidateScopeKey={ttsCandidateScopeKey}
    inspectorTargets={projectInspectorTargets({ view, selectedSegmentId })}
  />;
}
