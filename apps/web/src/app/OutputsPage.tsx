import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  type CapCutDraftExportJob,
  type CapCutHandoffDiagnostics,
  type EditingSession,
  type EditorPlaybackManifest,
  type FinalRenderJob,
  type JobRecord,
  type ReviewApproval,
  type ReviewSnapshot,
  type SubtitleJob,
  type TimelineJob,
} from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";

type ExactPreviewState = "current" | "pending" | "running" | "failed" | "stale" | "unavailable" | "unknown";

type OutputState = {
  projectId: string;
  session: EditingSession | null;
  timelineJob: JobRecord | null;
  timeline: TimelineJob | null;
  review: ReviewSnapshot | null;
  approval: ReviewApproval | null;
  subtitle: SubtitleJob | null;
  finalJobs: JobRecord[];
  finalJob: JobRecord | null;
  finalRender: FinalRenderJob | null;
  capcutJobs: JobRecord[];
  capcutDraft: CapCutDraftExportJob | null;
  diagnostics: CapCutHandoffDiagnostics | null;
  exactPreviewState: ExactPreviewState;
};

function mostRecentJob(jobs: JobRecord[], jobType: string, inputRef?: string | null) {
  return jobs.filter((job) => job.job_type === jobType && (inputRef == null || job.input_ref === inputRef)).reduce<JobRecord | null>((latest, job) => {
    if (!latest) return job;
    const timestamp = job.finished_at ?? job.started_at ?? "";
    const latestTimestamp = latest.finished_at ?? latest.started_at ?? "";
    return timestamp > latestTimestamp ? job : latest;
  }, null);
}

function deriveExactPreviewState(
  routeProjectId: string,
  session: EditingSession | null,
  manifest: EditorPlaybackManifest | null,
  readFailed: boolean,
): ExactPreviewState {
  if (!session) return "unavailable";
  if (readFailed || !manifest) return "unknown";
  const manifestIsCurrent = (
    session.project_id === routeProjectId &&
    manifest.project_id === session.project_id &&
    manifest.session_id === session.session_id &&
    manifest.timeline_id === session.timeline_id &&
    manifest.session_revision === session.session_revision &&
    manifest.source_status.status === "current" &&
    manifest.source_status.source_session_id === session.session_id &&
    manifest.source_status.source_session_revision === session.session_revision
  );
  if (!manifestIsCurrent || manifest.exact_preview.status === "stale") return "stale";
  if (manifest.exact_preview.status === "unavailable") return "unavailable";
  const exactPreviewMatchesSession = (
    manifest.exact_preview.source_session_id === session.session_id &&
    manifest.exact_preview.source_session_revision === session.session_revision
  );
  if (!exactPreviewMatchesSession) return "stale";
  if (manifest.exact_preview.status === "pending" || manifest.exact_preview.status === "running" || manifest.exact_preview.status === "failed") {
    return manifest.exact_preview.status;
  }
  if (manifest.exact_preview.status !== "succeeded") return "stale";
  return (
    Boolean(manifest.exact_preview.url) &&
    manifest.exact_preview.artifact_revision === session.session_revision
  ) ? "current" : "stale";
}

function exactPreviewDescription(state: ExactPreviewState | undefined) {
  switch (state) {
    case "current": return "현재 편집본 미리보기가 준비되었어요.";
    case "pending":
    case "running": return "미리보기를 준비하고 있어요.";
    case "failed": return "미리보기를 만들지 못했어요.";
    case "stale": return "미리보기가 최신 편집본과 달라요.";
    case "unavailable": return "아직 미리보기가 없어요.";
    default: return "미리보기 상태를 지금 확인할 수 없어요.";
  }
}

function isSameTimelineLineage(state: OutputState, projectId: string, timelineJobId: string) {
  return state.projectId === projectId && state.timelineJob?.job_id === timelineJobId;
}

type OutputRecoverySnapshot = {
  jobStates: string[];
  artifactState: string | null;
};

function jobIdentityStatus(jobId: string, status: string) {
  return `${jobId}\u0000${status}`;
}

function captureSubtitleRecoverySnapshot(state: OutputState | null): OutputRecoverySnapshot {
  const subtitle = state?.subtitle;
  return {
    jobStates: subtitle ? [jobIdentityStatus(subtitle.job_id, subtitle.status)] : [],
    artifactState: subtitle?.subtitle ? [
      subtitle.job_id,
      subtitle.status,
      subtitle.subtitle.subtitle_id,
      subtitle.subtitle.status,
      subtitle.subtitle.timeline_id,
      subtitle.subtitle.source_session_id ?? "",
      subtitle.subtitle.source_session_revision ?? "",
      subtitle.subtitle.is_current ?? "",
    ].join("\u0000") : null,
  };
}

function captureFinalRecoverySnapshot(state: OutputState | null): OutputRecoverySnapshot {
  const finalRender = state?.finalRender;
  return {
    jobStates: (state?.finalJobs ?? []).map((job) => jobIdentityStatus(job.job_id, job.status)),
    artifactState: finalRender?.render ? [
      finalRender.job_id,
      finalRender.status,
      finalRender.render.export_id,
      finalRender.render.status,
      finalRender.render.timeline_id,
      finalRender.render.source_session_id ?? "",
      finalRender.render.source_session_revision ?? "",
      finalRender.render.is_current ?? "",
    ].join("\u0000") : null,
  };
}

function captureCapcutRecoverySnapshot(state: OutputState | null): OutputRecoverySnapshot {
  const capcutDraft = state?.capcutDraft;
  return {
    jobStates: (state?.capcutJobs ?? []).map((job) => jobIdentityStatus(job.job_id, job.status)),
    artifactState: capcutDraft?.export ? [
      capcutDraft.job_id,
      capcutDraft.status,
      capcutDraft.export.export_id,
      capcutDraft.export.status,
      capcutDraft.export.timeline_id,
      capcutDraft.export.source_session_id ?? "",
      capcutDraft.export.source_session_revision ?? "",
      capcutDraft.export.is_current,
    ].join("\u0000") : null,
  };
}

function captureCapcutHandoffRecoverySnapshot(state: OutputState | null) {
  const capcutDraft = state?.capcutDraft;
  const handoff = capcutDraft?.export?.handoff;
  return handoff ? [
    capcutDraft.job_id,
    capcutDraft.export?.export_id ?? "",
    capcutDraft.export?.source_session_id ?? "",
    capcutDraft.export?.source_session_revision ?? "",
    handoff.status,
    handoff.registered_project_path ?? "",
    handoff.error_message ?? "",
    handoff.registered_at ?? "",
    handoff.reused,
    handoff.recoverable ?? "",
    handoff.recoverable_at ?? "",
  ].join("\u0000") : null;
}

function hasNewInFlightJob(jobs: JobRecord[], previous: OutputRecoverySnapshot) {
  const previousJobStates = new Set(previous.jobStates);
  return jobs.some((job) => (
    (job.status === "pending" || job.status === "running") &&
    !previousJobStates.has(jobIdentityStatus(job.job_id, job.status))
  ));
}

function needsSubtitleFailureFallback(
  state: OutputState,
  projectId: string,
  timelineJobId: string,
  previous: OutputRecoverySnapshot,
) {
  if (!isSameTimelineLineage(state, projectId, timelineJobId)) return false;
  const subtitle = state.subtitle;
  const next = captureSubtitleRecoverySnapshot(state);
  const hasNewInFlight = (
    (subtitle?.status === "pending" || subtitle?.status === "running") &&
    !previous.jobStates.includes(jobIdentityStatus(subtitle.job_id, subtitle.status))
  );
  const hasNewCurrentArtifact = (
    subtitle?.status === "succeeded" &&
    subtitle.subtitle?.status === "succeeded" &&
    state.session?.project_id === projectId &&
    subtitle.subtitle.project_id === projectId &&
    subtitle.subtitle.timeline_id === state.session.timeline_id &&
    subtitle.subtitle.source_session_id === state.session.session_id &&
    subtitle.subtitle.source_session_revision === state.session.session_revision &&
    subtitle.subtitle.is_current === true &&
    next.artifactState !== previous.artifactState
  );
  return !(hasNewInFlight || hasNewCurrentArtifact);
}

function needsFinalFailureFallback(
  state: OutputState,
  projectId: string,
  timelineJobId: string,
  previous: OutputRecoverySnapshot,
) {
  if (!isSameTimelineLineage(state, projectId, timelineJobId)) return false;
  const next = captureFinalRecoverySnapshot(state);
  const hasNewCurrentArtifact = (
    state.finalRender?.status === "succeeded" &&
    state.finalRender.render?.is_current === true &&
    state.session?.project_id === projectId &&
    state.finalRender.render.timeline_id === state.session.timeline_id &&
    state.finalRender.render.source_session_id === state.session.session_id &&
    state.finalRender.render.source_session_revision === state.session.session_revision &&
    next.artifactState !== previous.artifactState
  );
  return !(hasNewInFlightJob(state.finalJobs, previous) || hasNewCurrentArtifact);
}

function needsCapcutFailureFallback(
  state: OutputState,
  projectId: string,
  timelineJobId: string,
  previous: OutputRecoverySnapshot,
) {
  if (!isSameTimelineLineage(state, projectId, timelineJobId)) return false;
  const next = captureCapcutRecoverySnapshot(state);
  const hasNewCurrentArtifact = (
    state.capcutDraft?.status === "succeeded" &&
    state.capcutDraft.export?.status === "succeeded" &&
    state.capcutDraft.export.is_current === true &&
    state.session?.project_id === projectId &&
    state.capcutDraft.export.timeline_id === state.session.timeline_id &&
    state.capcutDraft.export.source_session_id === state.session.session_id &&
    state.capcutDraft.export.source_session_revision === state.session.session_revision &&
    next.artifactState !== previous.artifactState
  );
  return !(hasNewInFlightJob(state.capcutJobs, previous) || hasNewCurrentArtifact);
}

function needsCapcutHandoffFailureFallback(
  state: OutputState,
  projectId: string,
  timelineJobId: string,
  draftJobId: string,
  previousHandoffState: string | null,
) {
  if (!isSameTimelineLineage(state, projectId, timelineJobId)) return false;
  if (state.capcutDraft?.job_id !== draftJobId) return false;
  const currentSession = state.session;
  const currentExport = state.capcutDraft.export;
  if (
    !currentSession ||
    currentSession.project_id !== projectId ||
    currentExport?.timeline_id !== currentSession.timeline_id ||
    currentExport.source_session_id !== currentSession.session_id ||
    currentExport.source_session_revision !== currentSession.session_revision ||
    currentExport.is_current !== true
  ) return true;
  const handoffStatus = state.capcutDraft.export?.handoff?.status;
  const hasDurableProgress = (
    handoffStatus != null &&
    handoffStatus !== "pending" &&
    handoffStatus !== "not_started" &&
    captureCapcutHandoffRecoverySnapshot(state) !== previousHandoffState
  );
  return !hasDurableProgress;
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
    if (!isCurrentRequest()) return null;
    setIsLoading(true);
    setErrorProjectId(null);
    try {
      const [session, jobs] = await Promise.all([
        api.getLatestEditingSession(refreshProjectId),
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
      let exactPreviewReadFailed = false;
      const [timeline, review, approval, subtitle, finalRender, capcutDraft, diagnostics, playbackManifest] = await Promise.all([
        timelineJob ? api.getTimeline(refreshProjectId, timelineJob.job_id) : Promise.resolve(null),
        timelineJob ? api.getReviewSnapshot(refreshProjectId, timelineJob.job_id) : Promise.resolve(null),
        timelineJob && session ? api.getReviewApproval(refreshProjectId, session.timeline_id) : Promise.resolve(null),
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
        session
          ? api.getEditorPlaybackManifest(refreshProjectId, session.session_id).catch(() => {
            exactPreviewReadFailed = true;
            return null;
          })
          : Promise.resolve(null),
      ]);
      if (!isCurrentRequest()) return;
      setSubtitleErrorProjectId(null);
      setFinalErrorProjectId(null);
      setCapcutErrorProjectId(null);
      setCapcutHandoffErrorProjectId(null);
      const nextState: OutputState = {
        projectId: refreshProjectId,
        session,
        timelineJob,
        timeline,
        review,
        approval,
        subtitle,
        finalJobs,
        finalJob,
        finalRender,
        capcutJobs,
        capcutDraft,
        diagnostics,
        exactPreviewState: deriveExactPreviewState(refreshProjectId, session, playbackManifest, exactPreviewReadFailed),
      };
      setState(nextState);
      return nextState;
    } catch {
      if (!isCurrentRequest()) return null;
      setState(null);
      setErrorProjectId(refreshProjectId);
      return null;
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
  const currentSession = currentState?.session;
  const canRenderSubtitle = Boolean(
    timelineJob && currentSession && currentState?.timeline && currentState.review && currentState.approval &&
    currentSession.project_id === projectId &&
    currentState.timeline.timeline.project_id === projectId &&
    currentState.timeline.timeline.timeline_id === currentSession.timeline_id &&
    currentState.timeline.timeline.source_session_id === currentSession.session_id &&
    currentState.timeline.timeline.source_session_revision === currentSession.session_revision &&
    currentState.review.project_id === projectId &&
    currentState.review.timeline_id === currentSession.timeline_id &&
    currentState.approval.project_id === projectId &&
    currentState.approval.timeline_id === currentSession.timeline_id &&
    currentState.approval.source_session_id === currentSession.session_id &&
    currentState.approval.source_session_revision === currentSession.session_revision &&
    currentState.approval.is_current === true &&
    currentState.review.review_status === "approved" &&
    currentState.approval.review_status === "approved" &&
    currentState.timeline.timeline.review_flags.length === 0 &&
    currentState.timeline.timeline.pending_recommendations.length === 0 &&
    currentState.review.review_flags.length === 0 &&
    currentState.review.pending_recommendations.length === 0,
  );
  const finalJob = currentState?.finalJob;
  const hasPendingFinal = currentState?.finalJobs.some((job) => job.status === "pending" || job.status === "running") === true;
  const canRenderFinal = canRenderSubtitle && !hasPendingFinal;
  const subtitle = currentState?.subtitle;
  const currentSubtitle = subtitle?.status === "succeeded" && subtitle.subtitle?.status === "succeeded" && currentSession != null && (
    currentSession.project_id === projectId &&
    subtitle.subtitle.project_id === projectId &&
    subtitle.subtitle.timeline_id === currentSession.timeline_id &&
    subtitle.subtitle.source_session_id === currentSession.session_id &&
    subtitle.subtitle.source_session_revision === currentSession.session_revision &&
    subtitle.subtitle.is_current === true
  );
  const staleSubtitle = subtitle?.status === "succeeded" && Boolean(subtitle.subtitle) && !currentSubtitle;
  const finalRender = currentState?.finalRender;
  const currentFinal = finalRender?.status === "succeeded" && finalRender.render?.is_current === true && currentSession != null && (
    currentSession.project_id === projectId &&
      finalRender.render.timeline_id === currentSession.timeline_id &&
      finalRender.render.source_session_id === currentSession.session_id &&
      finalRender.render.source_session_revision === currentSession.session_revision
  );
  const staleFinal = finalRender?.status === "succeeded" && Boolean(finalRender.render) && !currentFinal;
  const capcutJobs = currentState?.capcutJobs ?? [];
  const hasPendingCapcut = capcutJobs.some((job) => job.status === "pending" || job.status === "running");
  const canExportCapcutDraft = canRenderFinal && !hasPendingCapcut;
  const capcutDraft = currentState?.capcutDraft;
  const currentCapcutDraft = capcutDraft?.status === "succeeded" && capcutDraft.export?.status === "succeeded" && capcutDraft.export.is_current === true && currentSession != null && (
    currentSession.project_id === projectId &&
      capcutDraft.export.timeline_id === currentSession.timeline_id &&
      capcutDraft.export.source_session_id === currentSession.session_id &&
      capcutDraft.export.source_session_revision === currentSession.session_revision
  );
  const staleCapcutDraft = capcutDraft?.status === "succeeded" && Boolean(capcutDraft.export) && !currentCapcutDraft;
  const capcutHandoff = currentCapcutDraft ? capcutDraft?.export?.handoff ?? null : null;
  const capcutHandoffInProgress = capcutHandoff?.status === "in_progress";
  const canRegisterCapcutHandoff = Boolean(
    currentCapcutDraft && capcutDraft?.export && capcutHandoff?.status !== "ready" && !capcutHandoffInProgress,
  );
  const handleRenderSubtitle = async () => {
    const submissionProjectId = projectId;
    if (currentProjectId.current !== submissionProjectId || !timelineJob || !canRenderSubtitle || isRenderingCurrentSubtitle) return;
    const recoverySnapshot = captureSubtitleRecoverySnapshot(currentState);
    const submissionEpoch = subtitleSubmissionEpoch.current + 1;
    const requestEpochAtSubmission = requestEpoch.current;
    subtitleSubmissionEpoch.current = submissionEpoch;
    subtitleRequestProjectId.current = submissionProjectId;
    setIsRenderingSubtitle(true);
    setSubtitleErrorProjectId(null);
    try {
      const result = await api.renderSubtitle(submissionProjectId, { timeline_job_id: timelineJob.job_id });
      try {
      const [jobs, subtitle] = await Promise.all([
        api.listJobs(submissionProjectId),
        api.getSubtitle(submissionProjectId, result.job_id),
      ]);
      if (submissionEpoch !== subtitleSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
      await (requestEpochAtSubmission === requestEpoch.current
        ? refresh({ jobs, subtitle })
        : refresh());
      } catch {
        if (submissionEpoch !== subtitleSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
        await refresh();
      }
    } catch {
      if (submissionEpoch !== subtitleSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
      const latestState = await refresh();
      if (
        submissionEpoch === subtitleSubmissionEpoch.current &&
        currentProjectId.current === submissionProjectId &&
        latestState &&
        needsSubtitleFailureFallback(latestState, submissionProjectId, timelineJob.job_id, recoverySnapshot)
      ) setSubtitleErrorProjectId(submissionProjectId);
    } finally {
      if (submissionEpoch === subtitleSubmissionEpoch.current && currentProjectId.current === submissionProjectId) setIsRenderingSubtitle(false);
    }
  };
  const handleRenderFinal = async () => {
    const submissionProjectId = projectId;
    const timelineKey = timelineJob ? `${submissionProjectId}:${timelineJob.job_id}` : null;
    if (currentProjectId.current !== submissionProjectId || !timelineJob || !timelineKey || !canRenderFinal || isRenderingCurrentFinal || finalInFlightTimelineKey.current === timelineKey) return;
    const recoverySnapshot = captureFinalRecoverySnapshot(currentState);
    const submissionEpoch = finalSubmissionEpoch.current + 1;
    const requestEpochAtSubmission = requestEpoch.current;
    finalSubmissionEpoch.current = submissionEpoch;
    finalRequestProjectId.current = submissionProjectId;
    finalInFlightTimelineKey.current = timelineKey;
    setIsRenderingFinal(true);
    setFinalErrorProjectId(null);
    try {
      const result = await api.startFinalRender(submissionProjectId, { timeline_job_id: timelineJob.job_id });
      try {
      const [jobs, nextFinalRender] = await Promise.all([
        api.listJobs(submissionProjectId),
        api.getFinalRender(submissionProjectId, result.job_id),
      ]);
      if (submissionEpoch !== finalSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
      await (requestEpochAtSubmission === requestEpoch.current
        ? refresh({ jobs, finalRender: nextFinalRender })
        : refresh());
      } catch {
        if (submissionEpoch !== finalSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
        await refresh();
      }
    } catch {
      if (submissionEpoch !== finalSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
      const latestState = await refresh();
      if (
        submissionEpoch === finalSubmissionEpoch.current &&
        currentProjectId.current === submissionProjectId &&
        latestState &&
        needsFinalFailureFallback(latestState, submissionProjectId, timelineJob.job_id, recoverySnapshot)
      ) setFinalErrorProjectId(submissionProjectId);
    } finally {
      if (finalInFlightTimelineKey.current === timelineKey) finalInFlightTimelineKey.current = null;
      if (submissionEpoch === finalSubmissionEpoch.current && currentProjectId.current === submissionProjectId) setIsRenderingFinal(false);
    }
  };
  const handleExportCapcutDraft = async () => {
    const submissionProjectId = projectId;
    const timelineKey = timelineJob ? `${submissionProjectId}:${timelineJob.job_id}` : null;
    if (currentProjectId.current !== submissionProjectId || !timelineJob || !timelineKey || !canExportCapcutDraft || isExportingCurrentCapcutDraft || capcutInFlightTimelineKey.current === timelineKey) return;
    const recoverySnapshot = captureCapcutRecoverySnapshot(currentState);
    const submissionEpoch = capcutSubmissionEpoch.current + 1;
    const requestEpochAtSubmission = requestEpoch.current;
    capcutSubmissionEpoch.current = submissionEpoch;
    capcutRequestProjectId.current = submissionProjectId;
    capcutInFlightTimelineKey.current = timelineKey;
    setIsExportingCapcutDraft(true);
    setCapcutErrorProjectId(null);
    try {
      const result = await api.startCapcutDraftExport(submissionProjectId, { timeline_job_id: timelineJob.job_id });
      try {
      const [jobs, nextCapcutDraft] = await Promise.all([
        api.listJobs(submissionProjectId),
        api.getCapcutDraftExport(submissionProjectId, result.job_id),
      ]);
      if (submissionEpoch !== capcutSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
      await (requestEpochAtSubmission === requestEpoch.current
        ? refresh({ jobs, capcutDraft: nextCapcutDraft })
        : refresh());
      } catch {
        if (submissionEpoch !== capcutSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
        await refresh();
      }
    } catch {
      if (submissionEpoch !== capcutSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
      const latestState = await refresh();
      if (
        submissionEpoch === capcutSubmissionEpoch.current &&
        currentProjectId.current === submissionProjectId &&
        latestState &&
        needsCapcutFailureFallback(latestState, submissionProjectId, timelineJob.job_id, recoverySnapshot)
      ) setCapcutErrorProjectId(submissionProjectId);
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
    const recoverySnapshot = captureCapcutHandoffRecoverySnapshot(currentState);
    const submissionEpoch = capcutHandoffSubmissionEpoch.current + 1;
    const requestEpochAtSubmission = requestEpoch.current;
    capcutHandoffSubmissionEpoch.current = submissionEpoch;
    capcutHandoffRequestProjectId.current = submissionProjectId;
    capcutHandoffInFlightJobKey.current = handoffJobKey;
    setIsRegisteringCapcutHandoff(true);
    setCapcutHandoffErrorProjectId(null);
    try {
      await api.registerCapcutDraftHandoff(submissionProjectId, capcutDraftJobId);
      try {
      const nextCapcutDraft = await api.getCapcutDraftExport(submissionProjectId, capcutDraftJobId);
      if (submissionEpoch !== capcutHandoffSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
      await (requestEpochAtSubmission === requestEpoch.current
        ? refresh({ capcutDraft: nextCapcutDraft })
        : refresh());
      } catch {
        if (submissionEpoch !== capcutHandoffSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
        await refresh();
      }
    } catch {
      if (submissionEpoch !== capcutHandoffSubmissionEpoch.current || currentProjectId.current !== submissionProjectId) return;
      const latestState = await refresh();
      if (
        submissionEpoch === capcutHandoffSubmissionEpoch.current &&
        currentProjectId.current === submissionProjectId &&
        latestState &&
        timelineJob &&
        needsCapcutHandoffFailureFallback(latestState, submissionProjectId, timelineJob.job_id, capcutDraftJobId, recoverySnapshot)
      ) setCapcutHandoffErrorProjectId(submissionProjectId);
    } finally {
      if (capcutHandoffInFlightJobKey.current === handoffJobKey) capcutHandoffInFlightJobKey.current = null;
      if (submissionEpoch === capcutHandoffSubmissionEpoch.current && currentProjectId.current === submissionProjectId) setIsRegisteringCapcutHandoff(false);
    }
  };

  return <section className="vb-outputs" aria-live="polite" data-testid="outputs-page">
    <div><p className="vb-eyebrow">출력</p><h1>완성본과 CapCut 초안</h1><p>현재 승인된 편집본의 자막, 완성본, CapCut 초안을 여기에서 만들 수 있어요.</p></div>
    <div className="vb-home-grid">
      <Card>
        <CardHeader><CardTitle>편집본 미리보기</CardTitle><CardDescription>{exactPreviewDescription(currentState?.exactPreviewState)}</CardDescription></CardHeader>
        <CardContent>
          <p>재생은 편집 화면의 한 플레이어에서 확인해 주세요.</p>
          <Button onClick={onOpenEditor}>편집에서 미리보기 열기</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>자막</CardTitle><CardDescription>{currentSubtitle ? "자막이 준비되었어요." : staleSubtitle ? "자막이 최신 편집본과 달라요." : currentState?.subtitle?.status === "failed" ? "자막을 만들지 못했어요." : timelineJob ? "현재 편집본의 자막을 만들 수 있어요." : "아직 자막이 없어요."}</CardDescription></CardHeader>
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
          {capcutHandoffInProgress ? <p>CapCut 등록이 진행 중이에요. 잠시 후 상태를 다시 확인해 주세요.</p> : null}
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
