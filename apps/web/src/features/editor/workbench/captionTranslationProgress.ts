import { api } from "../../../api";
import { pollJobUntilTerminal } from "../../../lib/pollJob";

/**
 * 자막 번역은 **걸어 두고 물어서 받는다**(2026-09-08, §1-6).
 *
 * 실측(2026-09-03)으로 최악 630초가 걸릴 수 있다 -- nginx 330초 벽보다 길다.
 * 더빙을 비동기로 바꾼 것과 같은 이유이고, 같은 방식(`dubbingProgress.ts`)을
 * 그대로 쓴다.
 *
 * 더빙과 달리 **장면별 진행 수를 서버가 아직 세지 않는다** -- 그 값까지
 * 재려면 백엔드에 새 계측이 필요하고, 이번 변경의 목적(330초 벽을 넘기지
 * 않는 것)과는 다른 일이다. 그래서 폴링 간격·최대 시도는 더빙처럼 장면 수에
 * 맞춰 계산하지 않고, 실측된 최악 630초에 넉넉한 여유를 곱한 고정값을 쓴다.
 */
const CAPTION_TRANSLATION_POLL_INTERVAL_MS = 3000;
/** 실측 최악 630초에 넉넉한 여유(약 3배)를 둔 고정 상한(약 32분). */
const CAPTION_TRANSLATION_MAX_POLL_ATTEMPTS = 640;

export type CaptionTranslationOutcome =
  | { kind: "succeeded"; missingCount: number }
  | { kind: "failed"; detail: string | null }
  | { kind: "cancelled" }
  | { kind: "timed_out" };

export async function runCaptionTranslationWithProgress(input: {
  projectId: string;
  sessionId: string;
  expectedRevision: number;
  language: string;
  isStillRelevant?: () => boolean;
}): Promise<CaptionTranslationOutcome> {
  const started = await api.startEditingSessionCaptionTranslation(input.projectId, input.sessionId, {
    expected_revision: input.expectedRevision,
    language: input.language,
  });

  const outcome = await pollJobUntilTerminal(
    () => api.getEditingSessionCaptionTranslationStatus(input.projectId, input.sessionId, started.job_id),
    {
      intervalMs: CAPTION_TRANSLATION_POLL_INTERVAL_MS,
      maxAttempts: CAPTION_TRANSLATION_MAX_POLL_ATTEMPTS,
      delayFirst: true,
      isStillRelevant: input.isStillRelevant,
    },
  );

  if (outcome.kind === "succeeded") {
    // **못 옮긴 장면이 있으면 말해 준다.** 안 말하면 그 장면은 원래 자막
    // 그대로 완성본에 나가는데, 창작자는 다 옮겨진 줄 안다.
    const missingCount = outcome.result.segments.filter(
      (segment) =>
        String(segment.caption_text ?? "").trim() &&
        !String(segment.caption_translations?.[input.language] ?? "").trim(),
    ).length;
    return { kind: "succeeded", missingCount };
  }
  if (outcome.kind === "cancelled") return { kind: "cancelled" };
  if (outcome.kind === "timed_out") return { kind: "timed_out" };
  return { kind: "failed", detail: outcome.error_detail ?? null };
}

/** 결과를 창작자 말로. */
export function captionTranslationOutcomeMessage(outcome: CaptionTranslationOutcome): string {
  if (outcome.kind === "succeeded") {
    return outcome.missingCount > 0
      ? `${outcome.missingCount}개 장면은 옮기지 못했어요. 그 장면은 원래 캡션 그대로 나가요. 다시 눌러 주시면 남은 장면만 다시 해 봐요.`
      : "자막을 번역했어요.";
  }
  if (outcome.kind === "timed_out") {
    return "자막 번역이 너무 오래 걸려서 기다리기를 멈췄어요. 잠시 뒤 다시 확인해 주세요.";
  }
  if (outcome.kind === "cancelled") return "자막 번역을 멈췄어요.";
  return "자막을 번역하지 못했어요.";
}
