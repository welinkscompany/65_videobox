import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  type EditingSession,
  type JobRecord,
  type ReviewApproval,
  type ReviewSnapshot,
  type TimelineJob,
} from "../../api";
import {
  collectTimelineReviewBlockers,
  isCurrentTimelineReviewState,
  selectCurrentTimelineJob,
  type TimelineReviewBlocker,
} from "./timeline-review-state";

export type TimelineReviewReadyState = Readonly<{
  kind: "ready";
  projectId: string;
  session: EditingSession;
  job: JobRecord;
  timeline: TimelineJob;
  review: ReviewSnapshot;
  approval: ReviewApproval;
  blockers: TimelineReviewBlocker[];
}>;

export type TimelineReviewState =
  | TimelineReviewReadyState
  | Readonly<{ kind: "loading"; projectId: string }>
  | Readonly<{ kind: "no-session"; projectId: string }>
  | Readonly<{ kind: "no-match"; projectId: string }>
  | Readonly<{ kind: "error"; projectId: string }>
  // 낡은 검토본을 지금 편집본으로 다시 세우려면 어느 편집본인지 알아야 한다.
  // 편집본 자체를 못 읽은 경우에는 없으므로 단추도 그때는 뜨지 않는다.
  | Readonly<{ kind: "stale"; projectId: string; sessionId?: string; reason?: string | null }>;

/** 현재 편집본에 대응하는 검토 상태를 읽는다.
 *
 * 검토 화면과 출력 화면이 같은 다섯 호출(`getLatestEditingSession`, `listJobs`,
 * `getTimeline`, `getReviewSnapshot`, `getReviewApproval`)을 따로 하고 있었다.
 * 한 화면에서 둘을 함께 보여주려면 조회가 하나여야 두 영역이 같은 사실을 본다.
 *
 * **경합 방어는 그대로 옮겼다.** epoch과 projectId를 함께 확인해서, 프로젝트를
 * 바꾼 뒤 늦게 도착한 이전 응답을 채택하지 않는다 -- 이건 성능 최적화가 아니라
 * 다른 프로젝트의 상태가 새는 것을 막는 계약이다.
 */
export function useTimelineReviewState(projectId: string) {
  const [state, setState] = useState<TimelineReviewState>({ kind: "loading", projectId });
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
        setState({ kind: "stale", projectId: loadProjectId, sessionId: session.session_id, reason: approval.invalidated_reason });
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
        setState({ kind: "stale", projectId: loadProjectId, reason: "session_mismatch" });
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

  return { state, refresh };
}
