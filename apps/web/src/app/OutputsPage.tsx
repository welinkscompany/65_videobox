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
  type VariantRenderItem,
} from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { VariantOutputCard } from "../features/outputs/VariantOutputCard";
import { mergeVariantRenderItems, variantLabel, variantRenderSummary } from "../features/outputs/variantOutputState";

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

// 백엔드가 실패 이유를 코드로 보내 준다. 옮길 문구가 없는 코드는 그대로
// 흘려보내지 않고 원래 쓰던 한 줄로 돌아간다 -- 화면에 영어를 띄우느니
// 덜 구체적인 편이 낫다.
const FINAL_RENDER_FAILURES: Record<string, string> = {
  final_output_requires_review_approval: "검토에서 아직 승인하지 않았어요. 검토를 마치면 완성본을 만들 수 있어요.",
  draft_bundle_gap_blocks_final_and_capcut_output: "장면이 비어 있는 구간이 있어요. 그 구간에 영상을 넣은 뒤 다시 만들어 주세요.",
};

export function finalRenderFailureMessage(reason: string | null | undefined) {
  const mapped = reason ? FINAL_RENDER_FAILURES[reason.trim()] : undefined;
  return mapped ?? "완성본을 만들지 못했어요.";
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

/** 검토 화면과 한 단계로 합쳐질 때, 그쪽이 이미 읽은 값을 받아 쓰기 위한 창구.
 *
 * 주지 않으면(단독으로 쓸 때) 지금까지처럼 이 화면이 직접 읽는다. 주면 편집본·
 * 작업 목록·타임라인·검토본·승인 기록을 다시 묻지 않는다 -- 한 화면에서 같은 것을
 * 두 번 물으면 요청이 두 배가 될 뿐 아니라 두 영역이 서로 다른 사실을 볼 수 있다.
 */
export type SharedTimelineRead = Readonly<{
  session: EditingSession | null;
  jobs: readonly JobRecord[];
  job: JobRecord | null;
  timeline: TimelineJob | null;
  review: ReviewSnapshot | null;
  approval: ReviewApproval | null;
}>;

export function OutputsPage({ projectId, onOpenEditor, shared, onSharedRefresh, reviewInline = false }: {
  projectId: string;
  onOpenEditor: () => void;
  shared?: SharedTimelineRead;
  onSharedRefresh?: () => Promise<SharedTimelineRead>;
  /** 이 화면 위에 검토 내용이 이미 같은 화면·같은 팝업 안에 보이고 있는가.
   *  `ReviewAndOutputPage`가 그 경우 이 값을 준다 -- 그때는 체크리스트의
   *  "검토" 항목이 통째로 `/review`로 이동시키는 링크를 내지 않는다. 승인
   *  전이라는 사실 자체는 여전히 보여준다.
   *
   *  실측(2026-08-30, 브라우저)으로 확인된 것도 이 값으로 함께 고친다 --
   *  이 값이 참이면 위(`TimelineReviewSections`)가 이미 이 화면의 `<h1>`과
   *  전체 aria-live 알림을 맡고 있으므로, 여기서 또 `<h1>`·`aria-live`를
   *  내면 한 화면에 최상위 제목·알림 영역이 두 벌 생긴다. */
  reviewInline?: boolean;
}) {
  // `reviewInline`일 때는 `TimelineReviewSections`가 이미 이 화면의 <h1>과
  // aria-live 알림을 맡는다 -- 그 아래 절은 <h2>로 내려가고, 알림 영역은
  // 중복해서 만들지 않는다.
  const HeadingTag = reviewInline ? "h2" : "h1";
  const pageLiveRegion = reviewInline ? undefined : "polite";
  const [state, setState] = useState<OutputState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorProjectId, setErrorProjectId] = useState<string | null>(null);
  const [isRenderingSubtitle, setIsRenderingSubtitle] = useState(false);
  const [subtitleErrorProjectId, setSubtitleErrorProjectId] = useState<string | null>(null);
  const [isRenderingFinal, setIsRenderingFinal] = useState(false);
  const [finalErrorProjectId, setFinalErrorProjectId] = useState<string | null>(null);
  const [formatName, setFormatName] = useState("");
  const [formatSavedProjectId, setFormatSavedProjectId] = useState<string | null>(null);
  const [isSavingFormat, setIsSavingFormat] = useState(false);
  // owner 요청(2026-08-28): 프리뷰 공유 링크. 프로젝트별로 기억해 다른 프로젝트로
  // 넘어가면 앞서 만든 링크가 남아 보이지 않게 한다.
  const [previewShareProjectId, setPreviewShareProjectId] = useState<string | null>(null);
  const [previewShareUrl, setPreviewShareUrl] = useState<string | null>(null);
  const [previewShareId, setPreviewShareId] = useState<string | null>(null);
  const [isCreatingPreviewShare, setIsCreatingPreviewShare] = useState(false);
  const [previewShareErrorProjectId, setPreviewShareErrorProjectId] = useState<string | null>(null);
  // 코드리뷰로 발견(2026-08-28): 만드는 단추만 있고 되돌리는 단추가 없었다 --
  // 토큰 하나가 인증 전부인 기능이라, 취소할 길이 만드는 길만큼 중요하다.
  const [isRevokingPreviewShare, setIsRevokingPreviewShare] = useState(false);
  const [previewShareRevoked, setPreviewShareRevoked] = useState(false);
  // 판단은 프로젝트별로 기억한다. 프로젝트를 바꾸면 앞 프로젝트의 안내가 남으면 안 된다.
  const [verdictProjectId, setVerdictProjectId] = useState<string | null>(null);
  const [verdictSaved, setVerdictSaved] = useState<"good" | "bad" | null>(null);
  const [isSavingVerdict, setIsSavingVerdict] = useState(false);
  const [isExportingCapcutDraft, setIsExportingCapcutDraft] = useState(false);
  const [capcutErrorProjectId, setCapcutErrorProjectId] = useState<string | null>(null);
  const [isRegisteringCapcutHandoff, setIsRegisteringCapcutHandoff] = useState(false);
  const [capcutHandoffErrorProjectId, setCapcutHandoffErrorProjectId] = useState<string | null>(null);
  const [variantOptions, setVariantOptions] = useState<{ variant_id: string; kind: string }[]>([]);
  const [selectedVariantIds, setSelectedVariantIds] = useState<string[]>([]);
  const [variantItems, setVariantItems] = useState<VariantRenderItem[]>([]);
  const [confirmedVariantIds, setConfirmedVariantIds] = useState<string[]>([]);
  const [isRenderingVariants, setIsRenderingVariants] = useState(false);
  const [variantError, setVariantError] = useState(false);
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
  // `shared`는 읽을 때마다 새 객체다. 이걸 `refresh`의 의존성에 두면 새 값이
  // 올 때마다 `refresh`가 다시 만들어지고, 그 effect가 또 읽어서 끝없이 돈다.
  // 읽기는 `onSharedRefresh`(안정적)로만 걸고 값 자체는 ref로 본다.
  const sharedRef = useRef(shared);
  sharedRef.current = shared;
  // CapCut 상태는 검토 쪽 승인 여부와 무관하다 -- `shared`가 새로 채워질
  // 때마다(`reuseShared: true`로 다시 도는 재동기화, 511행 effect 주석 참고)
  // 다시 물을 이유가 없다. 실측(2026-08-30)으로 한 화면에서 이 호출이
  // 두 번 나가는 것을 확인했다. 프로젝트를 바꾸면 캐시를 버린다.
  const diagnosticsRef = useRef<{ projectId: string; value: CapCutHandoffDiagnostics | null } | null>(null);

  const refresh = useCallback(async (options?: { jobs?: JobRecord[]; subtitle?: SubtitleJob | null; finalRender?: FinalRenderJob | null; capcutDraft?: CapCutDraftExportJob | null; reuseShared?: boolean }) => {
    const refreshProjectId = projectId;
    const epoch = requestEpoch.current + 1;
    requestEpoch.current = epoch;
    const isCurrentRequest = () => epoch === requestEpoch.current && currentProjectId.current === refreshProjectId;
    if (!isCurrentRequest()) return null;
    setIsLoading(true);
    setErrorProjectId(null);
    try {
      // 합쳐진 화면에서는 검토 쪽이 이미 읽은 값을 그대로 쓴다. 그쪽 refresh가
      // 읽은 값을 돌려주므로, prop이 다시 내려오길 기다리지 않고 바로 이어서
      // 판단할 수 있다.
      // 처음 그릴 때는 검토 쪽이 이미 읽은 값을 그대로 쓴다(`reuseShared`).
      // 다시 읽는 것은 이 화면이 무언가를 바꾼 뒤뿐이고, 그때만 공유 읽기를 부른다.
      const sharedRead = onSharedRefresh && !options?.reuseShared
        ? await onSharedRefresh()
        : sharedRef.current ?? null;
      const [session, jobs] = sharedRead
        ? [sharedRead.session, options?.jobs ?? [...sharedRead.jobs]]
        : await Promise.all([
          api.getLatestEditingSession(refreshProjectId),
          options?.jobs ? Promise.resolve(options.jobs) : api.listJobs(refreshProjectId),
        ]);
      if (!isCurrentRequest()) return;
      const timelineJob = sharedRead
        ? sharedRead.job
        : session
          ? mostRecentJob(jobs.filter((job) => job.status === "succeeded" && job.output_ref === session.timeline_id), "timeline_build")
          : null;
      const subtitleRecord = timelineJob ? mostRecentJob(jobs, "subtitle_render", timelineJob.job_id) : null;
      const finalJobs = timelineJob ? jobs.filter((job) => job.job_type === "final_render" && job.input_ref === timelineJob.job_id) : [];
      const finalJob = timelineJob ? mostRecentJob(finalJobs, "final_render") : mostRecentJob(jobs, "final_render");
      const capcutJobs = timelineJob ? jobs.filter((job) => job.job_type === "capcut_draft_export" && job.input_ref === timelineJob.job_id) : [];
      const capcutJob = timelineJob ? mostRecentJob(capcutJobs, "capcut_draft_export") : null;
      let exactPreviewReadFailed = false;
      const [timeline, review, approval, subtitle, finalRender, capcutDraft, diagnostics, playbackManifest] = await Promise.all([
        sharedRead ? Promise.resolve(sharedRead.timeline) : timelineJob ? api.getTimeline(refreshProjectId, timelineJob.job_id) : Promise.resolve(null),
        sharedRead ? Promise.resolve(sharedRead.review) : timelineJob ? api.getReviewSnapshot(refreshProjectId, timelineJob.job_id) : Promise.resolve(null),
        sharedRead ? Promise.resolve(sharedRead.approval) : timelineJob && session ? api.getReviewApproval(refreshProjectId, session.timeline_id) : Promise.resolve(null),
        options?.subtitle && session && options.subtitle.subtitle.timeline_id === session.timeline_id
          ? Promise.resolve(options.subtitle)
          : subtitleRecord ? api.getSubtitle(refreshProjectId, subtitleRecord.job_id) : Promise.resolve(null),
        options?.finalRender && finalJob && options.finalRender.job_id === finalJob.job_id
          ? Promise.resolve(options.finalRender)
          : finalJob ? api.getFinalRender(refreshProjectId, finalJob.job_id) : Promise.resolve(null),
        options?.capcutDraft && capcutJob && options.capcutDraft.job_id === capcutJob.job_id
          ? Promise.resolve(options.capcutDraft)
          : capcutJob ? api.getCapcutDraftExport(refreshProjectId, capcutJob.job_id) : Promise.resolve(null),
        options?.reuseShared && diagnosticsRef.current?.projectId === refreshProjectId
          ? Promise.resolve(diagnosticsRef.current.value)
          : api.getCapcutHandoffDiagnostics().catch(() => null),
        session
          ? api.getEditorPlaybackManifest(refreshProjectId, session.session_id).catch(() => {
            exactPreviewReadFailed = true;
            return null;
          })
          : Promise.resolve(null),
      ]);
      if (!isCurrentRequest()) return;
      diagnosticsRef.current = { projectId: refreshProjectId, value: diagnostics };
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
  }, [projectId, onSharedRefresh]);

  const variantSession = state?.projectId === projectId ? state.session : null;
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
    void refresh({ reuseShared: true });
    return () => {
      requestEpoch.current += 1;
      subtitleSubmissionEpoch.current += 1;
      finalSubmissionEpoch.current += 1;
      capcutSubmissionEpoch.current += 1;
      capcutHandoffSubmissionEpoch.current += 1;
    };
    // 합쳐진 화면에서는 검토 쪽 읽기가 끝나 `shared`가 채워질 때 다시 그린다.
    // 그 값 없이 먼저 그리면 아직 아무것도 없는 상태만 보인다.
  }, [refresh, shared]);

  useEffect(() => {
    let active = true;
    setVariantOptions([]);
    setSelectedVariantIds([]);
    setVariantItems([]);
    setConfirmedVariantIds([]);
    setVariantError(false);
    if (!variantSession) return () => { active = false; };
    void api.listOutputVariants(projectId, variantSession.session_id).then((result) => {
      if (!active) return;
      try {
        if (!active) return;
        const options = result.variants
          .filter((variant) => variant.kind === "horizontal" || variant.kind === "vertical_full" || variant.kind === "vertical_highlight")
          .map((variant) => ({ variant_id: variant.variant_id, kind: variant.kind }));
        setVariantOptions(options);
        setSelectedVariantIds(options.filter((variant) => variant.kind !== "vertical_highlight").map((variant) => variant.variant_id));
      } catch { if (active) setVariantError(true); }
    }).catch(() => {
      if (active) setVariantError(true);
    });
    return () => { active = false; };
  }, [projectId, variantSession?.session_id]);

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
  const handleRenderVariants = async (requestedVariantIds = selectedVariantIds) => {
    const session = currentState?.session;
    if (!session || !requestedVariantIds.length || isRenderingVariants) return;
    setIsRenderingVariants(true);
    setVariantError(false);
    try {
      const result = await api.startVariantRenders(projectId, { session_id: session.session_id, variant_ids: requestedVariantIds });
      setVariantItems((current) => mergeVariantRenderItems(current, result.items, requestedVariantIds));
      setConfirmedVariantIds([]);
      const jobs = await api.listJobs(projectId);
      const reconciled = await Promise.all(result.items.map(async (item) => {
        const job = jobs.find((candidate) => candidate.job_id === item.job_id);
        if (!job || !item.job_id) return item;
        try {
          const final = await api.getFinalRender(projectId, item.job_id);
          return { ...item, status: final.status, error_code: final.status === "failed" ? "renderer_failed" : item.error_code };
        } catch {
          return item;
        }
      }));
      setVariantItems((current) => mergeVariantRenderItems(current, reconciled, requestedVariantIds));
    } catch {
      setVariantError(true);
    } finally {
      setIsRenderingVariants(false);
    }
  };
  const handleRefreshVariants = async () => {
    const jobs = await api.listJobs(projectId).catch(() => [] as JobRecord[]);
    const next = await Promise.all(variantItems.map(async (item) => {
      if (!item.job_id) return item;
      const job = jobs.find((candidate) => candidate.job_id === item.job_id);
      if (!job) return item;
      try {
        const final = await api.getFinalRender(projectId, item.job_id);
        return { ...item, status: final.status };
      } catch {
        return item;
      }
    }));
    setVariantItems(next);
  };
  if (isLoading && !state && !hasError) return <section className="vb-outputs" aria-live={pageLiveRegion}><p>출력 상태를 불러오는 중이에요.</p></section>;
  if (hasError) return <section className="vb-outputs" aria-live={pageLiveRegion} data-testid="outputs-page"><HeadingTag>출력</HeadingTag><p>출력 상태를 불러오지 못했어요.</p><p>잠시 후 상태를 다시 확인하거나 편집 화면에서 작업을 이어가세요.</p><Button variant="outline" onClick={() => void refresh()}>상태 다시 확인</Button><Button onClick={onOpenEditor}>편집 열기</Button></section>;

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
  const hasCurrentEditingDraft = Boolean(
    currentSession && timelineJob && currentState?.timeline &&
    currentSession.project_id === projectId &&
    currentState.timeline.timeline.project_id === projectId &&
    currentState.timeline.timeline.timeline_id === currentSession.timeline_id &&
    currentState.timeline.timeline.source_session_id === currentSession.session_id &&
    currentState.timeline.timeline.source_session_revision === currentSession.session_revision,
  );
  const hasCurrentReviewIdentity = Boolean(
    currentState?.review && currentState.approval && currentSession && timelineJob &&
    currentSession.project_id === projectId &&
    currentState.review.project_id === projectId &&
    currentState.review.timeline_id === currentSession.timeline_id &&
    currentState.approval.project_id === projectId &&
    currentState.approval.timeline_id === currentSession.timeline_id &&
    currentState.approval.source_session_id === currentSession.session_id &&
    currentState.approval.source_session_revision === currentSession.session_revision,
  );
  const reviewApproved = Boolean(
    hasCurrentReviewIdentity &&
    currentState?.review?.review_status === "approved" &&
    currentState.approval?.review_status === "approved" &&
    currentState.approval.is_current === true,
  );
  const outputBlocked = !canRenderSubtitle;
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
  // 자동 제작은 "어떻게 만들지"를 이 포맷에서 가져간다. 마음에 든 완성본을 본
  // 순간이 그것을 남길 유일한 때다.
  const handleSaveFormat = async () => {
    const submissionProjectId = projectId;
    const name = formatName.trim();
    // 이름 없는 포맷이 쌓이면 다음 영상에서 무엇을 고를지 알 수 없다.
    if (!name || !currentSession?.session_id || isSavingFormat) return;
    setIsSavingFormat(true);
    try {
      await api.saveFormatTemplate(submissionProjectId, { name, session_id: currentSession.session_id });
      if (currentProjectId.current !== submissionProjectId) return;
      setFormatSavedProjectId(submissionProjectId);
      setFormatName("");
    } finally {
      if (currentProjectId.current === submissionProjectId) setIsSavingFormat(false);
    }
  };
  // 기계가 잰 지표만으로는 무엇이 좋은 영상인지 배울 수 없다. 이 판단이 라벨이다.
  const handleVerdict = async (verdict: "good" | "bad") => {
    const submissionProjectId = projectId;
    if (!finalRender?.job_id || isSavingVerdict) return;
    setIsSavingVerdict(true);
    try {
      await api.recordFinalRenderVerdict(submissionProjectId, finalRender.job_id, { verdict });
      if (currentProjectId.current !== submissionProjectId) return;
      setVerdictProjectId(submissionProjectId);
      setVerdictSaved(verdict);
    } finally {
      if (currentProjectId.current === submissionProjectId) setIsSavingVerdict(false);
    }
  };
  // owner 요청(2026-08-28): 프리뷰 공유 링크 — 토큰 링크 방식 승인. 이 앱은
  // 지금까지 인증이 전혀 없었다는 점을 밝혀 둔다. 링크 하나가 이 완성본 하나에만 닿는다.
  const handleCreatePreviewShare = async () => {
    const submissionProjectId = projectId;
    if (!finalRender?.job_id || isCreatingPreviewShare) return;
    setIsCreatingPreviewShare(true);
    setPreviewShareErrorProjectId(null);
    try {
      const created = await api.createPreviewShare(submissionProjectId, finalRender.job_id);
      if (currentProjectId.current !== submissionProjectId) return;
      setPreviewShareProjectId(submissionProjectId);
      setPreviewShareUrl(`${window.location.origin}${created.url}`);
      setPreviewShareId(created.share_id);
      setPreviewShareRevoked(false);
    } catch {
      if (currentProjectId.current !== submissionProjectId) return;
      setPreviewShareErrorProjectId(submissionProjectId);
    } finally {
      if (currentProjectId.current === submissionProjectId) setIsCreatingPreviewShare(false);
    }
  };
  const handleRevokePreviewShare = async () => {
    const submissionProjectId = projectId;
    if (!previewShareId || isRevokingPreviewShare) return;
    setIsRevokingPreviewShare(true);
    try {
      await api.revokePreviewShare(submissionProjectId, previewShareId);
      if (currentProjectId.current !== submissionProjectId) return;
      setPreviewShareRevoked(true);
    } finally {
      if (currentProjectId.current === submissionProjectId) setIsRevokingPreviewShare(false);
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

  return <section className="vb-outputs" aria-live={pageLiveRegion} data-testid="outputs-page">
    <div><p className="vb-eyebrow">출력</p><HeadingTag>완성본과 CapCut 초안</HeadingTag><p>승인된 편집본 · 자막 · 완성본 · CapCut 초안</p></div>
    {outputBlocked ? <section aria-label="출력 준비 체크리스트" className="vb-output-readiness">
      <h2>출력 준비 체크리스트</h2>
      <ol aria-label="출력 준비 단계">
        <li>
          <strong>편집본</strong>
          <span>{hasCurrentEditingDraft ? "준비됨" : "준비 필요"}</span>
          {!hasCurrentEditingDraft ? <Button variant="outline" onClick={onOpenEditor}>편집 화면 열기</Button> : null}
        </li>
        <li>
          <strong>검토</strong>
          <span>{reviewApproved ? "승인됨" : "승인 필요"}</span>
          {/* 검토가 이미 이 화면 위에 함께 보이고 있으면(`ReviewAndOutputPage`)
              따로 이동할 곳이 없다 -- 위로 올라가면 그 내용이 이미 있다.
              단독으로 쓰일 때만 `/review`로 안내한다. */}
          {!reviewApproved && hasCurrentEditingDraft && !reviewInline ? <a className="vb-action-link" href={`/projects/${encodeURIComponent(projectId)}/review`}>검토 화면 열기</a> : null}
        </li>
        <li>
          <strong>출력</strong>
          <span>{canRenderSubtitle ? "자막과 완성본을 만들 수 있어요." : "앞 단계 완료 필요"}</span>
        </li>
      </ol>
    </section> : null}
    <div className="vb-home-grid vb-outputs-grid">
      <Card>
        <CardHeader><CardTitle>편집본 미리보기</CardTitle><CardDescription>{exactPreviewDescription(currentState?.exactPreviewState)}</CardDescription></CardHeader>
        <CardContent>
          <p>재생은 편집 화면의 한 플레이어에서 확인해 주세요.</p>
          <Button onClick={onOpenEditor}>편집에서 미리보기 열기</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>가로·세로 출력</CardTitle><CardDescription>{variantRenderSummary(variantItems)}</CardDescription></CardHeader>
        <CardContent>
          <p>성공한 출력은 서로 독립적으로 재생하고, 실패한 출력만 다시 만들 수 있어요.</p>
          {variantError ? <p role="status">출력 변형 상태를 확인하지 못했어요.</p> : null}
          {variantOptions.map((option) => (
              <label key={option.variant_id}>
                <input
                  data-native-control="output-variant-select"
                type="checkbox"
                checked={selectedVariantIds.includes(option.variant_id)}
                onChange={() => setSelectedVariantIds((current) => current.includes(option.variant_id) ? current.filter((id) => id !== option.variant_id) : [...current, option.variant_id])}
              /> {variantLabel(option.kind)}
            </label>
          ))}
          <div className="vb-output-actions">
            <Button disabled={!currentState?.session || !selectedVariantIds.length || isRenderingVariants} onClick={() => void handleRenderVariants()}>{isRenderingVariants ? "출력 만드는 중" : "가로·세로 출력 만들기"}</Button>
            <Button variant="outline" disabled={!variantItems.length} onClick={() => void handleRefreshVariants()}>출력 상태 다시 확인</Button>
          </div>
        </CardContent>
      </Card>
      {variantItems.map((item) => (
        <VariantOutputCard key={item.variant_id} projectId={projectId} item={item} confirmed={confirmedVariantIds.includes(item.variant_id)} onConfirm={() => setConfirmedVariantIds((current) => current.includes(item.variant_id) ? current : [...current, item.variant_id])} onRetry={() => {
          setSelectedVariantIds([item.variant_id]);
          setConfirmedVariantIds((current) => current.filter((id) => id !== item.variant_id));
          void handleRenderVariants([item.variant_id]);
        }} />
      ))}
      <Card>
        <CardHeader><CardTitle>자막</CardTitle><CardDescription>{currentSubtitle ? "자막이 준비되었어요." : staleSubtitle ? "자막이 최신 편집본과 달라요." : currentState?.subtitle?.status === "failed" ? "자막을 만들지 못했어요." : timelineJob ? "현재 편집본의 자막을 만들 수 있어요." : "아직 자막이 없어요."}</CardDescription></CardHeader>
        <CardContent>
          {subtitleError ? <p>자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.</p> : null}
          {!timelineJob ? <p>먼저 편집 화면에서 현재 초안을 준비해 주세요.</p> : null}
          {timelineJob && !canRenderSubtitle ? <p>검토 승인과 확인할 항목을 모두 마친 뒤 자막을 만들 수 있어요.</p> : null}
          <Button disabled={!canRenderSubtitle || isRenderingCurrentSubtitle} onClick={() => void handleRenderSubtitle()}>{isRenderingCurrentSubtitle ? "자막 만드는 중" : "자막 만들기"}</Button>
          {/* Vrew의 "다양한 내보내기"(#14) 참고, owner 요청 2026-08-28: "srt...
              내보내기". 이미 디스크에 있던 .srt 파일을 내려받는 문 하나만 연다. */}
          {currentSubtitle && subtitle ? <a className="vb-action-link" download href={`/api/projects/${encodeURIComponent(projectId)}/subtitles/${encodeURIComponent(subtitle.job_id)}/content`}>SRT 자막 파일 내려받기</a> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>완성본</CardTitle><CardDescription>{currentFinal ? "완성본을 확인할 수 있어요." : staleFinal ? "완성본이 최신 편집본과 달라요." : finalRender?.status === "failed" ? finalRenderFailureMessage(finalRender?.error_message) : hasPendingFinal ? "완성본을 만드는 중이에요." : timelineJob ? "현재 편집본의 완성본을 만들 수 있어요." : "아직 완성본이 없어요."}</CardDescription></CardHeader>
        <CardContent>
          {finalError ? <p>{finalRenderFailureMessage(finalRender?.error_message)} 편집 상태를 확인한 뒤 다시 시도해 주세요.</p> : null}
          {!timelineJob ? <p>먼저 편집 화면에서 현재 초안을 준비해 주세요.</p> : null}
          {timelineJob && !canRenderSubtitle ? <p>검토 승인과 확인할 항목을 모두 마친 뒤 완성본을 만들 수 있어요.</p> : null}
          {currentFinal && finalRender.render?.has_sound === false ? <p>완성본에 소리가 들어 있지 않아요. 내레이션이나 음악을 넣고 다시 만들어 주세요.</p> : null}
          {currentFinal ? <video className="vb-output-video" aria-label="완성본 재생" controls preload="metadata" src={`/api/projects/${encodeURIComponent(projectId)}/final-renders/${encodeURIComponent(finalRender.job_id)}/content`}>이 브라우저에서는 완성본을 재생할 수 없어요.</video> : null}
          {/* Vrew의 "다양한 내보내기"(#14) 참고, owner 요청 2026-08-28: "오디오만...
              내보내기". 완성본 mp4에서 그때그때 오디오만 뽑는다(새 렌더 아님). */}
          {currentFinal ? <a className="vb-action-link" download href={`/api/projects/${encodeURIComponent(projectId)}/final-renders/${encodeURIComponent(finalRender.job_id)}/audio-content`}>오디오만 내려받기</a> : null}
          {/* Vrew #15 "프리뷰 공유" 참고, owner 요청(2026-08-28): 동료에게 링크로
              중간 공유. 토큰 하나가 이 완성본 하나에만 닿는다 — 앱에 로그인이 없어도
              그 사람은 이 링크로만 영상을 볼 수 있다. */}
          {currentFinal ? <div className="vb-preview-share">
            <Button disabled={isCreatingPreviewShare} onClick={() => void handleCreatePreviewShare()}>{isCreatingPreviewShare ? "공유 링크 만드는 중" : "동료에게 공유 링크 만들기"}</Button>
            {previewShareErrorProjectId === projectId ? <p>공유 링크를 만들지 못했어요. 다시 시도해 주세요.</p> : null}
            {previewShareProjectId === projectId && previewShareUrl ? (
              previewShareRevoked ? (
                <p>이 링크를 취소했어요. 더 이상 열리지 않아요.</p>
              ) : (
                <p>
                  동료에게 이 링크를 보내 주세요: <input data-native-control="preview-share-url" readOnly value={previewShareUrl} onFocus={(event) => event.currentTarget.select()} />
                  {" "}
                  <Button variant="outline" disabled={isRevokingPreviewShare} onClick={() => void handleRevokePreviewShare()}>{isRevokingPreviewShare ? "취소하는 중" : "이 링크 취소하기"}</Button>
                </p>
              )
            ) : null}
          </div> : null}
          {currentFinal ? <div className="vb-final-verdict">
            {/* 낡은 완성본은 평가하지 않는다. 어느 편집본에 대한 판단인지 알 수 없어진다. */}
            {verdictProjectId === projectId && verdictSaved
              ? <p>{verdictSaved === "good" ? "좋았다고 기록했어요." : "아쉬웠다고 기록했어요."}</p>
              : <p>이 완성본이 어땠는지 남겨 주시면 다음 추천이 좋아져요.</p>}
            <Button disabled={isSavingVerdict} onClick={() => void handleVerdict("good")}>이 완성본 좋아요</Button>
            <Button disabled={isSavingVerdict} onClick={() => void handleVerdict("bad")}>이 완성본 아쉬워요</Button>
          </div> : null}
          {currentFinal ? <div className="vb-final-format">
            {formatSavedProjectId === projectId
              ? <p>포맷을 저장했어요. 다음 영상에서 편집 화면의 저장한 포맷에서 고를 수 있어요.</p>
              : <p>이 영상처럼 만들고 싶으면 포맷으로 저장해 두세요.</p>}
            <label htmlFor="format-template-name">포맷 이름</label>
            <Input
              id="format-template-name"
              value={formatName}
              placeholder="예: 내 브이로그 포맷"
              onChange={(event) => setFormatName(event.target.value)}
            />
            <Button disabled={isSavingFormat} onClick={() => void handleSaveFormat()}>이 포맷 저장하기</Button>
          </div> : null}
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
    <div className="vb-output-actions"><Button variant="outline" onClick={() => void refresh()}>상태 다시 확인</Button><Button onClick={onOpenEditor}>편집 열기</Button></div>
  </section>;
}
