import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { RightDock } from "./RightDock";

afterEach(cleanup);

const proposal = {
  proposal_id: "proposal-1",
  revision_code: "r1",
  revision: 1,
  base_session_revision: 4,
  asset_index_revision: 1,
  source_session_id: "session-1",
  target_segment_ids: ["segment-1"],
  source_script_segment_ids: ["segment-1"],
  status: "ready",
  diff: {},
  expires_at: null,
  candidates: [
    { candidate_id: "candidate-1", visible_reference_code: "B-001", media_type: "broll", asset_id: "asset-1", library_asset_id: null, reason_chips: [], scores: {}, availability: "available", review_status: "ready", preview_uri: null, controls: {}, expected_content_sha256: null, media_revision: "r1", canonical_metadata: {}, license_policy: "local", warning_provenance: [] },
    { candidate_id: "candidate-2", visible_reference_code: "B-002", media_type: "broll", asset_id: "asset-2", library_asset_id: null, reason_chips: [], scores: {}, availability: "available", review_status: "ready", preview_uri: null, controls: {}, expected_content_sha256: null, media_revision: "r1", canonical_metadata: {}, license_policy: "local", warning_provenance: [] },
  ],
} as const;

function PersistentDock() {
  const [draft, setDraft] = useState("");
  return <RightDock
    draft={draft}
    onDraftChange={setDraft}
    proposal={proposal}
    messages={[{ user_message: { message_id: "user-1", conversation_id: "conversation-1", project_id: "project-1", session_id: "session-1", role: "user", text: "B-roll을 추천해 줘", proposal_id: null, metadata: {}, client_message_id: null, created_at: "2026-07-23T00:00:00Z" }, assistant_message: { message_id: "assistant-1", conversation_id: "conversation-1", project_id: "project-1", session_id: "session-1", role: "assistant", text: "두 가지를 준비했어요.", proposal_id: "proposal-1", metadata: {}, client_message_id: null, created_at: "2026-07-23T00:00:01Z" } }]}
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
