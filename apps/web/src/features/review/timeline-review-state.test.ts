import { describe, expect, it } from "vitest";

import type { EditingSession, JobRecord, ReviewSnapshot, TimelineJob } from "../../api";
import {
  collectTimelineReviewBlockers,
  isCurrentTimelineReviewState,
  selectCurrentTimelineJob,
} from "./timeline-review-state";

const session = {
  session_id: "session-current",
  project_id: "project-a",
  timeline_id: "timeline-current",
  session_revision: 7,
} as EditingSession;

function job(overrides: Partial<JobRecord>): JobRecord {
  return {
    job_id: "job-default",
    project_id: "project-a",
    job_type: "timeline_build",
    status: "succeeded",
    input_ref: null,
    output_ref: "timeline-current",
    error_message: null,
    started_at: "2026-07-23T00:00:00Z",
    finished_at: "2026-07-23T00:00:01Z",
    ...overrides,
  };
}

describe("timeline review state", () => {
  it("selects only the newest succeeded timeline build with an exact current timeline output", () => {
    const selected = selectCurrentTimelineJob(session, [
      job({ job_id: "newest-unrelated", output_ref: "timeline-other", finished_at: "2026-07-23T00:09:00Z" }),
      job({ job_id: "failed-current", status: "failed", finished_at: "2026-07-23T00:08:00Z" }),
      job({ job_id: "other-kind-current", job_type: "final_render", finished_at: "2026-07-23T00:07:00Z" }),
      job({ job_id: "older-current", finished_at: "2026-07-23T00:01:00Z" }),
      job({ job_id: "newer-current", finished_at: "2026-07-23T00:02:00Z" }),
    ]);

    expect(selected?.job_id).toBe("newer-current");
    expect(selectCurrentTimelineJob(session, [job({ output_ref: "timeline-other" })])).toBeNull();
  });

  it("breaks equal finish-time ties by started time and then job ID for ascending store rows", () => {
    const selected = selectCurrentTimelineJob(session, [
      job({ job_id: "job-a", started_at: "2026-07-23T00:00:00Z", finished_at: "2026-07-23T00:03:00Z" }),
      job({ job_id: "job-z", started_at: "2026-07-23T00:01:00Z", finished_at: "2026-07-23T00:03:00Z" }),
      job({ job_id: "job-y", started_at: "2026-07-23T00:02:00Z", finished_at: "2026-07-23T00:03:00Z" }),
      job({ job_id: "job-z", started_at: "2026-07-23T00:02:00Z", finished_at: "2026-07-23T00:03:00Z" }),
    ]);

    expect(selected?.job_id).toBe("job-z");
    expect(selected?.started_at).toBe("2026-07-23T00:02:00Z");
  });

  it("keeps every timeline and review blocker with its source and original detail", () => {
    const timelineFlag = { code: " Audio-Check ", segment_id: "segment-1", message: "타임라인 소리 확인" };
    const reviewFlag = { code: "audio-check", segment_id: "segment-1", message: "검토 화면 소리 확인" };
    const timelineRecommendation = {
      recommendation_id: "recommendation-shared",
      target_segment_id: "segment-1",
      recommendation_type: "broll",
      reason: "장면 보강",
      score: 0.4,
    };
    const reviewRecommendation = {
      recommendation_id: "recommendation-shared",
      target_segment_id: "segment-1",
      recommendation_type: "broll",
      reason: "장면 보강",
      score: 0.9,
    };
    const blockers = collectTimelineReviewBlockers(
      { timeline: { review_flags: [timelineFlag], pending_recommendations: [timelineRecommendation] } } as TimelineJob,
      { review_flags: [reviewFlag], pending_recommendations: [reviewRecommendation] } as ReviewSnapshot,
    );

    expect(blockers).toEqual([
      {
        semanticKey: "review_flag:audio-check:segment-1",
        sources: ["timeline", "review"],
        kind: "review_flag",
        item: reviewFlag,
        sourceEntries: [
          { source: "timeline", item: timelineFlag },
          { source: "review", item: reviewFlag },
        ],
      },
      {
        semanticKey: "pending_recommendation:recommendation-shared",
        sources: ["timeline", "review"],
        kind: "pending_recommendation",
        conflict: false,
        item: reviewRecommendation,
        sourceEntries: [
          { source: "timeline", item: timelineRecommendation },
          { source: "review", item: reviewRecommendation },
        ],
      },
    ]);
  });

  it("marks a duplicate recommendation ID with divergent semantics as a non-actionable conflict", () => {
    const timelineRecommendation = {
      recommendation_id: "recommendation-conflict",
      target_segment_id: "segment-1",
      recommendation_type: "broll",
      reason: "타임라인 장면 보강",
    };
    const reviewRecommendation = {
      recommendation_id: "recommendation-conflict",
      target_segment_id: "segment-2",
      recommendation_type: "music",
      reason: "검토 화면 음악 보강",
    };
    const [blocker] = collectTimelineReviewBlockers(
      { timeline: { review_flags: [], pending_recommendations: [timelineRecommendation] } } as TimelineJob,
      { review_flags: [], pending_recommendations: [reviewRecommendation] } as ReviewSnapshot,
    );

    expect(blocker).toMatchObject({
      semanticKey: "pending_recommendation:recommendation-conflict",
      kind: "pending_recommendation",
      conflict: true,
      item: reviewRecommendation,
      sourceEntries: [
        { source: "timeline", item: timelineRecommendation },
        { source: "review", item: reviewRecommendation },
      ],
    });
  });

  it("does not collapse malformed review flags whose canonical identity is missing", () => {
    const blockers = collectTimelineReviewBlockers(
      { timeline: { review_flags: [{ code: "", segment_id: "", message: "첫 확인" }], pending_recommendations: [] } } as TimelineJob,
      { review_flags: [{ code: "", segment_id: "", message: "둘째 확인" }], pending_recommendations: [] } as ReviewSnapshot,
    );

    expect(blockers).toHaveLength(2);
    expect(blockers.map((blocker) => blocker.semanticKey)).toEqual([
      "review_flag:fallback:timeline:0",
      "review_flag:fallback:review:0",
    ]);
  });

  it("fails closed unless every project, timeline, job, freshness, and revision binding is current", () => {
    const selectedJob = job({ job_id: "job-current" });
    const timeline = { job_id: "job-current", status: "succeeded", timeline: { timeline_id: "timeline-current", project_id: "project-a" } } as TimelineJob;
    const review = { project_id: "project-a", timeline_id: "timeline-current" } as ReviewSnapshot;
    const approval = {
      project_id: "project-a",
      timeline_id: "timeline-current",
      review_status: "draft",
      source_session_revision: 7,
      is_current: true,
    };
    const input = { projectId: "project-a", session, job: selectedJob, timeline, review, approval };

    expect(isCurrentTimelineReviewState(input)).toBe(true);
    expect(isCurrentTimelineReviewState({ ...input, approval: { ...approval, is_current: false } })).toBe(false);
    expect(isCurrentTimelineReviewState({ ...input, approval: { ...approval, source_session_revision: 6 } })).toBe(false);
    expect(isCurrentTimelineReviewState({ ...input, review: { ...review, timeline_id: "timeline-other" } })).toBe(false);
    expect(isCurrentTimelineReviewState({ ...input, timeline: { ...timeline, timeline: { ...timeline.timeline, timeline_id: "timeline-other" } } })).toBe(false);
  });
});
