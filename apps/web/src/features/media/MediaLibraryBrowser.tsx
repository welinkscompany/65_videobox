import { useEffect, useId, useState } from "react";

import { api, type LibraryAsset, type MediaLibraryAsset, type MediaLibraryInstallState } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { orderByFavouriteThenRecent } from "../../lib/pickerOrder";

type Filter = "all" | "broll" | "music" | "sfx" | "image";
export const MEDIA_LIBRARY_PAGE_SIZE = 24;
type BrowserAsset = MediaLibraryAsset | LibraryAsset;

function isPersonalAsset(item: BrowserAsset): item is LibraryAsset { return "origin" in item; }
function displayFilename(item: BrowserAsset, fallback: string) {
  if (isPersonalAsset(item)) {
    const filename = item.user_metadata?.filename;
    if (typeof filename === "string" && filename.trim()) return filename.trim();
  }
  return fallback;
}

export function libraryEmptyReason(installState: MediaLibraryInstallState | null, loadFailed: boolean, fixedFilter?: Exclude<Filter, "all">): string {
  // 영상은 꾸러미로 들여놓는 것이 아니라 owner가 직접 넣은 것만 있다.
  if (fixedFilter === "broll") {
    if (loadFailed) return "라이브러리 영상을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.";
    return "아직 라이브러리에 영상이 없어요. 내 라이브러리에서 영상을 먼저 추가해 주세요.";
  }
  if (installState?.status === "not_installed") return "음악과 효과음 꾸러미를 아직 들여놓지 않았어요. 꾸러미를 넣으면 여기에서 바로 들어볼 수 있어요.";
  if (loadFailed || !installState) return "음악과 효과음을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.";
  return "아직 준비된 음악과 효과음이 없어요.";
}

/** 영상은 "들어보는" 것이 아니라 "보는" 것이라 안내 문구가 달라진다. */
function browserCopy(fixedFilter?: Exclude<Filter, "all">) {
  if (fixedFilter === "broll") {
    return {
      heading: "라이브러리 영상",
      lead: "라이브러리에서 찾기 · 미리 보고 프로젝트에 추가하세요.",
      loading: "라이브러리 영상을 불러오고 있어요.",
      pagination: "라이브러리 영상 페이지 이동",
    };
  }
  return {
    heading: "음악과 효과음",
    lead: "라이브러리에서 찾기 · 미리 듣고 프로젝트에 추가하세요.",
    loading: "음악과 효과음을 불러오고 있어요.",
    pagination: "음악과 효과음 페이지 이동",
  };
}

type SortOrder = "recent" | "name";

const sortOrders: readonly { value: SortOrder; label: string }[] = [
  { value: "recent", label: "최근 순" },
  { value: "name", label: "이름 순" },
];

const filters: readonly { value: Filter; label: string }[] = [
  { value: "all", label: "전체 보기" },
  { value: "broll", label: "영상만 보기" },
  { value: "music", label: "음악만 보기" },
  { value: "sfx", label: "효과음만 보기" },
];

/** Project picker adapter for the global personal library and immutable starter pack. */
export function MediaLibraryBrowser({ projectId, fixedFilter, onMaterialized }: { projectId: string; fixedFilter?: Exclude<Filter, "all">; onMaterialized?: () => void }) {
  const [assets, setAssets] = useState<readonly BrowserAsset[]>([]);
  const [favourites, setFavourites] = useState<readonly string[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [ready, setReady] = useState(false);
  const [installState, setInstallState] = useState<MediaLibraryInstallState | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [recents, setRecents] = useState<readonly string[]>([]);
  const [page, setPage] = useState(1);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [favouriteBusy, setFavouriteBusy] = useState<readonly string[]>([]);
  const [materializeBusy, setMaterializeBusy] = useState<readonly string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortOrder>("recent");
  const [favouritesOnly, setFavouritesOnly] = useState(false);
  const searchId = useId();

  useEffect(() => {
    let active = true;
    setReady(false); setLoadFailed(false); setInstallState(null); setRecents([]); setFavouriteBusy([]); setMaterializeBusy([]); setMessage(null);
    // 좁혀 둔 조건은 다른 보관함으로 옮기면 뜻이 없어진다. 정렬 취향은 그대로 둔다.
    setQuery(""); setFavouritesOnly(false);
    void api.getMediaLibraryInstallState().then((state) => { if (active) setInstallState(state); }).catch(() => undefined);
    void api.listProjectRecentMediaLibraryAssetIds(projectId).then((recent) => { if (active) setRecents(recent.asset_ids); }).catch(() => undefined);
    let legacyFailed = false;
    let personalFailed = false;
    void Promise.all([
      api.listMediaLibraryAssets().catch(() => { legacyFailed = true; return { assets: [] as MediaLibraryAsset[] }; }),
      api.listLibraryAssets({ mediaType: fixedFilter, limit: 500 }).catch(() => { personalFailed = true; return { assets: [] }; }),
      api.listProjectMediaLibraryFavorites(projectId),
    ]).then(([legacy, personal, favourite]) => {
      if (!active) return;
      const merged = new Map<string, BrowserAsset>();
      [...legacy.assets, ...personal.assets.filter((item) => item.lifecycle !== "trashed")].forEach((item) => merged.set(item.library_asset_id, item));
      setAssets([...merged.values()]); setFavourites(favourite.asset_ids);
      if (legacyFailed && personalFailed) setLoadFailed(true);
    }).catch(() => { if (active) setLoadFailed(true); }).finally(() => { if (active) setReady(true); });
    setPage(1);
    return () => { active = false; };
  }, [fixedFilter, loadAttempt, projectId]);

  const toggle = async (libraryAssetId: string, enabled: boolean) => {
    if (favouriteBusy.includes(libraryAssetId)) return;
    setFavouriteBusy((current) => [...current, libraryAssetId]);
    setFavourites((current) => enabled ? [...current, libraryAssetId] : current.filter((item) => item !== libraryAssetId));
    try { setFavourites((await api.setProjectMediaLibraryFavorite(projectId, libraryAssetId, enabled)).asset_ids); }
    catch { setFavourites((current) => enabled ? current.filter((item) => item !== libraryAssetId) : [...current, libraryAssetId]); }
    finally { setFavouriteBusy((current) => current.filter((id) => id !== libraryAssetId)); }
  };

  const materialize = async (item: BrowserAsset) => {
    if (materializeBusy.includes(item.library_asset_id)) return;
    setMaterializeBusy((current) => [...current, item.library_asset_id]);
    try {
      if (isPersonalAsset(item)) await api.materializeLibraryAsset(item.library_asset_id, projectId);
      else await api.materializeMediaLibraryAsset(item.library_asset_id, projectId);
      setRecents((current) => [item.library_asset_id, ...current.filter((id) => id !== item.library_asset_id)]);
      setMessage(`「${displayFilename(item, item.asset_id ?? item.library_asset_id)}」을 프로젝트에 추가했어요.`);
      onMaterialized?.();
    } catch { setMessage("프로젝트에 추가하지 못했어요. 잠시 뒤 다시 시도해 주세요."); }
    finally { setMaterializeBusy((current) => current.filter((id) => id !== item.library_asset_id)); }
  };

  const displayNames = new Map<string, string>();
  for (const kind of ["broll", "music", "sfx", "image"] as const) {
    const label = kind === "broll" ? "영상" : kind === "music" ? "음악" : kind === "sfx" ? "효과음" : "그림";
    assets.filter((item) => item.media_type === kind).slice().sort((left, right) => String(left.asset_id ?? "").localeCompare(String(right.asset_id ?? ""))).forEach((item, index) => displayNames.set(item.library_asset_id, displayFilename(item, `${label} ${index + 1}`)));
  }
  const nameOf = (item: BrowserAsset) => displayNames.get(item.library_asset_id) ?? displayFilename(item, item.asset_id ?? item.library_asset_id);
  const selectedFilter = fixedFilter ?? filter;
  // 이름으로 좁히기. 종류 탭 안이 그냥 나열이라 쌓일수록 찾을 수 없었다.
  const needle = query.trim().toLocaleLowerCase("ko");
  const matching = assets.filter((item) => (selectedFilter === "all" || item.media_type === selectedFilter)
    && (needle === "" || nameOf(item).toLocaleLowerCase("ko").includes(needle))
    && (!favouritesOnly || favourites.includes(item.library_asset_id)));
  // 즐겨찾기는 어느 순서에서도 위에 남는다 -- 담아 둔 것을 다시 내려보내면 담아 둔 뜻이 없어진다.
  // "최근 순"은 프로젝트에서 최근에 쓴 것 다음에 늦게 넣은 것부터, "이름 순"은 가나다 순이다.
  const addedAt = (item: BrowserAsset) => (isPersonalAsset(item) && typeof item.created_at === "string" ? item.created_at : "");
  const byId = (left: BrowserAsset, right: BrowserAsset) => String(left.asset_id ?? "").localeCompare(String(right.asset_id ?? ""));
  const byAdded = (left: BrowserAsset, right: BrowserAsset) => addedAt(right).localeCompare(addedAt(left)) || byId(left, right);
  const byName = (left: BrowserAsset, right: BrowserAsset) => nameOf(left).localeCompare(nameOf(right), "ko") || byId(left, right);
  const visible = sort === "name"
    ? orderByFavouriteThenRecent(matching, (item) => item.library_asset_id, favourites, [], byName)
    : orderByFavouriteThenRecent(matching, (item) => item.library_asset_id, favourites, recents, byAdded);
  const pageCount = Math.max(1, Math.ceil(visible.length / MEDIA_LIBRARY_PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageItems = visible.slice((safePage - 1) * MEDIA_LIBRARY_PAGE_SIZE, safePage * MEDIA_LIBRARY_PAGE_SIZE);
  useEffect(() => { setPage((current) => Math.min(current, pageCount)); }, [pageCount]);

  const copy = browserCopy(fixedFilter);
  if (!ready) return <section className="vb-media-library" aria-labelledby="media-library-heading"><h2 id="media-library-heading">{copy.heading}</h2><p role="status">{copy.loading}</p></section>;
  return <section className="vb-media-library" aria-labelledby="media-library-heading">
    <h2 id="media-library-heading">{copy.heading}</h2>
    <p>{copy.lead}</p>
    {message ? <p role="status">{message}</p> : null}
    {installState?.status === "degraded" ? <p role="status">{`들여놓은 ${installState.installed_asset_count}개 가운데 일부는 확인이 끝나지 않아 아직 쓸 수 없어요.`}</p> : null}
    {fixedFilter ? null : <div className="vb-media-library__filters">{filters.map((item) => <Button key={item.value} type="button" variant={filter === item.value ? "default" : "outline"} aria-pressed={filter === item.value} onClick={() => { setFilter(item.value); setPage(1); }}>{item.label}</Button>)}</div>}
    <div className="vb-media-library__toolbar">
      <label htmlFor={searchId}>이름으로 찾기</label>
      <Input id={searchId} type="search" value={query} placeholder="이름 일부를 적어 보세요" onChange={(event) => { setQuery(event.target.value); setPage(1); }} />
      <div role="group" aria-label="정렬 순서" className="vb-media-library__filters">
        {sortOrders.map((item) => <Button key={item.value} type="button" variant={sort === item.value ? "default" : "outline"} aria-pressed={sort === item.value} onClick={() => { setSort(item.value); setPage(1); }}>{item.label}</Button>)}
      </div>
      <div className="vb-media-library__filters">
        <Button type="button" variant={favouritesOnly ? "default" : "outline"} aria-pressed={favouritesOnly} onClick={() => { setFavouritesOnly((current) => !current); setPage(1); }}>즐겨찾기만 보기</Button>
      </div>
    </div>
    {loadFailed ? <Button type="button" variant="outline" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>다시 불러오기</Button> : null}
    {visible.length ? <>
      <div className="vb-media-library__grid">{pageItems.map((item) => {
        const loved = favourites.includes(item.library_asset_id); const name = displayNames.get(item.library_asset_id) ?? displayFilename(item, item.asset_id ?? item.library_asset_id); const personal = isPersonalAsset(item); const previewUrl = personal ? (item.preview_url ?? api.libraryAssetPreviewUrl(item.library_asset_id)) : api.mediaLibraryPreviewUrl(item.library_asset_id);
        return <article key={item.library_asset_id} aria-label={`${name} 항목`}>
          {/* 그림은 길이가 없고 들을 것도 없다. 옛 갈래("영상이 아니면 소리")를
              그대로 두면 `효과음 · 0초`에 빈 소리 재생기가 붙는다. */}
          <p><strong>{name}</strong>{" · "}{item.media_type === "broll" ? "영상" : item.media_type === "music" ? "음악" : item.media_type === "image" ? "그림" : "효과음"}{item.media_type === "image" ? "" : `${" · "}${Math.round(isPersonalAsset(item) ? (item.duration_seconds ?? (typeof item.technical_metadata?.duration_seconds === "number" ? item.technical_metadata.duration_seconds : 0)) : (item.duration_seconds ?? 0))}초`}{!loved && recents.includes(item.library_asset_id) ? " · 최근에 썼어요" : ""}</p>
          {item.media_type === "image" ? <img aria-label={`${name} 미리보기`} src={previewUrl} alt={name} /> : item.media_type === "broll" ? <video controls preload="metadata" aria-label={`${name} 미리보기`} src={previewUrl} /> : <audio controls preload="none" aria-label={`${name} 미리 듣기`} src={previewUrl} />}
          <Button type="button" variant="default" disabled={materializeBusy.includes(item.library_asset_id)} aria-label={`${name} 프로젝트에 추가`} onClick={() => void materialize(item)}>{materializeBusy.includes(item.library_asset_id) ? "추가 중" : "프로젝트에 추가"}</Button>
          <Button type="button" variant="outline" disabled={favouriteBusy.includes(item.library_asset_id)} aria-label={`${name} 즐겨찾기${loved ? " 해제" : ""}`} onClick={() => void toggle(item.library_asset_id, !loved)}>{loved ? "즐겨찾기 해제" : "즐겨찾기"}</Button>
        </article>;
      })}</div>
      {pageCount > 1 ? <nav aria-label={copy.pagination} className="vb-media-library__pagination"><Button type="button" variant="outline" disabled={safePage <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>이전 페이지</Button><span aria-live="polite">{safePage} / {pageCount}페이지</span><Button type="button" variant="outline" disabled={safePage >= pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>다음 페이지</Button></nav> : null}
    </> : <p>{favouritesOnly && favourites.length === 0
      ? "아직 즐겨찾기에 담아 둔 것이 없어요. 자주 쓰는 것에 즐겨찾기를 눌러 두세요."
      : assets.length ? "고른 조건에 맞는 것이 없어요." : libraryEmptyReason(installState, loadFailed, fixedFilter)}</p>}
  </section>;
}
