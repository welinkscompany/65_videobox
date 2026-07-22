import type { EditorViewModel } from "../editorViewModel";
import { EditorAssetBrowser } from "../assets/EditorAssetBrowser";
import type { EditorAssetCard } from "../assets/editorAssetProjection";
import { TranscriptPanel } from "../transcript/TranscriptPanel";
import { projectTranscriptEntries } from "../transcript/transcriptProjection";

export function EditorWorkbenchReadOnlyAdapters({ view, dock, eugeneDraft, onEugeneDraftChange, selectedSegmentId, playbackSec, onSelectSegment, onSeek, onSaveCaption, isSavingCaption = false, assetCards = [], assetTarget, onPreviewAsset, onApplyAssetCard }: { view: EditorViewModel; dock: "left" | "right"; eugeneDraft: string; onEugeneDraftChange: (value: string) => void; selectedSegmentId: string | null; playbackSec: number; onSelectSegment: (segmentId: string) => void; onSeek: (seconds: number) => void; onSaveCaption?: (input: { segmentId: string; text: string }) => void | Promise<void>; isSavingCaption?: boolean; assetCards?: readonly EditorAssetCard[]; assetTarget: Readonly<{ segmentId: string; startSec: number; endSec: number }> | null; onPreviewAsset: (card: EditorAssetCard) => void; onApplyAssetCard?: (card: EditorAssetCard, segmentId: string) => void | Promise<void> }) {
  if (dock === "left") return <>
    <EditorAssetBrowser cards={assetCards} target={assetTarget} isSaving={isSavingCaption} onPreview={onPreviewAsset} onApply={(card, segmentId) => void onApplyAssetCard?.(card, segmentId)} />
    <section aria-label="자산" className="vb-editor-workbench__summary"><h2>자산</h2>{view.tracks.map((track) => <p key={track.trackId}>{track.role}: {track.clips.length}개 클립</p>)}</section>
    <TranscriptPanel entries={projectTranscriptEntries({ narration: view.tracks.filter((track) => track.role === "narration").flatMap((track) => track.clips.map((clip) => ({ segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec }))), captions: view.captions })} isSaving={isSavingCaption} onSaveCaption={onSaveCaption} onSeek={onSeek} onSelectSegment={onSelectSegment} playbackSec={playbackSec} selectedSegmentId={selectedSegmentId} />
  </>;
  const selected = selectedSegmentId ?? view.captions[0]?.segmentId ?? "선택된 구간 없음";
  return <>
    <section aria-label="유진" className="vb-editor-workbench__summary"><h2>유진</h2><label htmlFor="vb-eugene-request">유진에게 요청하기</label><textarea id="vb-eugene-request" disabled value={eugeneDraft} onChange={(event) => onEugeneDraftChange(event.target.value)} placeholder="다음 단계에서 사용할 수 있어요." /><button type="button" disabled>요청 보내기</button></section>
    <section aria-label="추천" className="vb-editor-workbench__summary"><h2>추천</h2><p>추천은 다음 단계에서 준비합니다.</p></section>
    <section aria-label="Inspector" className="vb-editor-workbench__summary"><h2>Inspector</h2><p>선택 구간: {selected}</p><p>트랙: {view.tracks.map((track) => track.role).join(", ") || "없음"}</p><p>자막: {view.captions.length}개</p><p>revision: {view.expectedRevision}</p></section>
  </>;
}
