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

/** 검토 판정과 별개로, 읽어 온 값 자체.
 *
 * 출력 쪽은 검토가 `stale`이어도 이 값들이 필요하다 -- "왜 아직 못 내보내는지"를
 * 그 값으로 판단해서 보여주기 때문이다. 그래서 판정(`state`)과 원본(`data`)을
 * 나눠서 내보낸다.
 */
export type TimelineReviewData = Readonly<{
  session: EditingSession | null;
  jobs: readonly JobRecord[];
  job: JobRecord | null;
  timeline: TimelineJob | null;
  review: ReviewSnapshot | null;
  approval: ReviewApproval | null;
}>;

const emptyData: TimelineReviewData = { session: null, jobs: [], job: null, timeline: null, review: null, approval: null };

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
  const [data, setData] = useState<TimelineReviewData>(emptyData);
  const requestEpoch = useRef(0);
  const currentProjectId = useRef(projectId);
  currentProjectId.current = projectId;

  const loadDetails = useCallback(async (
    session: EditingSession,
    jobs: readonly JobRecord[],
    job: JobRecord,
    options?: Readonly<{ loading?: boolean }>,
  ): Promise<TimelineReviewData> => {
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
      const loaded: TimelineReviewData = { session, jobs, job, timeline, review, approval };
      if (!isCurrent()) return loaded;
      setData(loaded);
      if (!isCurrentTimelineReviewState({ projectId: loadProjectId, session, job, timeline, review, approval })) {
        setState({ kind: "stale", projectId: loadProjectId, sessionId: session.session_id, reason: approval.invalidated_reason });
        return loaded;
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
      return loaded;
    } catch {
      if (isCurrent()) {
        setState({ kind: "error", projectId: loadProjectId });
        setData({ ...emptyData, session, jobs, job });
      }
      return { ...emptyData, session, jobs, job };
    }
  }, [projectId]);

  /** 읽어 온 값을 **돌려준다.** 출력 쪽은 무언가를 바꾼 직후 새 목록으로 곧바로
   * 다음 판단을 해야 하는데, prop으로 내려오길 기다리면 그 사이가 비어 어긋난다. */
  const refresh = useCallback(async (): Promise<TimelineReviewData> => {
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
      if (!isCurrent()) return { ...emptyData, session, jobs };
      if (!session) {
        setState({ kind: "no-session", projectId: loadProjectId });
        setData({ ...emptyData, jobs });
        return { ...emptyData, jobs };
      }
      if (session.project_id !== loadProjectId || !session.timeline_id) {
        setState({ kind: "stale", projectId: loadProjectId, reason: "session_mismatch" });
        setData({ ...emptyData, session, jobs });
        return { ...emptyData, session, jobs };
      }
      const job = selectCurrentTimelineJob(session, jobs);
      if (!job) {
        setState({ kind: "no-match", projectId: loadProjectId });
        setData({ ...emptyData, session, jobs });
        return { ...emptyData, session, jobs };
      }
      return await loadDetails(session, jobs, job);
    } catch {
      if (isCurrent()) {
        setState({ kind: "error", projectId: loadProjectId });
        setData(emptyData);
      }
      return emptyData;
    }
  }, [loadDetails, projectId]);

  useEffect(() => {
    void refresh();
    return () => {
      requestEpoch.current += 1;
    };
  }, [refresh]);

  return { state, data, refresh };
}
