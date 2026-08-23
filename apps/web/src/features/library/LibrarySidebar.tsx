import type { LibraryAssetLifecycle, LibraryMediaType } from "../../api";

export type LibraryFilter = LibraryMediaType | "all" | "favorites" | "trash";

// **분류 목록은 여기 하나뿐이다**(owner 결정 2026-08-23).
//
// `capcut-observed` 기록 §5: "탭을 누르면 **왼쪽에 분류 목록, 오른쪽에
// 격자**가 나온다" -- 캡컷은 왼쪽 목록 하나로 고르고, 격자 위에 같은 것을
// 다시 묻는 탭 줄을 두지 않는다. 캡컷 왼쪽 목록도 §5 오디오 탭처럼
// `가져오기 · 내 보관함 · 음악 · 사운드 효과`로 **종류와 보관 상태를 한 줄에
// 섞어** 둔다. 그래서 우리도 섞어서 한 줄이다.
//
// 2026-08-23에 한 번 반대로 정리했다가 되돌렸다 -- 그때는 여기서 종류 넷을
// 빼고 결과 영역 탭을 남겼는데, 그건 캡컷과 반대 방향이었고 `전체`가 두 군데
// 남아 둘 다 "선택됨"으로 보이는 상태가 됐다.
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
    <nav aria-label="자산 분류"><ul className="vb-library-filter-list">{filters.map((item) => (
      <li key={item.key}><button data-native-control="library-filter" type="button" className={activeFilter === item.key ? "is-active" : ""} aria-pressed={activeFilter === item.key} onClick={() => onFilter(item.key)}>{item.label}<span>{counts?.[item.key] ?? ""}</span></button></li>
    ))}</ul></nav>
    <div className="vb-library-sidebar__status" aria-label="분석 상태">
      <p>분석 상태</p>
      <span className={status === "needs_attention" ? "is-warning" : ""}>{status === "needs_attention" ? "확인 필요" : "전체 상태"}</span>
    </div>
  </aside>;
}
