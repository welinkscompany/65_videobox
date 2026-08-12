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
  const failedFiles = useRef(new Map<string, File>());
  const epoch = useRef(0);

  const load = useCallback(async () => {
    const currentEpoch = ++epoch.current;
    setLoading(true); setError(null);
    try {
      const result = await api.listLibraryAssets({ includeTrashed: activeFilter === "trash", q: search || undefined, limit: 500 });
      if (currentEpoch !== epoch.current) return;
      setAssets(result.assets);
      setSelected((previous) => previous ? result.assets.find((item) => item.library_asset_id === previous.library_asset_id) ?? null : result.assets[0] ?? null);
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
    const rejected: LibraryIngestItem[] = [];
    files.forEach((file) => { const type = fileType(file); if (!type) rejected.push({ filename: file.name, state: "needs_attention", error_code: "unsupported_media" }); else { failedFiles.current.set(file.name, file); groups.set(type, [...(groups.get(type) ?? []), file]); } });
    setIngestItems(rejected);
    const results: LibraryIngestItem[] = [...rejected];
    await Promise.all([...groups.entries()].map(async ([type, grouped]) => {
      try { const response = await api.ingestLibraryAssets(grouped, type, `drop-${Date.now()}-${type}`); results.push(...response.items); }
      catch { results.push(...grouped.map((file) => ({ filename: file.name, state: "needs_attention" as const, error_code: "network_error" }))); }
    }));
    setIngestItems(results);
    await load();
  }

  async function retry(filename: string) {
    const file = failedFiles.current.get(filename);
    if (file) await ingest([file]);
  }

  function selectFilter(filter: LibraryFilter) { setActiveFilter(filter); if (filter === "trash") setSelected(null); }
  return <main className="vb-library-page" data-testid="library-workspace" data-layout="three-pane"><span data-testid="global-library-page" className="sr-only">내 라이브러리</span><nav className="vb-library-global-nav" aria-label="전체 메뉴"><a href="/projects">프로젝트</a><a href="/library" aria-current="page">내 라이브러리</a><a href="/footage">촬영본 정리</a><a href="/settings/general">설정</a></nav><LibrarySidebar activeFilter={activeFilter} onFilter={selectFilter} counts={counts} status={assets.some((item) => item.lifecycle === "needs_attention") ? "needs_attention" : "all"} /><section className="vb-library-main"><AssetIngestDropzone onFiles={(files) => void ingest(files)} /><IngestJobTable items={ingestItems} onRetry={(filename) => void retry(filename)} /><LibraryResults assets={visible} activeFilter={activeFilter} search={search} onSearch={setSearch} onFilter={selectFilter} selectedId={selected?.library_asset_id} onSelect={setSelected} loading={loading} error={error} /></section><LibraryPreviewPane asset={selected} onChanged={() => void load()} /></main>;
}
