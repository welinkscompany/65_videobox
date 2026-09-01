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
  { value: "bright", label: "뽀샤시하게" },
  { value: "sepia", label: "세피아" },
  { value: "cinematic", label: "영화처럼" },
];

/** 안 고른 상태. 값이 없는 것과 "없음"을 고른 것을 화면에서 구별하지 않는다. */
export const SCENE_FILTER_NONE = "none";

/** 색감 코드를 화면 문구로. 목록에 없으면 `null`.
 *
 *  예전에는 여기 "쓸 자리가 생기면 그때 만든다"고 적어 두고 helper를 두지
 *  않았다. 2026-09-01에 자리가 생겼다 -- 유진이 말로 색감을 바꾸면 완료
 *  목록에 무엇을 했는지 적어야 하는데, `vintage`는 창작자에게 아무 뜻이
 *  없다(§10.13: 내부 코드를 화면에 쓰지 않는다). */
export function sceneFilterLabel(value: string): string | null {
  return SCENE_FILTER_CHOICES.find((choice) => choice.value === value)?.label ?? null;
}
