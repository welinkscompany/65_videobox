import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, type LibraryAsset, type LibraryIngestItem, type LibraryMediaType } from "../../api";
import { AssetIngestDropzone } from "./AssetIngestDropzone";
import { IngestJobTable } from "./IngestJobTable";
import { LibraryPreviewPane } from "./LibraryPreviewPane";
import { LibraryResults } from "./LibraryResults";
import { LibrarySidebar, type LibraryFilter } from "./LibrarySidebar";
import "./library.css";

function fileType(file: File): LibraryMediaType | null {
  const name = file.name.toLowerCase();
  if (file.type.startsWith("video/") || /\.(mp4|mov|m4v|webm|avi|mkv)$/.test(name)) return "broll";
  if (file.type.startsWith("audio/") || /\.(mp3|wav|m4a|ogg|flac|aac)$/.test(name)) return name.includes("sfx") || name.includes("effect") ? "sfx" : "music";
  return null;
}

function fileDisplayName(file: File): string {
  const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath?.trim();
  return relativePath || file.name;
}

function matchesFilter(asset: LibraryAsset, filter: LibraryFilter) {
  if (filter === "all") return asset.lifecycle !== "trashed";
  if (filter === "trash") return asset.lifecycle === "trashed";
  if (filter === "favorites") return Boolean(asset.user_metadata?.favorite);
  return asset.media_type === filter && asset.lifecycle !== "trashed";
}

export function LibraryPage() {
  const [assets, setAssets] = useState<LibraryAsset[]>([]);
  const [activeFilter, setActiveFilter] = useState<LibraryFilter>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<LibraryAsset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ingestItems, setIngestItems] = useState<LibraryIngestItem[]>([]);
  // 종류 탭 + 검색어일 때만 의미검색이 돈다. 어느 방식으로 찾았는지는 말한다.
  const [searchMode, setSearchMode] = useState<"semantic" | "word" | null>(null);
  const failedFiles = useRef(new Map<string, File>());
  const epoch = useRef(0);
  // A cross-entry link (e.g. from the footage organizer) names the asset it
  // wants selected. Only the first successful load honors it, so a later
  // reload never overrides a choice the owner made in the meantime.
  const requestedAssetId = useRef<string | null>(new URLSearchParams(window.location.search).get("library_asset_id"));

  const load = useCallback(async () => {
    const currentEpoch = ++epoch.current;
    setLoading(true); setError(null);
    try {
      // 종류 탭을 고르고 검색하면 의미검색(`/api/library/search`)을 부른다.
      // 이 엔드포인트는 백엔드에 있었는데 부르는 화면이 없어 검색이 언제나
      // 단어 매칭이었다. 종류가 없는 탭(전체·즐겨찾기·휴지통)은 목록 검색 그대로다.
      const semanticEligible = Boolean(search.trim()) && (activeFilter === "broll" || activeFilter === "music" || activeFilter === "sfx");
      let nextAssets: LibraryAsset[];
      if (semanticEligible) {
        const result = await api.searchLibraryAssets(search.trim(), activeFilter as LibraryMediaType, undefined);
        if (currentEpoch !== epoch.current) return;
        nextAssets = result.matches;
        setSearchMode(result.semantic ? "semantic" : "word");
      } else {
        const result = await api.listLibraryAssets({ includeTrashed: activeFilter === "trash", q: search || undefined, limit: 500 });
        if (currentEpoch !== epoch.current) return;
        nextAssets = result.assets;
        setSearchMode(null);
      }
      setAssets(nextAssets);
      const requestedId = requestedAssetId.current;
      requestedAssetId.current = null;
      const requested = requestedId ? nextAssets.find((item) => item.library_asset_id === requestedId) : null;
      setSelected((previous) => requested ?? (previous ? nextAssets.find((item) => item.library_asset_id === previous.library_asset_id) ?? null : nextAssets[0] ?? null));
    } catch {
      if (currentEpoch === epoch.current) setError("라이브러리를 불러오지 못했어요.");
    } finally { if (currentEpoch === epoch.current) setLoading(false); }
  }, [activeFilter, search]);
  useEffect(() => { const timer = window.setTimeout(() => void load(), search ? 180 : 0); return () => window.clearTimeout(timer); }, [load, search]);

  const visible = useMemo(() => assets.filter((asset) => matchesFilter(asset, activeFilter)), [assets, activeFilter]);
  const counts = useMemo(() => ({
    all: assets.filter((item) => item.lifecycle !== "trashed").length,
    broll: assets.filter((item) => item.media_type === "broll" && item.lifecycle !== "trashed").length,
    music: assets.filter((item) => item.media_type === "music" && item.lifecycle !== "trashed").length,
    sfx: assets.filter((item) => item.media_type === "sfx" && item.lifecycle !== "trashed").length,
    favorites: assets.filter((item) => Boolean(item.user_metadata?.favorite)).length,
    trash: assets.filter((item) => item.lifecycle === "trashed").length,
  }), [assets]);

  async function ingest(files: File[]) {
    const groups = new Map<LibraryMediaType, File[]>();
    const retryKeys = new Map<File, string>();
    files.forEach((file, index) => retryKeys.set(file, `${fileDisplayName(file)}#${index}`));
    const rejected: LibraryIngestItem[] = [];
    files.forEach((file) => { const type = fileType(file); if (!type) { const retryKey = retryKeys.get(file)!; failedFiles.current.set(retryKey, file); rejected.push({ filename: file.name, display_filename: fileDisplayName(file), retry_key: retryKey, state: "needs_attention", error_code: "unsupported_media" }); } else groups.set(type, [...(groups.get(type) ?? []), file]); });
    setIngestItems(rejected);
    const results: LibraryIngestItem[] = [...rejected];
    await Promise.all([...groups.entries()].map(async ([type, grouped]) => {
      const idempotencyKey = `drop-${Date.now()}-${type}`;
      try {
        const response = await api.ingestLibraryAssets(grouped, type, idempotencyKey);
        results.push(...response.items.map((item, index) => {
          const file = grouped[index];
          const retryKey = file ? retryKeys.get(file)! : item.retry_key ?? item.filename ?? `${type}-${index}`;
          if (item.state === "needs_attention" && file) failedFiles.current.set(retryKey, file);
          return { ...item, display_filename: file ? fileDisplayName(file) : item.display_filename ?? item.filename, retry_key: retryKey };
        }));
      } catch {
        results.push(...grouped.map((file) => { const retryKey = retryKeys.get(file)!; failedFiles.current.set(retryKey, file); return { filename: file.name, display_filename: fileDisplayName(file), retry_key: retryKey, state: "needs_attention" as const, error_code: "network_error" }; }));
      }
    }));
    setIngestItems(results);
    await load();
  }

  async function retry(retryKey: string) {
    const file = failedFiles.current.get(retryKey);
    if (file) await ingest([file]);
  }

  function selectFilter(filter: LibraryFilter) { setActiveFilter(filter); if (filter === "trash") setSelected(null); }
  return <main className="vb-library-page" data-testid="library-workspace" data-layout="three-pane">{/* 2026-08-19: 자체 메뉴 줄을 뺐다. 이 화면이 대시보드 껍데기 안으로 들어가면서
    좌측 메뉴가 늘 함께 있고, 여기 것과 **같은 링크 네 개가 두 벌**이 됐다.
    owner가 "좌측 메뉴는 그대로 두라"고 한 뒤의 정리다. */}
<span data-testid="global-library-page" className="sr-only">내 라이브러리</span><LibrarySidebar activeFilter={activeFilter} onFilter={selectFilter} counts={counts} status={assets.some((item) => item.lifecycle === "needs_attention") ? "needs_attention" : "all"} /><section className="vb-library-main"><AssetIngestDropzone onFiles={(files) => void ingest(files)} /><IngestJobTable items={ingestItems} onRetry={(filename) => void retry(filename)} /><LibraryResults assets={visible} activeFilter={activeFilter} search={search} onSearch={setSearch} onFilter={selectFilter} selectedId={selected?.library_asset_id} onSelect={setSelected} loading={loading} error={error} searchMode={searchMode} /></section><LibraryPreviewPane asset={selected} onChanged={() => void load()} /></main>;
}
