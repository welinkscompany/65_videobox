import type { LibraryAsset } from "../../api";

/**
 * 코사인 유사도는 절대값으로 "몇 % 확신"을 말할 수 없다(2026-08-31 실측:
 * "공원" 검색에서 관련 있는 것과 없는 것이 전부 0.44~0.49 사이에 몰렸다).
 * 그래서 이번 검색에서 가장 잘 맞는 것 대비 상대 백분율로 보여주고, 그
 * 최고점 대비 너무 낮은 것만 접는다 — 검색 결과가 0건이 되는 것보다 낫다.
 */
export const RELEVANCE_CUTOFF_PERCENT = 60;

export function withRelevance<T extends LibraryAsset>(matches: readonly T[]): T[] {
  const semanticScores = matches.filter((match) => match.semantic_match).map((match) => Number(match.score ?? 0));
  const top = semanticScores.length ? Math.max(...semanticScores) : 0;
  if (top <= 0) return [...matches];
  return matches
    .map((match) => (match.semantic_match ? { ...match, relevance_percent: Math.round((Number(match.score ?? 0) / top) * 100) } : match))
    .filter((match) => !match.semantic_match || (match.relevance_percent ?? 0) >= RELEVANCE_CUTOFF_PERCENT);
}
