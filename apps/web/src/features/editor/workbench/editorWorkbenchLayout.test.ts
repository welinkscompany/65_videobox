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

  it("opens with the preview alone so the edit is the largest thing on screen", () => {
    // A creator judging a cut needs the picture, not two reference columns.
    // Both docks are one toolbar click away.
    //
    // 2026-08-17: 캡컷처럼 왼쪽 재료 열을 기본으로 펴는 것은 owner 승인을 받았으나
    // 아직 넣지 않았다 -- 이 파일과 편집 작업판 테스트 13개를 함께 다시 써야 한다.
    const fresh = resolveEditorWorkbenchLayout({ viewportWidth: 1920, availableWorkbenchWidth: 1720, persisted: undefined });
    expect(fresh).toMatchObject({ mode: "desktop-single", leftOpen: false, rightOpen: false });
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

  it("rejects stale persisted state that contains editor identity", () => {
    // Falls back to the default, which is now preview-only.
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1440, availableWorkbenchWidth: 1130, persisted: { ...bothOpen, projectId: "wrong" } })).toMatchObject({ leftOpen: false, rightOpen: false, activeDrawer: null });
  });
});
