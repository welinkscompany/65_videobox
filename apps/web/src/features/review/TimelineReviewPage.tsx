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
  // 낡은 검토본을 지금 편집본으로 다시 세우려면 어느 편집본인지 알아야 한다.
  // 편집본 자체를 못 읽은 경우에는 없으므로 단추도 그때는 뜨지 않는다.
  | Readonly<{ kind: "stale"; projectId: string; sessionId?: string }>;

type OpenSegmentInput = Readonly<{ projectId: string; sessionId: string; segmentId: string }>;

export function TimelineReviewPage({
  projectId,
  onOpenSegment,
}: {
  projectId: string;
  onOpenSegment?: (input: OpenSegmentInput) => void;
}) {
  const [state, setState] = useState<ReviewState>({ kind: "loading", projectId });
  const [decisionMessage, setDecisionMessage] = useState<string | null>(null);
  const [deciding, setDeciding] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildMessage, setRebuildMessage] = useState<string | null>(null);
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
        setState({ kind: "stale", projectId: loadProjectId, sessionId: session.session_id });
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

  /** 낡은 검토본을 지금 편집본으로 다시 세운다.
   *
   * 편집은 승인 기록을 내린다. 그 판단은 옳지만 다시 세울 자리가 없어서, 편집을
   * 한 번만 해도 이 화면에서 나갈 길이 없었고 내보내기까지 막혔다. `다시 확인`은
   * 같은 것을 다시 읽을 뿐이라 답이 바뀌지 않는다.
   *
   * 승인은 하지 않는다 -- 다시 세운 검토본을 보고 승인하는 것은 owner의 몫이다.
   */
  const rebuild = useCallback(async (sessionId: string) => {
    const rebuildProjectId = projectId;
    setRebuilding(true);
    setRebuildMessage(null);
    try {
      await api.refreshReviewForCurrentEdit(rebuildProjectId, sessionId);
      if (currentProjectId.current !== rebuildProjectId) return;
      await refresh();
    } catch {
      if (currentProjectId.current !== rebuildProjectId) return;
      setRebuildMessage("검토본을 다시 만들지 못했어요. 잠시 뒤 다시 시도해 주세요.");
    } finally {
      if (currentProjectId.current === rebuildProjectId) setRebuilding(false);
    }
  }, [projectId, refresh]);

  // Task 31: approving is what unlocks subtitles, the final render and the
  // CapCut hand-off. The server refuses an approval that still has blockers
  // and invalidates it again once the session moves on, so the screen only has
  // to keep the owner from asking for something that cannot succeed.
  const decide = useCallback(async (
    kind: "approve" | "reopen",
    jobId: string,
    onDone: () => Promise<void>,
  ) => {
    const decideProjectId = projectId;
    setDeciding(true);
    setDecisionMessage(null);
    try {
      if (kind === "approve") await api.approveTimeline(decideProjectId, jobId);
      else await api.reopenTimeline(decideProjectId, jobId);
      if (currentProjectId.current !== decideProjectId) return;
      await onDone();
    } catch {
      if (currentProjectId.current !== decideProjectId) return;
      setDecisionMessage(kind === "approve"
        ? "검토를 승인하지 못했어요. 확인할 항목을 살펴본 뒤 다시 시도해 주세요."
        : "검토를 다시 열지 못했어요. 다시 시도해 주세요.");
    } finally {
      if (currentProjectId.current === decideProjectId) setDeciding(false);
    }
  }, [projectId]);

  if (state.projectId !== projectId || state.kind === "loading") {
    return <section aria-live="polite"><p>검토 내용을 불러오는 중이에요.</p></section>;
  }
  if (state.kind === "no-session") return <ReviewRecovery message="먼저 편집할 초안을 만들어 주세요." onRefresh={refresh} />;
  if (state.kind === "no-match") return <ReviewRecovery message="현재 편집본과 맞는 검토본이 없어요." onRefresh={refresh} />;
  if (state.kind === "error") return <ReviewRecovery message="검토 내용을 불러오지 못했어요." onRefresh={refresh} />;
  if (state.kind === "stale") {
    return <ReviewRecovery
      message="이 검토본은 현재 편집본과 맞지 않아요. 다시 확인해 주세요."
      onRefresh={refresh}
      onRebuild={state.sessionId ? () => rebuild(state.sessionId as string) : undefined}
      rebuilding={rebuilding}
      rebuildMessage={rebuildMessage}
    />;
  }

  const approved = state.approval.review_status === "approved";
  return (
    <section data-testid="timeline-review-page" data-project-id={state.projectId} aria-live="polite">
      <p>검토</p>
      <h1>영상 검토</h1>
      <p>장면과 추천 상태를 확인해 주세요.</p>
      <p>{approved ? "현재 편집본의 검토가 승인되었어요." : "현재 편집본을 검토하고 있어요."}</p>
      {approved ? (
        <>
          <p>이제 내보내기 화면에서 자막과 완성본을 만들 수 있어요.</p>
          <Button variant="outline" disabled={deciding} onClick={() => void decide("reopen", state.job.job_id, refresh)}>
            검토 다시 열기
          </Button>
        </>
      ) : (
        <>
          <p>{state.blockers.length === 0
            ? "승인하면 내보내기 화면에서 자막과 완성본을 만들 수 있어요."
            : "확인할 항목을 모두 마치면 승인할 수 있어요."}</p>
          <Button disabled={deciding || state.blockers.length > 0} onClick={() => void decide("approve", state.job.job_id, refresh)}>
            검토 승인
          </Button>
        </>
      )}
      {decisionMessage ? <p role="alert">{decisionMessage}</p> : null}

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

function ReviewRecovery({ message, onRefresh, onRebuild, rebuilding = false, rebuildMessage = null }: {
  message: string;
  onRefresh: () => Promise<void>;
  /** 낡은 검토본을 지금 편집본으로 다시 세운다. 다시 세울 편집본을 알 때만 있다. */
  onRebuild?: () => Promise<void>;
  rebuilding?: boolean;
  rebuildMessage?: string | null;
}) {
  return <section aria-live="polite">
    <h1>영상 검토</h1>
    <p>{message}</p>
    {onRebuild ? <Button disabled={rebuilding} onClick={() => void onRebuild()}>{rebuilding ? "검토본을 다시 만드는 중" : "검토 다시 받기"}</Button> : null}
    <Button variant="outline" onClick={() => void onRefresh()}>다시 확인</Button>
    {rebuildMessage ? <p role="alert">{rebuildMessage}</p> : null}
  </section>;
}
