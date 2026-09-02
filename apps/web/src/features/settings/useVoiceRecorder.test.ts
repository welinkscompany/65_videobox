/**
 * 녹음 길이 안내.
 *
 * **짧으면 왜 짧은지 말해 줘야 한다.** 목소리 복제는 참조가 짧으면 안 닮는데,
 * 몇 초를 읽었는지 안 보이면 창작자는 3초만 읽고 "안 닮네"라고 결론 내린다.
 */
import { describe, expect, it } from "vitest";

import { VOICE_ENOUGH_SECONDS, VOICE_MIN_SECONDS, recordingHint } from "./useVoiceRecorder";

describe("녹음 안내", () => {
  it("짧으면 더 읽으라고 하고, 왜인지도 말한다", () => {
    const hint = recordingHint(5);

    expect(hint).toContain("5초");
    expect(hint).toContain(`${VOICE_MIN_SECONDS}초는 넘겨`);
    expect(hint).toContain("잘 안 닮아요");
  });

  it("충분해지면 그렇게 말해 준다", () => {
    expect(recordingHint(VOICE_MIN_SECONDS + 1)).toContain("충분해요");
  });

  it("넉넉하면 멈춰도 된다고 말한다", () => {
    /** 더 읽어도 나아지지 않는데 계속 읽게 두면 시간만 쓴다. */
    expect(recordingHint(VOICE_ENOUGH_SECONDS + 5)).toContain("멈추셔도");
  });
});
