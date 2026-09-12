/**
 * 원본을 출력 화면에 **어떻게 앉힐까** — 화면에 보여 줄 목록.
 *
 * **이 목록은 백엔드의 `media_controls.BROLL_FIT_LABELS`와 한 벌이어야 한다.**
 * 여기 없는 것을 고를 수 없고, 저기 없는 것을 보내면 422로 거절된다. 두 벌이
 * 어긋나는 것을 사람 기억에 맡기지 않으려고
 * `tests/test_vertical_short_keeps_the_sides.py`가 두 파일을 맞대어 본다
 * (사진 움직임·색감 목록과 같은 방식).
 *
 * `crop`·`blur` 같은 코드는 화면에 쓰지 않는다(§10.13) — 이름표만 보인다.
 *
 * `hint`가 있는 이유: 셋의 차이는 **무엇을 잃는가**다. 이름만 보면 어느 것이
 * 좌우를 자르는지 알 수 없는데, 2026-09-12에 대표님이 실제로 그 자리에서
 * 잘린 화면을 보게 됐다 — "배경 좌우가 짤려서 글자가 양쪽 사이드가 안보여."
 */

export type FrameFitChoice = Readonly<{
  value: string;
  label: string;
  hint: string;
}>;

export const FRAME_FIT_CHOICES: readonly FrameFitChoice[] = [
  { value: "fit", label: "화면 안에 맞추기", hint: "위아래에 검은 띠가 생겨요" },
  { value: "crop", label: "꽉 채우기", hint: "좌우가 잘려요" },
  { value: "blur", label: "전체 담기", hint: "다 보이고 빈 자리는 흐린 배경" },
];

/** 화면 맞춤 값을 화면 문구로. 목록에 없으면 `null`.
 *
 *  유진이 말로 바꿔 주면 완료 목록에 무엇을 했는지 적어야 하는데,
 *  `blur`는 창작자에게 아무 뜻이 없다(§10.13). */
export function frameFitLabel(value: string): string | null {
  return FRAME_FIT_CHOICES.find((choice) => choice.value === value)?.label ?? null;
}
