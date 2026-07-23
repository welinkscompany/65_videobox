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
  projectId: string;
  timelineJob: JobRecord | null;
  timeline: TimelineJob | null;
  review: ReviewSnapshot | null;
  subtitle: SubtitleJob | null;
  finalJobs: JobRecord[];
  finalJob: JobRecord | null;
  finalRender: FinalRenderJob | null;
  capcutJobs: JobRecord[];
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
  const [errorProjectId, setErrorProjectId] = useState<string | null>(null);
  const [isRenderingSubtitle, setIsRenderingSubtitle] = useState(false);
  const [subtitleErrorProjectId, setSubtitleErrorProjectId] = useState<string | null>(null);
  const [isRenderingFinal, setIsRenderingFinal] = useState(false);
  const [finalErrorProjectId, setFinalErrorProjectId] = useState<string | null>(null);
  const [isExportingCapcutDraft, setIsExportingCapcutDraft] = useState(false);
  const [capcutErrorProjectId, setCapcutErrorProjectId] = useState<string | null>(null);
  const [isRegisteringCapcutHandoff, setIsRegisteringCapcutHandoff] = useState(false);
  const [capcutHandoffErrorProjectId, setCapcutHandoffErrorProjectId] = useState<string | null>(null);
  const requestEpoch = useRef(0);
  const subtitleSubmissionEpoch = useRef(0);
  const finalSubmissionEpoch = useRef(0);
  const capcutSubmissionEpoch = useRef(0);
  const capcutHandoffSubmissionEpoch = useRef(0);
  const currentProjectId = useRef(projectId);
  const subtitleRequestProjectId = useRef<string | null>(null);
  const finalRequestProjectId = useRef<string | null>(null);
  const capcutRequestProjectId = useRef<string | null>(null);
  const capcutHandoffRequestProjectId = useRef<string | null>(null);
  const finalInFlightTimelineKey = useRef<string | null>(null);
  const capcutInFlightTimelineKey = useRef<string | null>(null);
  const capcutHandoffInFlightJobKey = useRef<string | null>(null);
  currentProjectId.current = projectId;

  const refresh = useCallback(async (options?: { jobs?: JobRecord[]; subtitle?: SubtitleJob | null; finalRender?: FinalRenderJob | null; capcutDraft?: CapCutDraftExportJob | null }) => {
    const refreshProjectId = projectId;
    const epoch = requestEpoch.current + 1;
    requestEpoch.current = epoch;
    const isCurrentRequest = () => epoch === requestEpoch.current && currentProjectId.current === refreshProjectId;
    if (!isCurrentRequest()) return;
    setIsLoading(true);
    setErrorProjectId(null);
    try {
      const [session, jobs] = await Promise.all([
        api.getLatestEditingSession(refreshProjectId).catch(() => null),
        options?.jobs ? Promise.resolve(options.jobs) : api.listJobs(refreshProjectId),
      ]);
      if (!isCurrentRequest()) return;
      const timelineJob = session
        ? mostRecentJob(jobs.filter((job) => job.status === "succeeded" && job.output_ref === session.timeline_id), "timeline_build")
        : null;
      const subtitleRecord = timelineJob ? mostRecentJob(jobs, "subtitle_render", timelineJob.job_id) : null;
      const finalJobs = timelineJob ? jobs.filter((job) => job.job_type === "final_render" && job.input_ref === timelineJob.job_id) : [];
      const finalJob = timelineJob ? mostRecentJob(finalJobs, "final_render") : mostRecentJob(jobs, "final_render");
      const capcutJobs = timelineJob ? jobs.filter((job) => job.job_type === "capcut_draft_export" && job.input_ref === timelineJob.job_id) : [];
      const capcutJob = timelineJob ? mostRecentJob(capcutJobs, "capcut_draft_export") : null;
      const [timeline, review, subtitle, finalRender, capcutDraft, diagnostics] = await Promise.all([
        timelineJob ? api.getTimeline(refreshProjectId, timelineJob.job_id) : Promise.resolve(null),
        timelineJob ? api.getReviewSnapshot(refreshProjectId, timelineJob.job_id) : Promise.resolve(null),
        options?.subtitle && session && options.subtitle.subtitle.timeline_id === session.timeline_id
          ? Promise.resolve(options.subtitle)
          : subtitleRecord ? api.getSubtitle(refreshProjectId, subtitleRecord.job_id) : Promise.resolve(null),
        options?.finalRender && finalJob && options.finalRender.job_id === finalJob.job_id
          ? Promise.resolve(options.finalRender)
          : finalJob ? api.getFinalRender(refreshProjectId, finalJob.job_id) : Promise.resolve(null),
        options?.capcutDraft && capcutJob && options.capcutDraft.job_id === capcutJob.job_id
          ? Promise.resolve(options.capcutDraft)
          : capcutJob ? api.getCapcutDraftExport(refreshProjectId, capcutJob.job_id) : Promise.resolve(null),
        api.getCapcutHandoffDiagnostics().catch(() => null),
      ]);
      if (!isCurrentRequest()) return;
      setState({ projectId: refreshProjectId, timelineJob, timeline, review, subtitle, finalJobs, finalJob, finalRender, capcutJobs, capcutDraft, diagnostics });
    } catch {
      if (!isCurrentRequest()) return;
      setState(null);
      setErrorProjectId(refreshProjectId);
    } finally {
      if (isCurrentRequest()) setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    subtitleSubmissionEpoch.current += 1;
    finalSubmissionEpoch.current += 1;
    capcutSubmissionEpoch.current += 1;
    capcutHandoffSubmissionEpoch.current += 1;
    subtitleRequestProjectId.current = null;
    finalRequestProjectId.current = null;
    finalInFlightTimelineKey.current = null;
    capcutRequestProjectId.current = null;
    capcutInFlightTimelineKey.current = null;
    capcutHandoffRequestProjectId.current = null;
    capcutHandoffInFlightJobKey.current = null;
    setIsRenderingSubtitle(false);
    setSubtitleErrorProjectId(null);
    setIsRenderingFinal(false);
    setFinalErrorProjectId(null);
    setIsExportingCapcutDraft(false);
    setCapcutErrorProjectId(null);
    setIsRegisteringCapcutHandoff(false);
    setCapcutHandoffErrorProjectId(null);
    void refresh();
    return () => {
      requestEpoch.current += 1;
      subtitleSubmissionEpoch.current += 1;
      finalSubmissionEpoch.current += 1;
      capcutSubmissionEpoch.current += 1;
      capcutHandoffSubmissionEpoch.current += 1;
    };
  }, [refresh]);

  const currentState = state?.projectId === projectId ? state : null;
  const hasError = errorProjectId === projectId;
  const isRenderingCurrentSubtitle = isRenderingSubtitle && subtitleRequestProjectId.current === projectId;
  const subtitleError = subtitleErrorProjectId === projectId;
  const isRenderingCurrentFinal = isRenderingFinal && finalRequestProjectId.current === projectId;
  const finalError = finalErrorProjectId === projectId;
  const isExportingCurrentCapcutDraft = isExportingCapcutDraft && capcutRequestProjectId.current === projectId;
  const capcutError = capcutErrorProjectId === projectId;
  const isRegisteringCurrentCapcutHandoff = isRegisteringCapcutHandoff && capcutHandoffRequestProjectId.current === projectId;
  const capcutHandoffError = capcutHandoffErrorProjectId === projectId;
  if (isLoading && !state && !hasError) return <section className="vb-outputs" aria-live="polite"><p>출력 상태를 불러오는 중이에요.</p></section>;
  if (hasError) return <section className="vb-outputs" aria-live="polite" data-testid="outputs-page"><h1>출력</h1><p>출력 상태를 불러오지 못했어요.</p><p>잠시 후 상태를 다시 확인하거나 편집 화면에서 작업을 이어가세요.</p><Button variant="outline" onClick={() => void refresh()}>상태 다시 확인</Button><Button onClick={onOpenEditor}>편집 열기</Button></section>;

  const timelineJob = currentState?.timelineJob;
  const canRenderSubtitle = Boolean(
    timelineJob && currentState?.timeline && currentState.review &&
    currentState.review.review_status === "approved" &&
    currentState.timeline.timeline.review_flags.length === 0 &&
    currentState.timeline.timeline.pending_recommendations.length === 0 &&
    currentState.review.review_flags.length === 0 &&
    currentState.review.pending_recommendations.length === 0,
  );
  const finalJob = currentState?.finalJob;
  const hasPendingFinal = currentState?.finalJobs.some((job) => job.status === "pending" || job.status === "running") === true;
  const canRenderFinal = canRenderSubtitle && !hasPendingFinal;
  const finalRender = currentState?.finalRender;
  const currentFinal = finalRender?.status === "succeeded" && finalRender.render?.is_current === true;
  const staleFinal = finalRender?.status === "succeeded" && Boolean(finalRender.render) && !currentFinal;
  const capcutJobs = currentState?.capcutJobs ?? [];
  const hasPendingCapcut = capcutJobs.some((job) => job.status === "pending" || job.status === "running");
  const canExportCapcutDraft = canRenderFinal && !hasPendingCapcut;
  const capcutDraft = currentState?.capcutDraft;
  const currentCapcutDraft = capcutDraft?.status === "succeeded" && capcutDraft.export?.status === "succeeded" && capcutDraft.export.is_current === true;
  const staleCapcutDraft = capcutDraft?.status === "succeeded" && Boolean(capcutDraft.export) && !currentCapcutDraft;
  const capcutHandoff = currentCapcutDraft ? capcutDraft?.export?.handoff ?? null : null;
  const canRegisterCapcutHandoff = Boolean(currentCapcutDraft && capcutDraft?.export && capcutHandoff?.status !== "ready");
  const handleRenderSubtitle = async () => {
    const submissionProjectId = projectId;
    if (currentProjectId.current !== submissionProjectId || !timelineJob || !canRenderSubtitle || isRenderingCurrentSubtitle) return;
    const submissionEpoch = subtitleSubmissionEpoch.current + 1;
    subtitleSubmissionEpoch.current = submissionEpoch;
    subtitleRequestProjectId.current = submissionProjectId;
    setIsRenderingSubtitle(true);
    setSubtitleErrorProjectId(null);
    try {
      const result = await api.renderSubtitle(submissionProjectId, { timeline_job_id: timelineJob.job_id });
      const [jobs, subtitle] = await Promise.all([
        api.listJobs(submissionProjectId),
        api.getSubtitle(submissionProjectId, result.job_id),
      ]);
      if (submissionEpoch !== subtitleSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
      await refresh({ jobs, subtitle });
    } catch {
      if (submissionEpoch === subtitleSubmissionEpoch.current && currentProjectId.current === submissionProjectId) setSubtitleErrorProjectId(submissionProjectId);
    } finally {
      if (submissionEpoch === subtitleSubmissionEpoch.current && currentProjectId.current === submissionProjectId) setIsRenderingSubtitle(false);
    }
  };
  const handleRenderFinal = async () => {
    const submissionProjectId = projectId;
    const timelineKey = timelineJob ? `${submissionProjectId}:${timelineJob.job_id}` : null;
    if (currentProjectId.current !== submissionProjectId || !timelineJob || !timelineKey || !canRenderFinal || isRenderingCurrentFinal || finalInFlightTimelineKey.current === timelineKey) return;
    const submissionEpoch = finalSubmissionEpoch.current + 1;
    const requestEpochAtSubmission = requestEpoch.current;
    finalSubmissionEpoch.current = submissionEpoch;
    finalRequestProjectId.current = submissionProjectId;
    finalInFlightTimelineKey.current = timelineKey;
    setIsRenderingFinal(true);
    setFinalErrorProjectId(null);
    try {
      const result = await api.startFinalRender(submissionProjectId, { timeline_job_id: timelineJob.job_id });
      const [jobs, nextFinalRender] = await Promise.all([
        api.listJobs(submissionProjectId),
        api.getFinalRender(submissionProjectId, result.job_id),
      ]);
      if (submissionEpoch !== finalSubmissionEpoch.current || requestEpochAtSubmission !== requestEpoch.current || currentProjectId.current !== submissionProjectId) return;
      await refresh({ jobs, finalRender: nextFinalRender });
    } catch {
      if (submissionEpoch === finalSubmissionEpoch.current && currentProjectId.current === submissionProjectId) setFinalErrorProjectId(submissionProjectId);
    } finally {
      if (finalInFlightTimelineKey.current === timelineKey) finalInFlightTimelineKey.current = null;
      if (submissionEpoch === finalSubmissionEpoch.current && currentProjectId.current === submissionProjectId) setIsRenderingFinal(false);
    }
  };
  const handleExportCapcutDraft = async () => {
    const submissionProjectId = projectId;
    const timelineKey = timelineJob ? `${submissionProjectId}:${timelineJob.job_id}` : null;
    if (currentProjectId.current !== submissionProjectId || !timelineJob || !timelineKey || !canExportCapcutDraft || isExportingCurrentCapcutDraft || capcutInFlightTimelineKey.current === timelineKey) return;
    const submissionEpoch = capcutSubmissionEpoch.current + 1;
    const requestEpochAtSubmission = requestEpoch.current;
    capcutSubmissionEpoch.current = submissionEpoch;
    capcutRequestProjectId.current = submissionProjectId;
    capcutInFlightTimelineKey.current = timelineKey;
    setIsExportingCapcutDraft(true);
    setCapcutErrorProjectId(null);
    try {
      const result = await api.startCapcutDraftExport(submissionProjectId, { timeline_job_id: timelineJob.job_id });
      const [jobs, nextCapcutDraft] = await Promise.all([
        api.listJobs(submissionProjectId),
        api.getCapcutDraftExport(submissionProjectId, result.job_id),
      ]);
      if (submissionEpoch !== capcutSubmissionEpoch.current || requestEpochAtSubmission !== requestEpoch.current || currentProjectId.current !== submissionProjectId) return;
      await refresh({ jobs, capcutDraft: nextCapcutDraft });
    } catch {
      if (submissionEpoch === capcutSubmissionEpoch.current && currentProjectId.current === submissionProjectId) setCapcutErrorProjectId(submissionProjectId);
    } finally {
      if (capcutInFlightTimelineKey.current === timelineKey) capcutInFlightTimelineKey.current = null;
      if (submissionEpoch === capcutSubmissionEpoch.current && currentProjectId.current === submissionProjectId) setIsExportingCapcutDraft(false);
    }
  };
  const handleRegisterCapcutHandoff = async () => {
    const submissionProjectId = projectId;
    const capcutDraftJobId = capcutDraft?.job_id;
    const handoffJobKey = capcutDraftJobId ? `${submissionProjectId}:${capcutDraftJobId}` : null;
    if (currentProjectId.current !== submissionProjectId || !capcutDraftJobId || !handoffJobKey || !currentCapcutDraft || !canRegisterCapcutHandoff || isRegisteringCurrentCapcutHandoff || capcutHandoffInFlightJobKey.current === handoffJobKey) return;
    const submissionEpoch = capcutHandoffSubmissionEpoch.current + 1;
    const requestEpochAtSubmission = requestEpoch.current;
    capcutHandoffSubmissionEpoch.current = submissionEpoch;
    capcutHandoffRequestProjectId.current = submissionProjectId;
    capcutHandoffInFlightJobKey.current = handoffJobKey;
    setIsRegisteringCapcutHandoff(true);
    setCapcutHandoffErrorProjectId(null);
    try {
      await api.registerCapcutDraftHandoff(submissionProjectId, capcutDraftJobId);
      const nextCapcutDraft = await api.getCapcutDraftExport(submissionProjectId, capcutDraftJobId);
      if (submissionEpoch !== capcutHandoffSubmissionEpoch.current || requestEpochAtSubmission !== requestEpoch.current || currentProjectId.current !== submissionProjectId) return;
      await refresh({ capcutDraft: nextCapcutDraft });
    } catch {
      if (submissionEpoch === capcutHandoffSubmissionEpoch.current && requestEpochAtSubmission === requestEpoch.current && currentProjectId.current === submissionProjectId) setCapcutHandoffErrorProjectId(submissionProjectId);
    } finally {
      if (capcutHandoffInFlightJobKey.current === handoffJobKey) capcutHandoffInFlightJobKey.current = null;
      if (submissionEpoch === capcutHandoffSubmissionEpoch.current && currentProjectId.current === submissionProjectId) setIsRegisteringCapcutHandoff(false);
    }
  };

  return <section className="vb-outputs" aria-live="polite" data-testid="outputs-page">
    <div><p className="vb-eyebrow">출력</p><h1>완성본과 CapCut 초안</h1><p>현재 승인된 편집본의 자막, 완성본, CapCut 초안을 여기에서 만들 수 있어요.</p></div>
    <div className="vb-home-grid">
      <Card>
        <CardHeader><CardTitle>자막</CardTitle><CardDescription>{currentState?.subtitle?.status === "succeeded" ? "자막이 준비되었어요." : currentState?.subtitle?.status === "failed" ? "자막을 만들지 못했어요." : timelineJob ? "현재 편집본의 자막을 만들 수 있어요." : "아직 자막이 없어요."}</CardDescription></CardHeader>
        <CardContent>
          {subtitleError ? <p>자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.</p> : null}
          {!timelineJob ? <p>먼저 편집 화면에서 현재 초안을 준비해 주세요.</p> : null}
          {timelineJob && !canRenderSubtitle ? <p>검토 승인과 확인할 항목을 모두 마친 뒤 자막을 만들 수 있어요.</p> : null}
          <Button disabled={!canRenderSubtitle || isRenderingCurrentSubtitle} onClick={() => void handleRenderSubtitle()}>{isRenderingCurrentSubtitle ? "자막 만드는 중" : "자막 만들기"}</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>완성본</CardTitle><CardDescription>{currentFinal ? "완성본을 확인할 수 있어요." : staleFinal ? "완성본이 최신 편집본과 달라요." : finalRender?.status === "failed" ? "완성본을 만들지 못했어요." : hasPendingFinal ? "완성본을 만드는 중이에요." : timelineJob ? "현재 편집본의 완성본을 만들 수 있어요." : "아직 완성본이 없어요."}</CardDescription></CardHeader>
        <CardContent>
          {finalError ? <p>완성본을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.</p> : null}
          {!timelineJob ? <p>먼저 편집 화면에서 현재 초안을 준비해 주세요.</p> : null}
          {timelineJob && !canRenderSubtitle ? <p>검토 승인과 확인할 항목을 모두 마친 뒤 완성본을 만들 수 있어요.</p> : null}
          {currentFinal ? <video aria-label="완성본 재생" controls preload="metadata" src={`/api/projects/${encodeURIComponent(projectId)}/final-renders/${encodeURIComponent(finalRender.job_id)}/content`}>이 브라우저에서는 완성본을 재생할 수 없어요.</video> : null}
          {staleFinal ? <p>편집에서 새 완성본 만들기를 실행해 주세요.</p> : null}
          {finalRender?.status === "failed" ? <p>완성본 다시 만들기를 눌러 새 작업을 시작할 수 있어요.</p> : null}
          {hasPendingFinal ? <p>완료될 때까지 기다린 뒤 상태를 다시 확인해 주세요.</p> : null}
          <Button disabled={!canRenderFinal || isRenderingCurrentFinal} onClick={() => void handleRenderFinal()}>{isRenderingCurrentFinal ? "완성본 만드는 중" : finalRender?.status === "failed" || finalError ? "완성본 다시 만들기" : "완성본 만들기"}</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>CapCut 초안</CardTitle><CardDescription>{currentCapcutDraft ? "CapCut 초안이 준비되었어요." : staleCapcutDraft ? "CapCut 초안이 최신 편집본과 달라요." : capcutDraft?.status === "failed" ? "CapCut 초안을 만들지 못했어요." : hasPendingCapcut ? "CapCut 초안을 만드는 중이에요." : timelineJob ? "현재 편집본의 CapCut 초안을 만들 수 있어요." : "아직 CapCut 초안이 없어요."}</CardDescription></CardHeader>
        <CardContent>
          {capcutError ? <p>CapCut 초안을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.</p> : null}
          {!timelineJob ? <p>먼저 편집 화면에서 현재 초안을 준비해 주세요.</p> : null}
          {timelineJob && !canRenderSubtitle ? <p>검토 승인과 확인할 항목을 모두 마친 뒤 CapCut 초안을 만들 수 있어요.</p> : null}
          {hasPendingCapcut ? <p>완료될 때까지 기다린 뒤 상태를 다시 확인해 주세요.</p> : null}
          {capcutDraft?.status === "failed" ? <p>CapCut 초안 다시 만들기를 눌러 새 작업을 시작할 수 있어요.</p> : null}
          {staleCapcutDraft ? <p>현재 편집본으로 CapCut 초안을 새로 만들어 주세요.</p> : null}
          {currentCapcutDraft && capcutDraft.export ? <p>로컬 저장 위치: {capcutDraft.export.file_uri}</p> : null}
          {currentCapcutDraft && capcutDraft.export?.notes.length ? <p>일부 효과는 CapCut에서 확인해 주세요.</p> : null}
          {capcutHandoff?.status === "ready" ? <p>{capcutHandoff.reused ? "기존 CapCut 등록 정보를 다시 사용해요." : "CapCut 등록 상태가 준비되었어요."}</p> : null}
          {capcutHandoff?.status === "failed" ? <p>CapCut 등록을 완료하지 못했어요. 상태를 확인한 뒤 다시 시도해 주세요.</p> : null}
          {capcutHandoffError ? <p>CapCut 등록 상태를 확인하지 못했어요. 상태를 다시 확인한 뒤 시도해 주세요.</p> : null}
          {currentCapcutDraft ? <p>실제 CapCut Desktop에서 열기와 가져오기는 별도로 확인해야 해요.</p> : null}
          {currentState?.diagnostics && !currentState.diagnostics.is_supported ? <p>이 기기의 CapCut 연결 상태를 확인해 주세요.</p> : null}
          {currentState?.diagnostics ? <p>CapCut 연결 상태는 준비 여부만 표시하며, 실제 Desktop 완료를 뜻하지 않아요.</p> : null}
          {!currentState?.diagnostics ? <p>CapCut 연결 상태는 지금 확인할 수 없어요. 잠시 후 다시 확인해 주세요.</p> : null}
          <Button disabled={!canExportCapcutDraft || isExportingCurrentCapcutDraft} onClick={() => void handleExportCapcutDraft()}>{isExportingCurrentCapcutDraft ? "CapCut 초안 만드는 중" : capcutDraft?.status === "failed" || capcutError ? "CapCut 초안 다시 만들기" : "CapCut 초안 만들기"}</Button>
          {canRegisterCapcutHandoff ? <Button variant="outline" disabled={isRegisteringCurrentCapcutHandoff} onClick={() => void handleRegisterCapcutHandoff()}>{isRegisteringCurrentCapcutHandoff ? "CapCut 등록 중" : capcutHandoff?.status === "failed" || capcutHandoffError ? "CapCut 등록 다시 시도" : "CapCut에 등록"}</Button> : null}
        </CardContent>
      </Card>
    </div>
    <div className="vb-home-grid"><Button variant="outline" onClick={() => void refresh()}>상태 다시 확인</Button><Button onClick={onOpenEditor}>편집 열기</Button></div>
  </section>;
}
