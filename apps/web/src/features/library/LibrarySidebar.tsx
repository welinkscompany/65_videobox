import type { LibraryAssetLifecycle, LibraryMediaType } from "../../api";

export type LibraryFilter = LibraryMediaType | "all" | "favorites" | "trash";

const filters: Array<{ key: LibraryFilter; label: string }> = [
  { key: "all", label: "전체" },
  { key: "broll", label: "영상" },
  { key: "music", label: "음악" },
  { key: "sfx", label: "효과음" },
  { key: "image", label: "그림" },
  { key: "favorites", label: "즐겨찾기" },
  { key: "trash", label: "휴지통" },
];

export function LibrarySidebar({ activeFilter, onFilter, counts, status }: {
  activeFilter: LibraryFilter;
  onFilter: (filter: LibraryFilter) => void;
  counts?: Partial<Record<LibraryFilter, number>>;
  status?: LibraryAssetLifecycle | "all";
}) {
  return <aside className="vb-library-sidebar" data-testid="library-sidebar" aria-label="라이브러리 필터">
    <div className="vb-library-sidebar__heading"><p className="vb-eyebrow">내 라이브러리</p><h1>자산</h1></div>
    <nav aria-label="자산 종류"><ul className="vb-library-filter-list">{filters.map((item) => (
      <li key={item.key}><button data-native-control="library-filter" type="button" className={activeFilter === item.key ? "is-active" : ""} aria-pressed={activeFilter === item.key} onClick={() => onFilter(item.key)}>{item.label}<span>{counts?.[item.key] ?? ""}</span></button></li>
    ))}</ul></nav>
    <div className="vb-library-sidebar__status" aria-label="분석 상태">
      <p>분석 상태</p>
      <span className={status === "needs_attention" ? "is-warning" : ""}>{status === "needs_attention" ? "확인 필요" : "전체 상태"}</span>
    </div>
  </aside>;
}
