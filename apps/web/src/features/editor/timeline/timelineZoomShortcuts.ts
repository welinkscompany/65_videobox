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
import { editorShortcutFor } from "../editorShortcuts";

export type TimelineZoomCommand = "in" | "out" | "fit";

type Chord = Readonly<{ key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }>;

export function timelineZoomShortcutFor(event: Chord, targetIsEditable: boolean): TimelineZoomCommand | null {
  if (!event || typeof event.key !== "string") return null;
  // 글을 쓰는 칸에서는 가로채지 않는다. 브라우저가 원래 하던 일까지 같이 막힌다.
  if (targetIsEditable) return null;
  const id = editorShortcutFor({ key: event.key, ctrlKey: event.ctrlKey, metaKey: event.metaKey, altKey: event.altKey, shiftKey: event.shiftKey, target: null, repeat: false, isComposing: false, defaultPrevented: false });
  if (id === "zoom-in") return "in";
  if (id === "zoom-out") return "out";
  if (id === "zoom-fit") return "fit";
  return null;
}
