import type { ExactPreviewResponse } from "../../../api";
import { pollJobUntilTerminal, type JobStatusPayload, type PollOutcome } from "../../../lib/pollJob";

/** 편집본 미리보기가 만들어지는 동안 **가벼운 상태 길만** 묻는다.
 *
 * 예전에는 1.2초마다 세션(830KB)·매니페스트·변형본을 겹쳐 다시 불러, 서버가 바빠지고
 * 응답이 14~23초로 늘어 뒤 요청이 앞 응답을 무효로 만들었다(2026-10-08 점검 §3-2).
 * 이제는 응답을 받은 뒤에만 다음을 묻고(겹침 0), 간격이 점점 길어지며, 끝나면 멈춘다.
 */
export const EXACT_PREVIEW_POLL = {
  intervalMs: 1000,
  backoff: { factor: 1.5, maxMs: 5000 },
  maxAttempts: 240,
} as const;

/** 연달아 이만큼 못 읽으면 포기하고 사람에게 다시 시도를 맡긴다. */
export const EXACT_PREVIEW_MAX_CONSECUTIVE_ERRORS = 3;

export const EXACT_PREVIEW_UNREACHABLE = "preview_status_unreachable";

export const EXACT_PREVIEW_WATCH_ERROR_COPY = "미리보기 상태를 확인하지 못했어요. 미리보기 새로 만들기를 눌러 다시 시도해 주세요.";

export function exactPreviewPollStatus(response: ExactPreviewResponse): JobStatusPayload<ExactPreviewResponse> {
  switch (response.status) {
    case "pending":
    case "running":
      return { status: "processing", result: null, error_detail: null };
    case "succeeded":
      return { status: "succeeded", result: response, error_detail: null };
    default:
      return { status: "failed", result: null, error_detail: response.status };
  }
}

export function watchExactPreview(args: {
  fetchStatus: (generationId: string) => Promise<ExactPreviewResponse>;
  generationId: string;
  isActive: () => boolean;
  /** 테스트에서 줄이기 위한 값. 기본은 `EXACT_PREVIEW_POLL`. */
  poll?: Partial<typeof EXACT_PREVIEW_POLL>;
}): Promise<PollOutcome<ExactPreviewResponse>> {
  const { fetchStatus, generationId, isActive } = args;
  let consecutiveErrors = 0;
  return pollJobUntilTerminal<ExactPreviewResponse>(async () => {
    try {
      const response = await fetchStatus(generationId);
      consecutiveErrors = 0;
      // 기다리는 사이 다른 생성분으로 바뀌었거나 화면이 닫혔으면 이 응답은 버린다.
      if (!isActive()) return { status: "processing", result: null, error_detail: null };
      return exactPreviewPollStatus(response);
    } catch {
      consecutiveErrors += 1;
      if (consecutiveErrors >= EXACT_PREVIEW_MAX_CONSECUTIVE_ERRORS) {
        return { status: "failed", result: null, error_detail: EXACT_PREVIEW_UNREACHABLE };
      }
      return { status: "processing", result: null, error_detail: null };
    }
  }, { ...EXACT_PREVIEW_POLL, ...args.poll, delayFirst: true, isStillRelevant: isActive });
}
