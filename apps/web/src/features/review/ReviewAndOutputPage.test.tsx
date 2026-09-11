import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../../api";
import { ReviewAndOutputPage } from "./ReviewAndOutputPage";

beforeEach(() => {
  vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
  vi.spyOn(api, "listJobs").mockResolvedValue([]);
  vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue(null as never);
  vi.spyOn(api, "listOutputVariants").mockResolvedValue({ variants: [] } as never);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it("asks for the shared editing state once, not once per half of the screen", async () => {
  // 두 영역을 그냥 나란히 놓으면 같은 것을 두 번 묻는다. 요청이 두 배가 될 뿐
  // 아니라 두 영역이 서로 다른 시점의 사실을 볼 수 있다.
  render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} />);

  await waitFor(() => expect(api.listJobs).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByTestId("review-and-output-page")).toBeInTheDocument());

  expect(api.listJobs).toHaveBeenCalledTimes(1);
  expect(api.getLatestEditingSession).toHaveBeenCalledTimes(1);
});

it("shows both halves on one screen", async () => {
  render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} />);

  // 편집본이 없으면 검토는 안내로, 출력은 자기 상태로 각각 응답한다.
  await waitFor(() => expect(screen.getByText("먼저 편집할 초안을 만들어 주세요.")).toBeVisible());
  await waitFor(() => expect(screen.getByTestId("outputs-page")).toBeInTheDocument());
});

it("asks CapCut for handoff status once per screen, not once per re-sync", async () => {
  // 실측(2026-08-30, 브라우저 네트워크 로그): 한 화면을 여는 동안
  // `/api/capcut/handoff-diagnostics`가 두 번 나갔다. 출력 쪽 effect가
  // `shared`가 채워질 때 다시 도는 것 자체는 의도(주석 참고)이지만, 그때
  // CapCut 상태까지 다시 물을 이유는 없다 -- 검토 쪽 승인 여부와 CapCut
  // 상태는 서로 무관하다.
  render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} />);

  await waitFor(() => expect(screen.getByTestId("outputs-page")).toBeInTheDocument());
  await waitFor(() => expect(api.listJobs).toHaveBeenCalled());

  expect(api.getCapcutHandoffDiagnostics).toHaveBeenCalledTimes(1);
});

it("has exactly one page-level heading, not one per half", async () => {
  // 실측(2026-08-30, 브라우저): 두 절반이 각자 <h1>을 내서 화면 하나에
  // <h1>이 둘이었다("영상 검토" · "완성본과 CapCut 초안") -- 스크린리더가
  // 헤딩으로 훑을 때 페이지의 최상위 제목이 무엇인지 알 수 없게 만든다.
  render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} />);

  await waitFor(() => expect(screen.getByTestId("outputs-page")).toBeInTheDocument());

  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
});

/** 완성본을 만드는 동안 화면이 스스로 상태를 다시 읽는다. 그 재확인이 검토
 *  영역까지 "불러오는 중"으로 되돌리면, 몇 분짜리 완성본을 만드는 내내 화면
 *  윗부분이 5초마다 접혔다 펴진다(스크롤이 튄다). 하필 그 화면을 계속 열어
 *  두라고 안내하는 화면이다.
 *
 *  **이 시험은 합쳐진 화면으로 그린다.** 기존 재확인 시험들은 `OutputsPage`를
 *  단독으로(`shared`/`onSharedRefresh` 없이) 그려서 이 경계를 한 번도 안
 *  지났다 -- 그래서 깜빡임을 못 잡았다. */
function stubReadyReviewAndRunningFinal() {
  const session = {
    session_id: "session-a", project_id: "project-a", timeline_id: "timeline-a",
    session_revision: 4, segments: [], history: [],
  };
  const reviewJob = {
    job_id: "job-a", project_id: "project-a", job_type: "timeline_build", status: "succeeded",
    input_ref: "source", output_ref: "timeline-a", error_message: null,
    started_at: "2026-09-11T00:00:00Z", finished_at: "2026-09-11T00:01:00Z",
  };
  const runningFinal = {
    job_id: "final-a", project_id: "project-a", job_type: "final_render", status: "running",
    input_ref: "job-a", output_ref: null, error_message: null,
    started_at: "2026-09-11T00:02:00Z", finished_at: null,
  };
  vi.mocked(api.getLatestEditingSession).mockResolvedValue(session as never);
  vi.mocked(api.listJobs).mockResolvedValue([reviewJob, runningFinal] as never);
  vi.spyOn(api, "getTimeline").mockResolvedValue({
    job_id: "job-a", status: "succeeded",
    timeline: {
      timeline_id: "timeline-a", project_id: "project-a", version: "v1", output_mode: "review",
      review_status: "draft", source_session_id: "session-a", source_session_revision: 4,
      tracks: [], review_flags: [], applied_recommendations: [], pending_recommendations: [],
    },
  } as never);
  vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({
    project_id: "project-a", timeline_id: "timeline-a", review_status: "draft",
    segments: [], applied_recommendations: [], pending_recommendations: [], review_flags: [],
  } as never);
  vi.spyOn(api, "getReviewApproval").mockResolvedValue({
    project_id: "project-a", timeline_id: "timeline-a", review_status: "draft",
    approved_at: null, updated_at: "2026-09-11T00:02:00Z",
    source_session_id: "session-a", source_session_revision: 4, is_current: true,
    invalidated_at: null, invalidated_reason: null,
  } as never);
  vi.spyOn(api, "getFinalRender").mockResolvedValue({ job_id: "final-a", status: "running", render: null } as never);
  vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(null as never);
  vi.spyOn(api, "getSubtitle").mockResolvedValue(null as never);
}

it("완성본을 만드는 동안 스스로 다시 읽어도 검토 영역이 깜빡이지 않는다", async () => {
  vi.useFakeTimers();
  stubReadyReviewAndRunningFinal();

  render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} />);
  // fake timer 아래에서는 findBy/waitFor의 내부 타이머가 안 돈다 --
  // 마이크로태스크만 비워서 첫 읽기를 끝낸다(OutputsPage.test.tsx의 같은 처리).
  await act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
  expect(screen.getByRole("heading", { level: 1, name: "영상 검토" })).toBeVisible();

  // 두 번째 읽기를 붙잡아 둔다. 붙잡힌 **그 사이에** 화면이 무엇을 보여주는지가
  // 이 시험이 재는 것이다 -- 실제 서버에서는 그 사이가 수백 밀리초다.
  vi.mocked(api.getLatestEditingSession).mockImplementationOnce(() => new Promise(() => {}) as never);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
    for (let i = 0; i < 6; i += 1) await Promise.resolve();
  });

  // 재확인이 실제로 나갔는가 -- 이게 없으면 아래 단언이 엉뚱한 이유로 초록이 된다.
  expect(vi.mocked(api.getLatestEditingSession).mock.calls.length).toBeGreaterThan(1);
  expect(screen.queryByText("검토 내용을 불러오는 중이에요.")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1, name: "영상 검토" })).toBeVisible();
});
