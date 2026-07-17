import type { DirectorProposal } from "../../api";

export function ProposalComparisonTray({ proposal, selectedIds, preflight }: { proposal: DirectorProposal; selectedIds: string[]; preflight: { status?: string; code?: string; diff?: Record<string, unknown> } | null }) {
  return <section aria-label="루미 추천 비교"><p>추천 {selectedIds.length}개를 골랐어요.</p>{proposal.candidates.length < 2 ? <p>비교할 추천이 하나예요. 이 항목을 확인해 주세요.</p> : <p>고른 추천은 한 번에 편집본에 반영돼요.</p>}{preflight ? <p>추천을 적용하기 전에 변경된 내용이 있는지 확인하고 있어요.</p> : <p>추천을 확인하고 있어요.</p>}</section>;
}
