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

  it("opens both docks on a 1440px laptop, where the preview still clears 720px", () => {
    // 2026-08-23 실측: 1440px 창에서 작업판 폭이 1360px이었고 미리보기에 856px가
    // 남는데도(필요한 값은 720px) 오른쪽 세부 정보가 접혀 있었다. 관문이
    // `viewportWidth >= 1600`이라 폭 계산과 무관하게 막고 있었던 것 -- 캡컷은
    // 왼쪽 패널·플레이어·오른쪽 세부 정보를 한 화면에 같이 둔다(기록 §2).
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1440, availableWorkbenchWidth: 1360, persisted: bothOpen }))
      .toMatchObject({ mode: "desktop-both", leftOpen: true, rightOpen: true, previewMinPx: 720 });
  });

  it("still falls back to one dock at 1280, where the width genuinely runs out", () => {
    // 관문을 1280으로 낮춰도 좁은 화면이 뚫리지 않는다는 확인 -- 여기서는
    // 남는 폭이 696px라 `bothPreview` 조건이 걸러 낸다.
    expect(resolveEditorWorkbenchLayout({ viewportWidth: 1280, availableWorkbenchWidth: 1200, persisted: bothOpen }))
      .toMatchObject({ mode: "desktop-single", rightOpen: false });
  });

  it("opens with both columns beside the preview, like CapCut", () => {
    // **갱신 이유(2026-08-22).** 이 시험은 `오른쪽은 닫힌 채로 연다`를 고정하고
    // 있었고, 그 근거로 "둘 다 펴면 미리보기가 720px 아래로 밀린다"고 적혀 있었다.
    // **지금 상수로 재보면 틀렸다:**
    //
    //     1720 - leftMin 220 - rightMin 260 - gutter 12x2 = 1216px
    //
    // 720px을 훨씬 넘는다. 캡컷은 소재와 세부 정보가 둘 다 붙어 있고, owner가
    // "캡컷과 완전 비슷하게"라고 했다(2026-08-22).
    //
    // **좁아지면 되돌아간다** -- 바로 위 시험들이 그것을 지킨다(available 900이면
    // `desktop-single`, 800이면 `drawer`). 그러니 여기서 미리 닫아 둘 이유가 없다.
    const fresh = resolveEditorWorkbenchLayout({ viewportWidth: 1920, availableWorkbenchWidth: 1720, persisted: undefined });
    expect(fresh).toMatchObject({ mode: "desktop-both", leftOpen: true, rightOpen: true });
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
