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

/**
 * `find_audio_matches`/`find_footage_matches`가 2026-09-20부터 이 값을
 * 직접 매겨서 보낸다(백엔드가 값이 태어나는 자리다 — 코드리뷰 altitude
 * 지적: 화면만 이 계산을 하면 같은 함수를 부르는 유진의 추천 경로는 원시
 * 점수만 받는다). 그래서 화면은 **다시 계산하지 않고** 그 값을 그대로
 * 쓴다 — 같은 계산을 두 곳에서 하면 나중에 갈라질 수 있다. 아직 그 값이
 * 없는 응답(옛 캐시, 이 계산이 나오기 전 픽스처)만 여기서 대신 매긴다.
 */
export function withRelevance<T extends LibraryAsset>(matches: readonly T[]): T[] {
  const needsFallback = matches.some((match) => match.semantic_match && match.relevance_percent === undefined);
  const withPercent = needsFallback ? attachFallbackRelevance(matches) : matches;
  return withPercent.filter((match) => !match.semantic_match || match.relevance_percent === undefined || match.relevance_percent >= RELEVANCE_CUTOFF_PERCENT);
}

function attachFallbackRelevance<T extends LibraryAsset>(matches: readonly T[]): T[] {
  const topByFamily = new Map<string, number>();
  for (const match of matches) {
    if (!match.semantic_match || match.relevance_percent !== undefined) continue;
    const family = relevanceFamily(match.media_type);
    const score = Number(match.score ?? 0);
    if (score > (topByFamily.get(family) ?? 0)) topByFamily.set(family, score);
  }
  return matches.map((match) => {
    if (!match.semantic_match || match.relevance_percent !== undefined) return match;
    const top = topByFamily.get(relevanceFamily(match.media_type)) ?? 0;
    return top > 0 ? { ...match, relevance_percent: Math.round((Number(match.score ?? 0) / top) * 100) } : match;
  });
}
