import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { YujinPanel } from "./YujinPanel";
import type { RightDockEditingProposal } from "./rightDockTypes";

afterEach(cleanup);

/** 대부분의 시험은 이미 펼쳐진 패널을 본다 -- 닫힌 상태(알약 버튼) 자체를
 *  다루는 시험은 따로 있다. */
function renderOpen(extraProps: Partial<React.ComponentProps<typeof YujinPanel>> = {}) {
  return render(<YujinPanel
    open
    onOpenChange={vi.fn()}
    draft=""
    onDraftChange={vi.fn()}
    {...extraProps}
  />);
}

describe("YujinPanel", () => {
  it("shows a floating toggle button when closed, and opens on click", () => {
    // 캡컷 EditPilot처럼(owner 지시 2026-08-30, `docs/reference/capcut-observed-2026-08-22.ko.md`
    // §7) 속성/추천 도크와 무관하게 화면 구석에 뜬다. 닫혀 있을 때는 알약
    // 버튼, 열면 대화 패널로 바뀐다.
    function Persistent() {
      const [open, setOpen] = useState(false);
      return <YujinPanel open={open} onOpenChange={setOpen} draft="" onDraftChange={vi.fn()} />;
    }
    render(<Persistent />);

    expect(screen.queryByRole("region", { name: "유진" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "유진" }));

    expect(screen.getByRole("region", { name: "유진" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "유진 닫기" }));

    expect(screen.queryByRole("region", { name: "유진" })).toBeNull();
    expect(screen.getByRole("button", { name: "유진" })).toBeInTheDocument();
  });

  it("shows conversation starters that fill and focus the composer without sending", () => {
    const onDraftChange = vi.fn();
    const onSendMessage = vi.fn();
    const onStart = vi.fn();
    const onManualEdit = vi.fn();
    renderOpen({
      onDraftChange,
      onSendMessage,
      onStart,
      onManualEdit,
      state: "idle",
      runState: { kind: "idle" },
    });

    expect(screen.getByRole("group", { name: "대화 스타터" })).toBeInTheDocument();
    for (const label of [
      "이 장면에 어울리는 B-roll 추천해 줘",
      "현재 편집 흐름 점검해 줘",
      "자막을 더 간결하게 다듬어 줘",
      "세로 영상용으로 바꿀 부분 찾아 줘",
    ]) {
      expect(screen.getByRole("button", { name: label })).toBeVisible();
    }
    const starter = screen.getByRole("button", { name: "이 장면에 어울리는 B-roll 추천해 줘" });
    expect(starter).toBeVisible();

    fireEvent.click(starter);

    expect(onDraftChange).toHaveBeenCalledWith("이 장면에 어울리는 B-roll 추천해 줘");
    expect(onSendMessage).not.toHaveBeenCalled();
    expect(onStart).not.toHaveBeenCalled();
    expect(onManualEdit).not.toHaveBeenCalled();
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveFocus();
  });

  it("shows a CapCut-style completion checklist after Yujin applies something", () => {
    // 캡컷 EditPilot이 실행하면 "모든 작업 완료 1/1"과 실행한 항목을 목록으로
    // 남긴다(`capcut-observed` 기록 §6). owner 지시 2026-08-22: "유진 대화창에
    // 완료된 작업목록은 만들자."
    renderOpen({
      messages: [
        { id: "message-1", role: "user", text: "첫 장면에 산책 영상 넣어 줘" },
        { id: "message-2", role: "assistant", text: "산책 영상으로 채울게요." },
      ],
      completions: [
        {
          id: "completion-1",
          appliedAt: "2026-08-22T00:00:00Z",
          items: [{ label: "산책 영상", sceneLabel: "1번째 장면" }],
        },
      ],
    });

    const completion = screen.getByRole("status", { name: /모든 작업 완료/ });
    expect(completion).toHaveTextContent("모든 작업 완료");
    expect(completion).toHaveTextContent("1/1");
    expect(completion).toHaveTextContent("1번째 장면 · 산책 영상");
  });

  it("says nothing has run yet when there is no completion, instead of an empty checklist", () => {
    renderOpen({
      messages: [{ id: "message-1", role: "user", text: "요청" }],
      completions: [],
    });

    expect(screen.queryByRole("status", { name: /모든 작업 완료/ })).not.toBeInTheDocument();
  });

  it("hides conversation starters once a conversation or proposal exists", () => {
    const { rerender } = renderOpen({
      messages: [{ id: "message-1", role: "user", text: "요청" }],
    });

    expect(screen.queryByRole("group", { name: "대화 스타터" })).not.toBeInTheDocument();

    rerender(<YujinPanel open onOpenChange={vi.fn()} draft="" onDraftChange={vi.fn()} proposal={{ proposalId: "p", status: "ready", baseSessionRevision: 1, currentRevision: 1, candidates: [] }} />);

    expect(screen.queryByRole("group", { name: "대화 스타터" })).not.toBeInTheDocument();

    rerender(<YujinPanel open onOpenChange={vi.fn()} draft="" onDraftChange={vi.fn()} state="error" runState={{ kind: "idle" }} />);

    expect(screen.queryByRole("group", { name: "대화 스타터" })).not.toBeInTheDocument();

    rerender(<YujinPanel open onOpenChange={vi.fn()} draft="" onDraftChange={vi.fn()} runState={{ kind: "unavailable", message: "연결할 수 없어요." }} />);

    expect(screen.queryByRole("group", { name: "대화 스타터" })).not.toBeInTheDocument();
  });

  it("disables conversation starters when the composer is disabled", () => {
    renderOpen({ composerDisabled: true });

    expect(screen.getByRole("button", { name: "이 장면에 어울리는 B-roll 추천해 줘" })).toBeDisabled();
  });

  it("re-asks by itself when the recommendation goes stale while the creator is looking at it", async () => {
    // 편집본이 바뀌면 추천이 무효가 된다(백엔드가 7군데에서 지키는 계약이라 그건
    // 그대로 둔다). 문제는 그다음이다 -- 죽은 카드와 단추만 남고, 창작자가 그걸
    // 눈치채고 눌러야 대화가 이어진다. 보고 있을 때는 대신 물어본다. 패널이
    // 닫혀 있어도(알약 버튼만 보여도) 이 효과는 계속 돈다 -- 도크와 달리
    // 이 컴포넌트는 늘 마운트돼 있다.
    const onRefreshProposal = vi.fn();
    renderOpen({
      proposal: { proposalId: "p1", status: "ready", baseSessionRevision: 22, currentRevision: 31, candidates: [] } as never,
      onRefreshProposal,
    });

    await waitFor(() => expect(onRefreshProposal).toHaveBeenCalledTimes(1));
  });

  it("does not keep re-asking the same stale revision over and over", async () => {
    // 다시 묻는 것은 로컬 모델을 한 번 돌리는 일이다. 같은 편집본에서 두 번
    // 물으면 답은 같고 시간만 쓴다.
    const onRefreshProposal = vi.fn();
    const proposal = { proposalId: "p1", status: "ready", baseSessionRevision: 22, currentRevision: 31, candidates: [] } as never;
    const rendered = renderOpen({ proposal, onRefreshProposal });
    await waitFor(() => expect(onRefreshProposal).toHaveBeenCalledTimes(1));

    rendered.rerender(<YujinPanel open onOpenChange={vi.fn()} draft="다른 초안" onDraftChange={vi.fn()} proposal={proposal} onRefreshProposal={onRefreshProposal} />);

    expect(onRefreshProposal).toHaveBeenCalledTimes(1);
  });

  it("preserves the composer and conversation scroll while closing and reopening", () => {
    function Persistent() {
      const [open, setOpen] = useState(true);
      const [draft, setDraft] = useState("");
      const [conversationScroll, setConversationScroll] = useState({ key: "route-a", top: 0, pinnedToBottom: true });
      return <YujinPanel
        open={open}
        onOpenChange={setOpen}
        draft={draft}
        onDraftChange={setDraft}
        conversationScroll={conversationScroll}
        onConversationScrollChange={setConversationScroll}
      />;
    }
    render(<Persistent />);
    const composer = screen.getByLabelText("유진에게 요청하기");
    fireEvent.change(composer, { target: { value: "다음 추천도 보여 줘" } });
    const history = screen.getByRole("log", { name: "유진 대화" });
    // 닫으면 이 로그의 DOM이 사라졌다가 열 때 새로 생긴다 -- 그때 되살리는
    // 값은 raw DOM이 아니라 `conversationScroll` 상태다. 그러니 `onScroll`이
    // 실제로 그 상태를 갱신하도록 스크롤 이벤트로 흉내 낸다(jsdom은 레이아웃을
        // 안 재므로 scrollHeight·clientHeight도 같이 박아 둔다).
    Object.defineProperty(history, "scrollTop", { configurable: true, writable: true, value: 72 });
    Object.defineProperty(history, "scrollHeight", { configurable: true, writable: true, value: 1000 });
    Object.defineProperty(history, "clientHeight", { configurable: true, writable: true, value: 800 });
    fireEvent.scroll(history);

    fireEvent.click(screen.getByRole("button", { name: "유진 닫기" }));
    expect(screen.queryByRole("log", { name: "유진 대화" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "유진" }));

    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("다음 추천도 보여 줘");
    expect(screen.getByRole("log", { name: "유진 대화" }).scrollTop).toBe(72);
  });

  it("offers to take a pasted script, so the editor is reachable without the interview", () => {
    // 2026-08-19 owner: "유진이랑 대화하면서 대본을 복붙하면 유진이가 그걸 보고
    // 편집기에 붙여 줬으면". 지금은 대본이 `/plan`의 문답형 인터뷰로만 들어간다.
    // 긴 글을 붙여 넣으면 그것을 대본으로 받는 길을 준다. **확정은 사람이 한다** --
    // 이 단추는 대본을 만들 뿐 장면을 바로 만들지 않는다.
    const onUseDraftAsScript = vi.fn();
    const script = "안녕하세요. 오늘은 제주 바다를 소개합니다. 두 번째 문장입니다.";
    renderOpen({ draft: script, onUseDraftAsScript });

    fireEvent.click(screen.getByRole("button", { name: "이 글을 대본으로 쓰기" }));

    expect(onUseDraftAsScript).toHaveBeenCalledWith(script);
  });

  it("offers the same script button on Yujin's own answer, so nobody copies it back into the box", () => {
    // 2026-08-20 owner 실측: 유진에게 대본을 받아도 **손으로 복사해서 입력칸에
    // 도로 붙여넣어야** 단추가 떴다. 복사·붙여넣기 수고만 없앤다 --
    // 확정은 여전히 사람이 한다(2026-08-16 승인 기록).
    const onUseDraftAsScript = vi.fn();
    const script = "안녕하세요. 오늘은 제주 바다를 소개합니다. 두 번째 문장입니다.";
    renderOpen({
      onUseDraftAsScript,
      messages: [
        { id: "user-1", role: "user", text: "60초 대본 하나 써 줘" },
        { id: "assistant-1", role: "assistant", text: script },
      ],
    });

    fireEvent.click(screen.getByRole("button", { name: `이 답을 대본으로 쓰기 — ${script.slice(0, 20)}…` }));

    expect(onUseDraftAsScript).toHaveBeenCalledWith(script);
  });

  it("tells two Yujin answers apart, so the button can be reached by voice", () => {
    // 같은 이름의 단추가 여러 개면 음성으로 고를 수 없다. 보이는 글자는 짧게
    // 두고 접근 이름 뒤에 그 답의 첫머리를 붙인다(타임라인 클립과 같은 방식).
    const first = "첫 번째 대본입니다. 제주 바다에서 시작해 오름으로 올라갑니다.";
    const second = "두 번째 대본입니다. 한라산에서 시작해 바다로 내려갑니다.";
    renderOpen({
      onUseDraftAsScript: vi.fn(),
      messages: [
        { id: "assistant-1", role: "assistant", text: first },
        { id: "assistant-2", role: "assistant", text: second },
      ],
    });

    expect(screen.getByRole("button", { name: `이 답을 대본으로 쓰기 — ${first.slice(0, 20)}…` })).toBeVisible();
    expect(screen.getByRole("button", { name: `이 답을 대본으로 쓰기 — ${second.slice(0, 20)}…` })).toBeVisible();
  });

  it("does not offer the script button on a short answer or on what the creator typed", () => {
    // 짧은 답은 대본이 아니라 대꾸다. 그리고 내가 쓴 말은 유진의 대본이 아니다.
    renderOpen({
      onUseDraftAsScript: vi.fn(),
      messages: [
        { id: "assistant-1", role: "assistant", text: "네, 알겠습니다." },
        { id: "user-1", role: "user", text: "안녕하세요. 오늘은 제주 바다를 소개합니다. 두 번째 문장입니다." },
      ],
    });

    expect(screen.queryByRole("button", { name: /대본으로 쓰기/ })).toBeNull();
  });

  it("does not offer the script button for a short question", () => {
    // 짧은 한 줄은 요청이지 대본이 아니다. 늘 띄우면 단추가 소음이 된다.
    const onUseDraftAsScript = vi.fn();
    renderOpen({ draft: "B-roll 추천해 줘", onUseDraftAsScript });

    expect(screen.queryByRole("button", { name: "이 글을 대본으로 쓰기" })).toBeNull();
  });

  it("keeps manual editing available without clearing unavailable history", () => {
    const onManualEdit = vi.fn();
    renderOpen({
      state: "blocked",
      runState: { kind: "unavailable", message: "유진의 답을 받지 못했어요." },
      onManualEdit,
      messages: [{ id: "user-1", role: "user", text: "요청 내용" }],
    });

    expect(screen.getByText("유진의 답을 받지 못했어요.")).toBeInTheDocument();
    expect(screen.getByText("요청 내용")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "유진 없이 계속 편집" }));
    expect(onManualEdit).toHaveBeenCalledOnce();
    expect(screen.getByText("유진의 답을 받지 못했어요.")).toBeInTheDocument();
    expect(screen.getByText("요청 내용")).toBeInTheDocument();
  });

  it("announces only terminal state and never turns streamed token updates into live announcements", () => {
    const rendered = renderOpen({
      messages: [{ id: "assistant-1", role: "assistant", text: "첫" }],
      runState: { kind: "streaming", runId: "run-1", routeEpoch: 1, text: "첫" },
    });

    expect(screen.getByRole("log", { name: "유진 대화" })).not.toHaveAttribute("aria-live");
    expect(screen.queryByRole("status")).toBeNull();

    rendered.rerender(<YujinPanel
      open onOpenChange={vi.fn()} draft="" onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "첫 답" }]}
      runState={{ kind: "streaming", runId: "run-1", routeEpoch: 1, text: "첫 답" }}
    />);
    expect(screen.queryByRole("status")).toBeNull();

    rendered.rerender(<YujinPanel
      open onOpenChange={vi.fn()} draft="" onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "첫 답" }]}
      runState={{ kind: "complete", runId: "run-1" }}
    />);
    expect(screen.getByRole("status")).toHaveTextContent("유진 답변을 받았어요.");
    expect(screen.getAllByRole("status")).toHaveLength(1);

    rendered.rerender(<YujinPanel
      open onOpenChange={vi.fn()} draft="" onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "첫 답" }]}
      runState={{ kind: "unavailable", message: "유진의 답을 받지 못했어요." }}
    />);
    expect(screen.getByRole("status")).toHaveTextContent("유진의 답을 받지 못했어요.");
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("announces completion once while showing a later durable sync warning outside the live region", async () => {
    const rendered = renderOpen({
      messages: [{ id: "assistant-1", role: "assistant", text: "완료된 답" }],
      runState: { kind: "streaming", runId: "run-1", routeEpoch: 1, text: "완료된 답" },
    });
    const announcements: string[] = [];
    let previousAnnouncement = "";
    const observer = new MutationObserver(() => {
      const announcement = rendered.container
        .querySelector('[role="status"]')
        ?.textContent
        ?.trim() ?? "";
      if (announcement && announcement !== previousAnnouncement) {
        announcements.push(announcement);
        previousAnnouncement = announcement;
      }
    });
    observer.observe(rendered.container, {
      childList: true,
      characterData: true,
      subtree: true,
    });

    rendered.rerender(<YujinPanel
      open onOpenChange={vi.fn()} draft="" onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "완료된 답" }]}
      runState={{ kind: "complete", runId: "run-1" }}
    />);
    await waitFor(() => expect(announcements).toEqual(["유진 답변을 받았어요."]));

    rendered.rerender(<YujinPanel
      open onOpenChange={vi.fn()} draft="" onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "완료된 답" }]}
      runState={{
        kind: "complete",
        runId: "run-1",
        syncWarning: "대화 저장 상태를 확인하지 못했어요.",
      }}
    />);

    expect(screen.getByRole("status")).toHaveTextContent("유진 답변을 받았어요.");
    expect(screen.getByRole("status")).not.toHaveTextContent("대화 저장 상태");
    expect(screen.getByText("대화 저장 상태를 확인하지 못했어요.")).toBeVisible();
    await Promise.resolve();
    observer.disconnect();
    expect(announcements).toEqual(["유진 답변을 받았어요."]);
  });
});

describe("대화형 편집안", () => {
  it("검토 창에서 미리보기와 적용을 분리하고 후속 질문은 초안에만 넣는다", () => {
    const onDraftChange = vi.fn();
    const onPreviewEditingProposal = vi.fn();
    const onApplyEditingProposal = vi.fn();
    renderOpen({
      onDraftChange,
      messages: [{ id: "assistant-1", role: "assistant", text: "속도를 조절할 수 있어요." }],
      editingProposal: { proposalId: "editing-1", summary: "2번 장면 · 8초 → 4초", operationSummaries: ["2배로 속도를 바꿔요."], followUpQuestions: ["자막도 짧게 할까요?"], previewTarget: { segmentId: "segment-2", startSec: 8, endSec: 16 }, isApplying: false, error: null },
      onPreviewEditingProposal,
      onApplyEditingProposal,
    });

    fireEvent.click(screen.getByRole("button", { name: "편집안 보기" }));
    expect(screen.getByRole("dialog", { name: "편집안" })).toHaveTextContent("아직 적용되지 않았어요");
    fireEvent.click(screen.getByRole("button", { name: "이 구간 미리보기" }));
    fireEvent.click(screen.getByRole("button", { name: "이 편집안 적용" }));
    fireEvent.click(screen.getByRole("button", { name: "자막도 짧게 할까요?" }));

    expect(onPreviewEditingProposal).toHaveBeenCalledOnce();
    expect(onApplyEditingProposal).toHaveBeenCalledOnce();
    expect(onDraftChange).toHaveBeenCalledWith("자막도 짧게 할까요?");
  });
});

describe("편집안 미리보기", () => {
  // 이 창의 미리보기는 **아직 적용하지 않은 후보 결과**를 보여 준다.
  // 2026-08-26까지는 저장된 편집본을 보여 주고 있었다 -- 창작자는 바뀐 결과를
  // 확인했다고 믿었지만 실제로는 바뀌기 전 영상을 본 것이다.
  const proposalWithPreview = (
    preview: NonNullable<RightDockEditingProposal["preview"]>,
  ): RightDockEditingProposal => ({
    proposalId: "editing-1",
    summary: "2번 장면 · 8초 → 4초",
    operationSummaries: ["2배로 속도를 바꿔요."],
    followUpQuestions: [],
    previewTarget: { segmentId: "segment-2", startSec: 8, endSec: 16 },
    isApplying: false,
    error: null,
    preview,
  });

  function openDialog(preview: NonNullable<RightDockEditingProposal["preview"]>) {
    renderOpen({
      messages: [{ id: "assistant-1", role: "assistant", text: "속도를 조절할 수 있어요." }],
      editingProposal: proposalWithPreview(preview),
      onPreviewEditingProposal: vi.fn(),
      onApplyEditingProposal: vi.fn(),
    });
    fireEvent.click(screen.getByRole("button", { name: "편집안 보기" }));
    return screen.getByRole("dialog", { name: "편집안" });
  }

  it("만드는 중에는 영상 대신 진행 상태를 말한다", () => {
    const dialog = openDialog({ kind: "working", message: "편집안 미리보기를 만들고 있어요." });

    expect(dialog).toHaveTextContent("편집안 미리보기를 만들고 있어요.");
    expect(within(dialog).queryByLabelText("편집안 미리보기")).toBeNull();
  });

  it("준비되면 후보 결과 영상을 보여 준다", () => {
    const dialog = openDialog({ kind: "ready", videoUrl: "/api/projects/project-a/proposal-previews/pp-1/content" });

    expect(within(dialog).getByLabelText("편집안 미리보기")).toHaveAttribute(
      "src",
      "/api/projects/project-a/proposal-previews/pp-1/content",
    );
  });

  it("편집본이 바뀌었으면 낡은 영상을 보여 주지 않는다", () => {
    const dialog = openDialog({ kind: "unavailable", message: "편집본이 바뀌었어요. 새 편집안을 받아 보세요." });

    expect(dialog).toHaveTextContent("편집본이 바뀌었어요. 새 편집안을 받아 보세요.");
    expect(within(dialog).queryByLabelText("편집안 미리보기")).toBeNull();
  });
});
