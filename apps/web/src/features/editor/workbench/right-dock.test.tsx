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
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<readonly string[]>(["candidate-1"]);
  const [conversationScroll, setConversationScroll] = useState({ key: "route-a", top: 0, pinnedToBottom: true });
  return <RightDock
    draft={draft}
    onDraftChange={setDraft}
    proposal={proposal}
    messages={[
      { id: "user-1", role: "user", text: "B-roll을 추천해 줘" },
      { id: "assistant-1", role: "assistant", text: "두 가지를 준비했어요." },
    ]}
    selectedCandidateIds={selectedCandidateIds}
    onSelectedCandidateIdsChange={setSelectedCandidateIds}
    conversationScroll={conversationScroll}
    onConversationScrollChange={setConversationScroll}
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

    fireEvent.click(screen.getByRole("button", { name: "편집 항목 열기" }));
    expect(screen.getByRole("region", { name: "편집 항목" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "편집 항목 닫기" }));

    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("다음 추천도 보여 줘");
    expect(screen.getByRole("radio", { name: "B-002 선택" })).toBeChecked();
    expect(screen.getByRole("log", { name: "유진 대화" }).scrollTop).toBe(72);
  });

  it("is a controlled adapter for candidate selection and restored conversation scroll", () => {
    const onSelectedCandidateIdsChange = vi.fn();
    const onConversationScrollChange = vi.fn();
    const rendered = render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      proposal={proposal}
      selectedCandidateIds={["candidate-2"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
      conversationScroll={{ key: "route-a", top: 83, pinnedToBottom: false }}
      onConversationScrollChange={onConversationScrollChange}
    />);

    expect(screen.getByRole("radio", { name: "B-002 선택" })).toBeChecked();
    expect(screen.getByRole("log", { name: "유진 대화" }).scrollTop).toBe(83);
    fireEvent.click(screen.getByRole("radio", { name: "B-001 선택" }));
    expect(onSelectedCandidateIdsChange).toHaveBeenCalledWith(["candidate-1"]);
    expect(screen.getByRole("radio", { name: "B-002 선택" })).toBeChecked();

    rendered.rerender(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      proposal={proposal}
      selectedCandidateIds={["candidate-1"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
      conversationScroll={{ key: "route-a", top: 12, pinnedToBottom: false }}
      onConversationScrollChange={onConversationScrollChange}
    />);
    expect(screen.getByRole("radio", { name: "B-001 선택" })).toBeChecked();
    expect(screen.getByRole("log", { name: "유진 대화" }).scrollTop).toBe(12);
  });

  it("keeps manual editing available without clearing unavailable history", () => {
    const onManualEdit = vi.fn();
    render(<RightDock
      state="blocked"
      runState={{ kind: "unavailable", message: "유진의 답을 받지 못했어요." }}
      draft=""
      onDraftChange={vi.fn()}
      onManualEdit={onManualEdit}
      messages={[{ id: "user-1", role: "user", text: "요청 내용" }]}
    />);

    expect(screen.getByText("유진의 답을 받지 못했어요.")).toBeInTheDocument();
    expect(screen.getByText("요청 내용")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Yujin 없이 계속 편집" }));
    expect(onManualEdit).toHaveBeenCalledOnce();
    expect(screen.getByText("유진의 답을 받지 못했어요.")).toBeInTheDocument();
    expect(screen.getByText("요청 내용")).toBeInTheDocument();
  });

  it("never mounts an audio or video player and only exposes explicit apply for a ready proposal", () => {
    const onApplyProposal = vi.fn();
    const { container } = render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      proposal={proposal}
      selectedCandidateIds={["candidate-1"]}
      onSelectedCandidateIdsChange={vi.fn()}
      onApplyProposal={onApplyProposal}
    />);

    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "선택한 추천 적용" }));
    expect(onApplyProposal).toHaveBeenCalledWith("proposal-1", ["candidate-1"]);
  });
});
