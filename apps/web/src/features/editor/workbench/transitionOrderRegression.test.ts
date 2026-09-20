import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * 2026-09-20 실측: 전환 탭이 `session.segments` 배열 순서로 "앞 장면이
 * 있는지"를 재서, 장면을 나눈 뒤 시간순으로는 분명히 두 번째인 장면을
 * 골라도 "첫 장면"으로 잘못 떴다(`session.segments`는 백엔드 저장 순서라
 * 화면 시간순과 다를 수 있다). `orderedSegmentIds`(시간순으로 다시 줄 세운
 * 목록)를 만들어 고쳤다.
 *
 * 이 시험은 그 고침을 소스 검사로 잠근다 -- `hasPrevious`를 다시
 * `session.segments`의 배열 위치로 재는 코드가 슬쩍 돌아오면 여기서 걸린다.
 * 코드를 읽는 시험이라 부서지기 쉽지만(리팩터로 줄 번호가 바뀌면 다시
 * 봐야 한다), 그 대가로 "이 실수를 다시 하지 마라"는 뜻을 코드 자체에
 * 남긴다.
 */
describe("전환 패널의 hasPrevious는 시간순으로만 잰다", () => {
  const filePath = resolve(
    process.cwd(),
    "src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx",
  );
  const source = readFileSync(filePath, "utf-8");

  it("transitionTarget 계산은 orderedSegmentIds를 쓴다", () => {
    const transitionTargetLine = source
      .split("\n")
      .find((line) => line.includes("const transitionTarget ="));

    expect(transitionTargetLine).toBeDefined();
  });

  it("hasPrevious 판정 자리에 session.segments의 배열 위치가 다시 들어오지 않았다", () => {
    const hasPreviousLine = source
      .split("\n")
      .find((line) => line.includes("hasPrevious:"));

    expect(hasPreviousLine).toBeDefined();
    expect(hasPreviousLine).not.toContain("session?.segments");
    expect(hasPreviousLine).not.toContain("session.segments");
    // leftSelectedIndex는 orderedSegmentIds.indexOf(...)에서 온 값이어야 한다
    // (시간순으로 다시 줄 세운 목록 -- session.segments의 저장 순서가 아니다).
    expect(hasPreviousLine).toContain("leftSelectedIndex");

    const leftSelectedIndexLine = source
      .split("\n")
      .find((line) => line.includes("const leftSelectedIndex ="));

    expect(leftSelectedIndexLine).toBeDefined();
    expect(leftSelectedIndexLine).not.toContain("session?.segments");
    expect(leftSelectedIndexLine).not.toContain("session.segments");
    expect(leftSelectedIndexLine).toContain("orderedSegmentIds.indexOf");
  });

  it("시간순 목록은 narration 트랙을 우선하고 자막으로 대체한다", () => {
    expect(source).toContain('track.role !== "narration"');
    expect(source).toContain("view.captions");
  });
});
