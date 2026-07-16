import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { reloadDirectorSession, createDirectorConversation, createDirectorProposal, preflightDirectorProposal, prepareDirectorMessage, updateDirectorPreferences } = vi.hoisted(() => ({ reloadDirectorSession: vi.fn(), createDirectorConversation: vi.fn(), createDirectorProposal: vi.fn(), preflightDirectorProposal: vi.fn(), prepareDirectorMessage: vi.fn(), updateDirectorPreferences: vi.fn() }));
vi.mock("../../api", () => ({
  api: { reloadDirectorSession, createDirectorConversation, createDirectorProposal, prepareDirectorMessage, preflightDirectorProposal, refreshDirectorProposal: vi.fn(), updateDirectorPreferences, materializeDirectorCandidate: vi.fn(), applyDirectorProposal: vi.fn(), batchApplyDirectorProposal: vi.fn() },
}));
import { DirectorWorkspacePanel } from "./DirectorWorkspacePanel";

describe("DirectorWorkspacePanel recovery", () => {
  beforeEach(() => vi.clearAllMocks());
  it("does not POST on an empty reload and starts exactly once when the operator asks", async () => {
    reloadDirectorSession.mockResolvedValue({ conversation: null, messages: [], proposal: null, references: [] });
    createDirectorConversation.mockResolvedValue({ conversation_id: "conversation-1", project_id: "project-1", session_id: "session-1" });
    createDirectorProposal.mockResolvedValue({ proposal_id: "proposal-1", candidates: [], target_segment_ids: [], base_session_revision: 1 });
    preflightDirectorProposal.mockResolvedValue({ status: "ready" });
    render(<DirectorWorkspacePanel projectId="project-1" sessionId="session-1" sessionRevision={1} />);

    await screen.findByRole("button", { name: "디렉터 시작" });
    expect(createDirectorConversation).not.toHaveBeenCalled();
    expect(createDirectorProposal).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "디렉터 시작" }));
    await waitFor(() => expect(createDirectorConversation).toHaveBeenCalledTimes(1));
    expect(createDirectorProposal).toHaveBeenCalledTimes(1);
  });

  it("resumes a recovered conversation without a proposal and sends without creating a duplicate", async () => {
    reloadDirectorSession.mockResolvedValue({ conversation: { conversation_id: "conversation-recovered", project_id: "project-1", session_id: "session-1" }, messages: [], proposal: null, references: [] });
    prepareDirectorMessage.mockReturnValue({ send: vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: {}, assistant_message: { text: "재개 응답", proposal_id: null } } }) });
    render(<DirectorWorkspacePanel projectId="project-1" sessionId="session-1" sessionRevision={1} />);

    await screen.findByText(/상태: idle/);
    fireEvent.change(screen.getByLabelText("디렉터 메시지"), { target: { value: "이어가기" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(prepareDirectorMessage).toHaveBeenCalledWith("project-1", "conversation-recovered", expect.objectContaining({ text: "이어가기" })));
    expect(createDirectorConversation).not.toHaveBeenCalled();
  });

  it("retains a created conversation when proposal start fails and retries without a duplicate conversation", async () => {
    reloadDirectorSession.mockResolvedValue({ conversation: null, messages: [], proposal: null, references: [] });
    createDirectorConversation.mockResolvedValue({ conversation_id: "conversation-retained", project_id: "project-1", session_id: "session-1" });
    createDirectorProposal.mockRejectedValueOnce(new Error("proposal unavailable")).mockResolvedValueOnce({ proposal_id: "proposal-retry", candidates: [], target_segment_ids: [], base_session_revision: 1 });
    preflightDirectorProposal.mockResolvedValue({ status: "ready" });
    render(<DirectorWorkspacePanel projectId="project-1" sessionId="session-1" sessionRevision={1} />);

    fireEvent.click(await screen.findByRole("button", { name: "디렉터 시작" }));
    expect(await screen.findByRole("button", { name: "디렉터 시작" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "디렉터 시작" }));
    await waitFor(() => expect(createDirectorProposal).toHaveBeenCalledTimes(2));
    expect(createDirectorConversation).toHaveBeenCalledTimes(1);
  });

  it("sends Director preference updates with the active project id", async () => {
    reloadDirectorSession.mockResolvedValue({ conversation: { conversation_id: "conversation-1", project_id: "project-1", session_id: "session-1" }, messages: [], proposal: { proposal_id: "proposal-1", candidates: [{ candidate_id: "candidate-1", visible_reference_code: "P01-B-01", media_type: "broll", asset_id: "asset-1", library_asset_id: null, reason_chips: [], scores: {}, availability: "available", review_status: "approved", preview_uri: null, controls: {}, expected_content_sha256: null, media_revision: "1", canonical_metadata: {}, license_policy: "verified", warning_provenance: [] }], target_segment_ids: [], base_session_revision: 1 }, references: [] });
    preflightDirectorProposal.mockResolvedValue({ status: "ready" });
    updateDirectorPreferences.mockResolvedValue({});
    render(<DirectorWorkspacePanel projectId="project-1" sessionId="session-1" sessionRevision={1} />);

    fireEvent.click(await screen.findByRole("button", { name: "고정" }));
    await waitFor(() => expect(updateDirectorPreferences).toHaveBeenCalledWith("project-1", { pin_asset: ["asset-1"] }));
  });
});
