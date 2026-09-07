import { normalizedTimelineRem, type EditorWorkbenchPersistedState } from "./editorWorkbenchLayout";

// 기본값은 **한 곳에만** 두어야 한다. 2026-08-17에 `editorWorkbenchLayout`의 것만
// 바꿨더니 여기 있던 두 번째 벌이 이겨서 화면이 그대로였다 -- 승인된 변경이
// 아무에게도 닿지 않았다. 바꿀 때는 두 곳을 함께 본다.
//
// 왼쪽 재료 열은 기본으로 펴 둔다(owner 승인 2026-08-17). 캡컷처럼 영상·음악·
// 효과음이 편집기 왼쪽에 늘 붙어 있어야 한다.
//
// **오른쪽도 편다(2026-08-22).** 캡컷은 `세부 정보`가 늘 붙어 있고, owner가
// "캡컷과 완전 비슷하게"라고 했다.
//
// 앞서 여기 적혀 있던 이유는 **둘 다 펴면 미리보기가 720px 아래로 밀린다**였는데,
// 지금 상수로 재보면 그렇지 않다:
//
//     available 1720 - leftMin 220 - rightMin 260 - gutter 12x2 = 1216px
//
// 720px을 훨씬 넘는다. 그리고 좁은 화면에서는 `resolveEditorWorkbenchLayout`이
// **알아서 한쪽만 남긴다**(`bothPreview >= bothPreviewMinPx` 검사). 그 되돌림은
// `editorWorkbenchLayout.test.ts`가 이미 지키고 있으므로 여기서 미리 닫아 둘 필요가 없다.
export const defaultEditorUiState: EditorWorkbenchPersistedState = Object.freeze({
  leftOpen: true,
  rightOpen: true,
  activeDrawer: null,
  leftSize: 280,
  rightSize: 320,
  timelineRem: null,
});

/** 저장 키의 세대.
 *
 * 승인된 기본값을 바꿔도 예전에 저장된 값이 그대로 이기면 **바꾼 것이 아무에게도
 * 닿지 않는다.** 2026-08-17에 왼쪽 재료 패널을 기본으로 펴기로 했는데, 이미 써 온
 * 화면에는 `접힘`이 저장돼 있어 그대로였다. 세대를 올려 한 번만 새 기본값으로
 * 시작하게 한다 -- 그 뒤로 접으면 그 선택은 다시 지켜진다.
 *
 * 2026-08-18에 `timelineRem` 칸을 더했지만 세대는 올리지 않았다 -- 기본값이 바뀐
 * 것이 아니고, 칸이 없는 예전 저장분은 `null`(손대지 않음)로 읽혀 그대로 유효하다.
 * 세대를 올렸다면 모두의 도크 폭이 이유 없이 한 번 초기화됐을 것이다.
 */
const editorUiGeneration = "v2";

export function editorUiStorageKey(projectId: string, sessionId: string): string {
  return `videobox.editor-workbench.ui.${editorUiGeneration}:${encodeURIComponent(projectId)}:${encodeURIComponent(sessionId)}`;
}
const legacyEditorUiStorageKey = "videobox.editor-workbench.ui";
export function hasLegacyEditorUiState(): boolean {
  try {
    return window.localStorage.getItem(legacyEditorUiStorageKey) !== null;
  } catch {
    return false;
  }
}

function validState(value: unknown): EditorWorkbenchPersistedState | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  const timelineRem = normalizedTimelineRem(candidate.timelineRem);
  if (
    typeof candidate.leftOpen !== "boolean" ||
    typeof candidate.rightOpen !== "boolean" ||
    (candidate.activeDrawer !== null && candidate.activeDrawer !== "left" && candidate.activeDrawer !== "right") ||
    typeof candidate.leftSize !== "number" ||
    !Number.isFinite(candidate.leftSize) ||
    typeof candidate.rightSize !== "number" ||
    !Number.isFinite(candidate.rightSize) ||
    timelineRem === undefined
  ) return null;
  return {
    leftOpen: candidate.leftOpen,
    rightOpen: candidate.rightOpen,
    activeDrawer: candidate.activeDrawer,
    leftSize: Math.max(220, Math.round(candidate.leftSize)),
    rightSize: Math.max(260, Math.round(candidate.rightSize)),
    timelineRem,
  };
}

export function readEditorUiState(projectId: string, sessionId: string): EditorWorkbenchPersistedState {
  try {
    const raw = window.localStorage.getItem(editorUiStorageKey(projectId, sessionId))
      ?? window.localStorage.getItem(legacyEditorUiStorageKey);
    return raw === null ? defaultEditorUiState : validState(JSON.parse(raw)) ?? defaultEditorUiState;
  } catch {
    return defaultEditorUiState;
  }
}

export function hasPersistedEditorUiState(projectId: string, sessionId: string): boolean {
  try {
    return window.localStorage.getItem(editorUiStorageKey(projectId, sessionId)) !== null
      || window.localStorage.getItem(legacyEditorUiStorageKey) !== null;
  } catch {
    return false;
  }
}

export function writeEditorUiState(
  projectId: string,
  sessionId: string,
  value: EditorWorkbenchPersistedState,
): void {
  try {
    window.localStorage.setItem(
      editorUiStorageKey(projectId, sessionId),
      JSON.stringify({
        leftOpen: value.leftOpen,
        rightOpen: value.rightOpen,
        activeDrawer: value.activeDrawer,
        leftSize: value.leftSize,
        rightSize: value.rightSize,
        timelineRem: value.timelineRem,
      }),
    );
    // One-way compatibility migration for the old unscoped UI key.
    window.localStorage.removeItem(legacyEditorUiStorageKey);
  } catch {
    // UI persistence is best-effort and never editing-data authority.
  }
}

// Output variants are a comparison tool, not something judged on every visit,
// so whether the creator has them open is remembered per project (not per
// editing session -- opening it once for a project should stick).
function variantsCollapsedStorageKey(projectId: string): string {
  return `videobox.editor-workbench.variants-collapsed:${encodeURIComponent(projectId)}`;
}

export function readVariantsCollapsed(projectId: string): boolean {
  try {
    const raw = window.localStorage.getItem(variantsCollapsedStorageKey(projectId));
    return raw === null ? true : raw === "true";
  } catch {
    return true;
  }
}

export function writeVariantsCollapsed(projectId: string, collapsed: boolean): void {
  try {
    window.localStorage.setItem(variantsCollapsedStorageKey(projectId), String(collapsed));
  } catch {
    // UI persistence is best-effort and never editing-data authority.
  }
}
