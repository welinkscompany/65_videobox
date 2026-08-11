import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type EditingSession, type JobRecord, type ReviewApproval, type ReviewSnapshot, type TimelineJob } from "../../api";
import { TimelineReviewPage } from "./TimelineReviewPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const session = (projectId = "project-a", timelineId = "timeline-a"): EditingSession => ({
  session_id: `session-${projectId}`,
  project_id: projectId,
  timeline_id: timelineId,
  session_revision: 4,
  segments: [],
  history: [],
});
const timelineJob = (projectId = "project-a", timelineId = "timeline-a"): JobRecord => ({
  job_id: `job-${projectId}`,
  project_id: projectId,
  job_type: "timeline_build",
  status: "succeeded",
  input_ref: "source",
  output_ref: timelineId,
  error_message: null,
  started_at: "2026-07-23T00:00:00Z",
  finished_at: "2026-07-23T00:01:00Z",
});
const recommendation = {
  recommendation_id: "recommendation-a",
  target_segment_id: "segment-2",
  recommendation_type: "broll",
  selected_asset_id: null,
  score: 0.9,
  reason: "둘째 장면을 더 잘 보여줘요.",
  auto_apply_allowed: false,
  review_required: true,
  payload: {},
  created_at: "2026-07-23T00:00:00Z",
};
const timeline = (projectId = "project-a", timelineId = "timeline-a", pending = []): TimelineJob => ({
  job_id: `job-${projectId}`,
  status: "succeeded",
  timeline: {
    timeline_id: timelineId,
    project_id: projectId,
    version: "v1",
    output_mode: "review",
    review_status: "draft",
    tracks: [],
    review_flags: [],
    applied_recommendations: [],
    pending_recommendations: pending,
  },
});
const review = (projectId = "project-a", timelineId = "timeline-a", pending = []): ReviewSnapshot => ({
  project_id: projectId,
  timeline_id: timelineId,
  review_status: "draft",
  segments: [
    { segment_id: "segment-1", text: "첫 장면", start_sec: 0, end_sec: 1, confidence: 1, review_required: false, cleanup_decision: "keep" },
    { segment_id: "segment-2", text: "둘째 장면", start_sec: 1, end_sec: 2, confidence: 1, review_required: true, cleanup_decision: "review" },
  ],
  applied_recommendations: [],
  pending_recommendations: pending,
  review_flags: [],
});
const approval = (projectId = "project-a", timelineId = "timeline-a", status = "draft"): ReviewApproval => ({
  project_id: projectId,
  timeline_id: timelineId,
  review_status: status,
  approved_at: status === "approved" ? "2026-07-23T00:02:00Z" : null,
  updated_at: "2026-07-23T00:02:00Z",
  source_session_revision: 4,
  is_current: true,
  invalidated_at: null,
  invalidated_reason: null,
});

describe("TimelineReviewPage", () => {
  beforeEach(() => {
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(session());
    vi.spyOn(api, "listJobs").mockResolvedValue([timelineJob()]);
    vi.spyOn(api, "getTimeline").mockResolvedValue(timeline());
    vi.spyOn(api, "getReviewSnapshot").mockResolvedValue(review());
    vi.spyOn(api, "getReviewApproval").mockResolvedValue(approval());
  });

  it("loads read-only current review data and links an exact segment to the pinned editor", async () => {
    const onOpenSegment = vi.fn();
    const approveTimeline = vi.spyOn(api, "approveTimeline");
    const reopenTimeline = vi.spyOn(api, "reopenTimeline");
    const approveRecommendation = vi.spyOn(api, "approveReviewRecommendation");
    render(<TimelineReviewPage projectId="project-a" onOpenSegment={onOpenSegment} />);

    expect(screen.getByText("검토 내용을 불러오는 중이에요.")).toBeVisible();
    expect(await screen.findByRole("heading", { name: "영상 검토" })).toBeVisible();
    expect(screen.getByText("둘째 장면")).toBeVisible();
    const segmentLink = screen.getByRole("link", { name: "둘째 장면 편집하기" });
    expect(segmentLink).toHaveAttribute(
      "href",
      "/projects/project-a/editor?session_id=session-project-a&segment_id=segment-2",
    );
    expect(fireEvent.click(segmentLink)).toBe(false);
    expect(onOpenSegment).toHaveBeenCalledWith({
      projectId: "project-a",
      sessionId: "session-project-a",
      segmentId: "segment-2",
    });
    // Task 31: approval is what unlocks export. It used to be withheld here,
    // which left every output button permanently disabled in the browser.
    expect(screen.queryByText(/안전한 승인 계약이 준비될 때까지/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "검토 승인" }));
    await waitFor(() => expect(approveTimeline).toHaveBeenCalledWith("project-a", "job-project-a"));
    // Recommendation approve/reject stays out of scope for now.
    expect(approveRecommendation).not.toHaveBeenCalled();
    expect(reopenTimeline).not.toHaveBeenCalled();
  });

  it("blocks approval while items still need checking, and says why", async () => {
    // The server refuses an approval that still has blockers, so the screen
    // must not offer an action that cannot succeed.
    vi.mocked(api.getTimeline).mockResolvedValue(timeline("project-a", "timeline-a", [recommendation] as never));
    vi.mocked(api.getReviewSnapshot).mockResolvedValue(review("project-a", "timeline-a", [recommendation] as never));
    const approveTimeline = vi.spyOn(api, "approveTimeline");
    render(<TimelineReviewPage projectId="project-a" />);
    await screen.findByRole("heading", { name: "영상 검토" });

    expect(screen.getByRole("button", { name: "검토 승인" })).toBeDisabled();
    expect(screen.getByText("확인할 항목을 모두 마치면 승인할 수 있어요.")).toBeVisible();
    expect(approveTimeline).not.toHaveBeenCalled();
  });

  it("surfaces a failed approval in creator language without leaking the raw error", async () => {
    vi.spyOn(api, "approveTimeline").mockRejectedValue(new Error("timeline_has_blockers"));
    render(<TimelineReviewPage projectId="project-a" />);
    await screen.findByRole("heading", { name: "영상 검토" });

    fireEvent.click(screen.getByRole("button", { name: "검토 승인" }));

    expect(await screen.findByText("검토를 승인하지 못했어요. 확인할 항목을 살펴본 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(document.body.textContent).not.toContain("timeline_has_blockers");
  });

  it("shows no-session, no-exact-match, load error, and an explicit successful refresh", async () => {
    vi.mocked(api.getLatestEditingSession).mockResolvedValueOnce(null);
    render(<TimelineReviewPage projectId="project-a" />);
    expect(await screen.findByText("먼저 편집할 초안을 만들어 주세요.")).toBeVisible();
    expect(api.getTimeline).not.toHaveBeenCalled();

    vi.mocked(api.getLatestEditingSession).mockResolvedValue(session());
    vi.mocked(api.listJobs).mockResolvedValueOnce([timelineJob("project-a", "timeline-other")]);
    fireEvent.click(screen.getByRole("button", { name: "다시 확인" }));
    expect(await screen.findByText("현재 편집본과 맞는 검토본이 없어요.")).toBeVisible();

    vi.mocked(api.listJobs).mockRejectedValueOnce(new Error("offline"));
    fireEvent.click(screen.getByRole("button", { name: "다시 확인" }));
    expect(await screen.findByText("검토 내용을 불러오지 못했어요.")).toBeVisible();

    vi.mocked(api.listJobs).mockResolvedValue([timelineJob()]);
    fireEvent.click(screen.getByRole("button", { name: "다시 확인" }));
    expect(await screen.findByRole("heading", { name: "영상 검토" })).toBeVisible();
    expect(screen.getByTestId("timeline-review-page")).toBeVisible();
  });

  it("fails closed for mismatched responses or stale durable approval", async () => {
    vi.mocked(api.getReviewApproval).mockResolvedValue({ ...approval(), is_current: false, invalidated_reason: "edited" });
    render(<TimelineReviewPage projectId="project-a" />);

    expect(await screen.findByText("이 검토본은 현재 편집본과 맞지 않아요. 현재 편집본으로 다시 만들어 주세요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "현재 편집본으로 검토본 다시 만들기" })).toBeVisible();
    expect(screen.getByRole("link", { name: "편집으로 돌아가기" })).toHaveAttribute("href", "/projects/project-a/editor?session_id=session-project-a");
    expect(screen.queryByRole("button", { name: "검토 승인" })).toBeNull();
  });

  // 편집을 한 번이라도 하면 승인 기록이 내려간다. 그 자체는 옳지만 다시 세울 자리가
  // 없어서, 이 화면이 "맞지 않아요"에서 영영 나가지 못했고 내보내기까지 막혔다.
  // `다시 확인`은 같은 것을 다시 읽을 뿐이라 답이 바뀌지 않는다.
  it("offers a way out of a review the owner's own edit invalidated", async () => {
    vi.mocked(api.getReviewApproval).mockResolvedValueOnce({ ...approval(), is_current: false, invalidated_reason: "editing_session_mutation" });
    const refreshReview = vi.spyOn(api, "refreshReviewForCurrentEdit").mockResolvedValue({ ...approval(), review_status: "draft" });
    render(<TimelineReviewPage projectId="project-a" />);

    expect(await screen.findByText("편집이 바뀌어서 이 검토본은 현재 편집본과 맞지 않아요.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "현재 편집본으로 검토본 다시 만들기" }));

    await waitFor(() => expect(refreshReview).toHaveBeenCalledWith("project-a", "session-project-a"));
    expect(await screen.findByRole("heading", { name: "영상 검토" })).toBeVisible();
    expect(screen.getByTestId("timeline-review-page")).toBeVisible();
  });

  it("says so when the review could not be rebuilt, instead of looking unchanged", async () => {
    vi.mocked(api.getReviewApproval).mockResolvedValue({ ...approval(), is_current: false, invalidated_reason: "editing_session_mutation" });
    vi.spyOn(api, "refreshReviewForCurrentEdit").mockRejectedValue(new Error("offline"));
    render(<TimelineReviewPage projectId="project-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "현재 편집본으로 검토본 다시 만들기" }));

    expect(await screen.findByText("검토본을 다시 만들지 못했어요. 잠시 뒤 다시 시도해 주세요.")).toBeVisible();
  });

  it("shows one creator-facing row per matching blocker and exposes no mutation action", async () => {
    const timelineWithDuplicates = timeline("project-a", "timeline-a", [
      { ...recommendation, reason: "둘째 장면을 더 잘 보여줘요." },
    ]);
    vi.mocked(api.getReviewSnapshot).mockResolvedValue({
      ...review("project-a", "timeline-a", [recommendation]),
      review_flags: [{ code: "audio-check", segment_id: "segment-1", message: "검토 화면의 소리를 확인해 주세요." }],
    });
    vi.mocked(api.getTimeline).mockResolvedValue({
      ...timelineWithDuplicates,
      timeline: {
        ...timelineWithDuplicates.timeline,
        review_flags: [{ code: " AUDIO-CHECK ", segment_id: "segment-1", message: "타임라인의 이전 소리 설명" }],
      },
    });
    const approveRecommendation = vi.spyOn(api, "approveReviewRecommendation");
    render(<TimelineReviewPage projectId="project-a" />);

    expect(await screen.findByText("검토 화면의 소리를 확인해 주세요.")).toBeVisible();
    expect(screen.queryByText("타임라인의 이전 소리 설명")).toBeNull();
    expect(screen.getAllByText("둘째 장면을 더 잘 보여줘요.")).toHaveLength(1);
    expect(screen.getAllByText("종류: B-roll")).toHaveLength(1);
    expect(screen.getAllByText("대상: 2번째 장면 · 둘째 장면")).toHaveLength(1);
    expect(screen.getByText("대상: 1번째 장면 · 첫 장면")).toBeVisible();
    expect(screen.getAllByText("편집본·검토 화면에서 확인")).toHaveLength(2);
    expect(screen.queryByText(/segment-[12]|종류: broll/)).toBeNull();
    // Blockers are present, so approval is offered but held shut.
    expect(screen.getByRole("button", { name: "검토 승인" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /검토 다시 열기|이 추천 승인/ })).toBeNull();
    expect(approveRecommendation).not.toHaveBeenCalled();
  });

  it("keeps an already approved review read-only and calls no mutation endpoint", async () => {
    vi.mocked(api.getReviewApproval).mockResolvedValue(approval("project-a", "timeline-a", "approved"));
    const approveTimeline = vi.spyOn(api, "approveTimeline");
    const reopenTimeline = vi.spyOn(api, "reopenTimeline");
    const approveRecommendation = vi.spyOn(api, "approveReviewRecommendation");
    render(<TimelineReviewPage projectId="project-a" />);

    expect(await screen.findByText("현재 편집본의 검토가 승인되었어요.")).toBeVisible();
    // Already approved: re-approving is meaningless, and reopening is how the
    // owner gets back to editing without losing the approval record.
    expect(screen.queryByRole("button", { name: "검토 승인" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "검토 다시 열기" }));
    await waitFor(() => expect(reopenTimeline).toHaveBeenCalledWith("project-a", "job-project-a"));
    expect(approveTimeline).not.toHaveBeenCalled();
    expect(approveRecommendation).not.toHaveBeenCalled();
  });

  it("fences a late project A detail response after switching to B", async () => {
    let resolveA!: (value: TimelineJob) => void;
    vi.mocked(api.getTimeline).mockImplementation((projectId) => (
      projectId === "project-a" ? new Promise((resolve) => { resolveA = resolve; }) : Promise.resolve(timeline("project-b", "timeline-b"))
    ));
    vi.mocked(api.getLatestEditingSession).mockImplementation((projectId) => Promise.resolve(session(projectId, `timeline-${projectId.at(-1)}`)));
    vi.mocked(api.listJobs).mockImplementation((projectId) => Promise.resolve([timelineJob(projectId, `timeline-${projectId.at(-1)}`)]));
    vi.mocked(api.getReviewSnapshot).mockImplementation((projectId) => Promise.resolve(review(projectId, `timeline-${projectId.at(-1)}`)));
    vi.mocked(api.getReviewApproval).mockImplementation((projectId) => Promise.resolve(approval(projectId, `timeline-${projectId.at(-1)}`)));
    const rendered = render(<TimelineReviewPage projectId="project-a" />);
    await waitFor(() => expect(api.getTimeline).toHaveBeenCalledWith("project-a", "job-project-a"));

    rendered.rerender(<TimelineReviewPage projectId="project-b" />);
    expect(await screen.findByRole("heading", { name: "영상 검토" })).toBeVisible();
    expect(screen.getByTestId("timeline-review-page")).toHaveAttribute("data-project-id", "project-b");
    await act(async () => { resolveA(timeline("project-a", "timeline-a")); });
    expect(screen.getByTestId("timeline-review-page")).toHaveAttribute("data-project-id", "project-b");
  });

  it("shows divergent duplicate recommendations as a safe conflict with no raw action", async () => {
    vi.mocked(api.getTimeline).mockResolvedValue(timeline("project-a", "timeline-a", [{
      ...recommendation,
      target_segment_id: "segment-1",
      reason: "타임라인의 충돌 설명",
    }]));
    vi.mocked(api.getReviewSnapshot).mockResolvedValue(review("project-a", "timeline-a", [{
      ...recommendation,
      recommendation_type: "music",
      reason: "검토 화면의 충돌 설명",
    }]));
    const approveRecommendation = vi.spyOn(api, "approveReviewRecommendation");
    render(<TimelineReviewPage projectId="project-a" />);

    expect(await screen.findByText("같은 추천의 내용이 서로 달라 안전하게 표시할 수 없어요. 다시 확인해 주세요.")).toBeVisible();
    expect(screen.queryByText("타임라인의 충돌 설명")).toBeNull();
    expect(screen.queryByText("검토 화면의 충돌 설명")).toBeNull();
    expect(screen.queryByRole("button", { name: "이 추천 승인" })).toBeNull();
    expect(approveRecommendation).not.toHaveBeenCalled();
  });
});
