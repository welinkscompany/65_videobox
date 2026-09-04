/**
 * 대화가 한 번 끝날 때마다 유진이 이어서 권하는 것 셋.
 *
 * owner 지시(2026-09-01): "우리 프로그램에 기능들이 여러가지가 있는데, 유진이와
 * 질문 답변이 끝나면 꼬리질문도 3개 만들어서 제안해줘 -- 영상 퀄리티를 더 좋게
 * 만드는 방법으로."
 *
 * **모델에게 묻지 않는다.** 지금 편집본을 읽어서 만든다. 이유가 셋이다.
 *
 * 1. 메시지마다 로컬 모델을 한 번 더 부르지 않는다(대화 답변 + 편집 해석으로
 *    이미 둘이다).
 * 2. 지어내지 않는다. "배경 음악을 넣어 볼까요?"는 **그 장면에 음악이 없을 때만**
 *    나온다 -- 이미 넣은 장면에 다시 권하면 유진이 화면을 안 보고 있다는 뜻이 된다.
 * 3. **누르면 실제로 되는 것만 권한다.** 그 밖의 것을 권하면 눌렀을 때 "그건
 *    못 해요"가 돌아온다 -- 권하지 않느니만 못하다.
 *
 *    2026-09-02에 유진이 할 수 있는 것이 열하나로 늘었다(손떨림 보정·화면
 *    노이즈·변형·소리 정리가 들어왔다). 그래서 여기서도 권할 수 있게 됐다 --
 *    의도 목록이 넓어지면 이 파일도 같이 넓힌다는 약속을 지킨 것이다.
 */
import type { EditorViewModel } from "../editorViewModel";
import { sceneNumbersBySegmentId } from "../sceneNames";

/** 자막 한 줄이 이보다 길면 화면에서 두 줄로 감긴다(캡컷 기본 자막도 비슷하다). */
const LONG_CAPTION_CHARS = 28;
/** 이보다 긴 장면은 짧은 영상에서 늘어져 보인다. */
const LONG_SCENE_SEC = 8;

function clipsFor(view: EditorViewModel, segmentId: string, role: "broll" | "bgm" | "sfx") {
  return view.tracks
    .filter((track) => track.role === role)
    .flatMap((track) => track.clips)
    .filter((clip) => clip.segmentId === segmentId);
}

/** 지금 이야기 중인 장면. 고른 게 없으면 **손볼 곳이 남은 첫 장면**을 쓴다 --
 *  "어느 장면을 말하는 거지?"를 창작자가 되묻게 하지 않는다.
 *
 *  순서는 자막이 아니라 `sceneNumbersBySegmentId`를 따른다. 장면 번호를 세는
 *  자리는 이 저장소에 하나뿐이고(그 함수 주석 참고), 자막으로 따로 세면 자막이
 *  아직 없는 장면을 골라 놓고 번호를 못 붙이는 상태가 된다.
 */
function focusSegmentId(view: EditorViewModel, selectedSegmentId: string | null): string | null {
  if (selectedSegmentId) return selectedSegmentId;
  const ordered = [...sceneNumbersBySegmentId(view).keys()];
  return ordered.find((segmentId) => !clipsFor(view, segmentId, "bgm").length)
    ?? ordered.find((segmentId) => !clipsFor(view, segmentId, "sfx").length)
    ?? ordered[0]
    ?? null;
}

export function buildQualityFollowUps(
  { view, selectedSegmentId }: { view: EditorViewModel; selectedSegmentId: string | null },
): readonly string[] {
  const sceneNumbers = sceneNumbersBySegmentId(view);
  const segmentId = focusSegmentId(view, selectedSegmentId);
  if (!segmentId) return [];
  const sceneNumber = sceneNumbers.get(segmentId);
  if (!sceneNumber) return [];
  const scene = `${sceneNumber}번 장면`;
  const broll = clipsFor(view, segmentId, "broll");
  const hasAnyBroll = view.tracks.some((track) => track.role === "broll" && track.clips.length > 0);
  const caption = view.captions.find((item) => item.segmentId === segmentId);
  const suggestions: string[] = [];

  // 소리부터 권한다. 음악·효과음이 비어 있는 것이 완성본에서 가장 크게 티가 나고,
  // 그게 이 제품의 차별점이기도 하다(장면마다 뭘 쓸지 유진이 고른다).
  if (!clipsFor(view, segmentId, "bgm").length) suggestions.push(`${scene}에 어울리는 배경 음악을 넣어 줘`);
  if (!clipsFor(view, segmentId, "sfx").length) suggestions.push(`${scene}에 어울리는 효과음을 넣어 줘`);
  // 색감은 화면이 깔린 장면에만 걸 수 있다 -- 없는 장면에 권하면 거절된다.
  if (broll.length && !broll.some((clip) => clip.controls.filter)) {
    suggestions.push(`${scene} 색감을 따뜻하게 바꿔 줘`);
  }
  if (caption && caption.text.trim().length > LONG_CAPTION_CHARS) {
    suggestions.push(`${scene} 캡션을 더 짧게 다듬어 줘`);
  }
  if (caption && caption.endSec - caption.startSec > LONG_SCENE_SEC) {
    suggestions.push(`${scene}을 1.5배로 빠르게 해 줘`);
  }
  // 손떨림 보정은 **화면이 깔린 장면에만** 걸 수 있다(유진 쪽 검증도 같은 기준).
  // 이미 켜 둔 장면에는 권하지 않는다 -- 다른 권유와 같은 규칙이다.
  if (broll.length && !broll.some((clip) => clip.controls.stabilize)) {
    suggestions.push(`${scene} 흔들린 화면을 잡아 줘`);
  }
  if (clipsFor(view, segmentId, "bgm").some((clip) => !clip.controls.normalizeLoudness)) {
    suggestions.push(`${scene} 배경 음악 소리 크기를 고르게 맞춰 줘`);
  }
  // 이 장면에서 손볼 것이 셋이 안 되면 **편집본 전체를 보는 것**으로 채운다.
  // 처음에는 여기서도 색감을 한 번 더 권했는데, 이미 색감을 고른 장면에까지
  // 다른 색감을 권해서 "아까 골라 뒀는데 왜 또?"가 됐다. 채우는 줄은 그 장면에
  // 무엇이 있든 늘 뜻이 통하는 것이라야 한다.
  //
  // 셋 다 유진이 실제로 할 수 있는 것이다 -- 순서 바꾸기, 여러 장면 색감을
  // 한 번에(한 편집안에 열여섯 개까지 담긴다), 장면 빼기.
  const wholeTimeline = [
    sceneNumbers.size > 1 ? "장면 순서를 더 자연스럽게 바꿔 줘" : null,
    hasAnyBroll ? "모든 장면 색감을 하나로 맞춰 줘" : null,
    sceneNumbers.size > 1 ? "늘어지는 장면이 있으면 빼 줘" : null,
  ].filter((item): item is string => item !== null);
  for (const item of wholeTimeline) {
    if (suggestions.length >= 3) break;
    suggestions.push(item);
  }
  return suggestions.slice(0, 3);
}
