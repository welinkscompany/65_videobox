/**
 * 화면 클립의 색감 — 화면에 보여 줄 목록.
 *
 * **이 목록은 백엔드의 `videobox_core_engine/filters.py`와 한 벌이어야 한다.**
 * 여기 없는 것을 고를 수 없고, 저기 없는 것을 보내면 422로 거절된다. 두 벌이
 * 어긋나는 것을 사람이 기억하는 것에 맡기지 않으려고
 * `tests/test_scene_filter_catalog_matches_the_screen.py`가 두 파일을 맞대어 본다
 * (전환 목록과 같은 방식).
 *
 * 만든 것만 보여 준다. 캡컷 필터 탭의 이름표를 흉내 내지 않는다 — 그건 캡컷이
 * 자기 서버에서 받아 두는 자원이고, 우리 렌더러는 그 이름으로 아무것도 못 그린다.
 */

export type SceneFilterChoice = Readonly<{
  value: string;
  label: string;
}>;

export const SCENE_FILTER_CHOICES: readonly SceneFilterChoice[] = [
  { value: "mono", label: "흑백으로" },
  { value: "vintage", label: "옛날 필름" },
  { value: "warm", label: "따뜻하게" },
  { value: "cool", label: "차갑게" },
  { value: "vivid", label: "진하게" },
  { value: "faded", label: "옅게" },
];

/** 안 고른 상태. 값이 없는 것과 "없음"을 고른 것을 화면에서 구별하지 않는다. */
export const SCENE_FILTER_NONE = "none";

// 이름표를 돌려주는 helper는 두지 않는다. 전환 쪽에 같은 모양의
// `sceneTransitionLabel`이 있는데 부르는 곳이 하나도 없다 -- 쓸 자리가 생기면
// 그때 만든다. 안 쓰는 것을 미리 두면 다음 사람이 "어디서 쓰나" 찾게 된다.
