/**
 * 더빙이 실패하는 흔한 두 가지는 **다시 눌러도 안 된다.**
 * 그럴 때 "저장하지 못했어요"만 뜨면 창작자는 눌러 보다 포기한다.
 */
import { describe, expect, it } from "vitest";

import { ApiRequestError } from "../../../api";
import { voiceFailureMessage } from "./voiceFailureMessage";

describe("더빙 실패 안내", () => {
  it("목소리 프로그램이 꺼져 있으면 켜라고 한다", () => {
    const error = new ApiRequestError(
      "Voice bridge is not answering at http://host.docker.internal:8199. Start it with ...",
      500,
      "/dubbing",
    );

    expect(voiceFailureMessage(error)).toContain("목소리를 만드는 프로그램이 꺼져 있어요");
  });

  it("작업 상태로 온 사유도 창작자 말로 옮긴다", () => {
    // 더빙이 비동기가 된 뒤로 실패 사유는 `ApiRequestError`가 아니라 작업
    // 상태의 문자열로 온다. 문자열을 안 받으면 **영어 원문이 그대로 화면에
    // 나간다** -- 2026-09-03 리뷰에서 실제로 그러고 있었다.
    expect(
      voiceFailureMessage(
        "Voice bridge is not answering at http://host.docker.internal:8199. Start it with scripts/start-voice.ps1",
      ),
    ).toContain("목소리를 만드는 프로그램이 꺼져 있어요");
  });

  it("옮길 말이 없으면 null이다 -- 못 옮긴 영어를 보여 주느니 일반 안내가 낫다", () => {
    expect(voiceFailureMessage("KeyError: 'timeline_042:007'")).toBeNull();
    expect(voiceFailureMessage("")).toBeNull();
    expect(voiceFailureMessage(null)).toBeNull();
  });

  it("읽어 줄 목소리가 없으면 어디서 가져오는지 말해 준다", () => {
    const error = new ApiRequestError(
      "Voice sample not found: ''. Voice cloning needs a reference recording.",
      500,
      "/dubbing",
    );

    expect(voiceFailureMessage(error)).toContain("자료실의 내 목소리");
  });

  it("서버의 영어 기술 문구를 화면에 그대로 쓰지 않는다", () => {
    /** 창작자 화면에는 개발 용어를 쓰지 않는다(§10.13). */
    const error = new ApiRequestError("Voice bridge is not answering", 500, "/dubbing");

    const message = voiceFailureMessage(error);

    expect(message).not.toContain("Voice bridge");
    expect(message).not.toContain("http");
  });

  it("더빙과 무관한 실패는 건드리지 않는다", () => {
    /** 다른 편집 실패는 기존 문구가 맞다 -- 다시 누르면 되니까. */
    expect(voiceFailureMessage(new ApiRequestError("something else", 500, "/x"))).toBeNull();
    expect(voiceFailureMessage(new Error("boom"))).toBeNull();
  });
});
