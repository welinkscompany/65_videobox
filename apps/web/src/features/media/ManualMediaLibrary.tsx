import { useEffect, useMemo, useState, type DragEvent } from "react";
import { api, type BrollAsset, type MediaLibraryAsset } from "../../api";
import type { DirectorWorkspaceState } from "../director/directorTypes";

type SelectedSegment = { segmentId: string; startSec: number; endSec: number } | null;

export function ManualMediaLibrary({
  projectId, assets, brollAssets, favoriteIds, localFavoriteIds, recentIds, unavailableMessage, directorState, selectedSegment, activeBrollAssetId, busy, onToggleFavorite, onToggleLocalFavorite, onApplyGlobal, onApplyBroll, onClearBroll,
}: {
  projectId: string;
  assets: MediaLibraryAsset[];
  brollAssets: BrollAsset[];
  favoriteIds: string[];
  localFavoriteIds: string[];
  recentIds: string[];
  unavailableMessage?: string | null;
  directorState?: DirectorWorkspaceState;
  selectedSegment: SelectedSegment;
  activeBrollAssetId?: string | null;
  busy: boolean;
  onToggleFavorite: (id: string) => void;
  onToggleLocalFavorite: (id: string) => void;
  onApplyGlobal: (asset: MediaLibraryAsset) => void;
  onApplyBroll: (asset: BrollAsset) => void;
  onClearBroll?: () => void;
}) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"all" | "favorites" | "recent">("all");
  const [preview, setPreview] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [brollView, setBrollView] = useState<"all" | "favorites" | "recent">("all");
  const [brollType, setBrollType] = useState("all");
  const [brollAspect, setBrollAspect] = useState("all");
  const [brollDuration, setBrollDuration] = useState("all");
  const [brollAnalyzed, setBrollAnalyzed] = useState("all");
  const [brollReview, setBrollReview] = useState("all");
  const [keyboardBrollAssetId, setKeyboardBrollAssetId] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.getDirectorPreferences(projectId).then((preferences) => {
      if (!cancelled) { setPinned(preferences.pin_asset ?? []); setExcluded(preferences.exclude_asset ?? []); }
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [projectId]);
  const togglePreference = (kind: "pin_asset" | "exclude_asset", assetId: string) => {
    const current = kind === "pin_asset" ? pinned : excluded;
    const next = current.includes(assetId) ? current.filter((item) => item !== assetId) : [...current, assetId];
    void api.updateDirectorPreferences(projectId, { [kind]: next }).then((saved) => {
      setPinned(saved.pin_asset ?? []); setExcluded(saved.exclude_asset ?? []);
    });
  };
  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    return assets.filter((asset) => {
      if (view === "favorites" && !favoriteIds.includes(asset.library_asset_id)) return false;
      if (view === "recent" && !recentIds.includes(asset.library_asset_id)) return false;
      return !term || [asset.asset_id, asset.media_type, asset.media_type === "music" ? "bgm" : "sfx", ...asset.tags, String(asset.duration_seconds)].join(" ").toLowerCase().includes(term);
    });
  }, [assets, favoriteIds, query, recentIds, view]);
  const visibleBroll = useMemo(() => brollAssets.filter((asset) => {
    const term = query.trim().toLowerCase();
    const metadata = asset.metadata ?? {};
    const duration = Number(metadata.duration_seconds ?? 0);
    const matchesDuration = brollDuration === "all" || (brollDuration === "short" ? duration <= 10 : duration > 10);
    const matchesReview = brollReview === "all" || (brollReview === "needed" ? Boolean(metadata.review_required) : !metadata.review_required);
    return (brollView !== "favorites" || localFavoriteIds.includes(asset.asset_id))
      && (brollView !== "recent" || recentIds.includes(asset.asset_id))
      && (brollType === "all" || asset.asset_type === brollType)
      && (brollAspect === "all" || String(metadata.aspect_ratio ?? "unknown") === brollAspect)
      && matchesDuration
      && (brollAnalyzed === "all" || String(metadata.analysis_status ?? "pending") === brollAnalyzed)
      && matchesReview
      && (!term || [asset.asset_id, asset.asset_type, String(metadata.title ?? ""), String(metadata.duration_seconds ?? ""), String(metadata.aspect_ratio ?? ""), String(metadata.analysis_status ?? ""), JSON.stringify(metadata.tags ?? [])].join(" ").toLowerCase().includes(term));
  }).sort((left, right) => Number(pinned.includes(right.asset_id)) - Number(pinned.includes(left.asset_id))), [brollAnalyzed, brollAspect, brollAssets, brollDuration, brollReview, brollType, brollView, localFavoriteIds, pinned, query, recentIds]);
  const canPlace = Boolean(selectedSegment) && !busy;
  const keyboardBrollAsset = brollAssets.find((asset) => asset.asset_id === keyboardBrollAssetId);
  const canKeyboardPlace = canPlace && Boolean(keyboardBrollAsset) && !excluded.includes(keyboardBrollAsset?.asset_id ?? "");
  const placeDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    if (!canPlace) return;
    const globalId = event.dataTransfer.getData("application/x-videobox-library-asset");
    const localId = event.dataTransfer.getData("application/x-videobox-local-broll");
    const global = assets.find((asset) => asset.library_asset_id === globalId);
    const local = brollAssets.find((asset) => asset.asset_id === localId);
    if (global && global.available && global.verified) onApplyGlobal(global);
    if (local && !excluded.includes(local.asset_id)) onApplyBroll(local);
  };
  const placeKeyboardBroll = () => {
    if (canKeyboardPlace && keyboardBrollAsset) onApplyBroll(keyboardBrollAsset);
  };
  return <section className="media-library" aria-label="수동 미디어 라이브러리">
    <h3>수동 미디어 라이브러리</h3>
    {directorState === "blocked" || directorState === "error" ? <p role="status">Director {directorState === "blocked" ? "차단" : "오류"} 상태입니다. 수동 라이브러리는 계속 사용할 수 있습니다.</p> : null}
    <p className="meta-copy">설치된 검증 미디어 {assets.length}개</p>
    {assets.length ? <p className="meta-copy">Starter pack 설치됨</p> : null}
    <p className="meta-copy" aria-live="polite">{selectedSegment ? `대상 구간 ${selectedSegment.segmentId} · ${selectedSegment.startSec.toFixed(2)}–${selectedSegment.endSec.toFixed(2)}초` : "배치할 구간 또는 범위를 먼저 선택하세요."}</p>
    <div aria-disabled={!canKeyboardPlace} aria-label="선택 구간 배치 대상" className="media-library-drop-target" onDragOver={(event) => event.preventDefault()} onDrop={placeDrop} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); placeKeyboardBroll(); } }} role="button" tabIndex={0}>{selectedSegment ? keyboardBrollAsset ? `선택한 B롤 ${keyboardBrollAsset.asset_id}을(를) 여기에 적용하려면 Enter 또는 Space를 누르세요.` : "선택 구간에 여기로 끌어 놓거나 B롤 카드를 먼저 선택하세요." : "배치하려면 구간 또는 범위를 선택하세요."}</div>
    <div className="action-row" aria-label="수동 미디어 필터">
      <label className="field"><span>검색</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="BGM, SFX, 태그 또는 길이" /></label>
      <button className="action-button subtle" onClick={() => setView("all")} type="button">전체</button>
      <button className="action-button subtle" onClick={() => setView("favorites")} type="button">즐겨찾기</button>
      <button className="action-button subtle" onClick={() => setView("recent")} type="button">최근</button>
    </div>
    <p className="meta-copy">미리보기는 편집 세션을 변경하지 않습니다. 배치는 아래 ‘적용’으로만 수행합니다.</p>
    {preview ? <p className="meta-copy" aria-live="polite">미리보기 선택됨</p> : null}
    {unavailableMessage ? <p role="status">{unavailableMessage}</p> : null}
    {(["music", "sfx"] as const).map((mediaType) => <section className="media-library-group" key={mediaType}>
      <h4>{mediaType === "music" ? "BGM 라이브러리" : "SFX 라이브러리"}</h4>
      {visible.filter((asset) => asset.media_type === mediaType).map((asset) => <article className="media-library-card" key={asset.library_asset_id} draggable onDragStart={(event) => event.dataTransfer.setData("application/x-videobox-library-asset", asset.library_asset_id)}>
        <strong>{asset.asset_id}</strong><p className="meta-copy">{asset.source} · {asset.creator} · {asset.version} · {asset.duration_seconds}초</p>{asset.attribution_required ? <p className="meta-copy">표기 필요: {asset.attribution_text}</p> : null}<p className="meta-copy">{asset.tags.join(", ")}</p>
        <div className="action-row"><button className="action-button subtle" disabled={!asset.available || !asset.verified} onClick={() => setPreview(asset.library_asset_id)} type="button">{mediaType === "music" ? "BGM" : "SFX"} 미리보기</button><button className="action-button subtle" onClick={() => onToggleFavorite(asset.library_asset_id)} type="button">{mediaType === "music" ? "BGM" : "SFX"} {favoriteIds.includes(asset.library_asset_id) ? "즐겨찾기 해제" : "즐겨찾기"}</button><button className="action-button" disabled={!canPlace || !asset.available || !asset.verified} onClick={() => onApplyGlobal(asset)} type="button">{mediaType === "music" ? "BGM" : "SFX"} 적용</button></div>
        {preview === asset.library_asset_id ? <audio controls data-testid="media-library-preview" src={api.mediaLibraryPreviewUrl(asset.library_asset_id)} /> : null}
      </article>)}</section>)}
    <section className="media-library-group"><h4>B롤 (프로젝트 로컬)</h4>
      {activeBrollAssetId && onClearBroll ? <div className="action-row"><p className="meta-copy">현재 선택 구간 B롤: {activeBrollAssetId}</p><button className="action-button subtle" disabled={!canPlace} onClick={onClearBroll} type="button">선택 구간 B롤 해제</button></div> : null}
      <div className="action-row" aria-label="B롤 필터">
        <button className="action-button subtle" onClick={() => setBrollView("all")} type="button">B롤 필터: 전체</button><button className="action-button subtle" onClick={() => setBrollView("favorites")} type="button">B롤 필터: 즐겨찾기</button><button className="action-button subtle" onClick={() => setBrollView("recent")} type="button">B롤 필터: 최근</button>
        <label className="field"><span>type</span><select aria-label="B롤 type" value={brollType} onChange={(event) => setBrollType(event.target.value)}><option value="all">all</option>{[...new Set(brollAssets.map((asset) => asset.asset_type))].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="field"><span>aspect</span><select aria-label="B롤 aspect" value={brollAspect} onChange={(event) => setBrollAspect(event.target.value)}><option value="all">all</option>{[...new Set(brollAssets.map((asset) => String(asset.metadata?.aspect_ratio ?? "unknown")))].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="field"><span>duration</span><select aria-label="B롤 duration" value={brollDuration} onChange={(event) => setBrollDuration(event.target.value)}><option value="all">all</option><option value="short">≤10s</option><option value="long">&gt;10s</option></select></label>
        <label className="field"><span>analyzed</span><select aria-label="B롤 analyzed" value={brollAnalyzed} onChange={(event) => setBrollAnalyzed(event.target.value)}><option value="all">all</option>{[...new Set(brollAssets.map((asset) => String(asset.metadata?.analysis_status ?? "pending")))].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <button className="action-button subtle" onClick={() => setBrollReview("needed")} type="button">B롤 검토 필요</button><button className="action-button subtle" onClick={() => setBrollReview("clear")} type="button">B롤 검토 완료</button>
      </div>
      {visibleBroll.map((asset) => { const metadata = asset.metadata ?? {}; return <article aria-label={`B롤 자산 ${asset.asset_id}`} className="media-library-card" key={asset.asset_id} draggable onDragStart={(event) => event.dataTransfer.setData("application/x-videobox-local-broll", asset.asset_id)} onFocus={() => setKeyboardBrollAssetId(asset.asset_id)} tabIndex={0}>
        <strong>{String(metadata.title ?? asset.asset_id)}</strong><span className="meta-copy">{asset.asset_id}</span><p className="meta-copy">type: {asset.asset_type} · aspect: {String(metadata.aspect_ratio ?? "unknown")} · duration: {String(metadata.duration_seconds ?? "unknown")} · analyzed: {String(metadata.analysis_status ?? "pending")} · {metadata.review_required ? "review-needed" : "review-clear"}{pinned.includes(asset.asset_id) ? " · pinned" : ""}{excluded.includes(asset.asset_id) ? " · excluded" : ""}</p>
        <div className="action-row"><button className="action-button subtle" onClick={() => setPreview(`broll:${asset.asset_id}`)} type="button">B롤 미리보기</button><button className="action-button subtle" onClick={() => onToggleLocalFavorite(asset.asset_id)} type="button">{localFavoriteIds.includes(asset.asset_id) ? "B롤 즐겨찾기 해제" : "B롤 즐겨찾기"}</button><button className="action-button subtle" onClick={() => togglePreference("pin_asset", asset.asset_id)} type="button">{pinned.includes(asset.asset_id) ? "고정 해제" : "고정"}</button><button className="action-button subtle" onClick={() => togglePreference("exclude_asset", asset.asset_id)} type="button">{excluded.includes(asset.asset_id) ? "제외 해제" : "제외"}</button><button className="action-button" disabled={!canPlace || excluded.includes(asset.asset_id)} onClick={() => onApplyBroll(asset)} type="button">선택 구간에 B롤 적용</button></div>
        {preview === `broll:${asset.asset_id}` ? <video controls data-testid="manual-broll-preview" src={api.assetContentUrl(projectId, asset.asset_id)} /> : null}
      </article>; })}
    </section>
  </section>;
}
