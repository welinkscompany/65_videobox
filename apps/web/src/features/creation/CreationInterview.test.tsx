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
  it("shows a saved draft resume action and supported file guidance before starting another brief", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(firstBrief);
    render(<CreationInterview projectId="project_1" />);

    expect(await screen.findByRole("button", { name: "초안 이어서 하기" })).toBeVisible();
    cleanup();
    window.localStorage.clear();
    render(<CreationInterview projectId="project_1" />);
    // **갱신 이유(2026-08-22).** 구분자만 바뀌었다(`,` -> `·`) -- owner 지시로
    // 설명 문장을 키워드로 옮기는 중이다. 지키려는 것은 "어떤 파일을 고를 수
    // 있는지 화면이 말한다"이지 쉼표가 아니다.
    expect(screen.getByText(/TXT · MD · SRT/)).toBeVisible();
    expect(screen.getByLabelText("대본 파일 선택")).toBeVisible();
  });

  it("clears the previous project's brief before loading a reused route", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    const getBrief = vi.spyOn(api, "getCreationBrief").mockImplementation(async (projectId) => (
      projectId === "project_1"
        ? firstBrief
        : { ...firstBrief, brief_id: "brief_2", project_id: "project_2", script_text: "두 번째 프로젝트 대본" }
    ));
    const view = render(<CreationInterview projectId="project_1" />);
    await screen.findByText("누구에게 보여줄까요?");

    window.localStorage.setItem("videobox.creation-brief.project_2", "brief_2");
    view.rerender(<CreationInterview projectId="project_2" />);
    expect(screen.queryByText("누구에게 보여줄까요?")).not.toBeInTheDocument();
    expect(screen.getByText("새 프로젝트의 기획을 불러오는 중이에요.")).toBeVisible();
    expect(getBrief).toHaveBeenCalledWith("project_2", "brief_2");
    await screen.findByText("누구에게 보여줄까요?");
    expect(screen.queryByText("신제품을 소개합니다.")).not.toBeInTheDocument();
  });

  it("resets the orientation choice when a reused creation route changes projects", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_1");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    const ready = { readiness_id: "readiness_1", brief_id: "brief_1", status: "ready", revision: 3, result: {} } as never;
    const readyB = { readiness_id: "readiness_2", brief_id: "brief_2", status: "ready", revision: 1, result: {} } as never;
    vi.spyOn(api, "getCreationBrief").mockImplementation(async (projectId) => projectId === "project_1"
      ? approved
      : { ...approved, brief_id: "brief_2", project_id: "project_2" });
    vi.spyOn(api, "getDraftReadiness").mockImplementation(async (projectId) => projectId === "project_1" ? ready : readyB);
    const view = render(<CreationInterview projectId="project_1" />);
    const orientation = await screen.findByLabelText("숏폼(세로)으로 만들기");
    fireEvent.click(orientation);
    expect(orientation).toBeChecked();

    window.localStorage.setItem("videobox.creation-brief.project_2", "brief_2");
    window.localStorage.setItem("videobox.draft-readiness.project_2", "readiness_2");
    view.rerender(<CreationInterview projectId="project_2" />);
    const nextOrientation = await screen.findByLabelText("숏폼(세로)으로 만들기");
    expect(nextOrientation).not.toBeChecked();
  });

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

  it("keeps each question answer separate and restores only that question after going back", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    const afterFirst = { ...firstBrief, answers: { audience: "처음 방문한 고객" }, current_step: 1, revision: 2 };
    const backAtFirst = { ...afterFirst, current_step: 0, revision: 3 };
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(firstBrief);
    vi.spyOn(api, "answerCreationBriefQuestion").mockResolvedValue(afterFirst);
    const previous = vi.spyOn(api, "previousCreationBriefQuestion").mockResolvedValue(backAtFirst);
    render(<CreationInterview projectId="project_1" />);

    const answer = await screen.findByLabelText("답변");
    fireEvent.change(answer, { target: { value: "처음 방문한 고객" } });
    fireEvent.click(screen.getByRole("button", { name: "답변 저장" }));
    const nextAnswer = await screen.findByLabelText("답변");
    expect(nextAnswer).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "이전 질문" }));

    await screen.findByText("누구에게 보여줄까요?");
    expect(previous).toHaveBeenCalledWith("project_1", "brief_1", { expected_revision: 2 });
    expect(screen.getByLabelText("답변")).toHaveValue("처음 방문한 고객");
  });

  it("creates an editable non-empty summary from the script and saved creator answers", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    const ready = {
      ...firstBrief,
      script_text: "사무실에서 일하는 작은 팀을 소개합니다.",
      questions: [
        { question_id: "q_audience", field: "audience", prompt: "누구에게 보여줄까요?" },
        { question_id: "q_format", field: "format", prompt: "어디에 올릴 영상인가요?" },
        { question_id: "q_cta", field: "call_to_action", prompt: "시청자가 다음에 무엇을 하면 좋을까요?" },
      ],
      answers: { audience: "신규 고객", format: "인스타그램 릴스", call_to_action: "상담을 문의하기" },
      current_step: 3,
      status: "ready_for_approval",
      summary: "",
      revision: 4,
    };
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(ready);
    render(<CreationInterview projectId="project_1" />);

    const summary = await screen.findByLabelText("기획 요약");
    expect((summary as HTMLTextAreaElement).value).toContain("사무실에서 일하는 작은 팀을 소개합니다.");
    expect((summary as HTMLTextAreaElement).value).toContain("신규 고객");
    expect((summary as HTMLTextAreaElement).value).toContain("인스타그램 릴스");
    expect((summary as HTMLTextAreaElement).value).toContain("상담을 문의하기");
    expect(screen.getByRole("button", { name: "요약 승인" })).toBeEnabled();
  });

  it("saves a generated summary before approving it", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    const ready = {
      ...firstBrief,
      answers: { audience: "신규 고객", tone: "차분하게" },
      current_step: 2,
      status: "ready_for_approval",
      summary: "",
      revision: 3,
    };
    const saved = { ...ready, summary: "영상 내용: 신제품을 소개합니다.\n보여줄 사람: 신규 고객\n분위기: 차분하게", revision: 4 };
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(ready);
    const update = vi.spyOn(api, "updateCreationBriefSummary").mockResolvedValue(saved);
    const approve = vi.spyOn(api, "approveCreationBrief").mockResolvedValue({ ...saved, status: "approved", revision: 5 });
    render(<CreationInterview projectId="project_1" />);

    fireEvent.click(await screen.findByRole("button", { name: "요약 승인" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith("project_1", "brief_1", expect.objectContaining({ expected_revision: 3 })));
    await waitFor(() => expect(approve).toHaveBeenCalledWith("project_1", "brief_1", { expected_revision: 4 }));
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
    await screen.findByText("추가 미디어가 필요해요");
    expect(start).toHaveBeenCalledWith("project_1", expect.objectContaining({ brief_id: "brief_1", narration_choice: { kind: "silent" }, expected_brief_revision: 5 }));
  });

  it("requires an explicit creator confirmation before making an in-app-only gap draft", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    const needsAssets = { readiness_id: "readiness_gap", brief_id: "brief_1", status: "needs_assets", revision: 3, result: { gap_slots: [{ gap_slot_id: "gap-1", reason: "영상이 없어요." }] } } as never;
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(approved);
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue(needsAssets);
    const create = vi.spyOn(api, "createAtomicDraftBundle").mockResolvedValue({ session_id: "editing_1" } as never);
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_gap");
    render(<CreationInterview projectId="project_1" />);

    expect(await screen.findByText("누락된 장면은 빈 구간으로 남습니다. 이 초안은 내보낼 수 없어요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "빈 구간 포함 초안 만들기" })).toBeDisabled();
    expect(create).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText("빈 구간을 남긴 채 편집용 초안을 만들겠습니다"));
    fireEvent.click(screen.getByRole("button", { name: "빈 구간 포함 초안 만들기" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith("project_1", {
      brief_id: "brief_1", readiness_id: "readiness_gap", expected_brief_revision: 5,
      expected_readiness_revision: 3, idempotency_key: "draft-bundle-readiness_gap-3", allow_placeholder: true,
    }));
  });

  it("lets the creator pick shortform, and defaults to long-form", async () => {
    // Task 33: the owner makes both. Vertical output existed in the engine but
    // the draft path never carried a choice, so shortform was unreachable.
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_ready");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    const ready = { readiness_id: "readiness_ready", brief_id: "brief_1", status: "ready", revision: 3, result: {} } as never;
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(approved as never);
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue(ready);
    const create = vi.spyOn(api, "createAtomicDraftBundle").mockResolvedValue({ session_id: "editing_1" } as never);
    render(<CreationInterview projectId="project_1" />);

    await screen.findByRole("button", { name: "초안 만들기" });
    fireEvent.click(screen.getByLabelText("숏폼(세로)으로 만들기"));
    fireEvent.click(screen.getByRole("button", { name: "초안 만들기" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith("project_1", {
      brief_id: "brief_1", readiness_id: "readiness_ready", expected_brief_revision: 5,
      expected_readiness_revision: 3, idempotency_key: "draft-bundle-readiness_ready-3",
      orientation: "vertical",
    }));
  });

  it("keeps the placeholder confirmation when the same readiness effect flushes after the creator checks it", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_gap");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    const needsAssets = { readiness_id: "readiness_gap", brief_id: "brief_1", status: "needs_assets", revision: 3, result: { gap_slots: [{ gap_slot_id: "gap-1", reason: "영상이 없어요." }] } } as never;
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(approved);
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue(needsAssets);
    const create = vi.spyOn(api, "createAtomicDraftBundle").mockResolvedValue({ session_id: "editing_1" } as never);
    render(<CreationInterview projectId="project_1" />);

    const confirmation = await screen.findByLabelText("빈 구간을 남긴 채 편집용 초안을 만들겠습니다");
    fireEvent.click(confirmation);
    await Promise.resolve();

    expect(confirmation).toBeChecked();
    expect(screen.getByRole("button", { name: "빈 구간 포함 초안 만들기" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "빈 구간 포함 초안 만들기" }));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
  });

  it("clears the placeholder confirmation through delayed readiness A to B to A transitions", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_a");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    const readinessA = { readiness_id: "readiness_a", brief_id: "brief_1", status: "needs_assets", revision: 3, result: { gap_slots: [{ gap_slot_id: "gap-a", reason: "A 자산이 없어요." }] } } as never;
    const readinessB = { readiness_id: "readiness_b", brief_id: "brief_1", status: "needs_assets", revision: 4, result: { gap_slots: [{ gap_slot_id: "gap-b", reason: "B 자산이 없어요." }] } } as never;
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(approved);
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue(readinessA);
    const retry = vi.spyOn(api, "retryDraftReadiness").mockResolvedValueOnce(readinessB).mockResolvedValueOnce(readinessA);
    render(<CreationInterview projectId="project_1" />);

    const confirmation = await screen.findByLabelText("빈 구간을 남긴 채 편집용 초안을 만들겠습니다");
    fireEvent.click(confirmation);
    expect(confirmation).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "다시 준비" }));
    await waitFor(() => expect(retry).toHaveBeenCalledWith("project_1", "readiness_a", 3));
    await waitFor(() => expect(screen.getByLabelText("빈 구간을 남긴 채 편집용 초안을 만들겠습니다")).not.toBeChecked());

    fireEvent.click(screen.getByRole("button", { name: "다시 준비" }));
    await waitFor(() => expect(retry).toHaveBeenLastCalledWith("project_1", "readiness_b", 4));
    await waitFor(() => expect(screen.getByLabelText("빈 구간을 남긴 채 편집용 초안을 만들겠습니다")).not.toBeChecked());
    expect(screen.getByRole("button", { name: "빈 구간 포함 초안 만들기" })).toBeDisabled();
  });

  it("surfaces retry and cancel readiness failures instead of leaving an unhandled rejection", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_1");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    const failed = { readiness_id: "readiness_1", brief_id: "brief_1", status: "failed", revision: 3, result: null } as never;
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(approved);
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue(failed);
    vi.spyOn(api, "retryDraftReadiness").mockRejectedValue(new Error("conflict"));
    render(<CreationInterview projectId="project_1" />);

    fireEvent.click(await screen.findByRole("button", { name: "다시 준비" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("다시 준비하지 못했습니다");
  });

  it("surfaces candidate skip failures in the readiness workspace", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_1");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    const ready = { readiness_id: "readiness_1", brief_id: "brief_1", status: "ready", revision: 3, result: { broll_candidates: [{ asset_id: "asset_1", label: "제품 장면", target_range: { start_sec: 0, end_sec: 2 } }] } } as never;
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(approved);
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue(ready);
    vi.spyOn(api, "updateDraftReadinessCandidate").mockRejectedValue(new Error("conflict"));
    render(<CreationInterview projectId="project_1" />);

    fireEvent.click(await screen.findByRole("button", { name: "제품 장면 건너뛰기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("장면을 건너뛰지 못했습니다");
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

  it("does not show or submit B-roll candidates with an unusable time range", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_1");
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    const readiness = { readiness_id: "readiness_1", brief_id: "brief_1", status: "ready", revision: 3, result: { broll_candidates: [
      { asset_id: "asset_ok", label: "쓸 수 있는 장면", target_range: { start_sec: 0, end_sec: 4 }, media_duration_sec: 4 },
      { asset_id: "asset_bad", label: "잘못된 장면", target_range: { start_sec: 10, end_sec: 10 }, media_duration_sec: 10 },
    ] } } as never;
    vi.spyOn(api, "getCreationBrief").mockResolvedValue(approved);
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue(readiness);
    const updateRange = vi.spyOn(api, "updateDraftReadinessCandidateRange");
    render(<CreationInterview projectId="project_1" />);

    expect(await screen.findByLabelText("쓸 수 있는 장면 시작")).toBeVisible();
    expect(screen.queryByLabelText("잘못된 장면 시작")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "잘못된 장면 건너뛰기" })).not.toBeInTheDocument();
    expect(updateRange).not.toHaveBeenCalled();
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
    await waitFor(() => expect(window.localStorage.getItem("videobox.draft-readiness.project_1")).toBeNull());
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

  /** 찍어 둔 영상으로 시작하는 길이 **기존 기획 흐름으로 이어지는지**를 본다.
   *
   *  이 저장소가 반복해 온 실패가 "부품은 있는데 부르는 자리가 없다"이고,
   *  그 다음 단계가 "부르긴 하는데 그 다음으로 안 이어진다"이다. 받아쓰기만
   *  되고 그 영상이 내레이션으로 안 이어지면 owner는 자기가 올린 본편을 두고
   *  무음 초안을 만들게 된다. */
  it("영상에서 받아쓴 대본으로 기획을 열고, 그 영상을 내레이션으로도 이어 준다", async () => {
    const approved = { ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 };
    vi.spyOn(api, "uploadSourceVideo").mockResolvedValue({ asset_id: "raw_video_1", script_text: "받아쓴 대본", spoken_segment_count: 2 });
    // 올린 영상은 프로젝트 자산으로 남으므로 서버 후보 목록에도 들어온다.
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([{ asset_id: "raw_video_1", asset_type: "raw_video" }]);
    const create = vi.spyOn(api, "createCreationBrief").mockResolvedValue(approved);
    const startDraft = vi.spyOn(api, "startDraftReadiness").mockResolvedValue({ readiness_id: "readiness_1", brief_id: "brief_1", status: "planning", revision: 1, result: null });
    render(<CreationInterview projectId="project_1" />);

    fireEvent.change(screen.getByLabelText("찍어 둔 영상 선택"), { target: { files: [new File(["v"], "본편.mp4", { type: "video/mp4" })] } });
    fireEvent.click(screen.getByRole("button", { name: "영상에서 대본 만들기" }));

    const edited = await screen.findByLabelText("영상에서 받아쓴 대본");
    fireEvent.change(edited, { target: { value: "고쳐 쓴 대본" } });
    fireEvent.click(screen.getByRole("button", { name: "이 대본으로 기획 시작" }));

    // 받아쓴 글이 아니라 **owner가 고친 글**로 기획이 열려야 한다.
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][1]).toMatchObject({ script_text: "고쳐 쓴 대본" });

    // 그 영상이 곧 본편이다. 내레이션으로 고를 수 있어야 한다.
    fireEvent.click(await screen.findByRole("button", { name: "영상 소리로 초안 준비" }));
    await waitFor(() => expect(startDraft).toHaveBeenCalled());
    expect(startDraft.mock.calls[0][1]).toMatchObject({ narration_choice: { kind: "source_video", asset_id: "raw_video_1" } });
  });

  it("새로 고쳐도 올려 둔 영상을 내레이션 후보로 다시 찾아 준다", async () => {
    // 이 되짚기는 **이미 있던 동작**을 고정한다(승인되면 서버에서 후보를 다시
    // 읽는 효과가 이미 걸려 있다). 찍어 둔 영상 길이 생기면서 이 경로가 처음으로
    // 실제 쓰임을 갖게 됐으므로 -- 그 전에는 `raw_video` 후보를 만들 방법이
    // 아예 없었다 -- 조용히 끊기지 않게 여기서 붙잡아 둔다.
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue({ ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 });
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([{ asset_id: "raw_video_1", asset_type: "raw_video" }]);
    render(<CreationInterview projectId="project_1" />);

    expect(await screen.findByRole("button", { name: "영상 소리로 초안 준비" })).toBeVisible();
  });

  /** 빈 장면 자동 채우기(owner 요청 2026-08-29): "내 비롤에 ai 영상도 같이
   *  붙여서 자동화를 만드는거야." 브롤이 안 닿은 장면마다 owner가 일일이
   *  "그림 만들기"를 누르지 않아도, 한 번에 순서대로 다 채워야 한다. */
  it("빈 장면 모두 AI로 채우기를 누르면 브롤이 못 채운 장면을 순서대로 다 채운다", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_gap");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue({ ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 });
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([]);

    const scriptSegments = [
      { segment_id: "seg-1", text: "첫 장면 대사", start_sec: 0, end_sec: 2 },
      { segment_id: "seg-2", text: "둘째 장면 대사", start_sec: 2, end_sec: 4 },
    ];
    const withTwoGaps = {
      readiness_id: "readiness_gap", brief_id: "brief_1", status: "needs_assets", revision: 3,
      result: {
        script_segments: scriptSegments,
        gap_slots: [
          { gap_slot_id: "gap-1", reason: "장면에 넣을 영상이 없어요.", segment_id: "seg-1", target_range: { start_sec: 0, end_sec: 2 } },
          { gap_slot_id: "gap-2", reason: "장면에 넣을 영상이 없어요.", segment_id: "seg-2", target_range: { start_sec: 2, end_sec: 4 } },
        ],
      },
    } as never;
    const withOneGap = { ...withTwoGaps, revision: 4, result: { script_segments: scriptSegments, gap_slots: [withTwoGaps.result.gap_slots[1]] } } as never;
    const ready = { readiness_id: "readiness_gap", brief_id: "brief_1", status: "ready", revision: 5, result: { script_segments: scriptSegments, gap_slots: [] } } as never;

    vi.spyOn(api, "getDraftReadiness").mockResolvedValue(withTwoGaps);
    const createSceneImage = vi.spyOn(api, "createSceneImage").mockResolvedValue({
      image_asset_id: "img-1", scene_asset_id: "scene-1", segment_id: "seg-1", title: "t", prompt: "p", seed: 1,
    });
    const retry = vi.spyOn(api, "retryDraftReadiness")
      .mockResolvedValueOnce({ readiness_id: "readiness_gap", brief_id: "brief_1", status: "planning", revision: 4, result: null })
      .mockResolvedValueOnce({ readiness_id: "readiness_gap", brief_id: "brief_1", status: "planning", revision: 5, result: null });
    const complete = vi.spyOn(api, "completeDraftReadiness")
      .mockResolvedValueOnce(withOneGap)
      .mockResolvedValueOnce(ready);

    render(<CreationInterview projectId="project_1" />);

    const fillButton = await screen.findByRole("button", { name: "빈 장면 모두 AI로 채우기" });
    fireEvent.click(fillButton);

    await waitFor(() => expect(createSceneImage).toHaveBeenCalledTimes(2));
    // 첫 번째는 첫 장면(seg-1), 두 번째는 남은 장면(seg-2) -- 순서대로다.
    expect(createSceneImage.mock.calls[0][1]).toMatchObject({ segment_id: "seg-1", gap_slot_id: "gap-1", prompt: "첫 장면 대사" });
    expect(createSceneImage.mock.calls[1][1]).toMatchObject({ segment_id: "seg-2", gap_slot_id: "gap-2", prompt: "둘째 장면 대사" });
    expect(retry).toHaveBeenCalledTimes(2);
    expect(complete).toHaveBeenCalledTimes(2);

    await screen.findByText("AI 그림으로 2개 장면을 채웠어요.");
    // 다 채워졌으니 더 채울 빈 장면 단추는 사라진다.
    expect(screen.queryByRole("button", { name: "빈 장면 모두 AI로 채우기" })).not.toBeInTheDocument();
  });

  it("브롤이 못 채운 장면이 없으면 자동 채우기 단추가 보이지 않는다", async () => {
    window.localStorage.setItem("videobox.creation-brief.project_1", "brief_1");
    window.localStorage.setItem("videobox.draft-readiness.project_1", "readiness_no_gap");
    vi.spyOn(api, "getCreationBrief").mockResolvedValue({ ...firstBrief, questions: [], current_step: 0, status: "approved", revision: 5 });
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([]);
    vi.spyOn(api, "getDraftReadiness").mockResolvedValue({
      readiness_id: "readiness_no_gap", brief_id: "brief_1", status: "needs_assets", revision: 2,
      // segment_id 없는 공백은 AI로 못 채우는 자리다(예: 대본 자체가 비어 있는
      // 경우) -- 이런 자리만 있으면 자동 채우기 단추를 보여주지 않는다.
      result: { gap_slots: [{ gap_slot_id: "gap-1", reason: "대본이 비어 있어요." }] },
    } as never);

    render(<CreationInterview projectId="project_1" />);

    await screen.findByText("대본이 비어 있어요.");
    expect(screen.queryByRole("button", { name: "빈 장면 모두 AI로 채우기" })).not.toBeInTheDocument();
  });
});
