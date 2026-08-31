import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/** 감독 손잡이가 **화면까지 실제로 이어지는지** 지킨다.
 *
 * 2026-08-19: `onUseDraftAsScript`를 타입에도 넣고 `RightDock`에도 넣었는데
 * 가운데 있는 `editorWorkbenchReadOnlyAdapters`가 넘겨주지 않아서 화면에는
 * 단추가 끝내 뜨지 않았다. 배포된 화면에서 눌러 보고서야 알았다.
 *
 * 이 저장소가 반복해 겪은 패턴이라("부품은 있는데 부르는 자리가 없다") 양 끝이
 * 아니라 **잇는 구간**을 잡는다.
 */
function read(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf-8");
}

describe("right dock wiring", () => {
  it("forwards every director handler RightDock accepts", () => {
    const dockProps = read("./RightDock.tsx");
    const adapter = read("./editorWorkbenchReadOnlyAdapters.tsx");

    // RightDock이 props 타입에서 받겠다고 선언한 `on*` 손잡이들.
    // 2026-08-30 후속으로 유진 대화·추천이 `YujinPanel`로 완전히 빠지면서
    // RightDock은 속성 하나만 남았다 -- 손잡이 수가 확 줄어든 게 맞는
    // 상태다. 여기서는 정규식이 조용히 0개를 잡는 사고만 막는다.
    const declared = [...dockProps.matchAll(/^\s{2}(on[A-Z]\w*)\??:/gm)].map((match) => match[1]);
    expect(declared.length).toBeGreaterThan(0);

    const missing = declared.filter((handler) => !adapter.includes(handler));
    expect(missing, `어댑터가 넘기지 않는 손잡이: ${missing.join(", ")}`).toEqual([]);
  });
});
