import { api, type FootageDerivativeJob } from "../../api";
import { pollJobUntilTerminal } from "../../lib/pollJob";

/**
 * 촬영본 파생 렌더는 **걸어 두고 물어서 받는다**(2026-09-08, §1-6).
 *
 * 승인된 제안·가상 묶음의 구간을 실제 ffmpeg로 잘라 새 자료실 자산으로
 * 만드는 일이라, 원본이 길면 시간이 걸린다. 더빙·자막 번역·받아쓰기와
 * 같은 공용 폴링 루프(`pollJobUntilTerminal`)를 쓴다.
 */
const FOOTAGE_DERIVATIVE_POLL_INTERVAL_MS = 2000;
const FOOTAGE_DERIVATIVE_MAX_POLL_ATTEMPTS = 300;

export type FootageDerivativeOutcome =
  | { kind: "succeeded"; job: FootageDerivativeJob }
  | { kind: "failed"; errorDetail: string | null }
  | { kind: "cancelled" }
  | { kind: "timed_out" };

export async function renderFootageDerivativeWithProgress(input: {
  sourceKind: "proposal" | "sequence";
  sourceId: string;
  idempotencyKey: string;
  isStillRelevant?: () => boolean;
}): Promise<FootageDerivativeOutcome> {
  const started = await api.renderFootageDerivative({
    source_kind: input.sourceKind,
    source_id: input.sourceId,
    idempotency_key: input.idempotencyKey,
  });

  if (started.status === "succeeded") return { kind: "succeeded", job: started };
  if (started.status === "failed") return { kind: "failed", errorDetail: started.error_message ?? null };

  const outcome = await pollJobUntilTerminal(
    async () => {
      const job = await api.getFootageDerivativeJob(started.job_id);
      if (job.status === "succeeded") {
        return { status: "succeeded" as const, result: job, error_detail: null };
      }
      if (job.status === "failed") {
        return { status: "failed" as const, result: null, error_detail: job.error_message ?? "footage_derivative_failed" };
      }
      return { status: "processing" as const, result: null, error_detail: null };
    },
    {
      intervalMs: FOOTAGE_DERIVATIVE_POLL_INTERVAL_MS,
      maxAttempts: FOOTAGE_DERIVATIVE_MAX_POLL_ATTEMPTS,
      delayFirst: true,
      isStillRelevant: input.isStillRelevant,
    },
  );

  if (outcome.kind === "succeeded") return { kind: "succeeded", job: outcome.result };
  if (outcome.kind === "cancelled") return { kind: "cancelled" };
  if (outcome.kind === "timed_out") return { kind: "timed_out" };
  return { kind: "failed", errorDetail: outcome.error_detail };
}
