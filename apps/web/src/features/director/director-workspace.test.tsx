import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DirectorProposal } from "../../api";
import { DirectorWorkspace } from "./DirectorWorkspace";

const proposal: DirectorProposal = {
  proposal_id: "proposal-12", revision_code: "P12", revision: 12, base_session_revision: 4,
  asset_index_revision: 2, source_session_id: "session-1", target_segment_ids: ["seg-1"],
  source_script_segment_ids: ["seg-1"], status: "ready", diff: {}, expires_at: null,
  candidates: [{ candidate_id: "c-b", visible_reference_code: "P12-B-03", media_type: "broll", asset_id: "asset-b", library_asset_id: null, reason_chips: ["전환"], scores: {}, availability: "available", review_status: "verified", preview_uri: null, controls: { in_sec: 1, out_sec: 3 }, expected_content_sha256: null, media_revision: "1", canonical_metadata: {}, license_policy: "ok", warning_provenance: [] }, { candidate_id: "c-b2", visible_reference_code: "P12-B-04", media_type: "broll", asset_id: "asset-b2", library_asset_id: null, reason_chips: ["대안"], scores: {}, availability: "available", review_status: "verified", preview_uri: null, controls: {}, expected_content_sha256: null, media_revision: "1", canonical_metadata: {}, license_policy: "ok", warning_provenance: [] }],
};

describe("DirectorWorkspace", () => {
  it("루미의 시작과 요청 제어를 제작자 언어로 표시한다", () => {
    render(<DirectorWorkspace state="idle" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={null} preflightProposal={vi.fn()} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} onStart={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "루미" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "루미에게 추천받기" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "루미에게 요청하기" })).toBeInTheDocument();
  });

  it("현재 선택 위치에 내부 추천 코드와 세그먼트 ID를 노출하지 않는다", () => {
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} />);

    expect(screen.getByLabelText("현재 선택 위치")).toHaveTextContent("선택한 장면");
    expect(screen.queryByText("P12")).not.toBeInTheDocument();
    expect(screen.queryByText("seg-1")).not.toBeInTheDocument();
  });

  it("추천 항목을 다시 고를 때 P12와 접두사가 붙은 원시 참조 코드를 노출하지 않는다", async () => {
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "어느 추천인지 골라 주세요." }, disambiguation: { status: "needs_disambiguation", options: [{ source: "proposal", reference_code: "P12-B-03", immutable_id: "candidate_003" }, { source: "proposal", reference_code: "PR-1-M-02", immutable_id: "candidate_004" }] } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={sendMessage} onManualMode={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { target: { value: "3번 영상 교체" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await screen.findByText("루미 추천 12의 비롤 3번");
    expect(screen.getByText("루미 추천 1의 배경음악 2번")).toBeVisible();
    expect(screen.queryByText(/P12-B-03|PR-1-M-02|candidate_003|candidate_004/)).not.toBeInTheDocument();
  });

  it("추천을 만들지 못해도 직접 편집할 수 있다고 안내한다", () => {
    render(<DirectorWorkspace state="blocked" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={null} preflightProposal={vi.fn()} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} />);

    expect(screen.getByText("루미가 지금 추천을 만들 수 없어요. 직접 골라 계속 편집할 수 있어요.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 편집하기" })).toBeInTheDocument();
  });

  it("메시지 응답과 action intent는 표시만 하고 명시적 적용 전에는 mutation을 만들지 않는다", async () => {
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {} , assistant_message: { text: "후보를 확인했습니다" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    const applyProposal = vi.fn();
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} sendMessage={sendMessage} materializeCandidate={vi.fn()} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: { placements: {} } })} applyProposal={applyProposal} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { target: { value: "3번 영상 교체" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await screen.findByText("후보를 확인했습니다");
    expect(applyProposal).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("button", { name: "이 추천 적용" })).toBeEnabled());
  });

  it("명시적 적용은 preflight 뒤 선택 후보를 materialize하고 candidate_ids만 한번 적용한다", async () => {
    const materializeCandidate = vi.fn().mockResolvedValue({});
    const applyProposal = vi.fn().mockResolvedValue({});
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "적용 준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: { placements: {} } })} materializeCandidate={materializeCandidate} applyProposal={applyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { target: { value: "적용" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await screen.findByText("적용 준비");
    fireEvent.click(screen.getByRole("button", { name: "이 추천 적용" }));
    await waitFor(() => expect(materializeCandidate).toHaveBeenCalledWith("proposal-12", "c-b"));
    expect(applyProposal).toHaveBeenCalledWith("proposal-12", { candidate_ids: ["c-b"], expected_revision: 4 });
    expect(applyProposal.mock.calls[0][1]).not.toHaveProperty("scope");
  });

  it("immutable preflight가 stale이면 적용하지 않고 refresh 경로를 표시한다", async () => {
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ code: "stale_proposal", status: "stale", diff: { changed: ["seg-1"] } })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} />);
    expect(await screen.findByText("편집본이 바뀌었어요. 추천을 다시 만들어 주세요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "이 추천 적용" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "추천 다시 만들기" })).toBeVisible();
  });

  it("apply 직전 재검증이 stale이면 materialize나 apply를 호출하지 않는다", async () => {
    const preflightProposal = vi.fn().mockResolvedValueOnce({ status: "ready", diff: {} }).mockResolvedValueOnce({ code: "stale_proposal", status: "stale", diff: {} });
    const materializeCandidate = vi.fn(); const applyProposal = vi.fn();
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={preflightProposal} materializeCandidate={materializeCandidate} applyProposal={applyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { target: { value: "적용" } }); fireEvent.click(screen.getByRole("button", { name: "요청 보내기" })); await screen.findByText("준비");
    await waitFor(() => expect(screen.getByRole("button", { name: "이 추천 적용" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "이 추천 적용" }));
    await screen.findByText("편집본이 바뀌었어요. 추천을 다시 만들어 주세요.");
    expect(materializeCandidate).not.toHaveBeenCalled(); expect(applyProposal).not.toHaveBeenCalled();
  });

  it("후보 선택은 batch transaction으로 적용된다는 상태를 표시한다", () => {
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} />);
    expect(screen.getByRole("checkbox", { name: "루미 추천 12의 비롤 3번 고르기" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "루미 추천 12의 비롤 4번 고르기" })).not.toBeChecked();
    expect(screen.getByText("고른 추천은 한 번에 편집본에 반영돼요.")).toBeVisible();
  });

  it("명시적 all scope는 client materialize loop 없이 batch apply endpoint를 한 번만 호출한다", async () => {
    const batchApplyProposal = vi.fn().mockResolvedValue({});
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "일괄 적용 준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} batchApplyProposal={batchApplyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { target: { value: "모두 적용" } }); fireEvent.click(screen.getByRole("button", { name: "요청 보내기" })); await screen.findByText("일괄 적용 준비");
    fireEvent.click(screen.getByRole("checkbox", { name: "루미 추천 12의 비롤 4번 고르기" }));
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "루미 추천 12의 비롤 4번 고르기" })).toBeChecked());
    fireEvent.click(screen.getByRole("button", { name: "이 추천 적용" }));
    await waitFor(() => expect(batchApplyProposal).toHaveBeenCalledWith("proposal-12", { candidate_ids: ["c-b", "c-b2"], expected_revision: 4 }));
  });

  it("여러 후보가 선택됐는데 batch provider가 없으면 첫 후보만 적용하지 않고 오류를 표시한다", async () => {
    const materializeCandidate = vi.fn(); const applyProposal = vi.fn();
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "일괄 적용 준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={materializeCandidate} applyProposal={applyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { target: { value: "두 후보 적용" } }); fireEvent.click(screen.getByRole("button", { name: "요청 보내기" })); await screen.findByText("일괄 적용 준비");
    fireEvent.click(screen.getByRole("checkbox", { name: "루미 추천 12의 비롤 4번 고르기" }));
    fireEvent.click(screen.getByRole("button", { name: "이 추천 적용" }));
    await screen.findByText("여러 추천을 지금 적용할 수 없어요. 하나를 골라 다시 시도해 주세요.");
    expect(materializeCandidate).not.toHaveBeenCalled(); expect(applyProposal).not.toHaveBeenCalled();
  });

  it("apply scope는 selected/broll/all 명시 radio로 고르고 그 결과만 batch endpoint에 보낸다", async () => {
    const batchApplyProposal = vi.fn().mockResolvedValue({});
    const mixed = { ...proposal, candidates: [...proposal.candidates, { ...proposal.candidates[0], candidate_id: "c-m", media_type: "bgm", visible_reference_code: "P12-M-01" }] };
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "범위 적용 준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={mixed} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} batchApplyProposal={batchApplyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { target: { value: "B-roll 모두 적용" } }); fireEvent.click(screen.getByRole("button", { name: "요청 보내기" })); await screen.findByText("범위 적용 준비");
    fireEvent.click(screen.getByRole("radio", { name: "영상 추천만" }));
    fireEvent.click(screen.getByRole("button", { name: "이 추천 적용" }));
    await waitFor(() => expect(batchApplyProposal).toHaveBeenCalledWith("proposal-12", { candidate_ids: ["c-b", "c-b2"], expected_revision: 4 }));
  });

  it("전체 범위 radio는 선택 상태와 무관하게 proposal 순서 전체를 batch endpoint에 보낸다", async () => {
    const batchApplyProposal = vi.fn().mockResolvedValue({});
    const mixed = { ...proposal, candidates: [...proposal.candidates, { ...proposal.candidates[0], candidate_id: "c-m", media_type: "bgm", visible_reference_code: "P12-M-01" }] };
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "전체 적용 준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={mixed} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} batchApplyProposal={batchApplyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { target: { value: "전체 적용" } }); fireEvent.click(screen.getByRole("button", { name: "요청 보내기" })); await screen.findByText("전체 적용 준비");
    fireEvent.click(screen.getByRole("radio", { name: "모든 추천" }));
    fireEvent.click(screen.getByRole("button", { name: "이 추천 적용" }));
    await waitFor(() => expect(batchApplyProposal).toHaveBeenCalledWith("proposal-12", { candidate_ids: ["c-b", "c-b2", "c-m"], expected_revision: 4 }));
  });

  it("proposal 교체 시 이전 후보 id를 버리고 새 proposal의 후보로 선택을 재설정한다", async () => {
    const { rerender } = render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} />);
    const replaced = { ...proposal, proposal_id: "proposal-13", candidates: [{ ...proposal.candidates[1], candidate_id: "c-new", visible_reference_code: "P13-B-01" }] };
    rerender(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={replaced} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "루미 추천 13의 비롤 1번 고르기" })).toBeChecked());
    expect(screen.queryByRole("checkbox", { name: "루미 추천 12의 비롤 3번 고르기" })).not.toBeInTheDocument();
  });

  it("실제 선택 segment의 timecode를 보이고 성공 apply 뒤 draft-applied를 표시한다", async () => {
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} selectedSegment={{ segmentId: "seg-real", startSec: 12.5, endSec: 19.25, draftApplied: false }} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn().mockResolvedValue({})} applyProposal={vi.fn().mockResolvedValue({})} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    expect(screen.getByLabelText("현재 선택 위치")).toHaveTextContent("선택한 장면 · 12.50–19.25");
    fireEvent.change(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { target: { value: "적용" } }); fireEvent.click(screen.getByRole("button", { name: "요청 보내기" })); await screen.findByText("준비");
    await waitFor(() => expect(screen.getByRole("button", { name: "이 추천 적용" })).toBeEnabled()); fireEvent.click(screen.getByRole("button", { name: "이 추천 적용" }));
    await waitFor(() => expect(screen.getByLabelText("현재 선택 위치")).toHaveTextContent("편집본에 적용됨"));
  });

  it("blocked 상태에서도 수동 편집 진입을 막지 않는다", () => {
    const onManualMode = vi.fn();
    render(<DirectorWorkspace state="blocked" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={onManualMode} />);
    fireEvent.click(screen.getByRole("button", { name: "직접 편집하기" }));
    expect(onManualMode).toHaveBeenCalledOnce();
  });
});
