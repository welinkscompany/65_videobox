/**
 * 받아쓰기는 걸어 두고 물어서 받는다. Whisper 호출에 시간 제한이 없어 긴
 * 내레이션은 한 요청에 못 끝낸다(2026-09-08, §1-6).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { api } from "../../../api";
import { runTranscriptionWithProgress } from "./transcriptionProgress";

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

function stubTranscription(statuses: Array<Record<string, unknown>>) {
  vi.spyOn(api, "startTranscription").mockResolvedValue({
    job_id: "job_1", status: "running", transcript_uri: null,
  } as never);
  const status = vi.spyOn(api, "getTranscriptionJob");
  for (const item of statuses) status.mockResolvedValueOnce(item as never);
  return status;
}

describe("받아쓰기 진행", () => {
  it("성공하면 대본 위치를 담아 온다", { timeout: 20000 }, async () => {
    stubTranscription([
      { job_id: "job_1", status: "succeeded", transcript_uri: "local://projects/p/transcripts/job_1" },
    ]);

    const outcome = await runTranscriptionWithProgress({ projectId: "p", narrationAssetId: "asset_1" });

    expect(outcome).toEqual({ kind: "succeeded", jobId: "job_1", transcriptUri: "local://projects/p/transcripts/job_1" });
  });

  it("여러 번 처리 중이어도 끝까지 물어서 받는다", { timeout: 20000 }, async () => {
    stubTranscription([
      { job_id: "job_1", status: "running", transcript_uri: null },
      { job_id: "job_1", status: "running", transcript_uri: null },
      { job_id: "job_1", status: "succeeded", transcript_uri: "local://projects/p/transcripts/job_1" },
    ]);

    const outcome = await runTranscriptionWithProgress({ projectId: "p", narrationAssetId: "asset_1" });

    expect(outcome).toEqual({ kind: "succeeded", jobId: "job_1", transcriptUri: "local://projects/p/transcripts/job_1" });
  });

  it("실패하면 실패로 끝난다", { timeout: 20000 }, async () => {
    stubTranscription([{ job_id: "job_1", status: "failed", transcript_uri: null }]);

    const outcome = await runTranscriptionWithProgress({ projectId: "p", narrationAssetId: "asset_1" });

    expect(outcome).toEqual({ kind: "failed" });
  });

  it("멈추라고 하면 더 묻지 않고 멈춘다", { timeout: 20000 }, async () => {
    stubTranscription([{ job_id: "job_1", status: "running", transcript_uri: null }]);

    const outcome = await runTranscriptionWithProgress({
      projectId: "p", narrationAssetId: "asset_1", isStillRelevant: () => false,
    });

    expect(outcome).toEqual({ kind: "cancelled" });
  });
});
