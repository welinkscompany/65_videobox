import type { ArtifactFreshness, EditingSessionHistoryEntry } from "../../api";

export type NamedArtifact = ArtifactFreshness & { kind: string };
export const selectCurrentArtifacts = <T extends ArtifactFreshness>(artifacts: T[]) => artifacts.filter((artifact) => artifact.is_current !== false);

export function DirectorHistoryControls({ history, artifacts, onUndo, onRedo }: { history: EditingSessionHistoryEntry[]; artifacts: NamedArtifact[]; onUndo: () => void; onRedo: () => void }) {
  return <section aria-label="편집 기록">
    <button onClick={onUndo}>실행 취소</button><button onClick={onRedo}>다시 실행</button>
    <ul>{selectCurrentArtifacts(artifacts).map((artifact) => <li key={artifact.kind}><button aria-label={`${artifact.kind} 열기`}>{artifact.kind}</button></li>)}</ul>
    <ul>{artifacts.filter((artifact) => artifact.is_current === false).map((artifact) => <li key={`${artifact.kind}-${artifact.source_session_revision}`}>{artifact.kind} revision {artifact.source_session_revision} · {artifact.invalidated_reason ?? "stale"}</li>)}</ul>
    <ol>{history.map((entry) => <li key={entry.action_id ?? `${entry.mutation_type}-${entry.segment_id}`}>{entry.label ?? entry.mutation_type}{entry.blocked_reason ? ` · ${entry.blocked_reason}` : ""}</li>)}</ol>
  </section>;
}
