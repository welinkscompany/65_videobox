import assert from "node:assert/strict";
import test from "node:test";
import { classifyControl } from "./controlCensus.mjs";

const quiet = { domMutations: 0, requests: 0, focusMoved: false, ariaChanged: false, dialogOpened: false, urlChanged: false };
const base = { role: "button", name: "x", disabledInAllStates: false, hasHandler: true, isLink: false, isFormSubmit: false, skipped: false, reaction: quiet };

test("손잡이가 없는 단추는 no-handler", () => assert.equal(classifyControl({ ...base, hasHandler: false }), "no-handler"));
test("링크·폼 제출은 손잡이가 없어도 살아 있다", () => {
  assert.equal(classifyControl({ ...base, hasHandler: false, isLink: true, reaction: { ...quiet, urlChanged: true } }), "ok");
  assert.equal(classifyControl({ ...base, hasHandler: false, isFormSubmit: true, reaction: { ...quiet, requests: 1 } }), "ok");
});
test("눌렀는데 화면·요청·초점·aria 어느 것도 안 바뀌면 silent", () => assert.equal(classifyControl(base), "silent"));
test("무엇이든 바뀌면 ok", () => {
  for (const key of ["domMutations", "requests"]) assert.equal(classifyControl({ ...base, reaction: { ...quiet, [key]: 1 } }), "ok");
  for (const key of ["focusMoved", "ariaChanged", "dialogOpened", "urlChanged"]) assert.equal(classifyControl({ ...base, reaction: { ...quiet, [key]: true } }), "ok");
});
test("모든 상태에서 꺼져 있으면 always-disabled", () => assert.equal(classifyControl({ ...base, disabledInAllStates: true }), "always-disabled"));
test("부작용이 큰 단추는 누르지 않고 skipped-side-effect", () => assert.equal(classifyControl({ ...base, skipped: true }), "skipped-side-effect"));
test("클릭 지점이 자기 자신이 아니면(가려진 단추) 다른 것이 반응해도 silent", () =>
  assert.equal(classifyControl({ ...base, hitSelf: false, reaction: { ...quiet, domMutations: 3 } }), "silent"));
test("hitSelf를 모르면(undefined) 가려졌다고 보지 않는다", () =>
  assert.equal(classifyControl({ ...base, reaction: { ...quiet, domMutations: 3 } }), "ok"));
