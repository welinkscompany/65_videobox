import { useId } from "react";
import type { LibraryAsset } from "../../api";
import type { LibraryFilter } from "./LibrarySidebar";
import { AudioAssetRows } from "./AudioAssetRows";
import { VideoAssetGrid } from "./VideoAssetGrid";

/** 썸네일로 보는 것과 들어 보는 것. 그림을 소리 쪽에 넣으면 빈 재생기가 뜬다. */
const isSound = (mediaType: string) => mediaType === "music" || mediaType === "sfx";

export function LibraryResults({ assets, activeFilter, search, onSearch, selectedId, onSelect, loading, error, searchMode = null }: { assets: LibraryAsset[]; activeFilter: LibraryFilter; search: string; onSearch: (value: string) => void; selectedId?: string | null; onSelect: (asset: LibraryAsset) => void; loading?: boolean; error?: string | null; searchMode?: "semantic" | "word" | null }) {
  const searchId = useId();
  const visible = assets.slice(0, 24);
  const seen = visible.filter((item) => !isSound(item.media_type));
  const audio = visible.filter((item) => isSound(item.media_type));
  const showAudio = activeFilter === "music" || activeFilter === "sfx";
  const showGrid = activeFilter === "broll" || activeFilter === "image";
  return <section className="vb-library-results" data-testid="library-results" aria-label="미디어 목록"><header className="vb-library-results__header"><div><p className="vb-eyebrow">미디어</p><h2>{activeFilter === "broll" ? "영상" : activeFilter === "music" ? "음악" : activeFilter === "sfx" ? "효과음" : activeFilter === "image" ? "그림" : activeFilter === "trash" ? "휴지통" : "전체 미디어"}</h2></div><label htmlFor={searchId} className="vb-library-search"><span>검색</span><input data-native-control="library-search" id={searchId} value={search} placeholder="파일명·장면·분위기" onChange={(event) => onSearch(event.target.value)} /></label>{/* 어느 방식으로 찾았는지 숨기지 않는다 -- 의미검색이 조용히 단어 매칭으로
      떨어지면 추천이 갑자기 나빠진 이유를 owner가 알 수 없다. label 밖에 둔다:
      안에 넣으면 검색칸의 accessible name까지 이 문구가 붙어 버린다. */}
      {searchMode ? <span className="vb-library-search-mode" role="status" aria-label="찾은 방식">{searchMode === "semantic" ? "뜻으로 찾음" : "단어로만 찾음"}</span> : null}</header>{/* 종류를 고르는 탭 줄이 여기 있었다. 왼쪽 `LibrarySidebar`가 같은 것을
      물어 `전체`가 두 군데에서 동시에 "선택됨"으로 보였다 -- 캡컷은 왼쪽 목록
      하나로만 고른다(`capcut-observed` 기록 §5). owner 결정 2026-08-23으로
      왼쪽 하나에 합쳤다. */}<div className="vb-library-results-scroll" data-testid="library-results-scroll" data-bounded="true">{loading ? <p role="status" className="vb-library-state">미디어를 불러오는 중</p> : error ? <p role="alert" className="vb-library-state">{error}</p> : visible.length === 0 ? <p className="vb-library-state">아직 등록한 미디어가 없어요.</p> : activeFilter === "trash" || activeFilter === "all" ? <><VideoAssetGrid assets={seen} selectedId={selectedId} onSelect={onSelect} />{audio.length ? <AudioAssetRows assets={audio} selectedId={selectedId} onSelect={onSelect} /> : null}</> : showAudio ? <AudioAssetRows assets={visible.filter((item) => item.media_type === activeFilter)} selectedId={selectedId} onSelect={onSelect} /> : <VideoAssetGrid assets={showGrid ? visible.filter((item) => item.media_type === activeFilter) : visible} selectedId={selectedId} onSelect={onSelect} />}</div></section>;
}
