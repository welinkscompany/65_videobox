import type { ArtifactFreshness, EditingSessionHistoryEntry } from "../../api";

export type NamedArtifact = ArtifactFreshness & { kind: string };
export const selectCurrentArtifacts = <T extends ArtifactFreshness>(artifacts: T[]) => artifacts.filter((artifact) => artifact.is_current !== false);

function artifactLabel(kind: string) {
  return ({ preview: "미리보기", final: "완성본", subtitle: "자막", capcut_draft: "CapCut 초안" } as Record<string, string>)[kind] ?? "제작 결과";
}

function historyLabel(entry: EditingSessionHistoryEntry) {
  return ({ broll_override: "영상 추천 변경", bgm_override: "배경음악 변경", sfx_override: "효과음 변경" } as Record<string, string>)[entry.mutation_type] ?? "편집 내용 변경";
}

export function DirectorHistoryControls({ history, artifacts, onUndo, onRedo }: { history: EditingSessionHistoryEntry[]; artifacts: NamedArtifact[]; onUndo: () => void; onRedo: () => void }) {
  return <section aria-label="편집 기록">
    <button onClick={onUndo}>실행 취소</button><button onClick={onRedo}>다시 실행</button>
    <ul>{selectCurrentArtifacts(artifacts).map((artifact) => <li key={artifact.kind}><button aria-label={`${artifactLabel(artifact.kind)} 열기`}>{artifactLabel(artifact.kind)}</button></li>)}</ul>
    <ul>{artifacts.filter((artifact) => artifact.is_current === false).map((artifact) => <li key={`${artifact.kind}-${artifact.source_session_revision}`}>이전 결과예요. 현재 편집본으로 다시 만들 수 있어요.</li>)}</ul>
    <ol>{history.map((entry) => <li key={entry.action_id ?? `${entry.mutation_type}-${entry.segment_id}`}>{historyLabel(entry)}{entry.blocked_reason ? " · 지금은 적용할 수 없어요. 다시 확인해 주세요." : ""}</li>)}</ol>
  </section>;
}
