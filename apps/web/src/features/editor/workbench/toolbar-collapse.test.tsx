import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { EditorWorkbench } from "./EditorWorkbench";
import { readToolbarCollapsed, writeToolbarCollapsed } from "./editorUiState";

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1000 } as DOMRect);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1920 });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); window.localStorage.clear(); });

const view = { projectId: "project-a", sessionId: "session-a", timelineId: "timeline-a", timelineVersion: "v1", expectedRevision: 1, timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sampleAspectRatio: "1:1", rotation: 0, durationSec: 1 }, tracks: [], captions: [], gaps: [], source: { status: "current" }, playback: { auditionUrls: {}, exactPreview: { status: "unavailable" } }, local: { selectedSegmentId: null, seekSec: 0 } } as const;

/** 편집 작업판 머리(58px)를 접어 미리보기 줄에 높이를 돌려준다(2026-10-02). */
describe("편집 작업판 머리 접기", () => {
  it("접으면 이름표를 숨기고 단추는 남기며, 다시 열어도 기억한다", () => {
    const { unmount } = render(<EditorWorkbench view={view} />);
    const toggle = screen.getByRole("button", { name: "도구줄 접기" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(toggle);

    const header = document.querySelector(".vb-editor-workbench__toolbar");
    expect(header).toHaveAttribute("data-collapsed", "true");
    expect(screen.getByRole("button", { name: "내보내기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "도구줄 펼치기" })).toHaveAttribute("aria-expanded", "false");
    unmount();

    render(<EditorWorkbench view={{ ...view, projectId: "project-b", sessionId: "session-b" }} />);
    expect(screen.getByRole("button", { name: "도구줄 펼치기" })).toBeInTheDocument();
  });

  it("브라우저 저장소가 막혀도 화면이 죽지 않고 이번에는 접힌다", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota exceeded"); });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readToolbarCollapsed()).toBe(false);
    expect(() => writeToolbarCollapsed(true)).not.toThrow();

    render(<EditorWorkbench view={view} />);
    fireEvent.click(screen.getByRole("button", { name: "도구줄 접기" }));

    expect(document.querySelector(".vb-editor-workbench__toolbar")).toHaveAttribute("data-collapsed", "true");
  });

  it("접힌 머리와 접힌 가로·세로 띠는 위아래 여백이 4px이다", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");
    expect(css).toMatch(/\.vb-editor-workbench__toolbar\[data-collapsed="true"\]\s*\{[^}]*padding:\s*var\(--vb-space-1\)/);
    expect(css).toMatch(/\.vb-editor-variants\[data-collapsed="true"\]\s*\{[^}]*padding:\s*var\(--vb-space-1\)/);
  });

  it("낮은 화면(760px 미만)은 접은 채 시작하고, 저장된 선택이 있으면 그것이 이긴다 (2026-10-08)", () => {
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 700 });
    try {
      const first = render(<EditorWorkbench view={view} />);
      expect(document.querySelector(".vb-editor-workbench__toolbar")).toHaveAttribute("data-collapsed", "true");
      first.unmount();

      window.localStorage.setItem("videobox.editor-workbench.toolbar-collapsed", "false");
      render(<EditorWorkbench view={view} />);
      expect(document.querySelector(".vb-editor-workbench__toolbar")).toHaveAttribute("data-collapsed", "false");
    } finally {
      Object.defineProperty(window, "innerHeight", { configurable: true, value: 768 });
    }
  });
});
