import type { TimelineZoomCommand } from "./timelineZoomShortcuts";

/** 유진 채팅으로 타임라인을 늘리고 줄인다 (대표님 상시 지시 2026-09-11:
 *  "화면으로 되는 일은 전부 유진에게 말해서도 되어야 한다").
 *
 *  **유진의 두 대화 경로(직접 편집 A, 창작 제안 B) 어느 쪽도 타지 않는다** --
 *  두 경로 다 세션 리비전을 다루려고 만들어졌다. A는 적용마다 되돌리기 기록을
 *  쌓고(`yujin_editing_proposals.py`), B는 사람이 눌러야 적용되는 후보만
 *  만든다(`yujin_creator_proposals.py`). 확대·축소는 편집본을 한 글자도 안
 *  바꾸는 **보는 방식**이라 되돌릴 것도, 사람이 검토할 것도 없다 -- A에
 *  넣으면 아무것도 안 바꾼 일에 되돌리기 기계가 헛돌고, B에 넣으면 눌러야만
 *  되는 후보가 되어 "말하면 바로 된다"가 깨진다
 *  (`docs/surveys/2026-09-11-yujin-command-gap.ko.md` §0, task-3-brief).
 *
 *  그래서 이 함수는 **결정적**이다. 모델을 거치지 않고 브라우저에서 바로
 *  판단한다 -- `EditorWorkbenchRoute.sendDirectorMessage`가 이 함수로 먼저
 *  확인하고, 걸리면 그 자리에서 타임라인만 옮기고 끝난다(A/B 어느 쪽에도
 *  안 보낸다).
 *
 *  **`타임라인`이 반드시 있어야 잡는다.** "늘려줘"·"확대해줘"만으로 잡으면
 *  "이 장면 늘려줘"(장면 길이, `set_segment_bounds`)나 "화면 확대해줘"(장면
 *  화면 자체의 확대, `set_scene_transform` -- `_editing_prompt`가 이미
 *  "화면"을 그 뜻으로 쓴다)를 가로챈다. `타임라인`은 다른 15개 편집 의도
 *  어디에도 안 나오는 말이라 안전하다.
 */
export function timelineZoomCommandFromInstruction(instruction: string): TimelineZoomCommand | null {
  if (typeof instruction !== "string") return null;
  const text = instruction.trim();
  if (!text) return null;
  if (FIT_PATTERN.test(text)) return "fit";
  if (IN_PATTERN.test(text)) return "in";
  if (OUT_PATTERN.test(text)) return "out";
  return null;
}

// 전체가 화면에 맞도록. 대표님 예시 문장 "전체가 보이게 해줘"를 그대로 받는다.
// `타임라인`을 요구하지 않는다 -- "전체"가 이미 다른 15개 의도와 안 겹친다.
const FIT_PATTERN = /전체.{0,6}(보이|보기|맞춰|맞추)|(보이|맞춰|맞추).{0,6}전체/;
// 늘리기(확대). 대표님 예시 문장 "타임라인 좀 늘려줘"를 그대로 받는다.
const IN_PATTERN = /타임라인.{0,10}(늘려|늘리|키워|확대)|(늘려|늘리|키워|확대).{0,10}타임라인|줌\s*인|zoom\s*in/i;
// 줄이기(축소).
const OUT_PATTERN = /타임라인.{0,10}(줄여|줄이|축소)|(줄여|줄이|축소).{0,10}타임라인|줌\s*아웃|zoom\s*out/i;
