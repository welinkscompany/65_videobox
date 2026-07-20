import type { EditorViewModel } from "../editorViewModel";

function seconds(value: number) { return `${value.toFixed(1)}초`; }

export function EditorWorkbenchReadOnlyAdapters({ view, dock, eugeneDraft, onEugeneDraftChange }: { view: EditorViewModel; dock: "left" | "right"; eugeneDraft: string; onEugeneDraftChange: (value: string) => void }) {
  if (dock === "left") return <>
    <section aria-label="자산" className="vb-editor-workbench__summary"><h2>자산</h2>{view.tracks.map((track) => <p key={track.trackId}>{track.role}: {track.clips.length}개 클립</p>)}</section>
    <section aria-label="대본" className="vb-editor-workbench__summary"><h2>대본</h2>{view.captions.map((caption) => <p key={caption.segmentId}>{caption.text} · {seconds(caption.startSec)}–{seconds(caption.endSec)}</p>)}</section>
    <section aria-label="자막" className="vb-editor-workbench__summary"><h2>자막</h2><p>{view.captions.length}개 자막, 읽기 전용</p></section>
  </>;
  const selected = view.local.selectedSegmentId ?? view.captions[0]?.segmentId ?? "선택된 구간 없음";
  return <>
    <section aria-label="유진" className="vb-editor-workbench__summary"><h2>유진</h2><label htmlFor="vb-eugene-request">유진에게 요청하기</label><textarea id="vb-eugene-request" disabled value={eugeneDraft} onChange={(event) => onEugeneDraftChange(event.target.value)} placeholder="다음 단계에서 사용할 수 있어요." /><button type="button" disabled>요청 보내기</button></section>
    <section aria-label="추천" className="vb-editor-workbench__summary"><h2>추천</h2><p>추천은 다음 단계에서 준비합니다.</p></section>
    <section aria-label="Inspector" className="vb-editor-workbench__summary"><h2>Inspector</h2><p>선택 구간: {selected}</p><p>트랙: {view.tracks.map((track) => track.role).join(", ") || "없음"}</p><p>자막: {view.captions.length}개</p><p>revision: {view.expectedRevision}</p></section>
  </>;
}
