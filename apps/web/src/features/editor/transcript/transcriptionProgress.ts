import { api } from "../../../api";
import { pollJobUntilTerminal } from "../../../lib/pollJob";

/**
 * 받아쓰기는 **걸어 두고 물어서 받는다**(2026-09-08, §1-6).
 *
 * Whisper 호출에 시간 제한이 없어 긴 내레이션은 nginx 330초 벽을 넘길 수
 * 있다. 더빙·자막 번역과 같은 이유이고 같은 공용 폴링 루프(`pollJobUntilTerminal`)를
 * 쓴다. 장면별 진행 수가 없는 단일 잡이라 장면 수 기반 계산은 안 하고,
 * 실측 없이 넉넉한 고정 상한(10분)만 둔다.
 */
const TRANSCRIPTION_POLL_INTERVAL_MS = 2000;
const TRANSCRIPTION_MAX_POLL_ATTEMPTS = 300;

export type TranscriptionOutcome =
  | { kind: "succeeded"; jobId: string; transcriptUri: string }
  | { kind: "failed" }
  | { kind: "cancelled" }
  | { kind: "timed_out" };

export async function runTranscriptionWithProgress(input: {
  projectId: string;
  narrationAssetId: string;
  isStillRelevant?: () => boolean;
}): Promise<TranscriptionOutcome> {
  const started = await api.startTranscription(input.projectId, { narration_asset_id: input.narrationAssetId });

  const outcome = await pollJobUntilTerminal(
    async () => {
      const job = await api.getTranscriptionJob(input.projectId, started.job_id);
      return {
        status: job.status === "running" ? "processing" : job.status,
        result: job.status === "succeeded" && job.transcript_uri ? { transcript_uri: job.transcript_uri } : null,
        error_detail: job.status === "failed" ? "transcription_failed" : null,
      };
    },
    {
      intervalMs: TRANSCRIPTION_POLL_INTERVAL_MS,
      maxAttempts: TRANSCRIPTION_MAX_POLL_ATTEMPTS,
      delayFirst: true,
      isStillRelevant: input.isStillRelevant,
    },
  );

  if (outcome.kind === "succeeded") {
    return { kind: "succeeded", jobId: started.job_id, transcriptUri: outcome.result.transcript_uri };
  }
  if (outcome.kind === "cancelled") return { kind: "cancelled" };
  if (outcome.kind === "timed_out") return { kind: "timed_out" };
  return { kind: "failed" };
}
