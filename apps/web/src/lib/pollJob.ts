/** 서버가 백그라운드 job(202 + `job_id` 폴링 패턴)을 돌리는 동안 "처리 중"이
 * 아닐 때까지 물어보는 공통 루프. 코드리뷰(2026-08-30)로 잡힌 결함 --
 * 유튜브 학습(`VoiceTtsSettings.tsx`)과 AI 영상 생성(`SceneImageStudio.tsx`)이
 * 거의 같은 루프를 각자 따로 짜 놓고 있었다.
 *
 * 두 자리의 유일한 실제 차이는 확인 순서다 -- 유튜브 쪽은 매 시도마다
 * "아직 이 화면이 유효한가"부터 확인한 뒤 곧바로 상태를 묻고, 실패하지
 * 않았을 때만 다음 시도 전에 기다린다. 영상 쪽은 그런 유효성 확인이 없고
 * 매 시도 앞에 먼저 기다린다. `delayFirst`로 그 차이만 남겨 뒀다 -- 나머지
 * 루프 뼈대(간격·최대 시도·종료 판정)는 하나다. */
export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export type JobStatusPayload<TResult> = {
  status: "processing" | "succeeded" | "failed";
  result: TResult | null;
  error_detail: string | null;
};

export type PollOutcome<TResult> =
  | { kind: "succeeded"; result: TResult }
  | { kind: "failed"; error_detail: string | null }
  | { kind: "cancelled" }
  | { kind: "timed_out" };

export async function pollJobUntilTerminal<TResult>(
  fetchStatus: () => Promise<JobStatusPayload<TResult>>,
  options: {
    intervalMs: number;
    maxAttempts: number;
    /** true면 상태를 묻기 전에 먼저 기다린다(영상 쪽). 기본은 false(유튜브 쪽) --
     * 유효성부터 확인하고 곧바로 물은 뒤, 아직 안 끝났을 때만 다음 시도 전에 기다린다. */
    delayFirst?: boolean;
    isStillRelevant?: () => boolean;
  },
): Promise<PollOutcome<TResult>> {
  const { intervalMs, maxAttempts, delayFirst = false, isStillRelevant } = options;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (delayFirst) await delay(intervalMs);
    if (isStillRelevant && !isStillRelevant()) return { kind: "cancelled" };
    const current = await fetchStatus();
    if (current.status === "succeeded" && current.result) return { kind: "succeeded", result: current.result };
    if (current.status === "failed") return { kind: "failed", error_detail: current.error_detail };
    if (!delayFirst) await delay(intervalMs);
  }
  return { kind: "timed_out" };
}
