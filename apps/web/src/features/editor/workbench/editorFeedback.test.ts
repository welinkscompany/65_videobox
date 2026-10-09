import { beforeEach, describe, expect, it, vi } from "vitest";

const { loading, success, error } = vi.hoisted(() => ({ loading: vi.fn(), success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: { loading, success, error } }));

import { announceEditorFeedback } from "./editorFeedback";

describe("announceEditorFeedback", () => {
  beforeEach(() => {
    loading.mockClear();
    success.mockClear();
    error.mockClear();
  });

  it("세 종류가 같은 id로 불리고, 진행 중 알림만 사라지지 않는다", () => {
    announceEditorFeedback({ kind: "working", message: "변경 내용을 저장하고 있어요." });
    announceEditorFeedback({ kind: "done", message: "저장했어요." });
    announceEditorFeedback({ kind: "failed", message: "저장하지 못했어요." });
    expect(loading).toHaveBeenCalledWith("변경 내용을 저장하고 있어요.", { id: "editor-feedback", duration: Infinity });
    expect(success).toHaveBeenCalledWith("저장했어요.", { id: "editor-feedback", duration: 2000 });
    expect(error).toHaveBeenCalledWith("저장하지 못했어요.", { id: "editor-feedback", duration: 2000 });
  });

  it("id를 주면 그 id로 부른다", () => {
    announceEditorFeedback({ kind: "working", message: "a", id: "edit-7" });
    expect(loading).toHaveBeenCalledWith("a", { id: "edit-7", duration: Infinity });
  });
});
