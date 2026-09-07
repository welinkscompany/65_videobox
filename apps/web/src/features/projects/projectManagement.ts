import { useState } from "react";

/** 프로젝트 관리(보관 · 영구 삭제 · 보관함 되돌리기)의 규칙을 한 곳에 둔다.
 *
 * 지금 이 동작을 그리는 곳이 둘이다 -- 왼쪽 기둥의 프로젝트 전환 목록과
 * `프로젝트` 목록 화면. 기둥은 곧 위 띠로 바뀌면서 사라지고
 * (`docs/decisions/2026-08-21-capcut-shell-layout.ko.md`), 띠는 **고르는 것만**
 * 맡는다. 그때 기둥의 markup을 그냥 지우면 되도록 규칙만 여기로 옮겨 두었다.
 *
 * 그리는 모양은 서로 다르다(기둥은 메뉴 항목, 목록 화면은 카드 단추). 같아야
 * 하는 것은 모양이 아니라 **지키는 것**이다.
 *
 * - 보관은 확인 **한 번**.
 * - 영구 삭제는 확인 **두 번**. 첫 번째는 되돌릴 수 없다고 말할 뿐 지우지 않고,
 *   두 번째에서 실제로 지운다(owner 결정 2026-08-06). 서버도 `?confirm=true`를
 *   따로 요구하므로 이 화면 게이트가 유일한 방벽은 아니다.
 * - 실패하면 조용히 넘어가지 않고 **다시 해 보라고** 말한다.
 *
 * 화면에 보이는 문구는 일부러 여기 두지 않았다. `src/user-copy-policy.test.ts`는
 * JSX만 읽으므로, 단추 이름을 상수로 빼면 창작자 문구 검사가 두 화면에서
 * 한꺼번에 꺼진다.
 */
export type ProjectDeleteConfirm = { projectId: string; stage: 1 | 2 } | null;

export const projectActionFailureMessage = "프로젝트 작업에 실패했어요. 다시 시도해 주세요.";

export function useProjectManagement() {
  const [error, setError] = useState<string | null>(null);
  // 어느 프로젝트의 어느 동작이 도는 중인지까지 구분한다. 참/거짓 하나로 두면
  // 프로젝트가 여럿일 때 다른 카드의 단추까지 같이 잠긴다.
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [archiveConfirmId, setArchiveConfirmId] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<ProjectDeleteConfirm>(null);

  const run = async (key: string, action: () => void | Promise<void>) => {
    setError(null);
    setBusyKey(key);
    try {
      await action();
    } catch {
      setError(projectActionFailureMessage);
    } finally {
      setBusyKey(null);
    }
  };

  return { error, busyKey, archiveConfirmId, setArchiveConfirmId, deleteConfirm, setDeleteConfirm, run };
}

export type ProjectManagement = ReturnType<typeof useProjectManagement>;
