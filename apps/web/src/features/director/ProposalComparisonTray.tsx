import type { DirectorProposal } from "../../api";

export function ProposalComparisonTray({ proposal, selectedIds, preflight }: { proposal: DirectorProposal; selectedIds: string[]; preflight: { status?: string; code?: string; diff?: Record<string, unknown> } | null }) {
  return <section aria-label="제안 비교와 사전 확인"><p>{proposal.revision_code} · revision {proposal.base_session_revision} · 선택 {selectedIds.length}개</p>{proposal.candidates.length < 2 ? <p>비교할 후보가 부족합니다. 현재 후보 하나만 검토할 수 있습니다.</p> : <p>선택 후보는 하나의 원자적 변경으로 적용됩니다.</p>}{preflight ? <pre aria-label="immutable preflight diff">{JSON.stringify(preflight.diff ?? {})}</pre> : <p>사전 확인 중</p>}</section>;
}
