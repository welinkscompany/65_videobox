import type {
  EditingSession,
  JobRecord,
  RecommendationItem,
  ReviewApproval,
  ReviewFlag,
  ReviewSnapshot,
  TimelineJob,
} from "../../api";

type TimelineReviewSource = "timeline" | "review";
type ReviewFlagSourceEntry = Readonly<{ source: TimelineReviewSource; item: ReviewFlag }>;
type RecommendationSourceEntry = Readonly<{ source: TimelineReviewSource; item: RecommendationItem }>;

export type TimelineReviewBlocker =
  | Readonly<{
    semanticKey: string;
    sources: readonly TimelineReviewSource[];
    sourceEntries: readonly ReviewFlagSourceEntry[];
    kind: "review_flag";
    item: ReviewFlag;
  }>
  | Readonly<{
    semanticKey: string;
    sources: readonly TimelineReviewSource[];
    sourceEntries: readonly RecommendationSourceEntry[];
    kind: "pending_recommendation";
    conflict: boolean;
    item: RecommendationItem;
  }>;

function compareTimelineJobs(left: JobRecord, right: JobRecord) {
  const leftKeys = [left.finished_at ?? "", left.started_at ?? "", left.job_id];
  const rightKeys = [right.finished_at ?? "", right.started_at ?? "", right.job_id];
  for (let index = 0; index < leftKeys.length; index += 1) {
    if (leftKeys[index] > rightKeys[index]) return 1;
    if (leftKeys[index] < rightKeys[index]) return -1;
  }
  return 0;
}

export function selectCurrentTimelineJob(session: EditingSession, jobs: readonly JobRecord[]): JobRecord | null {
  return jobs.reduce<JobRecord | null>((newest, job) => {
    if (
      job.project_id !== session.project_id ||
      job.job_type !== "timeline_build" ||
      job.status !== "succeeded" ||
      job.output_ref !== session.timeline_id
    ) return newest;
    return newest === null || compareTimelineJobs(job, newest) > 0 ? job : newest;
  }, null);
}

export function collectTimelineReviewBlockers(timeline: TimelineJob, review: ReviewSnapshot): TimelineReviewBlocker[] {
  const blockers = new Map<string, TimelineReviewBlocker>();
  const addFlag = (source: TimelineReviewSource, item: ReviewFlag, index: number) => {
    const code = item.code.trim().toLowerCase();
    const segmentId = item.segment_id.trim();
    const semanticKey = code && segmentId
      ? `review_flag:${code}:${segmentId}`
      : `review_flag:fallback:${source}:${index}`;
    const current = blockers.get(semanticKey);
    if (current?.kind === "review_flag") {
      blockers.set(semanticKey, {
        ...current,
        sources: current.sources.includes(source) ? current.sources : [...current.sources, source],
        sourceEntries: [...current.sourceEntries, { source, item }],
        item: source === "review" ? item : current.item,
      });
      return;
    }
    blockers.set(semanticKey, {
      semanticKey,
      sources: [source],
      sourceEntries: [{ source, item }],
      kind: "review_flag",
      item,
    });
  };
  const recommendationSemantics = (item: RecommendationItem) => [
    item.recommendation_type.trim().toLowerCase(),
    item.target_segment_id.trim(),
    item.reason.trim(),
  ].join("\u0000");
  const addRecommendation = (source: TimelineReviewSource, item: RecommendationItem, index: number) => {
    const recommendationId = item.recommendation_id.trim();
    const semanticKey = recommendationId
      ? `pending_recommendation:${recommendationId}`
      : `pending_recommendation:fallback:${source}:${index}`;
    const current = blockers.get(semanticKey);
    if (current?.kind === "pending_recommendation") {
      blockers.set(semanticKey, {
        ...current,
        sources: current.sources.includes(source) ? current.sources : [...current.sources, source],
        sourceEntries: [...current.sourceEntries, { source, item }],
        conflict: current.conflict || recommendationSemantics(current.item) !== recommendationSemantics(item),
        item: source === "review" ? item : current.item,
      });
      return;
    }
    blockers.set(semanticKey, {
      semanticKey,
      sources: [source],
      sourceEntries: [{ source, item }],
      kind: "pending_recommendation",
      conflict: false,
      item,
    });
  };

  timeline.timeline.review_flags.forEach((item, index) => addFlag("timeline", item, index));
  timeline.timeline.pending_recommendations.forEach((item, index) => addRecommendation("timeline", item, index));
  review.review_flags.forEach((item, index) => addFlag("review", item, index));
  review.pending_recommendations.forEach((item, index) => addRecommendation("review", item, index));
  return [...blockers.values()];
}

export function isCurrentTimelineReviewState(input: Readonly<{
  projectId: string;
  session: EditingSession;
  job: JobRecord;
  timeline: TimelineJob;
  review: ReviewSnapshot;
  approval: ReviewApproval;
}>): boolean {
  const { projectId, session, job, timeline, review, approval } = input;
  return Boolean(
    session.project_id === projectId &&
    session.timeline_id &&
    job.project_id === projectId &&
    job.job_type === "timeline_build" &&
    job.status === "succeeded" &&
    job.output_ref === session.timeline_id &&
    timeline.status === "succeeded" &&
    timeline.job_id === job.job_id &&
    timeline.timeline.project_id === projectId &&
    timeline.timeline.timeline_id === session.timeline_id &&
    review.project_id === projectId &&
    review.timeline_id === session.timeline_id &&
    approval.project_id === projectId &&
    approval.timeline_id === session.timeline_id &&
    approval.is_current === true &&
    approval.source_session_revision === session.session_revision
  );
}
