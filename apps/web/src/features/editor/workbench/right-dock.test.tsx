import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { RightDock } from "./RightDock";
import type { RightDockEditingProposal, RightDockProposal } from "./rightDockTypes";

afterEach(cleanup);

const proposal: RightDockProposal = {
  proposalId: "proposal-1",
  status: "ready",
  baseSessionRevision: 7,
  currentRevision: 7,
  candidates: [
    {
      candidateId: "candidate-1", visibleReferenceCode: "B-001", mediaType: "broll", previewUrl: null,
      kind: "broll", sourceMediaKind: "broll_video", targetSegmentId: "segment-1",
      previewSummary: "첫 장면을 산책 영상으로 채웁니다.", supportedControls: { fit: "crop" },
      availability: "actionable", reviewStatus: "approved", actionable: true,
    },
    {
      candidateId: "candidate-2", visibleReferenceCode: "B-002", mediaType: "broll", previewUrl: null,
      kind: "broll", sourceMediaKind: "raw_video", targetSegmentId: "segment-1",
      previewSummary: "첫 장면을 원본 영상으로 채웁니다.", supportedControls: { fit: "fit" },
      availability: "actionable", reviewStatus: "approved", actionable: true,
    },
  ],
} as const;

/** 빈 장면 둘, 첫 장면에는 후보가 둘. 서버가 한 번에 받는 추천이다. */
const multiSceneProposal: RightDockProposal = {
  proposalId: "proposal-gaps",
  status: "ready",
  baseSessionRevision: 3,
  currentRevision: 3,
  allowsMultipleSelection: true,
  candidates: [
    {
      candidateId: "gap-1", visibleReferenceCode: "P02-B-01", displayName: "하늘 영상", mediaType: "broll", previewUrl: null,
      kind: "broll", sourceMediaKind: "broll", targetSegmentId: "segment-1", targetSceneLabel: "1번째 장면",
      previewSummary: "요약", supportedControls: {}, availability: "actionable", reviewStatus: "approved", actionable: true,
    },
    {
      candidateId: "gap-1-alt", visibleReferenceCode: "P02-B-02", displayName: "구름 영상", mediaType: "broll", previewUrl: null,
      kind: "broll", sourceMediaKind: "broll", targetSegmentId: "segment-1", targetSceneLabel: "1번째 장면",
      previewSummary: "요약", supportedControls: {}, availability: "actionable", reviewStatus: "approved", actionable: true,
    },
    {
      candidateId: "gap-2", visibleReferenceCode: "P02-B-03", displayName: "바다 영상", mediaType: "broll", previewUrl: null,
      kind: "broll", sourceMediaKind: "broll", targetSegmentId: "segment-2", targetSceneLabel: "2번째 장면",
      previewSummary: "요약", supportedControls: {}, availability: "actionable", reviewStatus: "approved", actionable: true,
    },
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
  it("shows conversation starters that fill and focus the composer without sending", () => {
    const onDraftChange = vi.fn();
    const onSendMessage = vi.fn();
    const onStart = vi.fn();
    const onApplyProposal = vi.fn();
    const onManualEdit = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={onDraftChange}
      onSendMessage={onSendMessage}
      onStart={onStart}
      onApplyProposal={onApplyProposal}
      onManualEdit={onManualEdit}
      state="idle"
      runState={{ kind: "idle" }}
    />);

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
    expect(onApplyProposal).not.toHaveBeenCalled();
    expect(onManualEdit).not.toHaveBeenCalled();
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveFocus();
  });

  it("shows a CapCut-style completion checklist after Yujin applies something", () => {
    // 캡컷 EditPilot이 실행하면 "모든 작업 완료 1/1"과 실행한 항목을 목록으로
    // 남긴다(`capcut-observed` 기록 §6). owner 지시 2026-08-22: "유진 대화창에
    // 완료된 작업목록은 만들자."
    render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      messages={[
        { id: "message-1", role: "user", text: "첫 장면에 산책 영상 넣어 줘" },
        { id: "message-2", role: "assistant", text: "산책 영상으로 채울게요." },
      ]}
      completions={[
        {
          id: "completion-1",
          appliedAt: "2026-08-22T00:00:00Z",
          items: [{ label: "산책 영상", sceneLabel: "1번째 장면" }],
        },
      ]}
    />);

    const completion = screen.getByRole("status", { name: /모든 작업 완료/ });
    expect(completion).toHaveTextContent("모든 작업 완료");
    expect(completion).toHaveTextContent("1/1");
    expect(completion).toHaveTextContent("1번째 장면 · 산책 영상");
  });

  it("says nothing has run yet when there is no completion, instead of an empty checklist", () => {
    render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      messages={[{ id: "message-1", role: "user", text: "요청" }]}
      completions={[]}
    />);

    expect(screen.queryByRole("status", { name: /모든 작업 완료/ })).not.toBeInTheDocument();
  });

  it("hides conversation starters once a conversation or proposal exists", () => {
    const { rerender } = render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      messages={[{ id: "message-1", role: "user", text: "요청" }]}
    />);

    expect(screen.queryByRole("group", { name: "대화 스타터" })).not.toBeInTheDocument();

    rerender(<RightDock draft="" onDraftChange={vi.fn()} proposal={proposal} />);

    expect(screen.queryByRole("group", { name: "대화 스타터" })).not.toBeInTheDocument();

    rerender(<RightDock draft="" onDraftChange={vi.fn()} state="error" runState={{ kind: "idle" }} />);

    expect(screen.queryByRole("group", { name: "대화 스타터" })).not.toBeInTheDocument();

    rerender(<RightDock draft="" onDraftChange={vi.fn()} runState={{ kind: "unavailable", message: "연결할 수 없어요." }} />);

    expect(screen.queryByRole("group", { name: "대화 스타터" })).not.toBeInTheDocument();
  });

  it("disables conversation starters when the composer is disabled", () => {
    render(<RightDock draft="" onDraftChange={vi.fn()} composerDisabled />);

    expect(screen.getByRole("button", { name: "이 장면에 어울리는 B-roll 추천해 줘" })).toBeDisabled();
  });

  it("shows the selected clip's properties first and already open", () => {
    // 캡컷은 클립을 누르면 속성이 이미 거기 있다. 우리는 `세부 정보` →
    // `편집 항목 열기` → `편집 대상` 셀렉트까지 **네 겹**을 지나야 속도에 닿았다.
    // 2026-08-17에 컷 도구에서 고친 것과 같은 병이 클립 속성에 남아 있었다.
    render(<PersistentDock />);

    expect(screen.getByRole("region", { name: "편집 항목" })).toBeInTheDocument();
    // 도크 안에서 **가장 먼저** 온다. 유진 대화를 지나 스크롤해야 나오면 여전히 못 찾는다.
    const dock = screen.getByRole("region", { name: "편집 항목" });
    const conversation = screen.getByRole("log", { name: "유진 대화" });
    expect(dock.compareDocumentPosition(conversation) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("offers only the approved shortform scene lengths for the selected scene", () => {
    const onSetSegmentRippleSpeed = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      selectedSegment={{
        segmentId: "segment-2", startSec: 4, endSec: 8, nextSegmentId: "segment-3",
        cutAction: "keep", draftApplied: false, ripplePlaybackRate: 1.5,
      }}
      onSetSegmentRippleSpeed={onSetSegmentRippleSpeed}
    />);

    const speed = screen.getByRole("group", { name: "장면 길이" });
    expect(speed).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1.5배" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "2배" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "2배" }));
    expect(onSetSegmentRippleSpeed).toHaveBeenCalledWith({ segmentId: "segment-2", rate: 2 });
  });

  it("offers a selected scene preview without changing the timeline", () => {
    const onPreviewSelectedRange = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      selectedSegment={{ segmentId: "segment-2", startSec: 4, endSec: 8, nextSegmentId: null, cutAction: "keep", draftApplied: false }}
      onPreviewSelectedRange={onPreviewSelectedRange}
    />);

    fireEvent.click(screen.getByRole("button", { name: "선택 구간 미리보기" }));
    expect(onPreviewSelectedRange).toHaveBeenCalledWith({ segmentId: "segment-2", startSec: 4, endSec: 8 });
  });

  it("offers keyword shortcuts for video, captions, and screen elements", () => {
    render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      inspectorTargets={[
        { id: "media-1", kind: "media", label: "영상", mediaKind: "broll", segmentId: "segment-1", fields: [], assetId: "asset-1", controls: {}, clearOnly: false },
        { id: "caption-1", kind: "caption", label: "자막", segmentId: "segment-1", fields: ["style"], style: {} as never },
        { id: "overlay-1", kind: "overlay", overlayKind: "shape", label: "화면 요소", segmentId: "segment-1", fields: [], value: { shape: "highlight_box", vertical: "middle", horizontal: "center", size: "medium", motion: "none" } },
      ]}
    />);

    expect(screen.getByRole("button", { name: "영상·소리" })).toBeVisible();
    expect(screen.getByRole("button", { name: "자막" })).toBeVisible();
    expect(screen.getByRole("button", { name: "화면 요소" })).toBeVisible();
  });

  it("re-asks by itself when the recommendation goes stale while the creator is looking at it", async () => {
    // 편집본이 바뀌면 추천이 무효가 된다(백엔드가 7군데에서 지키는 계약이라 그건
    // 그대로 둔다). 문제는 그다음이다 -- 죽은 카드와 단추만 남고, 창작자가 그걸
    // 눈치채고 눌러야 대화가 이어진다. 보고 있을 때는 대신 물어본다.
    const onRefreshProposal = vi.fn();
    render(<RightDock
      draft="" onDraftChange={vi.fn()}
      proposal={{ proposalId: "p1", status: "ready", baseSessionRevision: 22, currentRevision: 31, candidates: [] } as never}
      onRefreshProposal={onRefreshProposal}
    />);

    await waitFor(() => expect(onRefreshProposal).toHaveBeenCalledTimes(1));
  });

  it("does not keep re-asking the same stale revision over and over", async () => {
    // 다시 묻는 것은 로컬 모델을 한 번 돌리는 일이다. 같은 편집본에서 두 번
    // 물으면 답은 같고 시간만 쓴다.
    const onRefreshProposal = vi.fn();
    const proposal = { proposalId: "p1", status: "ready", baseSessionRevision: 22, currentRevision: 31, candidates: [] } as never;
    const rendered = render(<RightDock draft="" onDraftChange={vi.fn()} proposal={proposal} onRefreshProposal={onRefreshProposal} />);
    await waitFor(() => expect(onRefreshProposal).toHaveBeenCalledTimes(1));

    rendered.rerender(<RightDock draft="다른 초안" onDraftChange={vi.fn()} proposal={proposal} onRefreshProposal={onRefreshProposal} />);

    expect(onRefreshProposal).toHaveBeenCalledTimes(1);
  });

  it("still lets the creator fold the properties away", () => {
    // 항상 펴 두는 것과 접을 수 없는 것은 다르다.
    render(<PersistentDock />);
    fireEvent.click(screen.getByRole("button", { name: "편집 항목 닫기" }));
    expect(screen.queryByRole("region", { name: "편집 항목" })).not.toBeInTheDocument();
  });

  it("preserves the composer, selected candidate, and conversation scroll while Inspector opens and closes", () => {
    render(<PersistentDock />);
    const composer = screen.getByLabelText("유진에게 요청하기");
    const history = screen.getByRole("log", { name: "유진 대화" });
    fireEvent.change(composer, { target: { value: "다음 추천도 보여 줘" } });
    fireEvent.click(screen.getByRole("radio", { name: "B-002 선택" }));
    Object.defineProperty(history, "scrollTop", { configurable: true, writable: true, value: 72 });

    fireEvent.click(screen.getByRole("button", { name: "편집 항목 닫기" }));
    expect(screen.queryByRole("region", { name: "편집 항목" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "편집 항목 열기" }));

    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("다음 추천도 보여 줘");
    expect(screen.getByRole("radio", { name: "B-002 선택" })).toBeChecked();
    expect(screen.getByRole("log", { name: "유진 대화" }).scrollTop).toBe(72);
  });

  it("names a candidate by its asset, because a code is not something a person can choose by", () => {
    // 2026-08-19 owner 지적: 후보 일곱 개가 전부 `P08-B-01 · 미디어`였다.
    // 실제로 재 보니 서로 다른 장면을 겨냥한 같은 자산이었고, 카드만 봐서는
    // 무엇을 고르는지 알 수 없었다. 이름이 오면 이름을 쓴다.
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={{
        proposalId: "proposal-1",
        status: "ready",
        baseSessionRevision: 1,
        currentRevision: 1,
        candidates: [{
          candidateId: "candidate:segment-1:asset-sea",
          visibleReferenceCode: "P01-B-01",
          displayName: "제주 바다 드론",
          mediaType: "broll",
          previewUrl: null,
          kind: "broll",
          sourceMediaKind: "broll_video",
          targetSegmentId: "segment-1",
          previewSummary: "요약",
          supportedControls: {},
          availability: "available",
          reviewStatus: "approved",
          actionable: true,
        }],
      }}
    />);

    expect(screen.getByRole("radio", { name: "제주 바다 드론 선택" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /P01-B-01/ })).toBeNull();
  });

  it("says which scene each candidate is for, so the same asset twice is still two choices", () => {
    // 2026-08-20 owner 실측: 카드 열세 개가 전부 `20260612_091959 · 미디어`였다.
    // 서버는 후보마다 다른 `target_segment_id`를 실어 보내고 화면 코드도 그것을
    // 받는데, **카드가 그 값을 한 번도 쓰지 않았다.** 장면을 말하지 않으면
    // 같은 자산을 쓰는 후보들은 화면에서 구별할 방법이 없다.
    const sceneCandidate = (candidateId: string, targetSegmentId: string, targetSceneLabel: string) => ({
      candidateId,
      visibleReferenceCode: "P02-B-01",
      displayName: "20260612_091959",
      mediaType: "broll",
      previewUrl: null,
      kind: "broll",
      sourceMediaKind: "broll",
      targetSegmentId,
      targetSceneLabel,
      previewSummary: "요약",
      supportedControls: {},
      availability: "actionable",
      reviewStatus: "approved",
      actionable: true,
    });
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={{
        proposalId: "proposal-1",
        status: "ready",
        baseSessionRevision: 1,
        currentRevision: 1,
        candidates: [
          sceneCandidate("candidate-1", "segment-1", "1번째 장면 · 안녕하세요, 제주입니다"),
          sceneCandidate("candidate-2", "segment-2", "2번째 장면 · 오름에 올라 봅니다"),
        ],
      }}
    />);

    // 보이는 글자와 접근 이름이 **둘 다** 갈라져야 한다. 하나만 갈라지면
    // 눈으로 보거나 음성으로 듣는 사람 중 한쪽은 여전히 못 고른다.
    expect(screen.getByRole("radio", { name: "1번째 장면 · 안녕하세요, 제주입니다 — 20260612_091959 선택" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "2번째 장면 · 오름에 올라 봅니다 — 20260612_091959 선택" })).toBeInTheDocument();
    expect(screen.getByText(/1번째 장면 · 안녕하세요, 제주입니다/)).toBeVisible();
    expect(screen.getByText(/2번째 장면 · 오름에 올라 봅니다/)).toBeVisible();
  });

  it("keeps the old name when nothing is known about the scene, instead of inventing one", () => {
    // 장면을 모르면 아무 말도 하지 않는다. 지어낸 장면 이름은 코드보다 나쁘다.
    render(<RightDock draft="" onDraftChange={() => undefined} proposal={proposal} />);

    expect(screen.getByRole("radio", { name: "B-001 선택" })).toBeInTheDocument();
  });

  it("offers to take a pasted script, so the editor is reachable without the interview", () => {
    // 2026-08-19 owner: "유진이랑 대화하면서 대본을 복붙하면 유진이가 그걸 보고
    // 편집기에 붙여 줬으면". 지금은 대본이 `/plan`의 문답형 인터뷰로만 들어간다.
    // 긴 글을 붙여 넣으면 그것을 대본으로 받는 길을 준다. **확정은 사람이 한다** --
    // 이 단추는 대본을 만들 뿐 장면을 바로 만들지 않는다.
    const onUseDraftAsScript = vi.fn();
    const script = "안녕하세요. 오늘은 제주 바다를 소개합니다. 두 번째 문장입니다.";
    render(<RightDock draft={script} onDraftChange={() => undefined} onUseDraftAsScript={onUseDraftAsScript} />);

    fireEvent.click(screen.getByRole("button", { name: "이 글을 대본으로 쓰기" }));

    expect(onUseDraftAsScript).toHaveBeenCalledWith(script);
  });

  it("offers the same script button on Yujin's own answer, so nobody copies it back into the box", () => {
    // 2026-08-20 owner 실측: 유진에게 대본을 받아도 **손으로 복사해서 입력칸에
    // 도로 붙여넣어야** 단추가 떴다. 복사·붙여넣기 수고만 없앤다 --
    // 확정은 여전히 사람이 한다(2026-08-16 승인 기록).
    const onUseDraftAsScript = vi.fn();
    const script = "안녕하세요. 오늘은 제주 바다를 소개합니다. 두 번째 문장입니다.";
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      onUseDraftAsScript={onUseDraftAsScript}
      messages={[
        { id: "user-1", role: "user", text: "60초 대본 하나 써 줘" },
        { id: "assistant-1", role: "assistant", text: script },
      ]}
    />);

    fireEvent.click(screen.getByRole("button", { name: `이 답을 대본으로 쓰기 — ${script.slice(0, 20)}…` }));

    expect(onUseDraftAsScript).toHaveBeenCalledWith(script);
  });

  it("tells two Yujin answers apart, so the button can be reached by voice", () => {
    // 같은 이름의 단추가 여러 개면 음성으로 고를 수 없다. 보이는 글자는 짧게
    // 두고 접근 이름 뒤에 그 답의 첫머리를 붙인다(타임라인 클립과 같은 방식).
    const first = "첫 번째 대본입니다. 제주 바다에서 시작해 오름으로 올라갑니다.";
    const second = "두 번째 대본입니다. 한라산에서 시작해 바다로 내려갑니다.";
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      onUseDraftAsScript={vi.fn()}
      messages={[
        { id: "assistant-1", role: "assistant", text: first },
        { id: "assistant-2", role: "assistant", text: second },
      ]}
    />);

    expect(screen.getByRole("button", { name: `이 답을 대본으로 쓰기 — ${first.slice(0, 20)}…` })).toBeVisible();
    expect(screen.getByRole("button", { name: `이 답을 대본으로 쓰기 — ${second.slice(0, 20)}…` })).toBeVisible();
  });

  it("does not offer the script button on a short answer or on what the creator typed", () => {
    // 짧은 답은 대본이 아니라 대꾸다. 그리고 내가 쓴 말은 유진의 대본이 아니다.
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      onUseDraftAsScript={vi.fn()}
      messages={[
        { id: "assistant-1", role: "assistant", text: "네, 알겠습니다." },
        { id: "user-1", role: "user", text: "안녕하세요. 오늘은 제주 바다를 소개합니다. 두 번째 문장입니다." },
      ]}
    />);

    expect(screen.queryByRole("button", { name: /대본으로 쓰기/ })).toBeNull();
  });

  it("does not offer the script button for a short question", () => {
    // 짧은 한 줄은 요청이지 대본이 아니다. 늘 띄우면 단추가 소음이 된다.
    const onUseDraftAsScript = vi.fn();
    render(<RightDock draft="B-roll 추천해 줘" onDraftChange={() => undefined} onUseDraftAsScript={onUseDraftAsScript} />);

    expect(screen.queryByRole("button", { name: "이 글을 대본으로 쓰기" })).toBeNull();
  });

  it("lets several scenes be filled in one go when the server can apply them together", () => {
    // 2026-08-20 owner 실측: 빈 구간 열세 개를 채우려면 고르기·적용을 열세 번
    // 반복해야 했다. 후보 고르기가 라디오라 **한 번에 하나**만 됐기 때문이다.
    // `batch-apply`는 처음부터 여러 개를 한 번에 받아 **한 번의 편집**으로 쓴다.
    const onSelectedCandidateIdsChange = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={multiSceneProposal}
      selectedCandidateIds={["gap-1"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
    />);

    fireEvent.click(screen.getByRole("checkbox", { name: "2번째 장면 — 바다 영상 선택" }));

    expect(onSelectedCandidateIdsChange).toHaveBeenCalledWith(["gap-1", "gap-2"]);
    expect(screen.queryByRole("radio")).toBeNull();
  });

  it("keeps one candidate per scene, because two candidates for one scene would overwrite each other", () => {
    // 한 장면에 둘을 고르면 서버는 둘 다 그 장면에 쓰고 **나중 것이 이긴다** --
    // 조용히 하나가 사라진다. 같은 장면의 다른 후보를 고르면 앞의 것을 대신한다.
    const onSelectedCandidateIdsChange = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={multiSceneProposal}
      selectedCandidateIds={["gap-1", "gap-2"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
    />);

    fireEvent.click(screen.getByRole("checkbox", { name: "1번째 장면 — 구름 영상 선택" }));

    expect(onSelectedCandidateIdsChange).toHaveBeenCalledWith(["gap-1-alt", "gap-2"]);
  });

  it("selects one candidate for every scene at once, and clears them again", () => {
    const onSelectedCandidateIdsChange = vi.fn();
    const rendered = render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={multiSceneProposal}
      selectedCandidateIds={[]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
    />);

    fireEvent.click(screen.getByRole("button", { name: "장면마다 하나씩 모두 고르기" }));
    expect(onSelectedCandidateIdsChange).toHaveBeenCalledWith(["gap-1", "gap-2"]);

    rendered.rerender(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={multiSceneProposal}
      selectedCandidateIds={["gap-1", "gap-2"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
    />);
    fireEvent.click(screen.getByRole("button", { name: "고른 추천 모두 끄기" }));
    expect(onSelectedCandidateIdsChange).toHaveBeenCalledWith([]);
  });

  it("applies every selected scene in one press, and says how many are going", () => {
    const onApplyProposal = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={multiSceneProposal}
      selectedCandidateIds={["gap-1", "gap-2"]}
      onSelectedCandidateIdsChange={vi.fn()}
      onApplyProposal={onApplyProposal}
    />);

    fireEvent.click(screen.getByRole("button", { name: "고른 추천 2개 적용" }));

    expect(onApplyProposal).toHaveBeenCalledWith("proposal-gaps", ["gap-1", "gap-2"]);
    expect(onApplyProposal).toHaveBeenCalledTimes(1);
  });

  it("keeps a single-pick proposal on radios, because the server refuses to apply those together", () => {
    // 유진이 직접 실행하는 추천은 서버가 한 번에 하나만 받는다
    // (`reject_yujin_direct_apply`). 그런 추천까지 여러 개 고르게 하면
    // 고를 수는 있는데 적용이 거절되는 화면이 된다.
    render(<RightDock draft="" onDraftChange={() => undefined} proposal={proposal} />);

    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "장면마다 하나씩 모두 고르기" })).toBeNull();
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
    fireEvent.click(screen.getByRole("button", { name: "유진 없이 계속 편집" }));
    expect(onManualEdit).toHaveBeenCalledOnce();
    expect(screen.getByText("유진의 답을 받지 못했어요.")).toBeInTheDocument();
    expect(screen.getByText("요청 내용")).toBeInTheDocument();
  });

  it("announces only terminal state and never turns streamed token updates into live announcements", () => {
    const rendered = render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "첫" }]}
      runState={{ kind: "streaming", runId: "run-1", routeEpoch: 1, text: "첫" }}
    />);

    expect(screen.getByRole("log", { name: "유진 대화" })).not.toHaveAttribute("aria-live");
    expect(screen.queryByRole("status")).toBeNull();

    rendered.rerender(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "첫 답" }]}
      runState={{ kind: "streaming", runId: "run-1", routeEpoch: 1, text: "첫 답" }}
    />);
    expect(screen.queryByRole("status")).toBeNull();

    rendered.rerender(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "첫 답" }]}
      runState={{ kind: "complete", runId: "run-1" }}
    />);
    expect(screen.getByRole("status")).toHaveTextContent("유진 답변을 받았어요.");
    expect(screen.getAllByRole("status")).toHaveLength(1);

    rendered.rerender(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "첫 답" }]}
      runState={{ kind: "unavailable", message: "유진의 답을 받지 못했어요." }}
    />);
    expect(screen.getByRole("status")).toHaveTextContent("유진의 답을 받지 못했어요.");
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("announces completion once while showing a later durable sync warning outside the live region", async () => {
    const rendered = render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "완료된 답" }]}
      runState={{ kind: "streaming", runId: "run-1", routeEpoch: 1, text: "완료된 답" }}
    />);
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

    rendered.rerender(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      messages={[{ id: "assistant-1", role: "assistant", text: "완료된 답" }]}
      runState={{ kind: "complete", runId: "run-1" }}
    />);
    await waitFor(() => expect(announcements).toEqual(["유진 답변을 받았어요."]));

    rendered.rerender(<RightDock
      draft=""
      onDraftChange={vi.fn()}
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

  it("shows typed media details without mutation and disables stale or deferred choices", () => {
    const onApplyProposal = vi.fn();
    const onSelectedCandidateIdsChange = vi.fn();
    const stale: RightDockProposal = {
      ...proposal,
      baseSessionRevision: 6,
      currentRevision: 7,
      candidates: [
        proposal.candidates[0],
        {
          ...proposal.candidates[1],
          candidateId: "deferred-image",
          visibleReferenceCode: "B-003",
          sourceMediaKind: "image",
          availability: "candidate_only",
          reviewStatus: "pending",
          actionable: false,
        },
      ],
    };

    const { container } = render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      proposal={stale}
      selectedCandidateIds={["candidate-1"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
      onApplyProposal={onApplyProposal}
    />);

    expect(screen.getByText("첫 장면을 산책 영상으로 채웁니다.")).toBeVisible();
    expect(screen.getByText("영상")).toBeVisible();
    // 내부 세그먼트 식별자는 owner에게 뜻이 없다. 화면에는 나오지 않아야 한다.
    expect(screen.queryAllByText("segment-1")).toHaveLength(0);
    expect(screen.getByText("화면 채우기")).toBeVisible();
    expect(screen.getByText("제안 기준 편집본 6")).toBeVisible();
    expect(screen.getByText("현재 편집본 7")).toBeVisible();
    expect(screen.getByText("후보 상태: 적용 가능")).toBeVisible();
    expect(screen.getByText("후보 상태: 수동 적용")).toBeVisible();
    expect(screen.getByRole("radio", { name: "B-003 선택" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "선택한 추천 적용" })).toBeDisabled();
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    expect(onSelectedCandidateIdsChange).not.toHaveBeenCalled();
    expect(onApplyProposal).not.toHaveBeenCalled();
  });

  it("shows candidate-only references without preview, materialize, or apply controls", () => {
    const onPreviewCandidate = vi.fn();
    const onApplyProposal = vi.fn();
    const candidateOnly: RightDockProposal = {
      proposalId: "candidate-only-proposal",
      status: "candidate_only",
      baseSessionRevision: 7,
      currentRevision: 7,
      candidates: [{
        candidateId: "candidate-only-1",
        visibleReferenceCode: "P01-B-01",
        mediaType: "broll",
        previewUrl: "https://must-not-preview.invalid/candidate.mp4",
        kind: "broll",
        sourceMediaKind: "image",
        targetSegmentId: "segment-1",
        previewSummary: "이미지는 아직 직접 적용할 수 없습니다.",
        supportedControls: {},
        availability: "candidate_only",
        reviewStatus: "pending",
        actionable: false,
      }],
    };

    const { container } = render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      proposal={candidateOnly}
      selectedCandidateIds={["candidate-only-1"]}
      onSelectedCandidateIdsChange={vi.fn()}
      onPreviewCandidate={onPreviewCandidate}
      onApplyProposal={onApplyProposal}
    />);

    expect(screen.getByRole("radio", { name: "P01-B-01 선택" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "P01-B-01 미리 보기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "선택한 추천 적용" })).toBeNull();
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    expect(onPreviewCandidate).not.toHaveBeenCalled();
    expect(onApplyProposal).not.toHaveBeenCalled();
  });

  it("keeps output findings separate and never selectable or applicable", () => {
    const mixed: RightDockProposal = {
      ...proposal,
      candidates: [
        proposal.candidates[0],
        {
          candidateId: "finding-gaps",
          visibleReferenceCode: "P01-CHECK-01",
          mediaType: "output_check",
          previewUrl: null,
          kind: "output_check",
          sourceMediaKind: "output_check",
          targetSegmentId: "",
          previewSummary: "미디어, 미리보기, 내보내기 준비가 모두 끝났습니다.",
          supportedControls: { check: "timeline_gaps", gap_count: 2 },
          availability: "read_only",
          reviewStatus: "not_applicable",
          actionable: false,
          readOnlyFinding: true,
        },
      ],
    };
    const onApplyProposal = vi.fn();
    const onSelectedCandidateIdsChange = vi.fn();

    render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      proposal={mixed}
      selectedCandidateIds={[]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
      onApplyProposal={onApplyProposal}
    />);

    const finding = screen.getByRole("region", { name: "검사 결과" });
    expect(finding).toHaveTextContent("빈 구간 2개");
    expect(finding).not.toHaveTextContent("미디어, 미리보기, 내보내기 준비가 모두 끝났습니다.");
    expect(screen.queryByRole("radio", { name: "P01-CHECK-01 선택" })).toBeNull();
    expect(screen.getByRole("button", { name: "선택한 추천 적용" })).toBeDisabled();
    expect(onSelectedCandidateIdsChange).not.toHaveBeenCalled();
    expect(onApplyProposal).not.toHaveBeenCalled();
  });
});

describe("찾은 방식 표시", () => {
  function renderWithMode(matchMode: string | undefined) {
    return render(<RightDock
      draft=""
      onDraftChange={() => {}}
      proposal={{ ...proposal, matchMode } as never}
      messages={[]}
      selectedCandidateIds={[]}
      onSelectedCandidateIdsChange={() => {}}
      conversationScroll={{ key: "k", top: 0, pinnedToBottom: true }}
      onConversationScrollChange={() => {}}
      inspectorTargets={[]}
    />);
  }

  it("단어로만 찾았으면 그 사실을 말한다", () => {
    // 임베딩 조회가 실패하면 조용히 단어 매칭으로 떨어졌다. 추천이 갑자기
    // 나빠져도 owner는 원인을 알 수 없었다.
    renderWithMode("word");

    expect(screen.getByText("단어로만 찾음")).toBeVisible();
  });

  it("뜻으로 찾았으면 그렇게 말한다", () => {
    renderWithMode("semantic");

    expect(screen.getByText("뜻으로 찾음")).toBeVisible();
  });

  it("모르면 지어내지 않는다", () => {
    renderWithMode(undefined);

    expect(screen.queryByText(/찾음/)).toBeNull();
  });
});

describe("대화형 편집안", () => {
  it("검토 창에서 미리보기와 적용을 분리하고 후속 질문은 초안에만 넣는다", () => {
    const onDraftChange = vi.fn();
    const onPreviewEditingProposal = vi.fn();
    const onApplyEditingProposal = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={onDraftChange}
      messages={[{ id: "assistant-1", role: "assistant", text: "속도를 조절할 수 있어요." }]}
      editingProposal={{ proposalId: "editing-1", summary: "2번 장면 · 8초 → 4초", operationSummaries: ["2배로 속도를 바꿔요."], followUpQuestions: ["자막도 짧게 할까요?"], previewTarget: { segmentId: "segment-2", startSec: 8, endSec: 16 }, isApplying: false, error: null }}
      onPreviewEditingProposal={onPreviewEditingProposal}
      onApplyEditingProposal={onApplyEditingProposal}
    />);

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
    render(<RightDock
      draft=""
      onDraftChange={() => {}}
      messages={[{ id: "assistant-1", role: "assistant", text: "속도를 조절할 수 있어요." }]}
      editingProposal={proposalWithPreview(preview)}
      onPreviewEditingProposal={vi.fn()}
      onApplyEditingProposal={vi.fn()}
    />);
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
