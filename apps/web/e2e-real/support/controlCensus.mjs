// 편집기 조작 재고 조사의 분류 규칙(계획 H Task 2). 순수 함수 — 화면·서버를 모른다.
// 순서: 누르지 않음 -> 늘 꺼짐 -> 손잡이 없음 -> 가려짐 -> 반응 여섯 중 하나라도 있으면 ok, 아니면 silent.
export function classifyControl(observation) {
  const { disabledInAllStates, hasHandler, isLink, isFormSubmit, skipped, reaction, hitSelf } = observation;
  if (skipped) return "skipped-side-effect";
  if (disabledInAllStates) return "always-disabled";
  if (!hasHandler && !isLink && !isFormSubmit) return "no-handler";
  // 클릭 지점에 다른 요소가 있으면 그 단추는 마우스로 눌리지 않는다. 다른 요소가 반응했어도 이 단추의 반응이 아니다.
  if (hitSelf === false) return "silent";
  const reacted =
    reaction.domMutations > 0 ||
    reaction.requests > 0 ||
    reaction.focusMoved ||
    reaction.ariaChanged ||
    reaction.dialogOpened ||
    reaction.urlChanged;
  return reacted ? "ok" : "silent";
}
