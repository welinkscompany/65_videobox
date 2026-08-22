import type { LibraryAssetLifecycle, LibraryMediaType } from "../../api";

export type LibraryFilter = LibraryMediaType | "all" | "favorites" | "trash";

// 영상·음악·효과음·그림 자산 종류는 `LibraryResults`의 탭 줄이 이미 고른다
// (2026-08-23, `capcut-observed` 기록 §5: "탭을 누르면 왼쪽에 분류 목록,
// 오른쪽에 격자" -- 한 축에 목록이 하나다. 여기 있던 같은 다섯 항목은 결과
// 영역의 탭과 똑같은 선택을 두 번 보여 주고 있었다). 여기는 종류를 가리지
// 않는 상태(전체·즐겨찾기·휴지통)만 남긴다.
const filters: Array<{ key: LibraryFilter; label: string }> = [
  { key: "all", label: "전체" },
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
    <nav aria-label="보관 상태"><ul className="vb-library-filter-list">{filters.map((item) => (
      <li key={item.key}><button data-native-control="library-filter" type="button" className={activeFilter === item.key ? "is-active" : ""} aria-pressed={activeFilter === item.key} onClick={() => onFilter(item.key)}>{item.label}<span>{counts?.[item.key] ?? ""}</span></button></li>
    ))}</ul></nav>
    <div className="vb-library-sidebar__status" aria-label="분석 상태">
      <p>분석 상태</p>
      <span className={status === "needs_attention" ? "is-warning" : ""}>{status === "needs_attention" ? "확인 필요" : "전체 상태"}</span>
    </div>
  </aside>;
}
