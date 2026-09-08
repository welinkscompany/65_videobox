/**
 * 자막 번역은 걸어 두고 물어서 받는다. 실측 최악 630초라 한 요청에 못 끝낸다
 * (2026-09-08, §1-6).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { api } from "../../../api";
import { captionTranslationOutcomeMessage, runCaptionTranslationWithProgress } from "./captionTranslationProgress";

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

function stubTranslation(statuses: Array<Record<string, unknown>>) {
  vi.spyOn(api, "startEditingSessionCaptionTranslation").mockResolvedValue({
    job_id: "job_1", status: "processing",
  } as never);
  const status = vi.spyOn(api, "getEditingSessionCaptionTranslationStatus");
  for (const item of statuses) status.mockResolvedValueOnce(item as never);
  return status;
}

const segment = (captionText: string, translations: Record<string, string>) => ({
  segment_id: "seg_1", caption_text: captionText, caption_translations: translations,
});

describe("자막 번역 진행", () => {
  it("다 옮겼으면 못 옮긴 장면이 없다고 센다", { timeout: 20000 }, async () => {
    stubTranslation([
      {
        job_id: "job_1", status: "succeeded",
        result: { session_revision: 9, segments: [segment("안녕", { en: "Hello" })] },
        error_detail: null,
      },
    ]);

    const outcome = await runCaptionTranslationWithProgress({
      projectId: "p", sessionId: "s", expectedRevision: 8, language: "en",
    });

    expect(outcome).toEqual({ kind: "succeeded", missingCount: 0 });
  });

  it("못 옮긴 장면이 있으면 그 수를 센다", { timeout: 20000 }, async () => {
    stubTranslation([
      {
        job_id: "job_1", status: "succeeded",
        result: {
          session_revision: 9,
          segments: [segment("안녕", { en: "Hello" }), segment("반가워요", {})],
        },
        error_detail: null,
      },
    ]);

    const outcome = await runCaptionTranslationWithProgress({
      projectId: "p", sessionId: "s", expectedRevision: 8, language: "en",
    });

    expect(outcome).toEqual({ kind: "succeeded", missingCount: 1 });
    expect(captionTranslationOutcomeMessage(outcome)).toContain("1개 장면은 옮기지 못했어요");
  });

  it("여러 번 처리 중이어도 끝까지 물어서 받는다", { timeout: 20000 }, async () => {
    stubTranslation([
      { job_id: "job_1", status: "processing", result: null, error_detail: null },
      { job_id: "job_1", status: "processing", result: null, error_detail: null },
      {
        job_id: "job_1", status: "succeeded",
        result: { session_revision: 9, segments: [segment("안녕", { en: "Hello" })] },
        error_detail: null,
      },
    ]);

    const outcome = await runCaptionTranslationWithProgress({
      projectId: "p", sessionId: "s", expectedRevision: 8, language: "en",
    });

    expect(outcome).toEqual({ kind: "succeeded", missingCount: 0 });
  });

  it("실패하면 사유를 담아 온다", { timeout: 20000 }, async () => {
    stubTranslation([
      { job_id: "job_1", status: "failed", result: null, error_detail: "asset_file_missing" },
    ]);

    const outcome = await runCaptionTranslationWithProgress({
      projectId: "p", sessionId: "s", expectedRevision: 8, language: "en",
    });

    expect(outcome).toEqual({ kind: "failed", detail: "asset_file_missing" });
    expect(captionTranslationOutcomeMessage(outcome)).toBe("자막을 번역하지 못했어요.");
  });

  it("멈추라고 하면 더 묻지 않고 멈춘다", { timeout: 20000 }, async () => {
    stubTranslation([
      { job_id: "job_1", status: "processing", result: null, error_detail: null },
    ]);

    const outcome = await runCaptionTranslationWithProgress({
      projectId: "p", sessionId: "s", expectedRevision: 8, language: "en",
      isStillRelevant: () => false,
    });

    expect(outcome).toEqual({ kind: "cancelled" });
  });
});
