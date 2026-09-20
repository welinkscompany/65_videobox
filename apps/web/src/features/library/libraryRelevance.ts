import type { LibraryAsset } from "../../api";

/**
 * 코사인 유사도는 절대값으로 "몇 % 확신"을 말할 수 없다(2026-08-31 실측:
 * "공원" 검색에서 관련 있는 것과 없는 것이 전부 0.44~0.49 사이에 몰렸다).
 * 그래서 이번 검색에서 가장 잘 맞는 것 대비 상대 백분율로 보여주고, 그
 * 최고점 대비 너무 낮은 것만 접는다 — 검색 결과가 0건이 되는 것보다 낫다.
 */
export const RELEVANCE_CUTOFF_PERCENT = 60;

const AUDIO_MEDIA_TYPES = new Set<LibraryAsset["media_type"]>(["music", "sfx"]);

/**
 * 영상·그림은 한 임베딩 색인(`find_footage_matches`)을, 음악·효과음은 다른
 * 색인(`find_audio_matches`)을 쓴다(2026-09-20 코드리뷰 실측) — 서로 다른
 * 모델이 내는 코사인 점수 규모가 같다는 보장이 없다. "전체" 탭처럼 네
 * 종류를 한 번에 묻고 최고점을 하나로 합치면, 한쪽 색인이 원래 더 높은
 * 점수를 낸다는 이유만으로 다른 쪽 전체가 조용히 사라질 수 있다 — 그래서
 * 관련도는 **같은 색인을 쓰는 것들끼리만** 최고점 대비로 잰다.
 */
function relevanceFamily(mediaType: LibraryAsset["media_type"]): "audio" | "footage" {
  return AUDIO_MEDIA_TYPES.has(mediaType) ? "audio" : "footage";
}

export function withRelevance<T extends LibraryAsset>(matches: readonly T[]): T[] {
  const topByFamily = new Map<string, number>();
  for (const match of matches) {
    if (!match.semantic_match) continue;
    const family = relevanceFamily(match.media_type);
    const score = Number(match.score ?? 0);
    if (score > (topByFamily.get(family) ?? 0)) topByFamily.set(family, score);
  }
  return matches
    .map((match) => {
      if (!match.semantic_match) return match;
      const top = topByFamily.get(relevanceFamily(match.media_type)) ?? 0;
      return top > 0 ? { ...match, relevance_percent: Math.round((Number(match.score ?? 0) / top) * 100) } : match;
    })
    .filter((match) => !match.semantic_match || match.relevance_percent === undefined || match.relevance_percent >= RELEVANCE_CUTOFF_PERCENT);
}
