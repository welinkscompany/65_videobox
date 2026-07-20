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

  it("rejects stale persisted state that contains editor identity", () => {
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1440, availableWorkbenchWidth: 1130, persisted: { ...bothOpen, projectId: "wrong" } })).toMatchObject({ leftOpen: true, rightOpen: false, activeDrawer: null });
  });
});
