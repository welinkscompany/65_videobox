export type EditorWorkbenchPersistedState = Readonly<{
  leftOpen: boolean;
  rightOpen: boolean;
  activeDrawer: "left" | "right" | null;
  leftSize: number;
  rightSize: number;
  /** 편집자가 끌어서 정한 타임라인 높이(rem). 손대기 전에는 null이고 CSS 기본값이 쓰인다. */
  timelineRem: number | null;
}>;

export type EditorWorkbenchLayout = Readonly<{
  mode: "desktop-both" | "desktop-single" | "drawer";
  leftOpen: boolean;
  rightOpen: boolean;
  activeDrawer: "left" | "right" | null;
  leftSize: number;
  rightSize: number;
  timelineRem: number | null;
  previewMinPx: number;
}>;

export const editorWorkbenchPanelConstants = Object.freeze({ leftMinPx: 220, rightMinPx: 260, gutterPx: 12, bothPreviewMinPx: 720, singlePreviewMinPx: 640 });
// 재료 열은 기본으로 펴 두고(owner 승인 2026-08-17) 오른쪽은 닫아 둔다. 미리보기는
// 여전히 화면에서 가장 큰 것이고, 오른쪽 도크는 툴바 클릭 한 번 거리다.
//
// **여기만 고치면 화면에 닿지 않는다.** 실제로 쓰이는 기본값은 `editorUiState.ts`에
// 있고 이 벌은 persisted가 깨졌을 때의 대비책이다. 두 곳을 함께 본다.
/** 처음 여는 사람이 보는 배치. **캡컷은 소재와 세부 정보가 둘 다 열려 있다.**
 *
 *  `rightOpen`이 거짓이면 1600px가 넘어도 `desktop-both`로 못 간다(아래 `resolve`의
 *  첫 줄이 `state.rightOpen`을 본다). 그래서 넓은 화면에서도 늘 한쪽만 보였다 --
 *  2026-08-22에 1600px로 찍어 보고 알았다.
 *
 *  좁으면 `resolve`가 알아서 한쪽만 남기므로 여기서 걱정하지 않는다. */
const defaultPersisted: EditorWorkbenchPersistedState = { leftOpen: true, rightOpen: true, activeDrawer: null, leftSize: 280, rightSize: 320, timelineRem: null };

// 타임라인 높이의 상·하한. 손잡이(`EditorWorkbench`)와 두 검증기가 같은 값을 봐야
// 한다 -- 저장할 때와 읽을 때의 한계가 다르면 저장된 값이 조용히 잘린다.
export const timelineHeightLimitsRem = Object.freeze({ min: 6, max: 32 });

/** 저장된 타임라인 높이를 한계 안으로.
 *
 * `null`은 "손대지 않음"(이 칸이 생기기 전의 저장분 포함), `undefined`는 "무효"다.
 * 무효면 호출한 쪽이 저장분 전체를 버린다.
 */
export function normalizedTimelineRem(value: unknown): number | null | undefined {
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return Math.min(timelineHeightLimitsRem.max, Math.max(timelineHeightLimitsRem.min, value));
}

function persistedState(value: unknown): EditorWorkbenchPersistedState {
  if (!value || typeof value !== "object") return defaultPersisted;
  const candidate = value as Record<string, unknown>;
  const validKeys = ["leftOpen", "rightOpen", "activeDrawer", "leftSize", "rightSize", "timelineRem"];
  if (Object.keys(candidate).some((key) => !validKeys.includes(key))) return defaultPersisted;
  const timelineRem = normalizedTimelineRem(candidate.timelineRem);
  if (typeof candidate.leftOpen !== "boolean" || typeof candidate.rightOpen !== "boolean" || (candidate.activeDrawer !== null && candidate.activeDrawer !== "left" && candidate.activeDrawer !== "right") || !Number.isFinite(candidate.leftSize) || !Number.isFinite(candidate.rightSize) || timelineRem === undefined) return defaultPersisted;
  return { leftOpen: candidate.leftOpen, rightOpen: candidate.rightOpen, activeDrawer: candidate.activeDrawer, leftSize: Math.max(editorWorkbenchPanelConstants.leftMinPx, Number(candidate.leftSize)), rightSize: Math.max(editorWorkbenchPanelConstants.rightMinPx, Number(candidate.rightSize)), timelineRem };
}

export function resolveEditorWorkbenchLayout({ viewportWidth, availableWorkbenchWidth, persisted }: { viewportWidth: number; availableWorkbenchWidth: number; persisted: unknown }): EditorWorkbenchLayout {
  const state = persistedState(persisted);
  const available = Math.max(0, availableWorkbenchWidth);
  const { leftMinPx, rightMinPx, gutterPx, bothPreviewMinPx, singlePreviewMinPx } = editorWorkbenchPanelConstants;
  const bothPreview = available - leftMinPx - rightMinPx - gutterPx * 2;
  if (viewportWidth >= 1600 && state.leftOpen && state.rightOpen && bothPreview >= bothPreviewMinPx) return { ...state, mode: "desktop-both", activeDrawer: null, previewMinPx: bothPreviewMinPx };

  // Shutting both docks is a real choice, not a state to correct: it gives the
  // preview the whole width. Only pick a dock when the creator asked for one.
  const noDock = !state.leftOpen && !state.rightOpen;
  const requestedLeft = state.leftOpen;
  const dockMin = noDock ? 0 : requestedLeft ? leftMinPx : rightMinPx;
  const singlePreview = available - dockMin - (noDock ? 0 : gutterPx);
  const requiredSinglePreview = Math.max(singlePreviewMinPx, available / 2);
  if (viewportWidth >= 1280 && singlePreview >= requiredSinglePreview) return { ...state, mode: "desktop-single", leftOpen: !noDock && requestedLeft, rightOpen: !noDock && !requestedLeft, activeDrawer: null, previewMinPx: singlePreviewMinPx };

  return { ...state, mode: "drawer", leftOpen: false, rightOpen: false, activeDrawer: state.activeDrawer, previewMinPx: 0 };
}
