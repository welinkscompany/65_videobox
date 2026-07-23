import { useCallback, useEffect, useRef, useState } from "react";

import { api, type JobRecord } from "../../api";
import { Button } from "../../components/ui/button";

type JobScope = "current" | "global";
type VisibleJob = JobRecord & { project_name?: string };
type JobState = { projectId: string; scope: JobScope; jobs: VisibleJob[] };
type JobContext = { projectId: string; scope: JobScope; generation: number };
type RetryToken = {
  id: number;
  key: string;
  context: JobContext;
};

const retryableTypes = new Set([
  "transcription",
  "broll_recommendation",
  "music_recommendation",
  "subtitle_render",
  "final_render",
  "capcut_draft_export",
]);

const jobTypeCopy: Record<string, string> = {
  media_analysis: "미디어 분석",
  ingest: "소스 준비",
  transcription: "음성 받아쓰기",
  segment_analysis: "장면 나누기",
  broll_recommendation: "장면 추천",
  music_recommendation: "음악 추천",
  timeline_build: "편집 초안 만들기",
  partial_regeneration: "선택 구간 다시 만들기",
  subtitle_render: "자막 만들기",
  preview_render: "이전 미리보기",
  capcut_export: "이전 CapCut 내보내기",
  final_render: "완성본 만들기",
  capcut_draft_export: "CapCut 초안 만들기",
};

const jobStatusCopy: Record<string, string> = {
  pending: "차례를 기다리고 있어요",
  queued: "차례를 기다리고 있어요",
  running: "진행 중이에요",
  succeeded: "완료됐어요",
  failed: "다시 확인이 필요해요",
  blocked: "직접 확인이 필요해요",
  cancelled: "멈췄어요",
};

export function canRetryJob(job: JobRecord) {
  return job.status === "failed"
    && Boolean(job.input_ref)
    && retryableTypes.has(job.job_type);
}

function compareJobAttempts(left: JobRecord, right: JobRecord) {
  return (left.started_at ?? "").localeCompare(right.started_at ?? "")
    || (left.finished_at ?? "").localeCompare(right.finished_at ?? "")
    || left.job_id.localeCompare(right.job_id);
}

function lineageKey(job: JobRecord) {
  return JSON.stringify([job.project_id, job.job_type, job.input_ref]);
}

function newestRetryableJobKeys(jobs: VisibleJob[]) {
  const newestByLineage = new Map<string, VisibleJob>();
  for (const candidate of jobs) {
    const lineage = lineageKey(candidate);
    const current = newestByLineage.get(lineage);
    if (!current || compareJobAttempts(current, candidate) < 0) newestByLineage.set(lineage, candidate);
  }
  return new Set(
    [...newestByLineage.values()]
      .filter(canRetryJob)
      .map((job) => `${job.project_id}:${job.job_id}`),
  );
}

export function JobRecovery({
  projectId,
  onBusyChange,
}: {
  projectId: string;
  onBusyChange?: (busy: boolean) => void;
}) {
  const [scope, setScope] = useState<JobScope>("current");
  const [state, setState] = useState<JobState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const currentContext = useRef<JobContext>({ projectId, scope, generation: 0 });
  const loadEpoch = useRef(0);
  const retrySequence = useRef(0);
  const retryInFlight = useRef<RetryToken | null>(null);
  const pendingRetryCount = useRef(0);
  const busyCallback = useRef(onBusyChange);

  busyCallback.current = onBusyChange;

  if (currentContext.current.projectId !== projectId || currentContext.current.scope !== scope) {
    currentContext.current = {
      projectId,
      scope,
      generation: currentContext.current.generation + 1,
    };
    retryInFlight.current = null;
  }

  const load = useCallback(async () => {
    const loadProjectId = projectId;
    const loadScope = scope;
    const loadGeneration = currentContext.current.generation;
    const epoch = ++loadEpoch.current;
    setLoading(true);
    setError(null);
    try {
      const jobs: VisibleJob[] = loadScope === "global"
        ? await api.listAllJobs()
        : await api.listJobs(loadProjectId);
      const current = currentContext.current;
      if (current.projectId !== loadProjectId || current.scope !== loadScope
        || current.generation !== loadGeneration || loadEpoch.current !== epoch) return false;
      setState({ projectId: loadProjectId, scope: loadScope, jobs });
      return true;
    } catch {
      const current = currentContext.current;
      if (current.projectId !== loadProjectId || current.scope !== loadScope
        || current.generation !== loadGeneration || loadEpoch.current !== epoch) return false;
      setState(null);
      setError("작업 상태를 불러오지 못했어요.");
      return false;
    } finally {
      const current = currentContext.current;
      if (current.projectId === loadProjectId && current.scope === loadScope
        && current.generation === loadGeneration && loadEpoch.current === epoch) setLoading(false);
    }
  }, [projectId, scope]);

  useEffect(() => {
    setState(null);
    setMessage(null);
    setBusyKey(null);
    void load();
    return () => {
      loadEpoch.current += 1;
    };
  }, [load]);

  useEffect(() => () => busyCallback.current?.(false), []);

  async function retry(job: VisibleJob) {
    if (!canRetryJob(job)) return;
    const retryKey = `${job.project_id}:${job.job_id}`;
    if (retryInFlight.current !== null) return;
    const actionContext = { ...currentContext.current };
    const token: RetryToken = {
      id: ++retrySequence.current,
      key: retryKey,
      context: actionContext,
    };
    retryInFlight.current = token;
    pendingRetryCount.current += 1;
    busyCallback.current?.(true);
    setBusyKey(retryKey);
    setMessage(null);
    let mutationSucceeded = false;
    const isCurrentRetry = () => {
      const active = retryInFlight.current;
      const current = currentContext.current;
      return active?.id === token.id
        && current.projectId === token.context.projectId
        && current.scope === token.context.scope
        && current.generation === token.context.generation;
    };
    try {
      await api.retryJob(job.project_id, job.job_id);
      mutationSucceeded = true;
    } catch {
      if (isCurrentRetry()) {
        setMessage("자동으로 다시 시작하지 못했어요. 해당 화면에서 직접 다시 실행해 주세요.");
      }
    } finally {
      if (isCurrentRetry()) {
        const refreshed = await load();
        if (mutationSucceeded && refreshed && isCurrentRetry()) {
          setMessage("작업을 다시 시작했어요. 최신 상태를 확인했습니다.");
        }
      }
      if (retryInFlight.current?.id === token.id) {
        retryInFlight.current = null;
        setBusyKey(null);
      }
      pendingRetryCount.current = Math.max(0, pendingRetryCount.current - 1);
      if (pendingRetryCount.current === 0) busyCallback.current?.(false);
    }
  }

  const currentState = state?.projectId === projectId && state.scope === scope ? state : null;
  const retryableJobKeys = newestRetryableJobKeys(currentState?.jobs ?? []);

  return (
    <section
      aria-label="작업 복구"
      data-project-id={projectId}
      data-testid="job-recovery"
      className="grid min-w-80 gap-3 p-2"
    >
      <div className="flex gap-2">
        <Button type="button" size="sm" aria-pressed={scope === "current"} variant={scope === "current" ? "default" : "outline"} onClick={() => setScope("current")}>
          현재 프로젝트
        </Button>
        <Button type="button" size="sm" aria-pressed={scope === "global"} variant={scope === "global" ? "default" : "outline"} onClick={() => setScope("global")}>
          모든 프로젝트
        </Button>
      </div>
      {loading && !currentState ? <p role="status">작업 상태를 불러오고 있어요.</p> : null}
      {error ? <div role="alert"><p>{error}</p><Button type="button" size="sm" onClick={() => void load()}>다시 불러오기</Button></div> : null}
      {message ? <p role="status">{message}</p> : null}
      {currentState?.jobs.length === 0 ? <p>표시할 작업이 없어요.</p> : null}
      {currentState?.jobs.map((job) => {
        const key = `${job.project_id}:${job.job_id}`;
        return (
          <article key={key} className="grid gap-1 rounded-md border p-2">
            {scope === "global" && job.project_name ? <strong>{job.project_name}</strong> : null}
            <span>{jobTypeCopy[job.job_type] ?? "기타 작업"}</span>
            <span>{jobStatusCopy[job.status] ?? "상태를 확인하고 있어요"}</span>
            {job.status === "blocked"
              ? <span>자동 재시도 대신 원래 화면에서 직접 다시 실행해 주세요.</span>
              : null}
            {retryableJobKeys.has(key) ? (
              <Button type="button" size="sm" variant="outline" disabled={busyKey !== null} onClick={() => void retry(job)}>
                다시 실행
              </Button>
            ) : null}
          </article>
        );
      })}
    </section>
  );
}
