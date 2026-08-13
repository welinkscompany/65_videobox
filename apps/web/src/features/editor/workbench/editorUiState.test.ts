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

  it("does not leak state between sessions and rejects malformed state", () => {
    localStorage.clear();
    writeEditorUiState("project-1", "session-1", { ...defaultEditorUiState, leftOpen: false });
    expect(readEditorUiState("project-1", "session-2")).toEqual(defaultEditorUiState);
    localStorage.setItem(editorUiStorageKey("project-1", "session-2"), JSON.stringify({ leftOpen: false }));
    expect(readEditorUiState("project-1", "session-2")).toEqual(defaultEditorUiState);
  });
});
