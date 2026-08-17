import { describe, expect, it } from "vitest";

import {
  defaultEditorUiState,
  editorUiStorageKey,
  readEditorUiState,
  writeEditorUiState,
} from "./editorUiState";

describe("editorUiState", () => {
  it("scopes panel state by project and editing session", () => {
    expect(editorUiStorageKey("project/1", "session:1")).not.toBe(
      editorUiStorageKey("project/1", "session:2"),
    );
    expect(editorUiStorageKey("project/1", "session:1")).toContain("project%2F1");
  });

  it("round-trips UI position without storing editing data", () => {
    localStorage.clear();
    writeEditorUiState("project-1", "session-1", {
      leftOpen: false,
      rightOpen: true,
      activeDrawer: "right",
      leftSize: 180,
      rightSize: 410,
    });

    expect(readEditorUiState("project-1", "session-1")).toEqual({
      leftOpen: false,
      rightOpen: true,
      activeDrawer: "right",
      leftSize: 220,
      rightSize: 410,
    });
    expect(localStorage.getItem(editorUiStorageKey("project-1", "session-1"))).not.toContain("segments");
  });

  it("starts a fresh session with the material column already open", () => {
    // 이것이 화면에 실제로 닿는 기본값이다. `resolveEditorWorkbenchLayout`에도 같은
    // 기본값이 한 벌 더 있지만 readEditorUiState가 항상 완전한 값을 돌려주므로
    // 그쪽 fallback은 실행 중에 닿지 않는다 -- 그래서 여기가 승인된 기본값의 자리다.
    localStorage.clear();
    expect(readEditorUiState("project-x", "session-x")).toEqual({
      leftOpen: true,
      rightOpen: false,
      activeDrawer: null,
      leftSize: 280,
      rightSize: 320,
    });
  });

  it("does not leak state between sessions and rejects malformed state", () => {
    localStorage.clear();
    writeEditorUiState("project-1", "session-1", { ...defaultEditorUiState, leftOpen: false });
    expect(readEditorUiState("project-1", "session-2")).toEqual(defaultEditorUiState);
    localStorage.setItem(editorUiStorageKey("project-1", "session-2"), JSON.stringify({ leftOpen: false }));
    expect(readEditorUiState("project-1", "session-2")).toEqual(defaultEditorUiState);
  });
});
