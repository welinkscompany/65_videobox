import { afterEach, describe, expect, it, vi } from "vitest";

import { pollJobUntilTerminal } from "./pollJob";

// 코드리뷰(2026-08-30)로 잡힌 결함 -- 유튜브 학습(`VoiceTtsSettings.tsx`)과
// AI 영상 생성(`SceneImageStudio.tsx`)이 거의 같은 폴링 루프를 각자 따로 짜
// 놓고 있었다. 여기로 뽑은 뒤에는 이 파일 하나만 지키면 된다.

describe("공통 job 폴링 루프", () => {
  it("성공하면 결과를 그대로 돌려준다", async () => {
    const fetchStatus = vi.fn().mockResolvedValue({ status: "succeeded", result: { id: "a" }, error_detail: null });

    const outcome = await pollJobUntilTerminal(fetchStatus, { intervalMs: 0, maxAttempts: 5 });

    expect(outcome).toEqual({ kind: "succeeded", result: { id: "a" } });
  });

  it("실패하면 error_detail을 그대로 돌려준다", async () => {
    const fetchStatus = vi.fn().mockResolvedValue({ status: "failed", result: null, error_detail: "boom" });

    const outcome = await pollJobUntilTerminal(fetchStatus, { intervalMs: 0, maxAttempts: 5 });

    expect(outcome).toEqual({ kind: "failed", error_detail: "boom" });
  });

  it("계속 처리 중이면 최대 시도 뒤 timed_out을 돌려준다", async () => {
    const fetchStatus = vi.fn().mockResolvedValue({ status: "processing", result: null, error_detail: null });

    const outcome = await pollJobUntilTerminal(fetchStatus, { intervalMs: 0, maxAttempts: 3 });

    expect(outcome).toEqual({ kind: "timed_out" });
    expect(fetchStatus).toHaveBeenCalledTimes(3);
  });

  it("isStillRelevant가 false를 돌려주면 상태를 묻지 않고 cancelled로 끝낸다", async () => {
    const fetchStatus = vi.fn().mockResolvedValue({ status: "processing", result: null, error_detail: null });

    const outcome = await pollJobUntilTerminal(fetchStatus, {
      intervalMs: 0, maxAttempts: 5, isStillRelevant: () => false,
    });

    expect(outcome).toEqual({ kind: "cancelled" });
    expect(fetchStatus).not.toHaveBeenCalled();
  });

  it("delayFirst가 아니면 먼저 상태를 묻고, 아직 안 끝났을 때만 기다린 뒤 다시 묻는다", async () => {
    // 유튜브 학습 쪽 순서 -- 유효성부터 확인하고 곧바로 물은 뒤, 안 끝났을
    // 때만 다음 시도 전에 기다린다(맨 앞에 기다리지 않는다).
    let calls = 0;
    const fetchStatus = vi.fn().mockImplementation(() => {
      calls += 1;
      return Promise.resolve(
        calls < 3
          ? { status: "processing" as const, result: null, error_detail: null }
          : { status: "succeeded" as const, result: { id: "done" }, error_detail: null },
      );
    });

    const outcome = await pollJobUntilTerminal(fetchStatus, { intervalMs: 0, maxAttempts: 5 });

    expect(outcome).toEqual({ kind: "succeeded", result: { id: "done" } });
    expect(fetchStatus).toHaveBeenCalledTimes(3);
  });

  describe("점점 길게 묻기(backoff)와 겹치지 않기", () => {
    afterEach(() => vi.useRealTimers());

    it("backoff면 시도마다 간격이 factor배로 늘고 최대 maxMs에서 멈춘다", async () => {
      vi.useFakeTimers();
      const stamps: number[] = [];
      let calls = 0;
      const fetchStatus = vi.fn().mockImplementation(() => {
        stamps.push(Date.now());
        calls += 1;
        return Promise.resolve(
          calls <= 5
            ? { status: "processing" as const, result: null, error_detail: null }
            : { status: "succeeded" as const, result: "ok", error_detail: null },
        );
      });
      const start = Date.now();
      const done = pollJobUntilTerminal(fetchStatus, {
        intervalMs: 1000, maxAttempts: 20, delayFirst: true, backoff: { factor: 1.5, maxMs: 5000 },
      });
      await vi.runAllTimersAsync();
      await done;

      const gaps = stamps.map((t, i) => t - (i === 0 ? start : stamps[i - 1]!));
      expect(gaps.slice(0, 5)).toEqual([1000, 1500, 2250, 3375, 5000]);
    });

    it("상태 확인이 3초 걸려도 동시에 진행되는 요청은 하나뿐이다", async () => {
      vi.useFakeTimers();
      let inFlight = 0;
      let maxInFlight = 0;
      let calls = 0;
      const fetchStatus = vi.fn().mockImplementation(async () => {
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        calls += 1;
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
        inFlight -= 1;
        return calls < 4
          ? { status: "processing" as const, result: null, error_detail: null }
          : { status: "succeeded" as const, result: "ok", error_detail: null };
      });
      const done = pollJobUntilTerminal(fetchStatus, {
        intervalMs: 1000, maxAttempts: 10, delayFirst: true, backoff: { factor: 1.5, maxMs: 5000 },
      });
      await vi.runAllTimersAsync();
      await done;

      expect(calls).toBe(4);
      expect(maxInFlight).toBe(1);
    });
  });
});
