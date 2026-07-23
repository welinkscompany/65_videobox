import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  type EditingSession,
  type JobRecord,
  type ReviewApproval,
  type ReviewSnapshot,
  type TimelineJob,
} from "../../api";
import { Button } from "../../components/ui/button";
import {
  collectTimelineReviewBlockers,
  isCurrentTimelineReviewState,
  selectCurrentTimelineJob,
  type TimelineReviewBlocker,
} from "./timeline-review-state";

type ReadyState = Readonly<{
  kind: "ready";
  projectId: string;
  session: EditingSession;
  job: JobRecord;
  timeline: TimelineJob;
  review: ReviewSnapshot;
  approval: ReviewApproval;
  blockers: TimelineReviewBlocker[];
}>;
type ReviewState =
  | ReadyState
  | Readonly<{ kind: "loading"; projectId: string }>
  | Readonly<{ kind: "no-session"; projectId: string }>
  | Readonly<{ kind: "no-match"; projectId: string }>
  | Readonly<{ kind: "error"; projectId: string }>
  | Readonly<{ kind: "stale"; projectId: string }>;

type OpenSegmentInput = Readonly<{ projectId: string; sessionId: string; segmentId: string }>;

export function TimelineReviewPage({
  projectId,
  onOpenSegment,
}: {
  projectId: string;
  onOpenSegment?: (input: OpenSegmentInput) => void;
}) {
  const [state, setState] = useState<ReviewState>({ kind: "loading", projectId });
  const requestEpoch = useRef(0);
  const currentProjectId = useRef(projectId);
  currentProjectId.current = projectId;

  const loadDetails = useCallback(async (
    session: EditingSession,
    job: JobRecord,
    options?: Readonly<{ loading?: boolean }>,
  ) => {
    const loadProjectId = projectId;
    const epoch = requestEpoch.current + 1;
    requestEpoch.current = epoch;
    const isCurrent = () => currentProjectId.current === loadProjectId && requestEpoch.current === epoch;
    if (options?.loading !== false) setState({ kind: "loading", projectId: loadProjectId });
    try {
      const [timeline, review, approval] = await Promise.all([
        api.getTimeline(loadProjectId, job.job_id),
        api.getReviewSnapshot(loadProjectId, job.job_id),
        api.getReviewApproval(loadProjectId, session.timeline_id),
      ]);
      if (!isCurrent()) return;
      if (!isCurrentTimelineReviewState({ projectId: loadProjectId, session, job, timeline, review, approval })) {
        setState({ kind: "stale", projectId: loadProjectId });
        return;
      }
      setState({
        kind: "ready",
        projectId: loadProjectId,
        session,
        job,
        timeline,
        review,
        approval,
        blockers: collectTimelineReviewBlockers(timeline, review),
      });
    } catch {
      if (isCurrent()) setState({ kind: "error", projectId: loadProjectId });
    }
  }, [projectId]);

  const refresh = useCallback(async () => {
    const loadProjectId = projectId;
    const epoch = requestEpoch.current + 1;
    requestEpoch.current = epoch;
    const isCurrent = () => currentProjectId.current === loadProjectId && requestEpoch.current === epoch;
    setState({ kind: "loading", projectId: loadProjectId });
    try {
      const [session, jobs] = await Promise.all([
        api.getLatestEditingSession(loadProjectId),
        api.listJobs(loadProjectId),
      ]);
      if (!isCurrent()) return;
      if (!session) {
        setState({ kind: "no-session", projectId: loadProjectId });
        return;
      }
      if (session.project_id !== loadProjectId || !session.timeline_id) {
        setState({ kind: "stale", projectId: loadProjectId });
        return;
      }
      const job = selectCurrentTimelineJob(session, jobs);
      if (!job) {
        setState({ kind: "no-match", projectId: loadProjectId });
        return;
      }
      await loadDetails(session, job);
    } catch {
      if (isCurrent()) setState({ kind: "error", projectId: loadProjectId });
    }
  }, [loadDetails, projectId]);

  useEffect(() => {
    void refresh();
    return () => {
      requestEpoch.current += 1;
    };
  }, [refresh]);

  if (state.projectId !== projectId || state.kind === "loading") {
    return <section aria-live="polite"><p>검토 내용을 불러오는 중이에요.</p></section>;
  }
  if (state.kind === "no-session") return <ReviewRecovery message="먼저 편집할 초안을 만들어 주세요." onRefresh={refresh} />;
  if (state.kind === "no-match") return <ReviewRecovery message="현재 편집본과 맞는 검토본이 없어요." onRefresh={refresh} />;
  if (state.kind === "error") return <ReviewRecovery message="검토 내용을 불러오지 못했어요." onRefresh={refresh} />;
  if (state.kind === "stale") return <ReviewRecovery message="이 검토본은 현재 편집본과 맞지 않아요. 다시 확인해 주세요." onRefresh={refresh} />;

  const approved = state.approval.review_status === "approved";
  return (
    <section data-testid="timeline-review-page" data-project-id={state.projectId} aria-live="polite">
      <p>검토</p>
      <h1>영상 검토</h1>
      <p>장면과 추천 상태를 확인해 주세요.</p>
      <p>{approved ? "현재 편집본의 검토가 승인되었어요." : "현재 편집본을 검토하고 있어요."}</p>
      <p>안전한 승인 계약이 준비될 때까지 승인과 추천 변경은 사용할 수 없어요. 장면 편집과 다시 확인은 계속할 수 있어요.</p>

      <section aria-labelledby="review-blockers-title">
        <h2 id="review-blockers-title">확인할 항목</h2>
        {state.blockers.length === 0 ? <p>확인할 항목이 없어요.</p> : (
          <ul>{state.blockers.map((blocker) => (
            <li key={blocker.semanticKey}>
              <small>{blockerSourceLabel(blocker.sources)}</small>
              {blocker.kind === "review_flag" ? (
                <><p>{blocker.item.message}</p><p>{`대상: ${segmentTargetLabel(state.review, blocker.item.segment_id)}`}</p></>
              ) : blocker.conflict ? (
                <p>같은 추천의 내용이 서로 달라 안전하게 표시할 수 없어요. 다시 확인해 주세요.</p>
              ) : (
                <>
                  <p>{blocker.item.reason}</p>
                  <p>{`종류: ${recommendationTypeLabel(blocker.item.recommendation_type)}`}</p>
                  <p>{`대상: ${segmentTargetLabel(state.review, blocker.item.target_segment_id)}`}</p>
                </>
              )}
            </li>
          ))}</ul>
        )}
      </section>

      <section aria-labelledby="review-segments-title">
        <h2 id="review-segments-title">장면</h2>
        {state.review.segments.length === 0 ? <p>표시할 장면이 없어요.</p> : (
          <ul>{state.review.segments.map((segment) => (
            <li key={segment.segment_id}>
              <p>{segment.text}</p>
              <p>{`${segment.start_sec}초–${segment.end_sec}초`}</p>
              <a
                href={editorSegmentHref(state.projectId, state.session.session_id, segment.segment_id)}
                onClick={(event) => {
                  if (
                    !onOpenSegment ||
                    event.button !== 0 ||
                    event.metaKey ||
                    event.ctrlKey ||
                    event.shiftKey ||
                    event.altKey
                  ) return;
                  event.preventDefault();
                  onOpenSegment({
                    projectId: state.projectId,
                    sessionId: state.session.session_id,
                    segmentId: segment.segment_id,
                  });
                }}
              >
                {`${segment.text || segment.segment_id} 편집하기`}
              </a>
            </li>
          ))}</ul>
        )}
      </section>

      <Button variant="outline" onClick={() => void refresh()}>다시 확인</Button>
    </section>
  );
}

function editorSegmentHref(projectId: string, sessionId: string, segmentId: string) {
  return `/projects/${encodeURIComponent(projectId)}/editor?session_id=${encodeURIComponent(sessionId)}&segment_id=${encodeURIComponent(segmentId)}`;
}

function blockerSourceLabel(sources: readonly ("timeline" | "review")[]) {
  if (sources.includes("timeline") && sources.includes("review")) return "편집본·검토 화면에서 확인";
  return sources.includes("review") ? "검토 화면에서 확인" : "편집본에서 확인";
}

function recommendationTypeLabel(type: string) {
  switch (type.trim().toLowerCase()) {
    case "broll":
    case "b_roll":
    case "video":
      return "B-roll";
    case "music":
    case "bgm":
    case "background_music":
      return "배경 음악";
    case "sfx":
    case "sound_effect":
      return "효과음";
    case "caption":
    case "subtitle":
      return "자막";
    case "tts":
    case "voice":
    case "narration":
      return "음성";
    case "overlay":
    case "visual_overlay":
      return "오버레이";
    default:
      return "추천 항목";
  }
}

function segmentTargetLabel(review: ReviewSnapshot, segmentId: string) {
  const index = review.segments.findIndex((segment) => segment.segment_id === segmentId);
  if (index < 0) return "해당 장면";
  const text = review.segments[index].text.trim();
  return text ? `${index + 1}번째 장면 · ${text}` : `${index + 1}번째 장면`;
}

function ReviewRecovery({ message, onRefresh }: { message: string; onRefresh: () => Promise<void> }) {
  return <section aria-live="polite"><h1>영상 검토</h1><p>{message}</p><Button variant="outline" onClick={() => void onRefresh()}>다시 확인</Button></section>;
}
