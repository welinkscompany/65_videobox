/**
 * 편집을 하나 하면 화면 아래에 알림 하나가 뜬다: 시작 `working` -> 끝 `done`/`failed`.
 * 같은 편집은 같은 `id`를 쓰므로 알림이 쌓이지 않고 같은 자리에서 바뀐다.
 *
 * **이 파일 하나가 이음매다.** 계획 I(`docs/superpowers/plans/` 편집기 반응·모양 정리 계획)가
 * 공용 반응 모양을 정하면 이 파일만 바꾼다. 부르는 쪽(`announceEditorFeedback`)은 그대로 둔다.
 * 화면 읽기 프로그램용 `편집 저장 상태` 문장은 이것과 따로 두고 그대로 유지한다.
 */
import { toast } from "sonner";

export type EditorFeedback = Readonly<{
  kind: "working" | "done" | "failed";
  message: string;
  id?: string;
}>;

const DEFAULT_FEEDBACK_ID = "editor-feedback";
const SETTLED_DURATION_MS = 2000;

/** 알림을 거둔다. 편집이 끝나기 전에 화면을 떠나 `working` 알림이 남을 때만 쓴다. */
export function dismissEditorFeedback(id?: string): void {
  toast.dismiss(id ?? DEFAULT_FEEDBACK_ID);
}

export function announceEditorFeedback(feedback: EditorFeedback): void {
  const options = {
    id: feedback.id ?? DEFAULT_FEEDBACK_ID,
    duration: feedback.kind === "working" ? Infinity : SETTLED_DURATION_MS,
  };
  if (feedback.kind === "working") toast.loading(feedback.message, options);
  else if (feedback.kind === "done") toast.success(feedback.message, options);
  else toast.error(feedback.message, options);
}
