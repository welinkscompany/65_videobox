/** 타임라인을 늘리고 줄이는 단축키.
 *
 * 대표님 지시(2026-09-12): "이걸 단축키로 쉽게 늘리고 줄이고를 할수 있어야지".
 *
 * 캡컷을 벤치마킹한다(`CLAUDE.md` §2.1). 캡컷·프리미어·다빈치가 모두 쓰는
 * `Ctrl` + `=` / `-`이고, 전체 보기는 `Ctrl` + `0`이다(사진·그림 도구가 "원래
 * 크기로"에 쓰는 그 자리). 저장소에 캡컷 단축키를 실제로 받아 적어 둔 기록은
 * 없어서, 계획서가 이름한 그 관례를 따랐다.
 *
 * **부딪히는 키가 없다.** 편집기가 이미 쓰는 것은 `Ctrl+Z`·`Ctrl+Shift+Z`·
 * `Ctrl+Y`(되돌리기/다시), `Ctrl+B`(나누기), `Delete`·`Backspace`(빼기)뿐이고
 * (`workbench/cutShortcuts.ts`, `EditorWorkbench.tsx`), 글자가 겹치지 않는다.
 * 양쪽 방향을 시험이 지킨다(`timelineZoomShortcuts.test.ts`).
 *
 * **바퀴는 여기가 아니다.** 캡컷의 `Ctrl`+바퀴(늘리기·줄이기)와 `Shift`+바퀴(옆으로
 * 밀기)는 `timelineWheelGesture.ts`에 있다 -- 누른 글자가 아니라 굴린 거리를 보는
 * 다른 모양의 사건이고, React가 `wheel`을 passive로 달아서 다는 방식도 다르다.
 *
 * **키는 단추가 정한 것을 그대로 쓴다**(`cutShortcuts.ts`가 정한 규약). 그래서
 * 이 함수는 "무엇을 눌렀는가"만 답하고, "지금 그게 되는가"는 답하지 않는다 --
 * 그 판단은 화면(`TimelineDock`)이 단추와 키에 한 벌로 내려 준다.
 */
export type TimelineZoomCommand = "in" | "out" | "fit";

type Chord = Readonly<{ key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }>;

export function timelineZoomShortcutFor(event: Chord, targetIsEditable: boolean): TimelineZoomCommand | null {
  if (!event || typeof event.key !== "string") return null;
  // 글을 쓰는 칸에서는 가로채지 않는다. 브라우저가 원래 하던 일까지 같이 막힌다.
  if (targetIsEditable) return null;
  // Alt가 눌린 조합은 다른 뜻이다. 가로채지 않는다.
  if (event.altKey) return null;
  // 맥에는 Ctrl이 아니라 Cmd다. 하나만 받으면 나머지 절반이 못 쓴다 --
  // `cutShortcuts.ts`가 Delete/Backspace를 둘 다 받는 것과 같은 이유다.
  if (!(event.ctrlKey || event.metaKey)) return null;

  switch (event.key) {
    // 자판과 Shift에 따라 같은 자리가 `=`로도 `+`로도 온다(숫자판은 늘 `+`다).
    // 둘 다 안 받으면 대표님이 Shift를 같이 눌렀을 때 조용히 아무 일도 안 한다.
    case "=":
    case "+":
      return "in";
    case "-":
    case "_":
      return "out";
    case "0":
      return "fit";
    default:
      return null;
  }
}
