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
});
