import type { InspectorAction } from "../inspector/InspectorControls";
import type { CutToolbarState } from "./cutToolbar";

/** 캡컷 단축키.
 *
 * 2026-08-17까지 편집기 단축키는 `Ctrl+Z`·`Ctrl+Y` 둘뿐이었다. 컷 도구를 툴바에
 * 올렸으니 손이 가는 키도 같이 준다 -- 캡컷은 `Ctrl+B`로 나누고 `Delete`로 뺀다.
 *
 * **키는 툴바가 정한 것을 그대로 쓴다.** 무엇을 할 수 있는지 다시 계산하지 않는다.
 * 그러면 단추와 키가 서로 다른 판단을 하게 되고, 화면이 잠겼다고 말하는 동안 키로는
 * 통하는 일이 생긴다.
 */
type Chord = Readonly<{ key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }>;

export function cutShortcutFor(event: Chord, tools: CutToolbarState): InspectorAction | null {
  // Alt가 눌린 조합은 다른 뜻이다. 가로채지 않는다.
  if (event.altKey) return null;
  const chord = event.ctrlKey || event.metaKey;

  if (chord && event.key.toLowerCase() === "b") {
    return tools.split.enabled ? tools.split.action : null;
  }
  // 삭제 키는 두 이름으로 온다. 맥 키보드에는 Delete가 없고 Backspace만 있다.
  if (!chord && (event.key === "Delete" || event.key === "Backspace")) {
    return tools.drop.enabled ? tools.drop.action : null;
  }
  return null;
}
