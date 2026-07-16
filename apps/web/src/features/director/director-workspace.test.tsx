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
  it("메시지 응답과 action intent는 표시만 하고 명시적 적용 전에는 mutation을 만들지 않는다", async () => {
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {} , assistant_message: { text: "후보를 확인했습니다" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    const applyProposal = vi.fn();
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} sendMessage={sendMessage} materializeCandidate={vi.fn()} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: { placements: {} } })} applyProposal={applyProposal} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "디렉터 메시지" }), { target: { value: "3번 영상 교체" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await screen.findByText("후보를 확인했습니다");
    expect(applyProposal).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("button", { name: "변경 적용" })).toBeEnabled());
  });

  it("명시적 적용은 preflight 뒤 선택 후보를 materialize하고 candidate_ids만 한번 적용한다", async () => {
    const materializeCandidate = vi.fn().mockResolvedValue({});
    const applyProposal = vi.fn().mockResolvedValue({});
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "적용 준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: { placements: {} } })} materializeCandidate={materializeCandidate} applyProposal={applyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "디렉터 메시지" }), { target: { value: "적용" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await screen.findByText("적용 준비");
    fireEvent.click(screen.getByRole("button", { name: "변경 적용" }));
    await waitFor(() => expect(materializeCandidate).toHaveBeenCalledWith("proposal-12", "c-b"));
    expect(applyProposal).toHaveBeenCalledWith("proposal-12", { candidate_ids: ["c-b"], expected_revision: 4 });
    expect(applyProposal.mock.calls[0][1]).not.toHaveProperty("scope");
  });

  it("immutable preflight가 stale이면 적용하지 않고 refresh 경로를 표시한다", async () => {
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ code: "stale_proposal", status: "stale", diff: { changed: ["seg-1"] } })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} />);
    expect(await screen.findByText(/제안이 오래/)).toBeVisible();
    expect(screen.getByRole("button", { name: "변경 적용" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "제안 새로고침" })).toBeVisible();
  });

  it("apply 직전 재검증이 stale이면 materialize나 apply를 호출하지 않는다", async () => {
    const preflightProposal = vi.fn().mockResolvedValueOnce({ status: "ready", diff: {} }).mockResolvedValueOnce({ code: "stale_proposal", status: "stale", diff: {} });
    const materializeCandidate = vi.fn(); const applyProposal = vi.fn();
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={preflightProposal} materializeCandidate={materializeCandidate} applyProposal={applyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "디렉터 메시지" }), { target: { value: "적용" } }); fireEvent.click(screen.getByRole("button", { name: "보내기" })); await screen.findByText("준비");
    await waitFor(() => expect(screen.getByRole("button", { name: "변경 적용" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "변경 적용" }));
    await screen.findByText(/적용하지 않았습니다/);
    expect(materializeCandidate).not.toHaveBeenCalled(); expect(applyProposal).not.toHaveBeenCalled();
  });

  it("후보 선택은 batch transaction으로 적용된다는 상태를 표시한다", () => {
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} />);
    expect(screen.getByRole("checkbox", { name: "P12-B-03 선택" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "P12-B-04 선택" })).not.toBeChecked();
    expect(screen.getByText(/원자적 변경/)).toBeVisible();
  });

  it("명시적 all scope는 client materialize loop 없이 batch apply endpoint를 한 번만 호출한다", async () => {
    const batchApplyProposal = vi.fn().mockResolvedValue({});
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "일괄 적용 준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} batchApplyProposal={batchApplyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "디렉터 메시지" }), { target: { value: "모두 적용" } }); fireEvent.click(screen.getByRole("button", { name: "보내기" })); await screen.findByText("일괄 적용 준비");
    fireEvent.click(screen.getByRole("checkbox", { name: "P12-B-04 선택" }));
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "P12-B-04 선택" })).toBeChecked());
    fireEvent.click(screen.getByRole("button", { name: "변경 적용" }));
    await waitFor(() => expect(batchApplyProposal).toHaveBeenCalledWith("proposal-12", { candidate_ids: ["c-b", "c-b2"], expected_revision: 4 }));
  });

  it("여러 후보가 선택됐는데 batch provider가 없으면 첫 후보만 적용하지 않고 오류를 표시한다", async () => {
    const materializeCandidate = vi.fn(); const applyProposal = vi.fn();
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "일괄 적용 준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={materializeCandidate} applyProposal={applyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "디렉터 메시지" }), { target: { value: "두 후보 적용" } }); fireEvent.click(screen.getByRole("button", { name: "보내기" })); await screen.findByText("일괄 적용 준비");
    fireEvent.click(screen.getByRole("checkbox", { name: "P12-B-04 선택" }));
    fireEvent.click(screen.getByRole("button", { name: "변경 적용" }));
    await screen.findByText(/일괄 적용 기능을 사용할 수 없어/);
    expect(materializeCandidate).not.toHaveBeenCalled(); expect(applyProposal).not.toHaveBeenCalled();
  });

  it("apply scope는 selected/broll/all 명시 radio로 고르고 그 결과만 batch endpoint에 보낸다", async () => {
    const batchApplyProposal = vi.fn().mockResolvedValue({});
    const mixed = { ...proposal, candidates: [...proposal.candidates, { ...proposal.candidates[0], candidate_id: "c-m", media_type: "bgm", visible_reference_code: "P12-M-01" }] };
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "범위 적용 준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={mixed} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} batchApplyProposal={batchApplyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "디렉터 메시지" }), { target: { value: "B-roll 모두 적용" } }); fireEvent.click(screen.getByRole("button", { name: "보내기" })); await screen.findByText("범위 적용 준비");
    fireEvent.click(screen.getByRole("radio", { name: "B-roll 범위" }));
    fireEvent.click(screen.getByRole("button", { name: "변경 적용" }));
    await waitFor(() => expect(batchApplyProposal).toHaveBeenCalledWith("proposal-12", { candidate_ids: ["c-b", "c-b2"], expected_revision: 4 }));
  });

  it("전체 범위 radio는 선택 상태와 무관하게 proposal 순서 전체를 batch endpoint에 보낸다", async () => {
    const batchApplyProposal = vi.fn().mockResolvedValue({});
    const mixed = { ...proposal, candidates: [...proposal.candidates, { ...proposal.candidates[0], candidate_id: "c-m", media_type: "bgm", visible_reference_code: "P12-M-01" }] };
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "전체 적용 준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={mixed} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} batchApplyProposal={batchApplyProposal} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "디렉터 메시지" }), { target: { value: "전체 적용" } }); fireEvent.click(screen.getByRole("button", { name: "보내기" })); await screen.findByText("전체 적용 준비");
    fireEvent.click(screen.getByRole("radio", { name: "전체 범위" }));
    fireEvent.click(screen.getByRole("button", { name: "변경 적용" }));
    await waitFor(() => expect(batchApplyProposal).toHaveBeenCalledWith("proposal-12", { candidate_ids: ["c-b", "c-b2", "c-m"], expected_revision: 4 }));
  });

  it("proposal 교체 시 이전 후보 id를 버리고 새 proposal의 후보로 선택을 재설정한다", async () => {
    const { rerender } = render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} />);
    const replaced = { ...proposal, proposal_id: "proposal-13", candidates: [{ ...proposal.candidates[1], candidate_id: "c-new", visible_reference_code: "P13-B-01" }] };
    rerender(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={replaced} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "P13-B-01 선택" })).toBeChecked());
    expect(screen.queryByRole("checkbox", { name: "P12-B-03 선택" })).not.toBeInTheDocument();
  });

  it("실제 선택 segment의 timecode를 보이고 성공 apply 뒤 draft-applied를 표시한다", async () => {
    const sendMessage = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "준비" }, action_intent: { action: "apply", target: { reference_code: "P12-B-03", immutable_id: "c-b", source: "proposal" }, proposal_preflight: { proposal_id: "proposal-12" } } } });
    render(<DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={4} selectedSegment={{ segmentId: "seg-real", startSec: 12.5, endSec: 19.25, draftApplied: false }} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn().mockResolvedValue({})} applyProposal={vi.fn().mockResolvedValue({})} sendMessage={sendMessage} onManualMode={vi.fn()} />);
    expect(screen.getByLabelText("디렉터 컨텍스트")).toHaveTextContent("seg-real · 12.50–19.25");
    fireEvent.change(screen.getByRole("textbox", { name: "디렉터 메시지" }), { target: { value: "적용" } }); fireEvent.click(screen.getByRole("button", { name: "보내기" })); await screen.findByText("준비");
    await waitFor(() => expect(screen.getByRole("button", { name: "변경 적용" })).toBeEnabled()); fireEvent.click(screen.getByRole("button", { name: "변경 적용" }));
    await waitFor(() => expect(screen.getByLabelText("디렉터 컨텍스트")).toHaveTextContent("초안 적용됨"));
  });

  it("blocked 상태에서도 수동 편집 진입을 막지 않는다", () => {
    const onManualMode = vi.fn();
    render(<DirectorWorkspace state="blocked" projectId="project-1" sessionId="session-1" sessionRevision={4} proposal={proposal} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} sendMessage={vi.fn()} onManualMode={onManualMode} />);
    fireEvent.click(screen.getByRole("button", { name: "수동 편집 계속" }));
    expect(onManualMode).toHaveBeenCalledOnce();
  });
});
