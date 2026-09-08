/**
 * 부분 재생성은 걸어 두고 물어서 받는다. 선택한 항목에 따라 한 요청에 못
 * 끝낼 수 있다(2026-09-08, §1-6).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { api } from "../../api";
import { runPartialRegenerationWithProgress } from "./partialRegenerationProgress";

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

const payload = { expected_revision: 8, segment_ids: ["segment-1"], fields: ["caption"] };

function stubPartialRegeneration(statuses: Array<Record<string, unknown>>) {
  vi.spyOn(api, "startPartialRegeneration").mockResolvedValue({
    job_id: "job_1", status: "running", session_id: "session-a",
    segment_ids: ["segment-1"], fields: ["caption"], downstream_steps: [],
  } as never);
  const status = vi.spyOn(api, "getPartialRegenerationResult");
  for (const item of statuses) status.mockResolvedValueOnce(item as never);
  return status;
}

const succeededJob = {
  job_id: "job_1", status: "succeeded", partial_regeneration_id: "run_1",
  session_id: "session-a", session_updated_at: "2026-09-08T00:00:00Z",
  source_timeline_id: "timeline-a", timeline_id: "timeline-b",
  segment_ids: ["segment-1"], fields: ["caption"], downstream_steps: [],
  regenerated_segments: [{ segment_id: "segment-1" }], timeline: {},
  targeted_segments: [], affected_output_areas: [],
  predicted_review_status_after_rerun: "draft", prediction_reasons: [],
};

describe("부분 재생성 진행", () => {
  it("성공하면 결과를 담아 온다", { timeout: 20000 }, async () => {
    stubPartialRegeneration([succeededJob]);

    const outcome = await runPartialRegenerationWithProgress({ projectId: "p", sessionId: "s", payload });

    expect(outcome).toEqual({ kind: "succeeded", result: succeededJob });
  });

  it("여러 번 처리 중이어도 끝까지 물어서 받는다", { timeout: 20000 }, async () => {
    stubPartialRegeneration([
      { ...succeededJob, status: "running" },
      { ...succeededJob, status: "running" },
      succeededJob,
    ]);

    const outcome = await runPartialRegenerationWithProgress({ projectId: "p", sessionId: "s", payload });

    expect(outcome).toEqual({ kind: "succeeded", result: succeededJob });
  });

  it("실패하면 실패로 끝난다", { timeout: 20000 }, async () => {
    stubPartialRegeneration([{ ...succeededJob, status: "failed" }]);

    const outcome = await runPartialRegenerationWithProgress({ projectId: "p", sessionId: "s", payload });

    expect(outcome).toEqual({ kind: "failed" });
  });

  it("멈추라고 하면 더 묻지 않고 멈춘다", { timeout: 20000 }, async () => {
    stubPartialRegeneration([{ ...succeededJob, status: "running" }]);

    const outcome = await runPartialRegenerationWithProgress({
      projectId: "p", sessionId: "s", payload, isStillRelevant: () => false,
    });

    expect(outcome).toEqual({ kind: "cancelled" });
  });
});
