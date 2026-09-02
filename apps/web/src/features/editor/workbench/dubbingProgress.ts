import { api } from "../../../api";
import { pollJobUntilTerminal } from "../../../lib/pollJob";

/**
 * 더빙은 **걸어 두고 물어서 받는다.**
 *
 * 장면당 13초가 걸린다(2026-09-03 실측, chatterbox). 스물세 장면이면 프록시가
 * 끊고, 창작자의 실제 영상은 그보다 훨씬 길다 -- 8분짜리면 백 장면이 넘는다.
 * 유튜브 학습을 비동기로 바꾼 것과 같은 이유이고, 같은 방식을 쓴다.
 *
 * 물어보는 간격이 유튜브 쪽(2초)보다 긴 이유: 한 장면이 13초라 2초마다 물어도
 * 대부분 같은 숫자를 본다. 3초면 진행이 끊겨 보이지 않으면서 요청은 3분의 2다.
 */
const DUBBING_POLL_INTERVAL_MS = 3000;
/** 3초 × 700 = 35분. 백 장면이 넘는 영상(13초×100 ≈ 22분)도 넉넉히 덮는다. */
const DUBBING_POLL_MAX_ATTEMPTS = 700;

export type DubbingOutcome =
  | { kind: "succeeded"; dubbedSceneCount: number; notice: string | null }
  | { kind: "failed"; detail: string | null }
  | { kind: "cancelled" }
  | { kind: "timed_out" };

export async function runDubbingWithProgress(input: {
  projectId: string;
  sessionId: string;
  expectedRevision: number;
  language: string;
  voiceSampleAssetId?: string | null;
  /** 몇 장면 중 몇 장면째인지. 스무 장면이면 사 분이 넘으므로 말해 줘야 한다. */
  onProgress?: (done: number, total: number) => void;
  isStillRelevant?: () => boolean;
}): Promise<DubbingOutcome> {
  const started = await api.startEditingSessionDubbing(input.projectId, input.sessionId, {
    expected_revision: input.expectedRevision,
    language: input.language,
    voice_sample_asset_id: input.voiceSampleAssetId ?? null,
  });
  input.onProgress?.(0, started.total_scene_count);

  const outcome = await pollJobUntilTerminal(
    async () => {
      const status = await api.getEditingSessionDubbingStatus(
        input.projectId, input.sessionId, started.job_id,
      );
      input.onProgress?.(status.done_scene_count, status.total_scene_count);
      return status;
    },
    {
      intervalMs: DUBBING_POLL_INTERVAL_MS,
      maxAttempts: DUBBING_POLL_MAX_ATTEMPTS,
      delayFirst: true,
      isStillRelevant: input.isStillRelevant,
    },
  );

  if (outcome.kind === "succeeded") {
    return {
      kind: "succeeded",
      dubbedSceneCount: outcome.result?.dubbed_scene_count ?? 0,
      notice: outcome.result?.dubbing_notice ?? null,
    };
  }
  if (outcome.kind === "cancelled") return { kind: "cancelled" };
  if (outcome.kind === "timed_out") return { kind: "timed_out" };
  return { kind: "failed", detail: outcome.error_detail ?? null };
}

/** 결과를 창작자 말로. 못 넣은 장면이 있으면 그 사정이 그대로 나온다. */
export function dubbingOutcomeMessage(outcome: DubbingOutcome): string {
  if (outcome.kind === "succeeded") {
    return outcome.notice ?? `${outcome.dubbedSceneCount}개 장면의 목소리를 바꿨어요.`;
  }
  if (outcome.kind === "timed_out") {
    return "목소리 만들기가 너무 오래 걸려서 기다리기를 멈췄어요. 잠시 뒤 다시 확인해 주세요.";
  }
  if (outcome.kind === "cancelled") return "목소리 만들기를 멈췄어요.";
  return "목소리를 만들지 못했어요. 목소리 프로그램이 켜져 있는지 확인해 주세요.";
}
