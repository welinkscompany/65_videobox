import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { RightDock } from "./RightDock";
import type { RightDockProposal } from "./rightDockTypes";

afterEach(cleanup);

const proposal: RightDockProposal = {
  proposalId: "proposal-1",
  status: "ready",
  candidates: [
    { candidateId: "candidate-1", visibleReferenceCode: "B-001", mediaType: "broll", previewUrl: null },
    { candidateId: "candidate-2", visibleReferenceCode: "B-002", mediaType: "broll", previewUrl: null },
  ],
} as const;

function PersistentDock() {
  const [draft, setDraft] = useState("");
  return <RightDock
    draft={draft}
    onDraftChange={setDraft}
    proposal={proposal}
    messages={[{ id: "assistant-1", userText: "B-roll을 추천해 줘", assistantText: "두 가지를 준비했어요." }]}
    inspectorTargets={[{ id: "segment-1", label: "세그먼트 1", kind: "caption" }]}
  />;
}

describe("RightDock", () => {
  it("preserves the composer, selected candidate, and conversation scroll while Inspector opens and closes", () => {
    render(<PersistentDock />);
    const composer = screen.getByLabelText("유진에게 요청하기");
    const history = screen.getByRole("log", { name: "유진 대화" });
    fireEvent.change(composer, { target: { value: "다음 추천도 보여 줘" } });
    fireEvent.click(screen.getByRole("radio", { name: "B-002 선택" }));
    Object.defineProperty(history, "scrollTop", { configurable: true, writable: true, value: 72 });

    fireEvent.click(screen.getByRole("button", { name: "Inspector 열기" }));
    expect(screen.getByRole("region", { name: "Inspector" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspector 닫기" }));

    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("다음 추천도 보여 줘");
    expect(screen.getByRole("radio", { name: "B-002 선택" })).toBeChecked();
    expect(screen.getByRole("log", { name: "유진 대화" }).scrollTop).toBe(72);
  });

  it("keeps manual editing available with creator-safe copy when Eugene is blocked", () => {
    const onManualEdit = vi.fn();
    render(<RightDock state="blocked" draft="" onDraftChange={vi.fn()} onManualEdit={onManualEdit} />);

    expect(screen.getByText("유진이 지금 추천을 만들 수 없어요. 직접 골라 계속 편집할 수 있어요.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "직접 편집하기" }));
    expect(onManualEdit).toHaveBeenCalledOnce();
  });

  it("never mounts an audio or video player and only exposes explicit apply for a ready proposal", () => {
    const onApplyProposal = vi.fn();
    const { container } = render(<RightDock draft="" onDraftChange={vi.fn()} proposal={proposal} onApplyProposal={onApplyProposal} />);

    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "선택한 추천 적용" }));
    expect(onApplyProposal).toHaveBeenCalledWith("proposal-1", ["candidate-1"]);
  });
});
