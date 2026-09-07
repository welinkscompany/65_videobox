/**
 * 사진 한 장짜리 장면이 **어떻게** 움직일지 — 화면에 보여 줄 목록.
 *
 * **이 목록은 백엔드의 `media_controls.PHOTO_MOTION_LABELS`와 한 벌이어야 한다.**
 * 여기 없는 것을 고를 수 없고, 저기 없는 것을 보내면 422로 거절된다. 두 벌이
 * 어긋나는 것을 사람이 기억하는 것에 맡기지 않으려고
 * `tests/test_photo_motion_catalog_matches_the_screen.py`가 두 파일을 맞대어 본다
 * (색감·전환 목록과 같은 방식, `sceneFilters.ts`).
 *
 * `zoom_in` 같은 코드는 화면에 쓰지 않는다(§10.13) — 이름표만 보인다.
 */

export type PhotoMotionChoice = Readonly<{
  value: string;
  label: string;
}>;

export const PHOTO_MOTION_CHOICES: readonly PhotoMotionChoice[] = [
  { value: "zoom_in", label: "천천히 다가가기" },
  { value: "zoom_out", label: "천천히 멀어지기" },
  { value: "pan_left", label: "왼쪽으로 흐르기" },
  { value: "pan_right", label: "오른쪽으로 흐르기" },
  { value: "pan_up", label: "위로 흐르기" },
  { value: "pan_down", label: "아래로 흐르기" },
  { value: "still", label: "움직이지 않기" },
];

/** 안 고른 상태. **`움직이지 않기`와 다르다** — 안 고르면 장면마다 알아서
 *  움직이고, `움직이지 않기`는 멈춘다. 색감의 `원본 그대로`와 달리 여기서는
 *  둘을 화면에서도 갈라 보여 준다(하나로 뭉치면 끌 방법이 없어진다). */
export const PHOTO_MOTION_NONE = "auto";

/** 움직임 코드를 화면 문구로. 목록에 없으면 `null`.
 *
 *  유진이 말로 바꿔 주면 완료 목록에 무엇을 했는지 적어야 하는데,
 *  `pan_left`는 창작자에게 아무 뜻이 없다(§10.13). */
export function photoMotionLabel(value: string): string | null {
  return PHOTO_MOTION_CHOICES.find((choice) => choice.value === value)?.label ?? null;
}
