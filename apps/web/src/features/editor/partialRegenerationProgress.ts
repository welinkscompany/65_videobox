import { api, type PartialRegenerationJob, type PartialRegenerationRequest } from "../../api";
import { pollJobUntilTerminal } from "../../lib/pollJob";

/**
 * 부분 재생성은 **걸어 두고 물어서 받는다**(2026-09-08, §1-6).
 *
 * 선택한 항목(TTS 후보 생성·촬영본 추천 등)에 따라 한 요청에 못 끝낼 수
 * 있다 -- 더빙·자막 번역·받아쓰기와 같은 이유이고 같은 공용 폴링 루프
 * (`pollJobUntilTerminal`)를 쓴다. 항목이 무엇을 다시 만드는지에 따라 걸리는
 * 시간이 크게 달라져서 장면 수 기반 계산은 안 하고, 넉넉한 고정 상한만 둔다.
 */
const PARTIAL_REGENERATION_POLL_INTERVAL_MS = 2000;
const PARTIAL_REGENERATION_MAX_POLL_ATTEMPTS = 300;

export type PartialRegenerationOutcome =
  | { kind: "succeeded"; result: PartialRegenerationJob }
  | { kind: "failed" }
  | { kind: "cancelled" }
  | { kind: "timed_out" };

export async function runPartialRegenerationWithProgress(input: {
  projectId: string;
  sessionId: string;
  payload: PartialRegenerationRequest;
  isStillRelevant?: () => boolean;
}): Promise<PartialRegenerationOutcome> {
  const started = await api.startPartialRegeneration(input.projectId, input.sessionId, input.payload);

  const outcome = await pollJobUntilTerminal(
    async () => {
      const job = await api.getPartialRegenerationResult(input.projectId, started.job_id);
      if (job.status === "succeeded") {
        return { status: "succeeded" as const, result: job, error_detail: null };
      }
      if (job.status === "failed") {
        return { status: "failed" as const, result: null, error_detail: "partial_regeneration_failed" };
      }
      return { status: "processing" as const, result: null, error_detail: null };
    },
    {
      intervalMs: PARTIAL_REGENERATION_POLL_INTERVAL_MS,
      maxAttempts: PARTIAL_REGENERATION_MAX_POLL_ATTEMPTS,
      delayFirst: true,
      isStillRelevant: input.isStillRelevant,
    },
  );

  if (outcome.kind === "succeeded") return { kind: "succeeded", result: outcome.result };
  if (outcome.kind === "cancelled") return { kind: "cancelled" };
  if (outcome.kind === "timed_out") return { kind: "timed_out" };
  return { kind: "failed" };
}
