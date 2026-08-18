import { describe, expect, it } from "vitest";

import { resolveEditorWorkbenchLayout } from "./editorWorkbenchLayout";

const bothOpen = { leftOpen: true, rightOpen: true, activeDrawer: null, leftSize: 280, rightSize: 320 } as const;

describe("resolveEditorWorkbenchLayout", () => {
  it.each([
    [1920, 1720, "desktop-both", 720],
    [1440, 1130, "desktop-single", 640],
    [1280, 900, "desktop-single", 640],
    [768, 700, "drawer", 0],
    [390, 360, "drawer", 0],
  ] as const)("normalizes %ipx to the permitted density", (viewportWidth, availableWorkbenchWidth, mode, previewMinPx) => {
    expect(resolveEditorWorkbenchLayout({ viewportWidth, availableWorkbenchWidth, persisted: bothOpen })).toMatchObject({ mode, previewMinPx });
  });

  it("keeps both docks closed when the desktop preview would be narrower than 720px", () => {
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1600, availableWorkbenchWidth: 900, persisted: bothOpen })).toMatchObject({ mode: "desktop-single", rightOpen: false, previewMinPx: 640 });
  });

  it("uses a drawer when a single dock cannot preserve max(640, available/2)", () => {
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1280, availableWorkbenchWidth: 800, persisted: bothOpen })).toMatchObject({ mode: "drawer", leftOpen: false, rightOpen: false });
  });

  it.each([1599, 1279])("honors viewport boundary %i", (viewportWidth) => {
    const layout = resolveEditorWorkbenchLayout({ viewportWidth, availableWorkbenchWidth: 1130, persisted: bothOpen });
    expect(layout.mode).toBe(viewportWidth === 1599 ? "desktop-single" : "drawer");
  });

  it("opens with the material column beside the preview, and only that column", () => {
    // 캡컷처럼 재료가 편집기 왼쪽에 늘 붙어 있어야 한다(owner 승인 2026-08-17).
    // 오른쪽까지 함께 펴면 `desktop-both`가 되어 미리보기가 720px 아래로 밀리므로
    // 오른쪽은 툴바 클릭 한 번 거리에 그대로 둔다.
    const fresh = resolveEditorWorkbenchLayout({ viewportWidth: 1920, availableWorkbenchWidth: 1720, persisted: undefined });
    expect(fresh).toMatchObject({ mode: "desktop-single", leftOpen: true, rightOpen: false });
  });

  it("keeps both docks shut when the creator shut them", () => {
    const bothShut = { leftOpen: false, rightOpen: false, activeDrawer: null, leftSize: 280, rightSize: 320 };
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1920, availableWorkbenchWidth: 1720, persisted: bothShut }))
      .toMatchObject({ mode: "desktop-single", leftOpen: false, rightOpen: false });
  });

  it("still honours a dock the creator pinned open", () => {
    const leftOnly = { leftOpen: true, rightOpen: false, activeDrawer: null, leftSize: 280, rightSize: 320 };
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1920, availableWorkbenchWidth: 1720, persisted: leftOnly }))
      .toMatchObject({ leftOpen: true, rightOpen: false });
  });

  it("carries a clamped timeline height through, and treats a missing one as untouched", () => {
    // 두 검증기(editorUiState/여기)가 어긋나면 저장된 높이가 이 fallback에서 조용히
    // 사라진다. 한계 밖 값은 잘라서 받고, 칸이 없는 예전 저장분은 null이다.
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1440, availableWorkbenchWidth: 1130, persisted: { ...bothOpen, timelineRem: 40 } }))
      .toMatchObject({ timelineRem: 32 });
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1440, availableWorkbenchWidth: 1130, persisted: bothOpen }))
      .toMatchObject({ timelineRem: null });
  });

  it("rejects stale persisted state that contains editor identity", () => {
    // 저장된 값이 `bothOpen`이어도 채택하지 않고 기본값(왼쪽만 펴짐)으로 떨어진다.
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1440, availableWorkbenchWidth: 1130, persisted: { ...bothOpen, projectId: "wrong" } })).toMatchObject({ leftOpen: true, rightOpen: false, activeDrawer: null });
  });
});
