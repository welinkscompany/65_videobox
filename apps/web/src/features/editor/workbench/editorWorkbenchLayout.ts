export type EditorWorkbenchPersistedState = Readonly<{
  leftOpen: boolean;
  rightOpen: boolean;
  activeDrawer: "left" | "right" | null;
  leftSize: number;
  rightSize: number;
}>;

export type EditorWorkbenchLayout = Readonly<{
  mode: "desktop-both" | "desktop-single" | "drawer";
  leftOpen: boolean;
  rightOpen: boolean;
  activeDrawer: "left" | "right" | null;
  leftSize: number;
  rightSize: number;
  previewMinPx: number;
}>;

export const editorWorkbenchPanelConstants = Object.freeze({ leftMinPx: 220, rightMinPx: 260, gutterPx: 12, bothPreviewMinPx: 720, singlePreviewMinPx: 640 });
const defaultPersisted: EditorWorkbenchPersistedState = { leftOpen: true, rightOpen: false, activeDrawer: null, leftSize: 280, rightSize: 320 };

function persistedState(value: unknown): EditorWorkbenchPersistedState {
  if (!value || typeof value !== "object") return defaultPersisted;
  const candidate = value as Record<string, unknown>;
  const validKeys = ["leftOpen", "rightOpen", "activeDrawer", "leftSize", "rightSize"];
  if (Object.keys(candidate).some((key) => !validKeys.includes(key))) return defaultPersisted;
  if (typeof candidate.leftOpen !== "boolean" || typeof candidate.rightOpen !== "boolean" || (candidate.activeDrawer !== null && candidate.activeDrawer !== "left" && candidate.activeDrawer !== "right") || !Number.isFinite(candidate.leftSize) || !Number.isFinite(candidate.rightSize)) return defaultPersisted;
  return { leftOpen: candidate.leftOpen, rightOpen: candidate.rightOpen, activeDrawer: candidate.activeDrawer, leftSize: Math.max(editorWorkbenchPanelConstants.leftMinPx, Number(candidate.leftSize)), rightSize: Math.max(editorWorkbenchPanelConstants.rightMinPx, Number(candidate.rightSize)) };
}

export function resolveEditorWorkbenchLayout({ viewportWidth, availableWorkbenchWidth, persisted }: { viewportWidth: number; availableWorkbenchWidth: number; persisted: unknown }): EditorWorkbenchLayout {
  const state = persistedState(persisted);
  const available = Math.max(0, availableWorkbenchWidth);
  const { leftMinPx, rightMinPx, gutterPx, bothPreviewMinPx, singlePreviewMinPx } = editorWorkbenchPanelConstants;
  const bothPreview = available - leftMinPx - rightMinPx - gutterPx * 2;
  if (viewportWidth >= 1600 && state.leftOpen && state.rightOpen && bothPreview >= bothPreviewMinPx) return { ...state, mode: "desktop-both", activeDrawer: null, previewMinPx: bothPreviewMinPx };

  const requestedLeft = state.leftOpen || !state.rightOpen;
  const dockMin = requestedLeft ? leftMinPx : rightMinPx;
  const singlePreview = available - dockMin - gutterPx;
  const requiredSinglePreview = Math.max(singlePreviewMinPx, available / 2);
  if (viewportWidth >= 1280 && singlePreview >= requiredSinglePreview) return { ...state, mode: "desktop-single", leftOpen: requestedLeft, rightOpen: !requestedLeft, activeDrawer: null, previewMinPx: singlePreviewMinPx };

  return { ...state, mode: "drawer", leftOpen: false, rightOpen: false, activeDrawer: state.activeDrawer, previewMinPx: 0 };
}
