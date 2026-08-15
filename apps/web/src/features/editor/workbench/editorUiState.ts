import type { EditorWorkbenchPersistedState } from "./editorWorkbenchLayout";

// The preview is what the creator is judging, so a session with no saved
// choice opens with it alone. Both docks are one toolbar click away.
export const defaultEditorUiState: EditorWorkbenchPersistedState = Object.freeze({
  leftOpen: false,
  rightOpen: false,
  activeDrawer: null,
  leftSize: 280,
  rightSize: 320,
});

export function editorUiStorageKey(projectId: string, sessionId: string): string {
  return `videobox.editor-workbench.ui:${encodeURIComponent(projectId)}:${encodeURIComponent(sessionId)}`;
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
  if (
    typeof candidate.leftOpen !== "boolean" ||
    typeof candidate.rightOpen !== "boolean" ||
    (candidate.activeDrawer !== null && candidate.activeDrawer !== "left" && candidate.activeDrawer !== "right") ||
    typeof candidate.leftSize !== "number" ||
    !Number.isFinite(candidate.leftSize) ||
    typeof candidate.rightSize !== "number" ||
    !Number.isFinite(candidate.rightSize)
  ) return null;
  return {
    leftOpen: candidate.leftOpen,
    rightOpen: candidate.rightOpen,
    activeDrawer: candidate.activeDrawer,
    leftSize: Math.max(220, Math.round(candidate.leftSize)),
    rightSize: Math.max(260, Math.round(candidate.rightSize)),
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
