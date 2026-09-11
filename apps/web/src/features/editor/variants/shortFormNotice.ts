import type { ShortFormScenePick } from "../../../api";

/** 숏폼 장면을 고른 결과를 대표님 말로 옮긴다. **한 자리에서만 만든다.**
 *
 * 부르는 자리가 셋이다 -- 숏폼 만들기, 숏폼 다시 만들기, 유진에게 말해서 다시
 * 만들기. 문장을 자리마다 따로 지으면 같은 결과가 화면마다 다르게 읽히고,
 * 그중 하나가 **누가 골랐는지**를 빼먹는다. 자막 밀도로 고른 결과를 유진의
 * 판단이라고 말하는 것이 이 기능에서 가장 나쁜 결과다(`short_form_scene_pick.py`).
 *
 * `pick`이 없으면(옛 서버 응답) 누가 골랐는지 모른다 -- 그때는 유진을 들먹이지
 * 않는다.
 */
export function shortFormPickNotice(
  pick: ShortFormScenePick | undefined,
  options: { readonly remade: boolean },
): string {
  const made = options.remade ? "숏폼을 다시 만들었어요." : "숏폼을 만들었어요.";
  const undo = "마음에 안 들면 전체 장면으로 되돌릴 수 있어요.";
  const detail = pick?.notice?.trim() || "자막이 많은 장면 위주로 자동으로 골랐어요.";
  return `${made} ${detail} ${undo}`;
}
