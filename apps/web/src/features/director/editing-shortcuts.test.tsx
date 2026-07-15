import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useEditingShortcuts } from "./useEditingShortcuts";

function ShortcutHarness({ onUndo, onRedo }: { onUndo: () => void; onRedo: () => void }) {
  useEditingShortcuts({ onUndo, onRedo });
  return <><input aria-label="caption" /><button>canvas</button><div contentEditable aria-label="card" /></>;
}

describe("useEditingShortcuts", () => {
  it("Ctrl/Cmd undo-redo를 처리하지만 한글 IME와 editable target에서는 가로채지 않는다", () => {
    const onUndo = vi.fn(); const onRedo = vi.fn();
    const { container } = render(<ShortcutHarness onUndo={onUndo} onRedo={onRedo} />);
    const input = container.querySelector("input")!;
    const canvas = container.querySelector("button")!;
    const editable = container.querySelector("[contenteditable]")!;
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: "z", ctrlKey: true, isComposing: true });
    fireEvent.keyDown(input, { key: "z", ctrlKey: true });
    fireEvent.keyDown(editable, { key: "z", metaKey: true });
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(canvas, { key: "z", ctrlKey: true });
    fireEvent.keyDown(canvas, { key: "z", ctrlKey: true, shiftKey: true });
    fireEvent.keyDown(canvas, { key: "y", metaKey: true });
    expect(onUndo).toHaveBeenCalledTimes(1);
    expect(onRedo).toHaveBeenCalledTimes(2);
  });
});
