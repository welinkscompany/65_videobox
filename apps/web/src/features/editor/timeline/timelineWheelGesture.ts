/** 바퀴로 타임라인을 늘리고 줄이고 옆으로 민다.
 *
 * 대표님 지시(2026-09-12): "타임라인 늘리는걸 캡컷과 똑같이 단축키도 똑같은
 * 방밥으로 만들어줘. 유진이한테 말하는거 외에도 내가 직접 조작할수 있게 해야지".
 *
 * 캡컷을 벤치마킹한다(`CLAUDE.md` §2.1). 캡컷은 `Ctrl`(맥은 `Cmd`) + 바퀴로
 * 늘리고 줄이며, `Shift` + 바퀴로 옆으로 민다. 키 조합(`Ctrl`+`=`/`-`/`0`)은
 * 이미 있었고(`timelineZoomShortcuts.ts`) 바퀴만 빠져 있었다.
 *
 * **이 함수는 "무엇을 굴렸는가"만 답한다.** "지금 그게 되는가"는 답하지 않는다 --
 * 그 판단은 화면(`TimelineDock`)의 `zoomControls` 한 표가 단추·키·바퀴에 한 벌로
 * 내려 준다(`workbench/cutShortcuts.ts`가 정한 규약: "키는 툴바가 정한 것을 그대로
 * 쓴다. 무엇을 할 수 있는지 다시 계산하지 않는다").
 */
export type TimelineWheelGesture =
  | Readonly<{ kind: "zoom"; command: "in" | "out" }>
  /** 옆으로 밀 거리(px). 초로 바꾸는 것은 배율을 아는 화면 쪽 일이다. */
  | Readonly<{ kind: "scroll"; deltaPx: number }>;

type WheelChord = Readonly<{
  deltaX: number;
  deltaY: number;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
}>;

export function timelineWheelGestureFor(event: WheelChord, targetIsEditable: boolean): TimelineWheelGesture | null {
  if (!event) return null;
  // 글을 쓰는 칸 위에서는 가로채지 않는다. 두 형제 모듈과 같은 규칙이다.
  if (targetIsEditable) return null;
  // Alt가 눌린 조합은 다른 뜻이다. 가로채지 않는다.
  if (event.altKey) return null;

  const deltaY = Number.isFinite(event.deltaY) ? event.deltaY : 0;
  const deltaX = Number.isFinite(event.deltaX) ? event.deltaX : 0;

  // **늘리기·줄이기가 먼저다.** `Ctrl`+`Shift`+바퀴에서도 늘리기가 이긴다 --
  // 브라우저가 `Ctrl`+바퀴를 화면 확대로 잡는 것과 같은 순서다.
  // 맥에는 Ctrl이 아니라 Cmd다(`timelineZoomShortcuts.ts`와 같은 이유).
  if (event.ctrlKey || event.metaKey) {
    // 트랙패드 오므리기(pinch)도 브라우저가 `ctrlKey`를 켠 세로 바퀴로 보낸다 --
    // 그래서 세로 값을 먼저 보고, 없으면 가로 값을 본다. 둘 다 0이면 아무 일도
    // 없다(Ctrl만 눌러도 wheel이 오는 경우가 있다).
    const delta = deltaY !== 0 ? deltaY : deltaX;
    if (delta === 0) return null;
    // 바퀴를 위로(음수) 굴리면 늘어난다. 지도·그림 도구가 다 그렇다.
    return { kind: "zoom", command: delta < 0 ? "in" : "out" };
  }

  if (event.shiftKey) {
    // Shift는 **세로 바퀴를 가로 이동으로 바꾼다.** 그게 Shift+바퀴의 뜻이다.
    // 트랙패드가 가로 값만 보낼 때도 있어서 그때는 그 값을 쓴다.
    const delta = deltaY !== 0 ? deltaY : deltaX;
    if (delta === 0) return null;
    return { kind: "scroll", deltaPx: delta };
  }

  // **맨 바퀴는 예전 그대로다.** 가로 값(트랙패드 두 손가락)만 타임라인을 옆으로
  // 밀고, 세로 값은 가로채지 않는다 -- 타임라인 칸은 `overflow:auto`라 위아래로
  // 스크롤되고(`editor-workbench.css`), 그걸 막으면 아래쪽 트랙을 볼 수 없다.
  if (deltaX !== 0) return { kind: "scroll", deltaPx: deltaX };
  return null;
}
