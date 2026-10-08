import { afterEach, describe, expect, it, vi } from "vitest";

import type { ExactPreviewResponse } from "../../../api";
import { exactPreviewPollStatus, watchExactPreview } from "./exactPreviewWatch";

const response = (status: ExactPreviewResponse["status"], extra: Partial<ExactPreviewResponse> = {}): ExactPreviewResponse => ({
  status, generation_id: "g-1", timeline_start_sec: 0, timeline_end_sec: 1, artifact_revision: 1, fingerprint: "f", ...extra,
});

describe("exactPreviewPollStatus", () => {
  it("pending/running은 처리 중", () => {
    expect(exactPreviewPollStatus(response("pending")).status).toBe("processing");
    expect(exactPreviewPollStatus(response("running")).status).toBe("processing");
  });
  it("succeeded는 응답을 결과로 가진다", () => {
    const done = response("succeeded", { content_url: "/x.mp4" });
    expect(exactPreviewPollStatus(done)).toEqual({ status: "succeeded", result: done, error_detail: null });
  });
  it("failed/stale/unavailable은 실패, 상태 이름을 이유로 가진다", () => {
    for (const status of ["failed", "stale", "unavailable"] as const) {
      expect(exactPreviewPollStatus(response(status))).toEqual({ status: "failed", result: null, error_detail: status });
    }
  });
});

describe("watchExactPreview", () => {
  afterEach(() => vi.useRealTimers());

  it("응답을 받은 뒤에만 다음을 묻는다(겹침 0) -- 상태 확인이 3초 걸려도", async () => {
    vi.useFakeTimers();
    let inFlight = 0;
    let max = 0;
    let calls = 0;
    const fetchStatus = vi.fn(async () => {
      inFlight += 1; max = Math.max(max, inFlight); calls += 1;
      await new Promise((r) => window.setTimeout(r, 3000));
      inFlight -= 1;
      return response(calls < 4 ? "running" : "succeeded");
    });
    const done = watchExactPreview({ fetchStatus, generationId: "g-1", isActive: () => true });
    await vi.runAllTimersAsync();
    expect((await done).kind).toBe("succeeded");
    expect(max).toBe(1);
    expect(calls).toBe(4);
  });

  it("간격이 1, 1.5, 2.25, 3.375, 5초로 늘고 성공하면 더 묻지 않는다", async () => {
    vi.useFakeTimers();
    const stamps: number[] = [];
    const start = Date.now();
    const fetchStatus = vi.fn(async () => { stamps.push(Date.now()); return response(stamps.length < 6 ? "pending" : "succeeded"); });
    const done = watchExactPreview({ fetchStatus, generationId: "g-1", isActive: () => true });
    await vi.runAllTimersAsync();
    await done;
    expect(stamps.map((t, i) => t - (i === 0 ? start : stamps[i - 1]!)).slice(0, 5)).toEqual([1000, 1500, 2250, 3375, 5000]);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetchStatus).toHaveBeenCalledTimes(6);
  });

  it("실패·낡음·없음(unavailable)도 거기서 멈춘다", async () => {
    vi.useFakeTimers();
    for (const status of ["failed", "stale", "unavailable"] as const) {
      const fetchStatus = vi.fn(async () => response(status));
      const done = watchExactPreview({ fetchStatus, generationId: "g-1", isActive: () => true });
      await vi.runAllTimersAsync();
      expect(await done).toEqual({ kind: "failed", error_detail: status });
      expect(fetchStatus).toHaveBeenCalledTimes(1);
    }
  });

  it("화면이 닫히면(isActive=false) 더 묻지 않고 cancelled", async () => {
    vi.useFakeTimers();
    let active = true;
    const fetchStatus = vi.fn(async () => response("running"));
    const done = watchExactPreview({ fetchStatus, generationId: "g-1", isActive: () => active });
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchStatus).toHaveBeenCalledTimes(1);
    active = false;
    await vi.runAllTimersAsync();
    expect((await done).kind).toBe("cancelled");
    expect(fetchStatus).toHaveBeenCalledTimes(1);
  });

  it("묻는 사이 낡아진 생성분의 응답은 버린다(성공이어도 성공으로 치지 않는다)", async () => {
    vi.useFakeTimers();
    let active = true;
    const fetchStatus = vi.fn(async () => { active = false; return response("succeeded"); });
    const done = watchExactPreview({ fetchStatus, generationId: "g-old", isActive: () => active });
    await vi.runAllTimersAsync();
    expect((await done).kind).toBe("cancelled");
  });

  it("한두 번 못 읽는 건 견디고, 연달아 세 번 못 읽으면 멈춘다", async () => {
    vi.useFakeTimers();
    let n = 0;
    const flaky = vi.fn(async () => { n += 1; if (n <= 2) throw new Error("net"); return response("succeeded"); });
    const ok = watchExactPreview({ fetchStatus: flaky, generationId: "g-1", isActive: () => true });
    await vi.runAllTimersAsync();
    expect((await ok).kind).toBe("succeeded");

    const dead = vi.fn(async () => { throw new Error("net"); });
    const lost = watchExactPreview({ fetchStatus: dead, generationId: "g-1", isActive: () => true });
    await vi.runAllTimersAsync();
    expect(await lost).toEqual({ kind: "failed", error_detail: "preview_status_unreachable" });
    expect(dead).toHaveBeenCalledTimes(3);
  });

  it("계속 처리 중이면 최대 시도 뒤 timed_out", async () => {
    vi.useFakeTimers();
    const fetchStatus = vi.fn(async () => response("running"));
    const done = watchExactPreview({ fetchStatus, generationId: "g-1", isActive: () => true, poll: { maxAttempts: 5 } });
    await vi.runAllTimersAsync();
    expect((await done).kind).toBe("timed_out");
    expect(fetchStatus).toHaveBeenCalledTimes(5);
  });
});
