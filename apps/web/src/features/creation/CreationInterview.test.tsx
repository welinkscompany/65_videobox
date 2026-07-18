import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api } from "../../api";
import { CreationInterview } from "./CreationInterview";

afterEach(() => { cleanup(); vi.restoreAllMocks(); window.localStorage.clear(); });

const firstBrief = {
  brief_id: "brief_1", project_id: "project_1", idempotency_key: "stable-key", script_filename: "붙여넣은-대본.txt", script_text: "신제품을 소개합니다.", script_asset_id: null,
  capability_profile: { ai_execution: "disabled" }, questions: [
    { question_id: "q_audience", field: "audience", prompt: "누구에게 보여줄까요?" },
    { question_id: "q_tone", field: "tone", prompt: "어떤 분위기로 만들까요?" },
  ], answers: {}, current_step: 0, status: "interview", revision: 1, created_at: "now", updated_at: "now",
};

describe("CreationInterview", () => {
  it("starts a project-scoped Eugene interview from pasted script and saves the resulting brief id for refresh resume", async () => {
    const create = vi.spyOn(api, "createCreationBrief").mockResolvedValue(firstBrief);
    render(<CreationInterview projectId="project_1" />);

    fireEvent.change(screen.getByLabelText("대본 붙여넣기"), { target: { value: "신제품을 소개합니다." } });
    fireEvent.click(screen.getByRole("button", { name: "유진과 기획 시작" }));

    await screen.findByText("누구에게 보여줄까요?");
    expect(screen.getByText("1 / 2")).toBeVisible();
    expect(create).toHaveBeenCalledWith("project_1", expect.objectContaining({
      script_filename: "붙여넣은-대본.txt", script_text: "신제품을 소개합니다.", capability_profile: { ai_execution: "disabled" },
    }));
    expect(window.localStorage.getItem("videobox.creation-brief.project_1")).toBe("brief_1");
  });

  it("uploads a supported creator script instead of exposing a local filesystem path", async () => {
    const upload = vi.spyOn(api, "uploadCreationBrief").mockResolvedValue(firstBrief);
    render(<CreationInterview projectId="project_1" />);
    const file = new File(["# 신제품 소개"], "launch.md", { type: "text/markdown" });

    fireEvent.change(screen.getByLabelText("대본 파일 선택"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "파일로 기획 시작" }));

    await screen.findByText("누구에게 보여줄까요?");
    expect(upload).toHaveBeenCalledWith("project_1", file, expect.objectContaining({ capability_profile: { ai_execution: "disabled" } }));
  });

  it("reuses the pasted-script idempotency key when a creator retries before any server response", async () => {
    const create = vi.spyOn(api, "createCreationBrief").mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(firstBrief);
    render(<CreationInterview projectId="project_1" />);
    fireEvent.change(screen.getByLabelText("대본 붙여넣기"), { target: { value: "신제품을 소개합니다." } });
    fireEvent.click(screen.getByRole("button", { name: "유진과 기획 시작" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "유진과 기획 시작" }));

    await screen.findByText("누구에게 보여줄까요?");
    expect(create.mock.calls[0][1].idempotency_key).toBe(create.mock.calls[1][1].idempotency_key);
  });

  it("submits a creator shortcut as an answer and advances only from the durable response", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    const advanced = { ...firstBrief, answers: { audience: "추천해줘" }, current_step: 1, revision: 2 };
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(firstBrief);
    const answer = vi.spyOn(api, "answerCreationBriefQuestion").mockResolvedValue(advanced);
    render(<CreationInterview projectId="project_1" />);

    await screen.findByText("누구에게 보여줄까요?");
    fireEvent.click(screen.getByRole("button", { name: "추천해줘" }));

    await screen.findByText("어떤 분위기로 만들까요?");
    expect(answer).toHaveBeenCalledWith("project_1", "brief_1", "q_audience", { answer: "추천해줘", expected_revision: 1 });
    expect(screen.getByText("2 / 2")).toBeVisible();
  });

  it("lets a creator durably skip the remaining interview and move to the editable summary", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    const bypassed = { ...firstBrief, current_step: 2, status: "ready_for_approval", revision: 2, summary: "영상 기획을 직접 정리합니다." };
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(firstBrief);
    const bypass = vi.spyOn(api, "bypassCreationBriefInterview").mockResolvedValue(bypassed);
    render(<CreationInterview projectId="project_1" />);

    await screen.findByText("누구에게 보여줄까요?");
    fireEvent.click(screen.getByRole("button", { name: "바로 요약 보기" }));

    await screen.findByLabelText("기획 요약");
    expect(bypass).toHaveBeenCalledWith("project_1", "brief_1", { expected_revision: 1 });
  });

  it("keeps a failed durable answer on the same question with an actionable retry", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(firstBrief);
    const answer = vi.spyOn(api, "answerCreationBriefQuestion").mockRejectedValue(new Error("offline"));
    render(<CreationInterview projectId="project_1" />);

    await screen.findByText("누구에게 보여줄까요?");
    fireEvent.click(screen.getByRole("button", { name: "건너뛰기" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("답변을 저장하지 못했습니다."));
    expect(screen.getByText("누구에게 보여줄까요?")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(answer).toHaveBeenCalledTimes(2));
    expect(answer.mock.calls.map((call) => call[3])).toEqual([
      { answer: "건너뛰기", expected_revision: 1 },
      { answer: "건너뛰기", expected_revision: 1 },
    ]);
  });

  it("requires an editable durable summary before the creator approves the brief", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    const ready = { ...firstBrief, answers: { audience: "처음 방문한 고객", tone: "차분하게" }, current_step: 2, status: "ready_for_approval", revision: 3, summary: "처음 방문한 고객에게 차분하게 소개" };
    const saved = { ...ready, revision: 4, summary: "처음 방문한 고객에게 따뜻하게 소개" };
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(ready);
    const update = vi.spyOn(api, "updateCreationBriefSummary").mockResolvedValue(saved);
    const approve = vi.spyOn(api, "approveCreationBrief").mockResolvedValue({ ...saved, status: "approved", revision: 5 });
    render(<CreationInterview projectId="project_1" />);

    const summary = await screen.findByLabelText("기획 요약");
    fireEvent.change(summary, { target: { value: "처음 방문한 고객에게 따뜻하게 소개" } });
    fireEvent.click(screen.getByRole("button", { name: "요약 저장" }));
    await waitFor(() => expect(update).toHaveBeenCalledWith("project_1", "brief_1", { summary: "처음 방문한 고객에게 따뜻하게 소개", expected_revision: 3 }));
    fireEvent.click(screen.getByRole("button", { name: "요약 승인" }));
    await waitFor(() => expect(approve).toHaveBeenCalledWith("project_1", "brief_1", { expected_revision: 4 }));
    expect(screen.getByText("기획을 확인했어요")).toBeVisible();
  });

  it("confirms deletion of retained creator input then clears the resumable interview", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(firstBrief);
    const remove = vi.spyOn(api, "deleteCreationBrief").mockResolvedValue();
    vi.stubGlobal("confirm", vi.fn(() => true));
    render(<CreationInterview projectId="project_1" />);

    await screen.findByText("누구에게 보여줄까요?");
    fireEvent.click(screen.getByRole("button", { name: "대본과 기획 삭제" }));

    await screen.findByRole("heading", { name: "유진과 영상 기획을 시작해요" });
    expect(remove).toHaveBeenCalledWith("project_1", "brief_1");
    expect(window.localStorage.getItem("videobox.creation-brief.project_1")).toBeNull();
  });

  it("starts a durable, silent draft preview only after approval", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(approved);
    const start = vi.spyOn(api, "startDraftReadiness").mockResolvedValue({ readiness_id: "ready_1", status: "needs_assets", revision: 1, result: { gap_slots: [{ gap_slot_id: "gap-1", reason: "영상이 없어요." }] } } as never);
    render(<CreationInterview projectId="project_1" />);
    fireEvent.click(await screen.findByRole("button", { name: "무음으로 초안 준비" }));
    await screen.findByText("추가 자산이 필요해요");
    expect(start).toHaveBeenCalledWith("project_1", expect.objectContaining({ brief_id: "brief_1", narration_choice: { kind: "silent" }, expected_brief_revision: 5 }));
  });

  it("saves each B-roll candidate's chosen seconds with the current readiness revision", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    const readiness = { readiness_id: "readiness_1", brief_id: "brief_1", status: "ready", revision: 3, result: { broll_candidates: [{ asset_id: "asset_1", label: "제품을 보여 주는 장면", target_range: { start_sec: 0, end_sec: 5 } }] } } as never;
    const saved = { ...readiness, revision: 4, result: { broll_candidates: [{ asset_id: "asset_1", label: "제품을 보여 주는 장면", target_range: { start_sec: 1.5, end_sec: 4 } }] } } as never;
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(approved);
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue(readiness);
    const updateRange = vi.spyOn(api, "updateDraftReadinessCandidateRange").mockResolvedValue(saved);
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_1");
    render(<CreationInterview projectId="project_1" />);

    fireEvent.change(await screen.findByLabelText("제품을 보여 주는 장면 시작"), { target: { value: "1.5" } });
    fireEvent.change(screen.getByLabelText("제품을 보여 주는 장면 끝"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "구간 저장" }));

    await waitFor(() => expect(updateRange).toHaveBeenCalledWith("project_1", "readiness_1", "asset_1", 1.5, 4, 3));
    expect(screen.getByDisplayValue("1.5")).toBeVisible();
  });

  it("resumes only a server-confirmed readiness id from the route", async () => {
    window.history.replaceState({}, "", "/projects/project_1/create?readiness_id=readiness_1");
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue({ ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 });
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue({ readiness_id: "readiness_1", brief_id: "brief_1", status: "cancelled", revision: 2, result: null });
    render(<CreationInterview projectId="project_1" />);
    expect(await screen.findByRole("heading", { name: "초안 준비를 멈췄어요" })).toBeVisible();
    expect(screen.getByRole("button", { name: "다시 준비" })).toBeVisible();
  });

  it("refreshes a failed automatic advance before retrying with the server's current revision", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_1");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    const planning = { readiness_id: "readiness_1", brief_id: "brief_1", status: "planning", revision: 3, result: null } as never;
    const failed = { ...planning, status: "failed", revision: 7 } as never;
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(approved);
    const getReadiness = vi.spyOn(api, "getDraftReadiness").mockResolvedValueOnce(planning).mockResolvedValueOnce(failed);
    vi.spyOn(api, "completeDraftReadiness").mockRejectedValue(new Error("conflict"));
    const retry = vi.spyOn(api, "retryDraftReadiness").mockResolvedValue({ ...failed, status: "planning", revision: 8 });
    render(<CreationInterview projectId="project_1" />);

    await waitFor(() => expect(getReadiness).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "초안을 준비하지 못했어요" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "준비 계속하기" }));
    await waitFor(() => expect(retry).toHaveBeenCalledWith("project_1", "readiness_1", 7));
  });

  it("does not resume readiness that belongs to a deleted or replaced brief", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_legacy");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue({ ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 });
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue({ readiness_id: "readiness_legacy", brief_id: "brief_deleted", status: "failed", revision: 7, result: { gap_slots: [{ gap_slot_id: "old", reason: "이전 기획 결과" }] } } as never);
    render(<CreationInterview projectId="project_1" />);

    expect(await screen.findByRole("button", { name: "무음으로 초안 준비" })).toBeVisible();
    expect(screen.queryByText("이전 기획 결과")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("videobox.draft-readiness.project_1")).toBeNull();
  });

  it("shows a helpful retry when microphone permission is denied", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue({ ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 });
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockRejectedValue(new Error("denied")) } });
    render(<CreationInterview projectId="project_1" />);
    fireEvent.click(await screen.findByRole("button", { name: "마이크로 녹음 시작" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("마이크를 사용할 수 없습니다");
  });

  it("uploads a stopped microphone recording through the narration endpoint and offers retry", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue({ ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 });
    const upload = vi.spyOn(api, "uploadDraftNarration").mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ asset_id: "narration-1", asset_type: "narration_audio" });
    class Recorder { ondataavailable: ((event: { data: Blob }) => void) | null = null; onstop: (() => void) | null = null; start() {} stop() { this.ondataavailable?.({ data: new Blob(["audio"], { type: "audio/webm" }) }); this.onstop?.(); } }
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) } });
    vi.stubGlobal("MediaRecorder", Recorder);
    render(<CreationInterview projectId="project_1" />);
    fireEvent.click(await screen.findByRole("button", { name: "마이크로 녹음 시작" }));
    fireEvent.click(await screen.findByRole("button", { name: "녹음 마치기" }));
    await screen.findByText("소리 파일을 준비하지 못했습니다.");
    fireEvent.click(screen.getByRole("button", { name: "녹음 다시 올리기" }));
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    expect(upload.mock.calls[0][1]).toBeInstanceOf(File);
  });

  it("discards a recorder on unmount without uploading its onstop blob", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue({ ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 });
    const upload = vi.spyOn(api, "uploadDraftNarration").mockResolvedValue({ asset_id: "n", asset_type: "narration_audio" });
    const stop = vi.fn(); const stream = { getTracks: () => [{ stop }] };
    class Recorder { ondataavailable: ((event: { data: Blob }) => void) | null = null; onstop: (() => void) | null = null; state = "inactive"; start() { this.state = "recording"; } stop() { this.ondataavailable?.({ data: new Blob(["audio"]) }); this.onstop?.(); } }
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue(stream) } }); vi.stubGlobal("MediaRecorder", Recorder);
    const view = render(<CreationInterview projectId="project_1" />); fireEvent.click(await screen.findByRole("button", { name: "마이크로 녹음 시작" })); await waitFor(() => expect(stop).not.toHaveBeenCalled()); view.unmount();
    expect(stop).toHaveBeenCalled(); expect(upload).not.toHaveBeenCalled();
  });
});
