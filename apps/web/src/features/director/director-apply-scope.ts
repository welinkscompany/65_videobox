/** Public UI scope names deliberately mirror the Director API contract. */
export type DirectorApplyScope = "selected_references" | "broll_only" | "all";

export function candidateIdsForScope(
  scope: DirectorApplyScope, selectedIds: readonly string[], candidates: readonly { candidate_id: string; media_type: string }[],
): string[] {
  const selected = new Set(selectedIds);
  return candidates.filter((candidate) => scope === "all" || (scope === "broll_only" && candidate.media_type === "broll") || (scope === "selected_references" && selected.has(candidate.candidate_id))).map((candidate) => candidate.candidate_id);
}
