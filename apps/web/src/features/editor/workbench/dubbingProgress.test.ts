/**
 * 더빙은 걸어 두고 물어서 받는다. 장면당 13초라 긴 영상은 한 요청에 못 끝낸다.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { api } from "../../../api";
import { dubbingOutcomeMessage, pollAttemptsFor, runDubbingWithProgress } from "./dubbingProgress";

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

function stubDubbing(statuses: Array<Record<string, unknown>>) {
  vi.spyOn(api, "startEditingSessionDubbing").mockResolvedValue({
    job_id: "job_1", status: "processing", total_scene_count: 3,
  } as never);
  const status = vi.spyOn(api, "getEditingSessionDubbingStatus");
  for (const item of statuses) status.mockResolvedValueOnce(item as never);
  return status;
}

describe("더빙 진행", () => {
  // 물어보는 간격이 3초라(장면 하나가 13초다) 두 번 물으면 6초가 걸린다.
  it("몇 장면 중 몇 장면째인지 계속 알린다", { timeout: 20000 }, async () => {
    /** 스무 장면이면 사 분이 넘는다. 아무 말 없으면 멈춘 줄 안다. */
    stubDubbing([
      { job_id: "job_1", status: "processing", result: null, error_detail: null, done_scene_count: 1, total_scene_count: 3 },
      { job_id: "job_1", status: "succeeded", result: { dubbed_scene_count: 3, dubbing_notice: null, session_revision: 9 }, error_detail: null, done_scene_count: 3, total_scene_count: 3 },
    ]);
    const seen: Array<[number, number]> = [];

    const outcome = await runDubbingWithProgress({
      projectId: "p", sessionId: "s", expectedRevision: 8, language: "en",
      onProgress: (done, total) => seen.push([done, total]),
    });

    expect(outcome).toEqual({ kind: "succeeded", dubbedSceneCount: 3, notice: null });
    // 걸자마자 0/3을 알리고, 물어볼 때마다 갱신한다.
    expect(seen[0]).toEqual([0, 3]);
    expect(seen.at(-1)).toEqual([3, 3]);
  });

  it("못 넣은 장면이 있으면 그 사정을 그대로 전한다", { timeout: 20000 }, async () => {
    stubDubbing([
      { job_id: "job_1", status: "succeeded", result: { dubbed_scene_count: 2, dubbing_notice: "1개 장면은 옮긴 말이 길어서 넣지 못했어요.", session_revision: 9 }, error_detail: null, done_scene_count: 3, total_scene_count: 3 },
    ]);

    const outcome = await runDubbingWithProgress({
      projectId: "p", sessionId: "s", expectedRevision: 8, language: "en",
    });

    expect(dubbingOutcomeMessage(outcome)).toContain("옮긴 말이 길어서");
  });

  it("전부 됐으면 몇 장면을 바꿨는지 말한다", () => {
    expect(dubbingOutcomeMessage({ kind: "succeeded", dubbedSceneCount: 5, notice: null }))
      .toBe("5개 장면의 목소리를 바꿨어요.");
  });

  it("실패하면 무엇을 확인하면 되는지 말한다", () => {
    /** "실패했어요"만으로는 창작자가 할 일을 모른다. */
    expect(dubbingOutcomeMessage({ kind: "failed", detail: null }))
      .toContain("목소리 프로그램이 켜져 있는지");
  });
});

describe("기다리는 시간", () => {
  it("장면이 많으면 더 오래 기다린다", () => {
    /** 창작자의 실제 대본은 243장면이고 그건 52분이 걸린다.
     *  고정 35분이었을 때는 더빙이 도는 중에 화면만 포기했다(2026-09-03). */
    const attempts = pollAttemptsFor(243);
    const minutes = (attempts * 3) / 60;

    expect(minutes).toBeGreaterThan(52);
  });

  it("장면이 적어도 너무 빨리 포기하지 않는다", () => {
    expect(pollAttemptsFor(1) * 3).toBeGreaterThanOrEqual(300);
  });

  it("장면이 늘면 기다리는 시간도 늘어난다", () => {
    expect(pollAttemptsFor(200)).toBeGreaterThan(pollAttemptsFor(50));
  });
});
