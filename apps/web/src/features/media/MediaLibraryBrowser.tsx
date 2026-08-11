import { useEffect, useState } from "react";

import { api, type MediaLibraryAsset, type MediaLibraryInstallState } from "../../api";
import { Button } from "../../components/ui/button";
import { orderByFavouriteThenRecent } from "../../lib/pickerOrder";

type Filter = "all" | "music" | "sfx";
export const MEDIA_LIBRARY_PAGE_SIZE = 24;

/** 비어 있는 목록에 이유를 붙인다.
 *
 * 빈 화면은 세 가지 서로 다른 사정을 같은 얼굴로 보여 준다 -- 꾸러미를 아직
 * 넣지 않았거나, 넣었는데 확인이 끝나지 않았거나, 목록을 못 읽었거나.
 * 무엇을 해야 할지가 셋 다 다르므로 하나로 뭉뚱그리면 owner는 멈춘다.
 */
export function libraryEmptyReason(
  installState: MediaLibraryInstallState | null,
  loadFailed: boolean,
): string {
  if (installState?.status === "not_installed") {
    return "음악과 효과음 꾸러미를 아직 들여놓지 않았어요. 꾸러미를 넣으면 여기에서 바로 들어볼 수 있어요.";
  }
  if (loadFailed || !installState) {
    return "음악과 효과음을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.";
  }
  return "아직 준비된 음악과 효과음이 없어요.";
}

const filters: readonly { value: Filter; label: string }[] = [
  { value: "all", label: "전체 보기" },
  { value: "music", label: "음악만 보기" },
  { value: "sfx", label: "효과음만 보기" },
];

/** Browse the music and effects library, hear one, and keep the good ones.
 *
 * The library, its favourites and its preview URL all existed; nothing on
 * screen used them. With 130 assets installed, choosing meant reading
 * filenames and guessing.
 */
export function MediaLibraryBrowser({ projectId, fixedFilter }: { projectId: string; fixedFilter?: Exclude<Filter, "all"> }) {
  const [assets, setAssets] = useState<readonly MediaLibraryAsset[]>([]);
  const [favourites, setFavourites] = useState<readonly string[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [ready, setReady] = useState(false);
  const [installState, setInstallState] = useState<MediaLibraryInstallState | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [recents, setRecents] = useState<readonly string[]>([]);
  const [page, setPage] = useState(1);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setReady(false);
    setLoadFailed(false);
    setInstallState(null);
    // 꾸러미 상태는 목록과 따로 묻는다. 하나로 묶으면 목록이 실패한 순간
    // 이유까지 같이 사라져서, 빈 화면이 다시 아무 말도 하지 않게 된다.
    void api.getMediaLibraryInstallState()
      .then((state) => { if (active) setInstallState(state); })
      .catch(() => { /* 이유를 못 물었으면 못 읽었다고 말한다 */ });
    setRecents([]);
    // 프로젝트로 들여온 것은 이미 최근 목록에 쌓이고 있었는데 아무도 다시
    // 읽지 않았다. 못 읽으면 순서만 덜 똑똑해진다.
    void api.listRecentMediaLibraryAssetIds()
      .then((recent) => { if (active) setRecents(recent.asset_ids); })
      .catch(() => { /* 정렬만 예전대로 돌아간다 */ });
    void Promise.all([api.listMediaLibraryAssets(), api.listMediaLibraryFavorites()])
      .then(([library, favourite]) => {
        if (!active) return;
        setAssets(library.assets);
        setFavourites(favourite.asset_ids);
      })
      .catch(() => { if (active) setLoadFailed(true); })
      .finally(() => { if (active) setReady(true); });
    setPage(1);
    return () => { active = false; };
  }, [loadAttempt, projectId]);

  const toggle = async (libraryAssetId: string, enabled: boolean) => {
    // Show the change now; the list re-sorts on the server's answer.
    setFavourites((current) => enabled
      ? [...current, libraryAssetId]
      : current.filter((item) => item !== libraryAssetId));
    try {
      const saved = await api.setMediaLibraryFavorite(libraryAssetId, enabled);
      setFavourites(saved.asset_ids);
    } catch {
      setFavourites((current) => enabled
        ? current.filter((item) => item !== libraryAssetId)
        : [...current, libraryAssetId]);
    }
  };

  // 팩이 주는 `asset_id`는 내부 슬러그다(`music-005`). owner에게 보일 이름은
  // 종류별 고정 순서로 매긴 번호로 만든다 -- 즐겨찾기가 위로 올라가도 같은
  // 곡이 같은 번호를 유지해야 한다.
  const displayNames = new Map<string, string>();
  for (const kind of ["music", "sfx"] as const) {
    const label = kind === "music" ? "음악" : "효과음";
    assets
      .filter((item) => item.media_type === kind)
      .slice()
      .sort((left, right) => left.asset_id.localeCompare(right.asset_id))
      .forEach((item, index) => displayNames.set(item.library_asset_id, `${label} ${index + 1}`));
  }

  // Favourites first, then whatever was used most recently: the point of
  // marking one is not to hunt for it again, and neither is having just used it.
  const selectedFilter = fixedFilter ?? filter;
  const visible = orderByFavouriteThenRecent(
    assets.filter((item) => selectedFilter === "all" || item.media_type === selectedFilter),
    (item) => item.library_asset_id,
    favourites,
    recents,
    (left, right) => left.asset_id.localeCompare(right.asset_id),
  );

  const pageCount = Math.max(1, Math.ceil(visible.length / MEDIA_LIBRARY_PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageItems = visible.slice((safePage - 1) * MEDIA_LIBRARY_PAGE_SIZE, safePage * MEDIA_LIBRARY_PAGE_SIZE);

  useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  if (!ready) return <section className="vb-media-library" aria-labelledby="media-library-heading"><h2 id="media-library-heading">음악과 효과음</h2><p role="status">음악과 효과음을 불러오고 있어요.</p></section>;
  return (
    <section className="vb-media-library" aria-labelledby="media-library-heading">
      <h2 id="media-library-heading">음악과 효과음</h2>
      <p>들어보고 마음에 드는 것은 즐겨찾기에 담아 두세요.</p>
      {installState?.status === "degraded" ? (
        <p role="status">{`들여놓은 ${installState.installed_asset_count}개 가운데 일부는 확인이 끝나지 않아 아직 쓸 수 없어요.`}</p>
      ) : null}
      {fixedFilter ? null : <div className="vb-media-library__filters">
        {filters.map((item) => (
          <Button
            key={item.value}
            type="button"
            variant="outline"
            aria-pressed={filter === item.value}
            onClick={() => { setFilter(item.value); setPage(1); }}
          >
            {item.label}
          </Button>
        ))}
      </div>}
      {loadFailed ? <Button type="button" variant="outline" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>다시 불러오기</Button> : null}
      {visible.length ? <>
        <div className="vb-media-library__grid">
        {pageItems.map((item) => {
        const loved = favourites.includes(item.library_asset_id);
        const name = displayNames.get(item.library_asset_id) ?? item.asset_id;
        return (
          <article key={item.library_asset_id} aria-label={`${name} 항목`}>
            <p>
              <strong>{name}</strong>
              {" · "}
              {item.media_type === "music" ? "음악" : "효과음"}
              {" · "}
              {`${Math.round(item.duration_seconds)}초`}
              {!loved && recents.includes(item.library_asset_id) ? " · 최근에 썼어요" : ""}
            </p>
            <audio
              controls
              preload="none"
              aria-label={`${name} 미리 듣기`}
              src={api.mediaLibraryPreviewUrl(item.library_asset_id)}
            />
            <Button
              type="button"
              variant="outline"
              aria-label={`${name} 즐겨찾기${loved ? " 해제" : ""}`}
              onClick={() => void toggle(item.library_asset_id, !loved)}
            >
              {loved ? "즐겨찾기 해제" : "즐겨찾기"}
            </Button>
          </article>
        );
      })}
        </div>
        {pageCount > 1 ? <nav aria-label="음악과 효과음 페이지 이동" className="vb-media-library__pagination">
          <Button type="button" variant="outline" disabled={safePage <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>이전 페이지</Button>
          <span aria-live="polite">{safePage} / {pageCount}페이지</span>
          <Button type="button" variant="outline" disabled={safePage >= pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>다음 페이지</Button>
        </nav> : null}
      </> : <p>{assets.length ? "고른 조건에 맞는 것이 없어요." : libraryEmptyReason(installState, loadFailed)}</p>}
    </section>
  );
}
