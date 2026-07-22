import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { TranscriptPanel } from "./TranscriptPanel";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const entries = [
  { segmentId: "segment-1", startSec: 0, endSec: 2, text: "첫 번째 자막" },
  { segmentId: "segment-2", startSec: 2, endSec: 4, text: "두 번째 자막" },
] as const;

describe("TranscriptPanel", () => {
  it("selects and seeks the same segment from the transcript row", () => {
    const onSelectSegment = vi.fn();
    const onSeek = vi.fn();
    render(<TranscriptPanel entries={entries} playbackSec={0} selectedSegmentId={null} onSelectSegment={onSelectSegment} onSeek={onSeek} />);

    fireEvent.click(screen.getByRole("button", { name: "두 번째 자막 대본 선택" }));

    expect(onSelectSegment).toHaveBeenCalledWith("segment-2");
    expect(onSeek).toHaveBeenCalledWith(2);
  });

  it("keeps keyboard navigation out of an active IME composition", () => {
    const onSelectSegment = vi.fn();
    render(<TranscriptPanel entries={entries} playbackSec={0} selectedSegmentId="segment-1" onSelectSegment={onSelectSegment} onSeek={vi.fn()} />);

    const editor = screen.getByRole("textbox", { name: "segment-1 자막 텍스트" });
    fireEvent.keyDown(editor, { key: "ArrowDown", isComposing: true });
    expect(onSelectSegment).not.toHaveBeenCalled();
    fireEvent.keyDown(editor, { key: "ArrowDown" });
    expect(onSelectSegment).toHaveBeenCalledWith("segment-2");
  });

  it("saves only caption text for the selected linked segment", () => {
    const onSaveCaption = vi.fn();
    render(<TranscriptPanel entries={entries} playbackSec={0} selectedSegmentId="segment-1" onSelectSegment={vi.fn()} onSeek={vi.fn()} onSaveCaption={onSaveCaption} />);

    fireEvent.change(screen.getByRole("textbox", { name: "segment-1 자막 텍스트" }), { target: { value: "수정한 자막" } });
    fireEvent.click(screen.getByRole("button", { name: "자막 저장" }));

    expect(onSaveCaption).toHaveBeenCalledWith({ segmentId: "segment-1", text: "수정한 자막" });
  });

  it("locks transcript editing and navigation while a caption save is pending", () => {
    const onSelectSegment = vi.fn();
    const onSeek = vi.fn();
    const onSaveCaption = vi.fn();
    render(<TranscriptPanel entries={entries} isSaving onSaveCaption={onSaveCaption} onSeek={onSeek} onSelectSegment={onSelectSegment} playbackSec={0} selectedSegmentId="segment-1" />);

    const rowButtons = entries.map((entry) => screen.getByRole("button", { name: `${entry.text} 대본 선택` }));
    const editor = screen.getByRole("textbox", { name: "segment-1 자막 텍스트" });
    const saveButton = screen.getByRole("button", { name: "자막 저장" });
    rowButtons.forEach((button) => expect(button).toBeDisabled());
    expect(editor).toBeDisabled();
    expect(saveButton).toBeDisabled();

    fireEvent.click(rowButtons[1]);
    fireEvent.change(editor, { target: { value: "저장 중 입력" } });
    fireEvent.click(saveButton);

    expect(onSelectSegment).not.toHaveBeenCalled();
    expect(onSeek).not.toHaveBeenCalled();
    expect(onSaveCaption).not.toHaveBeenCalled();
  });

  it("mounts no more than 120 transcript rows for a long caption list", () => {
    const longEntries = Array.from({ length: 1_000 }, (_, index) => ({ segmentId: `segment-${index}`, startSec: index, endSec: index + 1, text: `자막 ${index}` }));
    render(<TranscriptPanel entries={longEntries} playbackSec={500} selectedSegmentId={null} onSelectSegment={vi.fn()} onSeek={vi.fn()} />);

    expect(screen.getAllByRole("listitem")).toHaveLength(120);
  });

  it("does not mark an older selection as current while playback is in a narration gap", () => {
    render(<TranscriptPanel entries={[{ segmentId: "segment-1", startSec: 0, endSec: 1, text: "첫 자막" }, { segmentId: "segment-2", startSec: 2, endSec: 3, text: "둘째 자막" }]} playbackSec={1.5} selectedSegmentId="segment-1" onSelectSegment={vi.fn()} onSeek={vi.fn()} />);

    expect(screen.getByRole("button", { name: "첫 자막 대본 선택" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: "둘째 자막 대본 선택" })).not.toHaveAttribute("aria-current");
  });
});
