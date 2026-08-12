import { useId } from "react";
import type { LibraryAsset } from "../../api";
import type { LibraryFilter } from "./LibrarySidebar";
import { AudioAssetRows } from "./AudioAssetRows";
import { VideoAssetGrid } from "./VideoAssetGrid";

const tabs: Array<{ key: LibraryFilter; label: string }> = [{ key: "all", label: "전체" }, { key: "broll", label: "영상" }, { key: "music", label: "음악" }, { key: "sfx", label: "효과음" }];

export function LibraryResults({ assets, activeFilter, search, onSearch, onFilter, selectedId, onSelect, loading, error }: { assets: LibraryAsset[]; activeFilter: LibraryFilter; search: string; onSearch: (value: string) => void; onFilter: (filter: LibraryFilter) => void; selectedId?: string | null; onSelect: (asset: LibraryAsset) => void; loading?: boolean; error?: string | null }) {
  const searchId = useId();
  const visible = assets.slice(0, 24);
  const videos = visible.filter((item) => item.media_type === "broll");
  const audio = visible.filter((item) => item.media_type !== "broll");
  const showAudio = activeFilter === "music" || activeFilter === "sfx";
  const trashVideos = visible.filter((item) => item.media_type === "broll");
  const trashAudio = visible.filter((item) => item.media_type !== "broll");
  return <section className="vb-library-results" data-testid="library-results" aria-label="자산 목록"><header className="vb-library-results__header"><div><p className="vb-eyebrow">라이브러리에서 찾기</p><h2>{activeFilter === "broll" ? "영상" : activeFilter === "music" ? "음악" : activeFilter === "sfx" ? "효과음" : activeFilter === "trash" ? "휴지통" : "전체 자산"}</h2></div><label htmlFor={searchId} className="vb-library-search"><span>검색</span><input id={searchId} value={search} placeholder="파일명·장면·분위기" onChange={(event) => onSearch(event.target.value)} /></label></header><div className="vb-library-tabs" role="tablist" aria-label="자산 종류 탭">{tabs.map((tab) => <button key={tab.key} type="button" role="tab" aria-selected={activeFilter === tab.key} tabIndex={activeFilter === tab.key ? 0 : -1} onClick={() => onFilter(tab.key)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onFilter(tab.key); } }}>{tab.label}</button>)}</div><div className="vb-library-results-scroll" data-testid="library-results-scroll" data-bounded="true">{loading ? <p role="status" className="vb-library-state">자산을 불러오는 중</p> : error ? <p role="alert" className="vb-library-state">{error}</p> : visible.length === 0 ? <p className="vb-library-state">아직 등록한 자산이 없어요.</p> : activeFilter === "trash" ? <><VideoAssetGrid assets={trashVideos} selectedId={selectedId} onSelect={onSelect} />{trashAudio.length ? <AudioAssetRows assets={trashAudio} selectedId={selectedId} onSelect={onSelect} /> : null}</> : activeFilter === "all" ? <><VideoAssetGrid assets={videos} selectedId={selectedId} onSelect={onSelect} />{audio.length ? <AudioAssetRows assets={audio} selectedId={selectedId} onSelect={onSelect} /> : null}</> : showAudio ? <AudioAssetRows assets={visible.filter((item) => item.media_type === activeFilter)} selectedId={selectedId} onSelect={onSelect} /> : <VideoAssetGrid assets={activeFilter === "broll" ? videos : visible} selectedId={selectedId} onSelect={onSelect} />}</div></section>;
}
