/**
 * 장면을 넘기는 방법 — 화면에 보여 줄 목록.
 *
 * **이 목록은 백엔드의 `videobox_core_engine/transitions.py`와 한 벌이어야 한다.**
 * 여기 없는 것을 고를 수 없고, 저기 없는 것을 보내면 422로 거절된다. 두 벌이
 * 어긋나는 것을 사람이 기억하는 것에 맡기지 않으려고
 * `tests/test_scene_transition_catalog_matches_the_screen.py`가 두 파일을 맞대어 본다.
 *
 * 만든 것만 보여 준다. 캡컷의 1,137개를 흉내 내지 않는다 — 없는 기능의 자리를
 * 만들어 두면 배치가 거짓말을 한다.
 */

export type SceneTransitionChoice = Readonly<{
  value: string;
  label: string;
}>;

export const SCENE_TRANSITION_CHOICES: readonly SceneTransitionChoice[] = [
  { value: "fade", label: "서서히 겹치기" },
  { value: "fadeblack", label: "검게 저물기" },
  { value: "dissolve", label: "흩어지며 넘기기" },
  { value: "wipeleft", label: "왼쪽으로 쓸어내기" },
  { value: "slideup", label: "위로 밀어올리기" },
  { value: "circleopen", label: "원으로 열기" },
];

/** 안 고른 상태. 값이 없는 것과 "없음"을 고른 것을 화면에서 구별하지 않는다. */
export const SCENE_TRANSITION_NONE = "none";

export const DEFAULT_SCENE_TRANSITION_DURATION_SEC = 0.5;

export function sceneTransitionLabel(value: string | null | undefined): string {
  if (!value || value === SCENE_TRANSITION_NONE) return "바로 넘기기";
  return SCENE_TRANSITION_CHOICES.find((choice) => choice.value === value)?.label ?? "바로 넘기기";
}
