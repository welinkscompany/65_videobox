import type { EditorViewModel } from "../editorViewModel";
import type { EditorSessionSnapshot } from "../editorSnapshot";
import { Button } from "../../../components/ui/button";
import { EditorAssetBrowser, type EditorAssetPreviewState } from "../assets/EditorAssetBrowser";
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

export function EditorWorkbenchReadOnlyAdapters({ view, session, dock, director, eugeneDraft, onEugeneDraftChange, selectedSegmentId, playbackSec, onSelectSegment, onSeek, onSaveCaption, isSavingCaption = false, assetCards = [], assetPreviewStates = {}, assetTarget, onPreviewAsset, onPreviewSource, sources = [], onRefreshExactPreview, onApplyAssetCard, onApplyImageOverlay, onInspectorAction, partialRegeneration, loadApprovedTtsCandidates, ttsCandidateScopeKey }: { view: EditorViewModel; session?: EditorSessionSnapshot | null; dock: "left" | "right"; director?: RightDockDirector; eugeneDraft: string; onEugeneDraftChange: (value: string) => void; selectedSegmentId: string | null; playbackSec: number; onSelectSegment: (segmentId: string) => void; onSeek: (seconds: number) => void; onSaveCaption?: (input: { segmentId: string; text: string }) => void | Promise<void>; isSavingCaption?: boolean; assetCards?: readonly EditorAssetCard[]; assetPreviewStates?: Readonly<Record<string, EditorAssetPreviewState>>; assetTarget: Readonly<{ segmentId: string; startSec: number; endSec: number }> | null; onPreviewAsset: (card: EditorAssetCard) => void; onPreviewSource?: (source: AuditionSource) => void; sources?: readonly AuditionSource[]; onRefreshExactPreview?: () => void; onApplyAssetCard?: (card: EditorAssetCard, segmentId: string) => void | Promise<void>; onApplyImageOverlay?: (card: EditorAssetCard, segmentId: string) => void | Promise<void>; onInspectorAction?: (action: InspectorAction) => void | Promise<void>; partialRegeneration?: PartialRegenerationControls; loadApprovedTtsCandidates?: (segmentId: string) => Promise<readonly ApprovedTtsCandidate[]>; ttsCandidateScopeKey?: string }) {
  if (dock === "left") {
    const localSources = sources.filter((source) => isAllowedLocalUrl(source.url));
    return <>
    <EditorAssetBrowser cards={assetCards} target={assetTarget} isSaving={isSavingCaption} onPreview={onPreviewAsset} onApply={(card, segmentId) => void onApplyAssetCard?.(card, segmentId)} onApplyOverlay={onApplyImageOverlay ? (card, segmentId) => void onApplyImageOverlay(card, segmentId) : undefined} previewStates={assetPreviewStates} onRefreshExactPreview={onRefreshExactPreview} projectId={view.projectId} />
    <section aria-label="자산" className="vb-editor-workbench__summary"><h2>자산</h2>{view.tracks.map((track) => <p key={track.trackId}>{trackRoleLabel(track.role)}: {track.clips.length}개 클립</p>)}</section>
    {localSources.length > 0 && <section aria-label="소스 확인" className="vb-editor-workbench__sources"><h2>소스 확인</h2><p>편집본에 적용하지 않고 원본만 확인합니다.</p><div>{localSources.map((source) => <Button key={source.id} type="button" variant="outline" onClick={() => onPreviewSource?.(source)} aria-label={`${source.label} 원본 열기`}>{source.label}</Button>)}</div></section>}
    <TranscriptPanel entries={projectTranscriptEntries({ narration: view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips.map((clip) => ({ segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec }))), captions: view.captions })} isSaving={isSavingCaption} onSaveCaption={onSaveCaption} onSeek={onSeek} onSelectSegment={onSelectSegment} playbackSec={playbackSec} selectedSegmentId={selectedSegmentId} />
  </>;
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
    draft={eugeneDraft}
    composerDisabled={director?.composerDisabled ?? true}
    conversationScroll={director?.conversationScroll}
    messages={director?.messages}
    memory={director?.memory}
    onApplyProposal={director?.onApplyProposal}
    onDraftChange={onEugeneDraftChange}
    onConversationScrollChange={director?.onConversationScrollChange}
    onCancelRun={director?.onCancelRun}
    onManualEdit={director?.onManualEdit}
    onUseDraftAsScript={director?.onUseDraftAsScript}
    onPreviewCandidate={director?.onPreviewCandidate}
    onRefreshProposal={director?.onRefreshProposal}
    onRetryMessage={director?.onRetryMessage}
    onRetryRun={director?.onRetryRun}
    onSelectedCandidateIdsChange={director?.onSelectedCandidateIdsChange}
    onSendMessage={director?.onSendMessage}
    onStart={director?.onStart}
    startFailure={director?.startFailure}
    proposal={director?.proposal}
    retryAfterSeconds={director?.retryAfterSeconds}
    runState={director?.runState}
    selectedCandidateIds={director?.selectedCandidateIds}
    state={director?.state}
    inspectorDisabled={isSavingCaption}
    loadApprovedTtsCandidates={loadApprovedTtsCandidates}
    onInspectorAction={onInspectorAction}
    partialRegeneration={partialRegeneration}
    selectedSegment={selectedRange ? {
      segmentId: selectedRange.segmentId,
      startSec: selectedRange.startSec,
      endSec: selectedRange.endSec,
      nextSegmentId: selectedSessionSegmentIndex >= 0 ? session?.segments[selectedSessionSegmentIndex + 1]?.segmentId ?? null : null,
      cutAction: selectedSessionSegment?.cutAction ?? "keep",
      draftApplied: false,
      ttsReplacement: selectedSessionSegment?.ttsReplacement ?? null,
    } : undefined}
    ttsCandidateScopeKey={ttsCandidateScopeKey}
    inspectorTargets={projectInspectorTargets({ view, selectedSegmentId })}
  />;
}
