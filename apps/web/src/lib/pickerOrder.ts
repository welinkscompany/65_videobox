/** 즐겨찾기 먼저, 그다음 최근에 쓴 것, 나머지는 원래 순서.
 *
 * 저장소는 최근 쓴 것을 이미 기록하고 있었다 -- 자막 모양은 적용할 때마다,
 * 음악과 효과음은 프로젝트로 들여올 때마다. 그런데 어느 화면도 그것을 다시
 * 읽지 않아서, 방금 쓴 것을 다음에도 목록 아래에서 찾아 내려가야 했다.
 *
 * 최근 목록은 가장 최근이 앞이다. 즐겨찾기와 겹치면 즐겨찾기가 이긴다 --
 * 한 번 담아 둔 것을 다시 내려보내면 담아 둔 뜻이 없어진다.
 */
export function orderByFavouriteThenRecent<T>(
  items: readonly T[],
  identify: (item: T) => string,
  favourites: readonly string[],
  recents: readonly string[],
  tieBreak: (left: T, right: T) => number = () => 0,
): T[] {
  const recentRank = new Map(recents.map((id, index) => [id, index]));
  const rankOf = (item: T): number => {
    const id = identify(item);
    if (favourites.includes(id)) return 0;
    return recentRank.has(id) ? 1 : 2;
  };
  return items.slice().sort((left, right) => {
    const difference = rankOf(left) - rankOf(right);
    if (difference !== 0) return difference;
    if (rankOf(left) === 1) {
      const order = (recentRank.get(identify(left)) ?? 0) - (recentRank.get(identify(right)) ?? 0);
      if (order !== 0) return order;
    }
    return tieBreak(left, right);
  });
}
