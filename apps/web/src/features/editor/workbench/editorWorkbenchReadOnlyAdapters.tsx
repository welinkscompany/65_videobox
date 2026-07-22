import type { EditorViewModel } from "../editorViewModel";
import { EditorAssetBrowser } from "../assets/EditorAssetBrowser";
import type { EditorAssetCard } from "../assets/editorAssetProjection";
import { TranscriptPanel } from "../transcript/TranscriptPanel";
import { projectTranscriptEntries } from "../transcript/transcriptProjection";
import { projectInspectorTargets } from "../inspector/inspectorRegistry";
import { RightDock } from "./RightDock";
import type { RightDockDirector } from "./rightDockTypes";

export function EditorWorkbenchReadOnlyAdapters({ view, dock, director, eugeneDraft, onEugeneDraftChange, selectedSegmentId, playbackSec, onSelectSegment, onSeek, onSaveCaption, isSavingCaption = false, assetCards = [], assetTarget, onPreviewAsset, onApplyAssetCard }: { view: EditorViewModel; dock: "left" | "right"; director?: RightDockDirector; eugeneDraft: string; onEugeneDraftChange: (value: string) => void; selectedSegmentId: string | null; playbackSec: number; onSelectSegment: (segmentId: string) => void; onSeek: (seconds: number) => void; onSaveCaption?: (input: { segmentId: string; text: string }) => void | Promise<void>; isSavingCaption?: boolean; assetCards?: readonly EditorAssetCard[]; assetTarget: Readonly<{ segmentId: string; startSec: number; endSec: number }> | null; onPreviewAsset: (card: EditorAssetCard) => void; onApplyAssetCard?: (card: EditorAssetCard, segmentId: string) => void | Promise<void> }) {
  if (dock === "left") return <>
    <EditorAssetBrowser cards={assetCards} target={assetTarget} isSaving={isSavingCaption} onPreview={onPreviewAsset} onApply={(card, segmentId) => void onApplyAssetCard?.(card, segmentId)} />
    <section aria-label="자산" className="vb-editor-workbench__summary"><h2>자산</h2>{view.tracks.map((track) => <p key={track.trackId}>{track.role}: {track.clips.length}개 클립</p>)}</section>
    <TranscriptPanel entries={projectTranscriptEntries({ narration: view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips.map((clip) => ({ segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec }))), captions: view.captions })} isSaving={isSavingCaption} onSaveCaption={onSaveCaption} onSeek={onSeek} onSelectSegment={onSelectSegment} playbackSec={playbackSec} selectedSegmentId={selectedSegmentId} />
  </>;
  const selectedNarration = selectedSegmentId === null ? null : view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips).find((clip) => clip.segmentId === selectedSegmentId) ?? null;
  return <RightDock
    draft={eugeneDraft}
    composerDisabled={director?.composerDisabled ?? true}
    messages={director?.messages}
    onApplyProposal={director?.onApplyProposal}
    onDraftChange={onEugeneDraftChange}
    onManualEdit={director?.onManualEdit}
    onPreviewCandidate={director?.onPreviewCandidate}
    onRetryMessage={director?.onRetryMessage}
    onSendMessage={director?.onSendMessage}
    onStart={director?.onStart}
    proposal={director?.proposal}
    retryAfterSeconds={director?.retryAfterSeconds}
    state={director?.state}
    selectedSegment={selectedNarration ? { segmentId: selectedNarration.segmentId, startSec: selectedNarration.startSec, endSec: selectedNarration.endSec, draftApplied: false } : undefined}
    inspectorTargets={projectInspectorTargets({ view, selectedSegmentId })}
  />;
}
