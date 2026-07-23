import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  type CapCutDraftExportJob,
  type CapCutHandoffDiagnostics,
  type FinalRenderJob,
  type JobRecord,
  type ReviewSnapshot,
  type SubtitleJob,
  type TimelineJob,
} from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";

type OutputState = {
  timelineJob: JobRecord | null;
  timeline: TimelineJob | null;
  review: ReviewSnapshot | null;
  subtitle: SubtitleJob | null;
  finalRender: FinalRenderJob | null;
  capcutDraft: CapCutDraftExportJob | null;
  diagnostics: CapCutHandoffDiagnostics | null;
};

function mostRecentJob(jobs: JobRecord[], jobType: string, inputRef?: string | null) {
  return jobs.filter((job) => job.job_type === jobType && (inputRef == null || job.input_ref === inputRef)).reduce<JobRecord | null>((latest, job) => {
    if (!latest) return job;
    const timestamp = job.finished_at ?? job.started_at ?? "";
    const latestTimestamp = latest.finished_at ?? latest.started_at ?? "";
    return timestamp > latestTimestamp ? job : latest;
  }, null);
}

export function OutputsPage({ projectId, onOpenEditor }: { projectId: string; onOpenEditor: () => void }) {
  const [state, setState] = useState<OutputState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);
  const [isRenderingSubtitle, setIsRenderingSubtitle] = useState(false);
  const [subtitleError, setSubtitleError] = useState(false);
  const requestEpoch = useRef(0);
  const subtitleSubmissionEpoch = useRef(0);

  const refresh = useCallback(async (options?: { jobs?: JobRecord[]; subtitle?: SubtitleJob | null }) => {
    const epoch = requestEpoch.current + 1;
    requestEpoch.current = epoch;
    setIsLoading(true);
    setError(false);
    try {
      const [session, jobs] = await Promise.all([
        api.getLatestEditingSession(projectId).catch(() => null),
        options?.jobs ? Promise.resolve(options.jobs) : api.listJobs(projectId),
      ]);
      if (epoch !== requestEpoch.current) return;
      const timelineJob = session
        ? mostRecentJob(jobs.filter((job) => job.status === "succeeded" && job.output_ref === session.timeline_id), "timeline_build")
        : null;
      const subtitleRecord = timelineJob ? mostRecentJob(jobs, "subtitle_render", timelineJob.job_id) : null;
      const finalJob = mostRecentJob(jobs, "final_render");
      const capcutJob = mostRecentJob(jobs, "capcut_draft_export");
      const [timeline, review, subtitle, finalRender, capcutDraft, diagnostics] = await Promise.all([
        timelineJob ? api.getTimeline(projectId, timelineJob.job_id) : Promise.resolve(null),
        timelineJob ? api.getReviewSnapshot(projectId, timelineJob.job_id) : Promise.resolve(null),
        options?.subtitle && session && options.subtitle.subtitle.timeline_id === session.timeline_id
          ? Promise.resolve(options.subtitle)
          : subtitleRecord ? api.getSubtitle(projectId, subtitleRecord.job_id) : Promise.resolve(null),
        finalJob ? api.getFinalRender(projectId, finalJob.job_id) : Promise.resolve(null),
        capcutJob ? api.getCapcutDraftExport(projectId, capcutJob.job_id) : Promise.resolve(null),
        api.getCapcutHandoffDiagnostics().catch(() => null),
      ]);
      if (epoch !== requestEpoch.current) return;
      setState({ timelineJob, timeline, review, subtitle, finalRender, capcutDraft, diagnostics });
    } catch {
      if (epoch !== requestEpoch.current) return;
      setState(null);
      setError(true);
    } finally {
      if (epoch === requestEpoch.current) setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    subtitleSubmissionEpoch.current += 1;
    setIsRenderingSubtitle(false);
    setSubtitleError(false);
    void refresh();
    return () => {
      requestEpoch.current += 1;
      subtitleSubmissionEpoch.current += 1;
    };
  }, [refresh]);

  if (isLoading && !state && !error) return <section className="vb-outputs" aria-live="polite"><p>출력 상태를 불러오는 중이에요.</p></section>;
  if (error) return <section className="vb-outputs" aria-live="polite" data-testid="outputs-page"><h1>출력</h1><p>출력 상태를 불러오지 못했어요.</p><p>잠시 후 상태를 다시 확인하거나 편집 화면에서 작업을 이어가세요.</p><Button variant="outline" onClick={() => void refresh()}>상태 다시 확인</Button><Button onClick={onOpenEditor}>편집 열기</Button></section>;

  const timelineJob = state?.timelineJob;
  const canRenderSubtitle = Boolean(
    timelineJob && state?.timeline && state.review &&
    state.review.review_status === "approved" &&
    state.timeline.timeline.review_flags.length === 0 &&
    state.review.review_flags.length === 0 &&
    state.review.pending_recommendations.length === 0,
  );
  const finalRender = state?.finalRender;
  const currentFinal = finalRender?.status === "succeeded" && finalRender.render?.is_current === true;
  const staleFinal = finalRender?.status === "succeeded" && Boolean(finalRender.render) && !currentFinal;
  const capcutHandoff = state?.capcutDraft?.export?.handoff;
  const capcutReady = state?.capcutDraft?.status === "succeeded" && capcutHandoff?.status === "ready";
  const handleRenderSubtitle = async () => {
    if (!timelineJob || !canRenderSubtitle || isRenderingSubtitle) return;
    const submissionEpoch = subtitleSubmissionEpoch.current + 1;
    subtitleSubmissionEpoch.current = submissionEpoch;
    setIsRenderingSubtitle(true);
    setSubtitleError(false);
    try {
      const result = await api.renderSubtitle(projectId, { timeline_job_id: timelineJob.job_id });
      const [jobs, subtitle] = await Promise.all([
        api.listJobs(projectId),
        api.getSubtitle(projectId, result.job_id),
      ]);
      if (submissionEpoch !== subtitleSubmissionEpoch.current) return;
      await refresh({ jobs, subtitle });
    } catch {
      if (submissionEpoch === subtitleSubmissionEpoch.current) setSubtitleError(true);
    } finally {
      if (submissionEpoch === subtitleSubmissionEpoch.current) setIsRenderingSubtitle(false);
    }
  };

  return <section className="vb-outputs" aria-live="polite" data-testid="outputs-page">
    <div><p className="vb-eyebrow">출력</p><h1>완성본과 CapCut 초안</h1><p>현재 승인된 편집본의 자막만 여기에서 만들 수 있어요. 완성본과 CapCut 초안은 편집 화면에서 시작해 주세요.</p></div>
    <div className="vb-home-grid">
      <Card>
        <CardHeader><CardTitle>자막</CardTitle><CardDescription>{state?.subtitle?.status === "succeeded" ? "자막이 준비되었어요." : state?.subtitle?.status === "failed" ? "자막을 만들지 못했어요." : timelineJob ? "현재 편집본의 자막을 만들 수 있어요." : "아직 자막이 없어요."}</CardDescription></CardHeader>
        <CardContent>
          {subtitleError ? <p>자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.</p> : null}
          {!timelineJob ? <p>먼저 편집 화면에서 현재 초안을 준비해 주세요.</p> : null}
          {timelineJob && !canRenderSubtitle ? <p>검토 승인과 확인할 항목을 모두 마친 뒤 자막을 만들 수 있어요.</p> : null}
          <Button disabled={!canRenderSubtitle || isRenderingSubtitle} onClick={() => void handleRenderSubtitle()}>{isRenderingSubtitle ? "자막 만드는 중" : "자막 만들기"}</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>완성본</CardTitle><CardDescription>{currentFinal ? "완성본을 확인할 수 있어요." : staleFinal ? "완성본이 최신 편집본과 달라요." : finalRender?.status === "failed" ? "완성본을 만들지 못했어요." : "아직 완성본이 없어요."}</CardDescription></CardHeader>
        <CardContent>
          {currentFinal ? <video aria-label="완성본 재생" controls preload="metadata" src={`/api/projects/${encodeURIComponent(projectId)}/final-renders/${encodeURIComponent(finalRender.job_id)}/content`}>이 브라우저에서는 완성본을 재생할 수 없어요.</video> : null}
          {staleFinal ? <p>편집에서 새 완성본 만들기를 실행해 주세요.</p> : null}
          {finalRender?.status === "failed" ? <p>편집 화면에서 원인을 확인한 뒤 다시 시도해 주세요.</p> : null}
          {!finalRender ? <p>편집을 마친 뒤 완성본을 만들면 여기에서 확인할 수 있어요.</p> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>CapCut 초안</CardTitle><CardDescription>{capcutReady ? "CapCut에서 초안을 열 수 있어요." : state?.capcutDraft?.status === "failed" || capcutHandoff?.status === "failed" ? "CapCut 초안 준비를 완료하지 못했어요." : state?.capcutDraft?.export ? "CapCut 초안의 연결 준비가 필요해요." : "아직 CapCut 초안이 없어요."}</CardDescription></CardHeader>
        <CardContent>
          {state?.capcutDraft?.export?.notes.length ? <p>일부 효과는 CapCut에서 확인해 주세요.</p> : null}
          {state?.capcutDraft?.status === "failed" || capcutHandoff?.status === "failed" ? <p>편집 화면에서 상태를 확인한 뒤 다시 진행해 주세요.</p> : null}
          {state?.diagnostics && !state.diagnostics.is_supported ? <p>이 기기의 CapCut 연결 상태를 확인해 주세요.</p> : null}
          {!state?.diagnostics ? <p>CapCut 연결 상태는 지금 확인할 수 없어요. 잠시 후 다시 확인해 주세요.</p> : null}
        </CardContent>
      </Card>
    </div>
    <div className="vb-home-grid"><Button variant="outline" onClick={() => void refresh()}>상태 다시 확인</Button><Button onClick={onOpenEditor}>편집 열기</Button></div>
  </section>;
}
