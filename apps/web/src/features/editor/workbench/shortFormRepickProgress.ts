import { api, type OutputVariant, type ShortFormScenePick } from "../../../api";
import { pollJobUntilTerminal } from "../../../lib/pollJob";

/**
 * 숏폼을 다시 고르는 일은 **걸어 두고 물어서 받는다**(2026-09-12).
 *
 * 실측(대표님 영상, 장면 94개): 유진이 전 구간을 읽는 데 129.8초, 후보를 짜는 데
 * 266.8초 -- 합쳐 약 400초다. 서버 앞단은 330초에 끊으므로 한 요청으로는 끝까지
 * 기다릴 수 없고, 끊기면 대표님은 우리 문구 대신 오류 화면을 본다.
 *
 * 대표님 결정(2026-09-12)은 **"다른 모델 쓸 때는 잠시 기다리자"**였다. 기다리려면
 * 요청 밖으로 나와야 한다 -- 더빙·자막 번역이 같은 이유로 이미 이 모양이고,
 * 폴링 뼈대(`pollJob.ts`)도 그 둘과 같은 것을 쓴다.
 *
 * 장면별 진행 수는 서버가 세지 않는다(자막 번역과 같은 이유). 그래서 간격·상한은
 * 장면 수로 계산하지 않고 실측에 여유를 둔 고정값이다.
 */
const SHORT_FORM_REPICK_POLL_INTERVAL_MS = 3000;
/** 실측 약 400초에 넉넉한 여유(약 4배)를 둔 고정 상한(약 27분). */
const SHORT_FORM_REPICK_MAX_POLL_ATTEMPTS = 540;

export type ShortFormRepickResult = {
  variant: OutputVariant;
  scene_pick?: ShortFormScenePick;
};

export type ShortFormRepickOutcome =
  | { kind: "succeeded"; result: ShortFormRepickResult }
  | { kind: "failed"; detail: string | null }
  | { kind: "cancelled" }
  | { kind: "timed_out" };

export async function repickShortFormWithProgress(input: {
  projectId: string;
  variantId: string;
  expectedVariantRevision: number;
  isStillRelevant?: () => boolean;
}): Promise<ShortFormRepickOutcome> {
  const started = await api.repickShortFormScenes(input.projectId, input.variantId, {
    expected_variant_revision: input.expectedVariantRevision,
  });

  const outcome = await pollJobUntilTerminal(
    () => api.getShortFormRepickJob(input.projectId, input.variantId, started.job_id),
    {
      intervalMs: SHORT_FORM_REPICK_POLL_INTERVAL_MS,
      maxAttempts: SHORT_FORM_REPICK_MAX_POLL_ATTEMPTS,
      delayFirst: true,
      isStillRelevant: input.isStillRelevant,
    },
  );

  if (outcome.kind === "succeeded") return { kind: "succeeded", result: outcome.result };
  if (outcome.kind === "cancelled") return { kind: "cancelled" };
  if (outcome.kind === "timed_out") return { kind: "timed_out" };
  return { kind: "failed", detail: outcome.error_detail ?? null };
}
