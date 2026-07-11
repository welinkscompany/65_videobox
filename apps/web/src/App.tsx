import { Fragment, useEffect, useMemo, useState } from "react";

import {
  api,
  type BrollAsset,
  type CapCutDraftExportJob,
  type EditingSession,
  type EditingSessionSegment,
  type ExportJob,
  type FinalRenderJob,
  type GeminiProviderKey,
  type JobRecord,
  type PartialRegenerationPreflight,
  type PartialRegenerationRun,
  type PreviewJob,
  type Project,
  type RecommendationItem,
  type ReviewSnapshot,
  type SubtitleJob,
  type TimelineJob,
  type TtsCandidateRecord,
  type JobRecordWithProject,
} from "./api";
import {
  buildDefaultEditingSelection,
  buildDefaultRegenerationFields,
  buildEditingDrafts,
  canResumeCandidate,
  createEmptyGeminiKeyForm,
  type EditingMutationFeedback,
  type EditingSegmentDraft,
  findLatestSucceededJob,
  findLatestTimelineJob,
  formatAffectedOutputArea,
  formatBrollAssetLabel,
  formatBrollAssetTags,
  formatBrollAssetTitle,
  formatDisplayText,
  formatEditingMutationFeedbackLabel,
  formatFieldLabel,
  formatJobValue,
  formatNullableValue,
  formatOperatorNote,
  formatPredictedReviewStatusDescription,
  formatPredictedReviewStatusLabel,
  formatReviewActionLabel,
  formatReviewFlagCode,
  formatSeconds,
  formatSegmentReviewReason,
  formatStatusLabel,
  formatTrackLabel,
  formatWorkflowStep,
  type GeminiKeyFormState,
  haveSameMembers,
  type LoadState,
  mapRecommendationTypeToEditingField,
  prettifyJobType,
  readOverlay,
  readRecordValue,
  renderBrollRecommendationEvidence,
  restoredTargetedSegmentsMatch,
  reviewActions,
} from "./lib/formatters";
import { ProjectOnboarding } from "./ProjectOnboarding";

export function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedSection, setSelectedSection] = useState<
    "overview" | "timeline" | "review" | "editing" | "settings"
  >("overview");
  const [projectDetail, setProjectDetail] = useState<Project | null>(null);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [timelineJob, setTimelineJob] = useState<TimelineJob | null>(null);
  const [reviewSnapshot, setReviewSnapshot] = useState<ReviewSnapshot | null>(null);
  const [editingSession, setEditingSession] = useState<EditingSession | null>(null);
  const [editingDrafts, setEditingDrafts] = useState<Record<string, EditingSegmentDraft>>({});
  const [selectedEditingSegmentId, setSelectedEditingSegmentId] = useState<string | null>(null);
  const [selectedRegenerationFields, setSelectedRegenerationFields] = useState<string[]>([]);
  const [partialRegenerationPreflight, setPartialRegenerationPreflight] =
    useState<PartialRegenerationPreflight | null>(null);
  const [partialRegenerationRun, setPartialRegenerationRun] =
    useState<PartialRegenerationRun | null>(null);
  const [subtitleJob, setSubtitleJob] = useState<SubtitleJob | null>(null);
  const [previewJob, setPreviewJob] = useState<PreviewJob | null>(null);
  const [exportJob, setExportJob] = useState<ExportJob | null>(null);
  const [finalRenderJob, setFinalRenderJob] = useState<FinalRenderJob | null>(null);
  const [capcutDraftJob, setCapcutDraftJob] = useState<CapCutDraftExportJob | null>(null);
  const [voiceSamplePath, setVoiceSamplePath] = useState("");
  const [voiceSampleAssetId, setVoiceSampleAssetId] = useState("");
  const [isRegisteringVoiceSample, setIsRegisteringVoiceSample] = useState(false);
  const [voiceSampleMessage, setVoiceSampleMessage] = useState<string | null>(null);
  const [voiceSampleError, setVoiceSampleError] = useState<string | null>(null);
  const [ttsCandidateVoiceSampleId, setTtsCandidateVoiceSampleId] = useState("");
  const [isGeneratingTtsCandidate, setIsGeneratingTtsCandidate] = useState(false);
  const [ttsCandidateMessage, setTtsCandidateMessage] = useState<string | null>(null);
  const [ttsCandidateError, setTtsCandidateError] = useState<string | null>(null);
  const [ttsCandidates, setTtsCandidates] = useState<TtsCandidateRecord[]>([]);
  const [isLoadingTtsCandidates, setIsLoadingTtsCandidates] = useState(false);
  const [brollAssets, setBrollAssets] = useState<BrollAsset[]>([]);
  const [brollAssetLoadError, setBrollAssetLoadError] = useState<string | null>(null);
  const [brollFolderPath, setBrollFolderPath] = useState(
    "D:\\AI_Workspace_louis_office_50\\20_project\\65_videobox-project\\비롤_라이브러리\\검수완료",
  );
  const [brollSourcePaths, setBrollSourcePaths] = useState("");
  const [brollImportTags, setBrollImportTags] = useState("");
  const [brollAssetFilter, setBrollAssetFilter] = useState("");
  const [brollImportError, setBrollImportError] = useState<string | null>(null);
  const [brollImportMessage, setBrollImportMessage] = useState<string | null>(null);
  const [isImportingBroll, setIsImportingBroll] = useState(false);
  const [geminiKeys, setGeminiKeys] = useState<GeminiProviderKey[]>([]);
  const [geminiLoadError, setGeminiLoadError] = useState<string | null>(null);
  const [editingSessionRestoreError, setEditingSessionRestoreError] = useState<string | null>(null);
  const [partialRegenerationRestoreWarning, setPartialRegenerationRestoreWarning] = useState<
    string | null
  >(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [editingMutationFeedback, setEditingMutationFeedback] =
    useState<EditingMutationFeedback>(null);
  const [isRebuildingTimeline, setIsRebuildingTimeline] = useState(false);
  const [isApprovingTimeline, setIsApprovingTimeline] = useState(false);
  const [isReopeningTimeline, setIsReopeningTimeline] = useState(false);
  const [isRenderingSubtitle, setIsRenderingSubtitle] = useState(false);
  const [isRenderingPreview, setIsRenderingPreview] = useState(false);
  const [isExportingCapcut, setIsExportingCapcut] = useState(false);
  const [isRenderingFinal, setIsRenderingFinal] = useState(false);
  const [finalRenderProgress, setFinalRenderProgress] = useState<number | null>(null);
  const [isExportingCapcutDraft, setIsExportingCapcutDraft] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [isAllJobsPanelOpen, setIsAllJobsPanelOpen] = useState(false);
  const [allJobs, setAllJobs] = useState<JobRecordWithProject[]>([]);
  const [isLoadingAllJobs, setIsLoadingAllJobs] = useState(false);
  const [allJobsError, setAllJobsError] = useState<string | null>(null);
  const [isStartingEditingSession, setIsStartingEditingSession] = useState(false);
  const [isSavingEditingMutation, setIsSavingEditingMutation] = useState<string | null>(null);
  const [isRequestingRegenerationPreflight, setIsRequestingRegenerationPreflight] =
    useState(false);
  const [isRunningPartialRegeneration, setIsRunningPartialRegeneration] = useState(false);
  const [isGeminiFormOpen, setIsGeminiFormOpen] = useState(false);
  const [editingGeminiKeyId, setEditingGeminiKeyId] = useState<string | null>(null);
  const [geminiForm, setGeminiForm] = useState<GeminiKeyFormState>(createEmptyGeminiKeyForm);
  const [isSavingGeminiKey, setIsSavingGeminiKey] = useState(false);
  const [togglingGeminiKeyId, setTogglingGeminiKeyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadProjects() {
      setLoadState("loading");
      setErrorMessage(null);
      try {
        const projectItems = await api.listProjects();
        if (cancelled) {
          return;
        }
        setProjects(projectItems);
        setSelectedProjectId((current) => current ?? projectItems[0]?.project_id ?? null);
        setLoadState("ready");
      } catch (error) {
        if (cancelled) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
        setLoadState("error");
      }
    }

    void loadProjects();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setProjectDetail(null);
      setJobs([]);
      setTimelineJob(null);
      setReviewSnapshot(null);
      setEditingSession(null);
      setEditingDrafts({});
      setSelectedEditingSegmentId(null);
      setSelectedRegenerationFields([]);
      setPartialRegenerationPreflight(null);
      setPartialRegenerationRun(null);
      setSubtitleJob(null);
      setPreviewJob(null);
      setExportJob(null);
      setBrollAssets([]);
      setBrollAssetLoadError(null);
      setBrollAssetFilter("");
      setBrollImportError(null);
      setBrollImportMessage(null);
      setGeminiKeys([]);
      setGeminiLoadError(null);
      setIsGeminiFormOpen(false);
      setEditingGeminiKeyId(null);
      setGeminiForm(createEmptyGeminiKeyForm());
      return;
    }

    let cancelled = false;
    const projectId = selectedProjectId;

    async function loadProjectWorkspace() {
      setLoadState("loading");
      setErrorMessage(null);
      setBrollAssetLoadError(null);
      setBrollAssetFilter("");
      setBrollImportError(null);
      setBrollImportMessage(null);
      setGeminiLoadError(null);
      setEditingSessionRestoreError(null);
      setPartialRegenerationRestoreWarning(null);
      try {
        const project = await api.getProject(projectId);
        const jobItems = await api.listJobs(projectId);
        let archivedBrollAssets: BrollAsset[] = [];
        try {
          archivedBrollAssets = await api.listBrollAssets(projectId);
        } catch {
          archivedBrollAssets = [];
          setBrollAssetLoadError("B롤 보관함 오류");
        }
        let latestEditingSession: EditingSession | null = null;
        try {
          latestEditingSession = await api.getLatestEditingSession(projectId);
        } catch (error) {
          setEditingSessionRestoreError(
            error instanceof Error
              ? `편집 세션 복구 실패 · 기존 타임라인 유지 (${error.message})`
              : "편집 세션 복구 실패 · 기존 타임라인 유지",
          );
          latestEditingSession = null;
        }
        const latestTimelineJob = findLatestTimelineJob(jobItems);
        const [stableTimeline, stableReview] = latestTimelineJob
          ? await Promise.all([
              api.getTimeline(projectId, latestTimelineJob.job_id),
              api.getReviewSnapshot(projectId, latestTimelineJob.job_id),
            ])
          : [null, null];
        const latestPreviewJob = latestTimelineJob
          ? findLatestSucceededJob(jobItems, "preview_render", latestTimelineJob.job_id)
          : null;
        const latestSubtitleJob = latestTimelineJob
          ? findLatestSucceededJob(jobItems, "subtitle_render", latestTimelineJob.job_id)
          : null;
        const latestExportJob = latestTimelineJob
          ? findLatestSucceededJob(jobItems, "capcut_export", latestTimelineJob.job_id)
          : null;
        const subtitle = latestSubtitleJob
          ? await api.getSubtitle(projectId, latestSubtitleJob.job_id)
          : null;
        const preview = latestPreviewJob
          ? await api.getPreview(projectId, latestPreviewJob.job_id)
          : null;
        const capcutExport = latestExportJob
          ? await api.getExport(projectId, latestExportJob.job_id)
          : null;
        let activeTimeline = stableTimeline;
        let activeReview = stableReview;
        let resumedSelection: { segmentId: string | null; fields: string[] } | null = null;
        let resumedPartialRegenerationPreflight: PartialRegenerationPreflight | null = null;
        let resumedPartialRegeneration: PartialRegenerationRun | null = null;
        let resumedPartialRegenerationRestoreWarning: string | null = null;
        let activeSubtitle = subtitle;
        let activePreview = preview;
        let activeExport = capcutExport;
        if (latestEditingSession) {
          const latestCandidateJob = findLatestSucceededJob(
            jobItems,
            "partial_regeneration",
            latestEditingSession.session_id,
          );
          if (latestCandidateJob) {
            try {
              const candidateResult = await api.getPartialRegenerationResult(
                projectId,
                latestCandidateJob.job_id,
              );
              if (canResumeCandidate(latestEditingSession, candidateResult)) {
                const candidateReview = await api.getReviewSnapshot(
                  projectId,
                  latestCandidateJob.job_id,
                );
                const canRepresentResumedScope = candidateResult.segment_ids.length === 1;
                if (canRepresentResumedScope) {
                  try {
                    const restoredPreflight = await api.previewPartialRegeneration(
                      projectId,
                      candidateResult.session_id,
                      {
                        segment_ids: candidateResult.segment_ids,
                        fields: candidateResult.fields,
                      },
                    );
                    const restoredTargetedSegmentIds = restoredPreflight.targeted_segments
                      .map((segment) => String(segment.segment_id ?? ""))
                      .filter(Boolean);
                    const restoredTargetedSegmentsMatchReviewState = restoredTargetedSegmentsMatch(
                      restoredPreflight.targeted_segments,
                      latestEditingSession,
                      (segment, currentSessionSegment) =>
                        Boolean(segment.review_required) ===
                        Boolean(currentSessionSegment.review_required),
                    );
                    const restoredTargetedSegmentsMatchTtsReplacement = restoredTargetedSegmentsMatch(
                      restoredPreflight.targeted_segments,
                      latestEditingSession,
                      (segment, currentSessionSegment) => {
                        const restoredTtsRecommendationId = String(
                          readRecordValue(segment.tts_replacement)?.recommendation_id ?? "",
                        );
                        const restoredTtsAssetId = String(
                          readRecordValue(segment.tts_replacement)?.asset_id ?? "",
                        );
                        const currentTtsRecommendationId = String(
                          currentSessionSegment.tts_replacement?.recommendation_id ?? "",
                        );
                        const currentTtsAssetId = String(
                          currentSessionSegment.tts_replacement?.asset_id ?? "",
                        );
                        return (
                          restoredTtsRecommendationId === currentTtsRecommendationId &&
                          restoredTtsAssetId === currentTtsAssetId
                        );
                      },
                    );
                    const restoredTargetedSegmentsMatchVisualOverlays = restoredTargetedSegmentsMatch(
                      restoredPreflight.targeted_segments,
                      latestEditingSession,
                      (segment, currentSessionSegment) =>
                        JSON.stringify(segment.visual_overlays ?? []) ===
                        JSON.stringify(currentSessionSegment.visual_overlays ?? []),
                    );
                    const restoredTargetedSegmentsMatchBrollOverride = restoredTargetedSegmentsMatch(
                      restoredPreflight.targeted_segments,
                      latestEditingSession,
                      (segment, currentSessionSegment) => {
                        const restoredBrollAssetId = String(
                          readRecordValue(segment.broll_override)?.asset_id ?? "",
                        );
                        const currentBrollAssetId = String(
                          currentSessionSegment.broll_override?.asset_id ?? "",
                        );
                        return restoredBrollAssetId === currentBrollAssetId;
                      },
                    );
                    const restoredTargetedSegmentsMatchMusicOverride = restoredTargetedSegmentsMatch(
                      restoredPreflight.targeted_segments,
                      latestEditingSession,
                      (segment, currentSessionSegment) => {
                        const restoredMusicAssetId = String(
                          readRecordValue(segment.music_override)?.asset_id ?? "",
                        );
                        const currentMusicAssetId = String(
                          currentSessionSegment.music_override?.asset_id ?? "",
                        );
                        return restoredMusicAssetId === currentMusicAssetId;
                      },
                    );
                    if (
                      restoredPreflight.session_id === candidateResult.session_id &&
                      haveSameMembers(restoredPreflight.segment_ids, candidateResult.segment_ids) &&
                      haveSameMembers(restoredTargetedSegmentIds, candidateResult.segment_ids) &&
                      restoredTargetedSegmentsMatchReviewState &&
                      restoredTargetedSegmentsMatchTtsReplacement &&
                      restoredTargetedSegmentsMatchVisualOverlays &&
                      restoredTargetedSegmentsMatchBrollOverride &&
                      restoredTargetedSegmentsMatchMusicOverride &&
                      haveSameMembers(restoredPreflight.fields, candidateResult.fields)
                    ) {
                      resumedPartialRegenerationPreflight = restoredPreflight;
                    } else {
                      resumedPartialRegenerationPreflight = null;
                      resumedPartialRegenerationRestoreWarning =
                        "재개 범위 확인 · 검수 예측 없음";
                    }
                  } catch {
                    resumedPartialRegenerationPreflight = null;
                    resumedPartialRegenerationRestoreWarning =
                      "재개 범위 확인 · 검수 예측 없음";
                  }
                }
                activeTimeline = {
                  job_id: candidateResult.job_id,
                  status: candidateResult.status,
                  timeline: candidateResult.timeline,
                };
                activeReview = candidateReview;
                resumedPartialRegeneration = {
                  job_id: candidateResult.job_id,
                  status: candidateResult.status,
                  session_id: candidateResult.session_id,
                  segment_ids: candidateResult.segment_ids,
                  fields: candidateResult.fields,
                  downstream_steps: candidateResult.downstream_steps,
                  targeted_segments: [],
                  affected_output_areas: [],
                  delta: {
                    regenerated_segments: candidateResult.regenerated_segments,
                    timeline_id: candidateResult.timeline_id,
                  },
                };
                resumedSelection = canRepresentResumedScope
                  ? {
                      segmentId: candidateResult.segment_ids[0] ?? null,
                      fields: [...candidateResult.fields],
                    }
                  : null;
                activeSubtitle = null;
                activePreview = null;
                activeExport = null;
              }
            } catch {
              resumedPartialRegeneration = null;
              resumedPartialRegenerationRestoreWarning =
                "후보 복구 실패 · 기존 타임라인 유지";
            }
          }
        }
        if (cancelled) {
          return;
        }
        setProjectDetail(project);
        setJobs(jobItems);
        setTimelineJob(activeTimeline);
        setReviewSnapshot(activeReview);
        if (latestEditingSession) {
          applyEditingSessionState(latestEditingSession);
          if (resumedSelection) {
            setSelectedEditingSegmentId(resumedSelection.segmentId);
            setSelectedRegenerationFields(resumedSelection.fields);
          }
        } else {
          setEditingSession(null);
          setEditingDrafts({});
          setSelectedEditingSegmentId(null);
          setSelectedRegenerationFields([]);
        }
        setPartialRegenerationPreflight(resumedPartialRegenerationPreflight);
        setPartialRegenerationRun(resumedPartialRegeneration);
        setPartialRegenerationRestoreWarning(resumedPartialRegenerationRestoreWarning);
        setSubtitleJob(activeSubtitle);
        setPreviewJob(activePreview);
        setExportJob(activeExport);
        setBrollAssets(archivedBrollAssets);
        setLoadState("ready");
        try {
          const providerKeys = await api.listGeminiProviderKeys(projectId);
          if (cancelled) {
            return;
          }
          setGeminiKeys(providerKeys);
          setGeminiLoadError(null);
        } catch {
          if (cancelled) {
            return;
          }
          setGeminiKeys([]);
          setGeminiLoadError("제미나이 라우팅 오류");
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
        setLoadState("error");
      }
    }

    void loadProjectWorkspace();
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId || !selectedEditingSegmentId) {
      setTtsCandidates([]);
      return;
    }
    void loadTtsCandidates(selectedEditingSegmentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId, selectedEditingSegmentId]);

  const latestTimelineBuildJob = useMemo(
    () => findLatestTimelineJob(jobs),
    [jobs],
  );
  const activeTimelineJobId = timelineJob?.job_id ?? latestTimelineBuildJob?.job_id ?? null;

  const pipelineStages = useMemo(
    () => [
      { label: "전사", jobType: "transcription" },
      { label: "세그먼트", jobType: "segment_analysis" },
      { label: "B롤 추천", jobType: "broll_recommendation" },
      { label: "음악 추천", jobType: "music_recommendation" },
      { label: "타임라인", jobType: "timeline_build" },
      { label: "자막", jobType: "subtitle_render" },
      { label: "미리보기", jobType: "preview_render" },
      { label: "캡컷", jobType: "capcut_export" },
    ],
    [],
  );

  const stageStatus = useMemo(() => {
    return pipelineStages.map((stage) => {
      const matchingJobs = jobs.filter((job) => {
        if (job.job_type !== stage.jobType) {
          return false;
        }
        if (
          stage.jobType === "subtitle_render" ||
          stage.jobType === "preview_render" ||
          stage.jobType === "capcut_export"
        ) {
          return job.input_ref === activeTimelineJobId;
        }
        return true;
      });
      const stageJob =
        matchingJobs.length > 0 ? matchingJobs[matchingJobs.length - 1] : undefined;
      return {
        ...stage,
        status: stageJob?.status ?? "pending",
        jobId: stageJob?.job_id ?? "not-started",
      };
    });
  }, [activeTimelineJobId, jobs, pipelineStages]);

  const rebuildInputs = useMemo(() => {
    const segmentAnalysisJob = [...jobs]
      .reverse()
      .find((job) => job.job_type === "segment_analysis" && job.status === "succeeded");
    const recommendationJobIds = jobs
      .filter(
        (job) =>
          (job.job_type === "broll_recommendation" || job.job_type === "music_recommendation") &&
          job.status === "succeeded",
      )
      .map((job) => job.job_id);
    if (!segmentAnalysisJob || recommendationJobIds.length === 0) {
      return null;
    }
    return {
      segmentAnalysisJobId: segmentAnalysisJob.job_id,
      recommendationJobIds,
    };
  }, [jobs]);

  const reviewStatus = reviewSnapshot?.review_status ?? timelineJob?.timeline.review_status ?? "blocked";
  const hasReviewBlockers = useMemo(() => {
    if (!timelineJob || !reviewSnapshot) {
      return true;
    }
    return (
      timelineJob.timeline.review_flags.length > 0 ||
      reviewSnapshot.pending_recommendations.length > 0
    );
  }, [reviewSnapshot, timelineJob]);
  const canApproveTimeline = !!activeTimelineJobId && !hasReviewBlockers && reviewStatus !== "approved";
  const canReopenTimeline = !!activeTimelineJobId && reviewStatus === "approved";
  const canGenerateOutputs =
    !!activeTimelineJobId && !hasReviewBlockers && reviewStatus === "approved";
  const outputReadiness = useMemo(() => {
    const reviewFlagCount =
      reviewSnapshot?.review_flags.length ?? timelineJob?.timeline.review_flags.length ?? 0;
    const pendingRecommendationCount =
      reviewSnapshot?.pending_recommendations.length ??
      timelineJob?.timeline.pending_recommendations.length ??
      0;

    if (!timelineJob || !reviewSnapshot) {
      return {
        tone: "blocked",
        title: "준비 확인 불가",
        detail: "타임라인과 검수 데이터 필요",
        next: "다음: 타임라인 생성",
        reviewFlagCount,
        pendingRecommendationCount,
      };
    }

    if (hasReviewBlockers) {
      return {
        tone: "blocked",
        title: "내보내기 보류",
        detail: `검수 표시 ${reviewFlagCount} · 대기 추천 ${pendingRecommendationCount}`,
        next: "다음: 검수 탭에서 보류 항목 처리",
        reviewFlagCount,
        pendingRecommendationCount,
      };
    }

    if (reviewStatus !== "approved") {
      return {
        tone: "pending",
        title: "승인 필요",
        detail: "보류 항목 없음",
        next: "다음: 타임라인 승인",
        reviewFlagCount,
        pendingRecommendationCount,
      };
    }

    return {
      tone: "ready",
      title: "내보내기 가능",
      detail: "검수 승인 완료",
      next: "다음: 미리보기 또는 캡컷 내보내기",
      reviewFlagCount,
      pendingRecommendationCount,
    };
  }, [hasReviewBlockers, reviewSnapshot, reviewStatus, timelineJob]);
  const actionablePendingRecommendation =
    reviewSnapshot?.pending_recommendations.length === 1
      ? reviewSnapshot.pending_recommendations[0]
      : null;

  function applyEditingSessionState(session: EditingSession) {
    setEditingSession(session);
    setEditingDrafts(buildEditingDrafts(session));
    const selection = buildDefaultEditingSelection(session);
    setSelectedEditingSegmentId((current) => current ?? selection.segmentId);
    setSelectedRegenerationFields((current) =>
      current.length > 0 ? current : selection.fields,
    );
  }

  function updateEditingDraft(
    segmentId: string,
    patch: Partial<EditingSegmentDraft>,
  ) {
    setEditingDrafts((current) => ({
      ...current,
      [segmentId]: {
        ...current[segmentId],
        ...patch,
      },
    }));
  }

  async function applyEditingMutation(
    mutationKey: string,
    action: () => Promise<EditingSession>,
    options?: {
      addRegenerationField?: string;
      feedbackAction?: "저장" | "해제" | "삭제";
      removeRegenerationField?: string;
    },
  ) {
    const feedbackLabel = formatEditingMutationFeedbackLabel(mutationKey);
    const feedbackAction = options?.feedbackAction ?? "저장";
    setIsSavingEditingMutation(mutationKey);
    setErrorMessage(null);
    setEditingMutationFeedback(null);
    try {
      const session = await action();
      applyEditingSessionState(session);
      if (options?.addRegenerationField) {
        setSelectedRegenerationFields((current) =>
          current.includes(options.addRegenerationField!)
            ? current
            : [...current, options.addRegenerationField!],
        );
      }
      if (options?.removeRegenerationField) {
        setSelectedRegenerationFields((current) =>
          current.filter((item) => item !== options.removeRegenerationField),
        );
      }
      setPartialRegenerationPreflight(null);
      setPartialRegenerationRun(null);
      setTimelineJob(null);
      setReviewSnapshot(null);
      setSubtitleJob(null);
      setPreviewJob(null);
      setExportJob(null);
      setEditingMutationFeedback({
        kind: "success",
        message: `${feedbackLabel} ${feedbackAction}됨`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "알 수 없는 오류";
      setErrorMessage(message);
      setEditingMutationFeedback({
        kind: "error",
        message: `${feedbackLabel} ${feedbackAction} 실패 · ${message}`,
      });
    } finally {
      setIsSavingEditingMutation(null);
    }
  }

  async function handleStartEditingSession() {
    if (!selectedProjectId || !latestTimelineBuildJob) {
      return;
    }
    setIsStartingEditingSession(true);
    setErrorMessage(null);
    setEditingSessionRestoreError(null);
    setPartialRegenerationRestoreWarning(null);
    try {
      const session = await api.createEditingSession(selectedProjectId, {
        timeline_job_id: latestTimelineBuildJob.job_id,
      });
      applyEditingSessionState(session);
      setPartialRegenerationPreflight(null);
      setPartialRegenerationRun(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsStartingEditingSession(false);
    }
  }

  async function handleRequestRegenerationPreflight() {
    if (
      !selectedProjectId ||
      !editingSession ||
      isSavingEditingMutation ||
      !selectedEditingSegmentId ||
      selectedRegenerationFields.length === 0
    ) {
      return;
    }
    setIsRequestingRegenerationPreflight(true);
    setErrorMessage(null);
    setPartialRegenerationRestoreWarning(null);
    setPartialRegenerationPreflight(null);
    try {
      const preflight = await api.previewPartialRegeneration(
        selectedProjectId,
        editingSession.session_id,
        {
          segment_ids: [selectedEditingSegmentId],
          fields: selectedRegenerationFields,
        },
      );
      setPartialRegenerationPreflight(preflight);
      setPartialRegenerationRun(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsRequestingRegenerationPreflight(false);
    }
  }

  async function handleRunPartialRegeneration() {
    if (
      !selectedProjectId ||
      !editingSession ||
      isSavingEditingMutation ||
      !selectedEditingSegmentId ||
      selectedRegenerationFields.length === 0 ||
      !hasFreshMatchingPreflight ||
      isRequestingRegenerationPreflight
    ) {
      return;
    }
    setIsRunningPartialRegeneration(true);
    setErrorMessage(null);
    setPartialRegenerationRestoreWarning(null);
    try {
      const result = await api.runPartialRegeneration(
        selectedProjectId,
        editingSession.session_id,
        {
          segment_ids: [selectedEditingSegmentId],
          fields: selectedRegenerationFields,
        },
      );
      setPartialRegenerationPreflight(null);
      setPartialRegenerationRun(result);
      setSubtitleJob(null);
      setPreviewJob(null);
      setExportJob(null);
      setReviewSnapshot(null);
      const [jobItems, refreshedSession] = await Promise.all([
        api.listJobs(selectedProjectId),
        api.getEditingSession(selectedProjectId, editingSession.session_id),
      ]);
      setJobs(jobItems);
      applyEditingSessionState(refreshedSession);
      if (result.job_id) {
        const [jobResult, review] = await Promise.all([
          api.getPartialRegenerationResult(selectedProjectId, result.job_id),
          api.getReviewSnapshot(selectedProjectId, result.job_id),
        ]);
        setTimelineJob({
          job_id: jobResult.job_id,
          status: jobResult.status,
          timeline: jobResult.timeline,
        });
        setReviewSnapshot(review);
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsRunningPartialRegeneration(false);
    }
  }

  async function handleRebuildTimeline() {
    if (!selectedProjectId || !rebuildInputs) {
      return;
    }
    setIsRebuildingTimeline(true);
    setErrorMessage(null);
    try {
      const buildResult = await api.buildTimeline(selectedProjectId, {
        segment_analysis_job_id: rebuildInputs.segmentAnalysisJobId,
        recommendation_job_ids: rebuildInputs.recommendationJobIds,
      });
      const [jobItems, timeline, review] = await Promise.all([
        api.listJobs(selectedProjectId),
        api.getTimeline(selectedProjectId, buildResult.job_id),
        api.getReviewSnapshot(selectedProjectId, buildResult.job_id),
      ]);
      setJobs(jobItems);
      setTimelineJob(timeline);
      setReviewSnapshot(review);
      setEditingSession(null);
      setEditingDrafts({});
      setSelectedEditingSegmentId(null);
      setSelectedRegenerationFields([]);
      setPartialRegenerationPreflight(null);
      setPartialRegenerationRun(null);
      setSubtitleJob(null);
      setPreviewJob(null);
      setExportJob(null);
      setSelectedSection("timeline");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsRebuildingTimeline(false);
    }
  }

  async function handleRenderPreview() {
    if (!selectedProjectId || !activeTimelineJobId || !canGenerateOutputs) {
      return;
    }
    setIsRenderingPreview(true);
    setErrorMessage(null);
    try {
      const renderResult = await api.renderPreview(selectedProjectId, {
        timeline_job_id: activeTimelineJobId,
      });
      const [jobItems, preview] = await Promise.all([
        api.listJobs(selectedProjectId),
        api.getPreview(selectedProjectId, renderResult.job_id),
      ]);
      setJobs(jobItems);
      setPreviewJob(preview);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsRenderingPreview(false);
    }
  }

  async function handleExportCapcut() {
    if (!selectedProjectId || !activeTimelineJobId || !canGenerateOutputs) {
      return;
    }
    setIsExportingCapcut(true);
    setErrorMessage(null);
    try {
      const exportResult = await api.exportCapcut(selectedProjectId, {
        timeline_job_id: activeTimelineJobId,
      });
      const [jobItems, capcutExport] = await Promise.all([
        api.listJobs(selectedProjectId),
        api.getExport(selectedProjectId, exportResult.job_id),
      ]);
      setJobs(jobItems);
      setExportJob(capcutExport);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsExportingCapcut(false);
    }
  }

  async function pollUntilJobFinished<T extends { status: string }>(
    fetchResult: () => Promise<T>,
    options?: { intervalMs?: number; timeoutMs?: number; jobId?: string; onProgress?: (percent: number | null) => void },
  ): Promise<T> {
    const intervalMs = options?.intervalMs ?? 1000;
    const timeoutMs = options?.timeoutMs ?? 60 * 60 * 1000;
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const result = await fetchResult();
      if (options?.jobId && options.onProgress && selectedProjectId) {
        try {
          const jobItems = await api.listJobs(selectedProjectId);
          const matchingJob = jobItems.find((job) => job.job_id === options.jobId);
          options.onProgress(matchingJob?.progress_percent ?? null);
        } catch {
          // Progress is a display nicety; ignore transient lookup failures.
        }
      }
      if (result.status === "succeeded" || result.status === "failed") {
        return result;
      }
      if (Date.now() > deadline) {
        throw new Error("작업이 시간 내에 끝나지 않았습니다");
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  }

  async function handleFinalRender() {
    if (!selectedProjectId || !activeTimelineJobId || !canGenerateOutputs) {
      return;
    }
    setIsRenderingFinal(true);
    setFinalRenderProgress(null);
    setErrorMessage(null);
    try {
      const renderResult = await api.startFinalRender(selectedProjectId, {
        timeline_job_id: activeTimelineJobId,
      });
      const finalRender = await pollUntilJobFinished(
        () => api.getFinalRender(selectedProjectId, renderResult.job_id),
        { jobId: renderResult.job_id, onProgress: setFinalRenderProgress },
      );
      const jobItems = await api.listJobs(selectedProjectId);
      setJobs(jobItems);
      setFinalRenderJob(finalRender);
      if (finalRender.status === "failed") {
        setErrorMessage(`완성본 렌더 실패: ${finalRender.error_message ?? "결과 파일을 만들지 못했습니다."}`);
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsRenderingFinal(false);
      setFinalRenderProgress(null);
    }
  }

  async function handleCapcutDraftExport() {
    if (!selectedProjectId || !activeTimelineJobId || !canGenerateOutputs) {
      return;
    }
    setIsExportingCapcutDraft(true);
    setErrorMessage(null);
    try {
      const exportResult = await api.startCapcutDraftExport(selectedProjectId, {
        timeline_job_id: activeTimelineJobId,
      });
      const capcutDraftExport = await pollUntilJobFinished(() =>
        api.getCapcutDraftExport(selectedProjectId, exportResult.job_id),
      );
      const jobItems = await api.listJobs(selectedProjectId);
      setJobs(jobItems);
      setCapcutDraftJob(capcutDraftExport);
      if (capcutDraftExport.status === "failed") {
        setErrorMessage(
          `CapCut 초안 내보내기 실패: ${capcutDraftExport.error_message ?? "결과 파일을 만들지 못했습니다."}`,
        );
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsExportingCapcutDraft(false);
    }
  }

  async function handleRetryJob(jobId: string) {
    if (!selectedProjectId) {
      return;
    }
    setRetryingJobId(jobId);
    setErrorMessage(null);
    try {
      await api.retryJob(selectedProjectId, jobId);
      const jobItems = await api.listJobs(selectedProjectId);
      setJobs(jobItems);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setRetryingJobId(null);
    }
  }

  async function handleToggleAllJobsPanel() {
    const nextIsOpen = !isAllJobsPanelOpen;
    setIsAllJobsPanelOpen(nextIsOpen);
    if (!nextIsOpen) {
      return;
    }
    setIsLoadingAllJobs(true);
    setAllJobsError(null);
    try {
      const jobItems = await api.listAllJobs();
      setAllJobs(jobItems);
    } catch (error) {
      setAllJobsError(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsLoadingAllJobs(false);
    }
  }

  async function handleRegisterVoiceSample() {
    if (!selectedProjectId || !voiceSamplePath.trim()) {
      return;
    }
    setIsRegisteringVoiceSample(true);
    setVoiceSampleError(null);
    setVoiceSampleMessage(null);
    try {
      const asset = await api.registerVoiceSample(selectedProjectId, {
        source_path: voiceSamplePath.trim(),
      });
      setVoiceSampleAssetId(asset.asset_id);
      setTtsCandidateVoiceSampleId(asset.asset_id);
      setVoiceSampleMessage(`등록됨 · ${asset.asset_id}`);
    } catch (error) {
      setVoiceSampleError(
        error instanceof Error ? `음성 샘플 등록 실패 · ${error.message}` : "음성 샘플 등록 실패",
      );
    } finally {
      setIsRegisteringVoiceSample(false);
    }
  }

  async function loadTtsCandidates(segmentId: string) {
    if (!selectedProjectId) {
      return;
    }
    setIsLoadingTtsCandidates(true);
    try {
      const result = await api.listTtsCandidates(selectedProjectId, segmentId);
      setTtsCandidates(result.candidates);
    } catch (error) {
      setTtsCandidateError(
        error instanceof Error ? `TTS 후보 목록 조회 실패 · ${error.message}` : "TTS 후보 목록 조회 실패",
      );
    } finally {
      setIsLoadingTtsCandidates(false);
    }
  }

  async function handleGenerateTtsCandidate(segmentId: string, segmentText: string) {
    if (!selectedProjectId || !ttsCandidateVoiceSampleId.trim() || !segmentText.trim()) {
      return;
    }
    setIsGeneratingTtsCandidate(true);
    setTtsCandidateError(null);
    setTtsCandidateMessage(null);
    try {
      const asset = await api.generateTtsCandidate(selectedProjectId, {
        segment_text: segmentText,
        voice_sample_asset_id: ttsCandidateVoiceSampleId.trim(),
        segment_id: segmentId,
      });
      updateEditingDraft(segmentId, { ttsAssetId: asset.asset_id });
      setTtsCandidateMessage(`생성됨 · ${asset.asset_id} (TTS 자산 ID에 채워짐)`);
      await loadTtsCandidates(segmentId);
    } catch (error) {
      setTtsCandidateError(
        error instanceof Error ? `TTS 후보 생성 실패 · ${error.message}` : "TTS 후보 생성 실패",
      );
    } finally {
      setIsGeneratingTtsCandidate(false);
    }
  }

  async function handleApproveTimeline() {
    if (!selectedProjectId || !activeTimelineJobId || !canApproveTimeline) {
      return;
    }
    setIsApprovingTimeline(true);
    setErrorMessage(null);
    setPartialRegenerationRestoreWarning(null);
    try {
      await api.approveTimeline(selectedProjectId, activeTimelineJobId);
      const [timeline, review] = await Promise.all([
        api.getTimeline(selectedProjectId, activeTimelineJobId),
        api.getReviewSnapshot(selectedProjectId, activeTimelineJobId),
      ]);
      setTimelineJob(timeline);
      setReviewSnapshot(review);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsApprovingTimeline(false);
    }
  }

  async function handleApproveRecommendation() {
    if (
      !selectedProjectId ||
      !activeTimelineJobId ||
      !actionablePendingRecommendation
    ) {
      return;
    }
    setErrorMessage(null);
    setPartialRegenerationRestoreWarning(null);
    try {
      const [review, timeline] = await Promise.all([
        api.approveReviewRecommendation(
          selectedProjectId,
          activeTimelineJobId,
          actionablePendingRecommendation.recommendation_id,
        ),
        api.getTimeline(selectedProjectId, activeTimelineJobId),
      ]);
      setReviewSnapshot(review);
      setTimelineJob(timeline);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    }
  }

  function handleMarkRecommendationForManualEdit() {
    if (!actionablePendingRecommendation) {
      return;
    }
    const mappedField = mapRecommendationTypeToEditingField(
      actionablePendingRecommendation.recommendation_type,
    );
    openSegmentInEditor(
      actionablePendingRecommendation.target_segment_id,
      mappedField ? [mappedField] : undefined,
    );
  }

  async function handleReopenTimeline() {
    if (!selectedProjectId || !activeTimelineJobId || !canReopenTimeline) {
      return;
    }
    setIsReopeningTimeline(true);
    setErrorMessage(null);
    setPartialRegenerationRestoreWarning(null);
    try {
      await api.reopenTimeline(selectedProjectId, activeTimelineJobId);
      const [timeline, review, jobItems] = await Promise.all([
        api.getTimeline(selectedProjectId, activeTimelineJobId),
        api.getReviewSnapshot(selectedProjectId, activeTimelineJobId),
        api.listJobs(selectedProjectId),
      ]);
      setTimelineJob(timeline);
      setReviewSnapshot(review);
      setJobs(jobItems);
      setEditingSession(null);
      setEditingDrafts({});
      setSelectedEditingSegmentId(null);
      setSelectedRegenerationFields([]);
      setPartialRegenerationPreflight(null);
      setPartialRegenerationRun(null);
      setSubtitleJob(null);
      setPreviewJob(null);
      setExportJob(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsReopeningTimeline(false);
    }
  }

  async function handleRenderSubtitle() {
    if (!selectedProjectId || !activeTimelineJobId || !canGenerateOutputs) {
      return;
    }
    setIsRenderingSubtitle(true);
    setErrorMessage(null);
    try {
      const subtitleResult = await api.renderSubtitle(selectedProjectId, {
        timeline_job_id: activeTimelineJobId,
      });
      const [jobItems, subtitle] = await Promise.all([
        api.listJobs(selectedProjectId),
        api.getSubtitle(selectedProjectId, subtitleResult.job_id),
      ]);
      setJobs(jobItems);
      setSubtitleJob(subtitle);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsRenderingSubtitle(false);
    }
  }

  async function refreshGeminiKeys(projectId: string) {
    const providerKeys = await api.listGeminiProviderKeys(projectId);
    setGeminiKeys(providerKeys);
    setGeminiLoadError(null);
  }

  async function refreshBrollAssets(projectId: string) {
    const assets = await api.listBrollAssets(projectId);
    setBrollAssets(assets);
    setBrollAssetLoadError(null);
  }

  async function handleImportBrollBatch() {
    if (!selectedProjectId) {
      return;
    }
    const sourceDirectory = brollFolderPath.trim();
    const sourcePaths = brollSourcePaths
      .split(/\r?\n/)
      .map((path) => path.trim())
      .filter(Boolean);
    if (!sourceDirectory && sourcePaths.length === 0) {
      setBrollImportError("B롤 가져오기 실패 · 경로 필요");
      setBrollImportMessage(null);
      return;
    }
    setIsImportingBroll(true);
    setBrollImportError(null);
    setBrollImportMessage(null);
    try {
      await api.importBrollBatch(selectedProjectId, {
        source_directory: sourceDirectory || undefined,
        source_paths: sourcePaths,
        tags: brollImportTags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      });
      const beforeCount = brollAssets.length;
      const assets = await api.listBrollAssets(selectedProjectId);
      setBrollAssets(assets);
      setBrollAssetLoadError(null);
      const importedCount = Math.max(assets.length - beforeCount, 0);
      setBrollImportMessage(
        importedCount > 0 ? `가져옴 ${importedCount}개` : `보관함 ${assets.length}개`,
      );
    } catch (error) {
      setBrollImportError(
        error instanceof Error ? `B롤 가져오기 실패 · ${error.message}` : "B롤 가져오기 실패",
      );
      setBrollImportMessage(null);
    } finally {
      setIsImportingBroll(false);
    }
  }

  function openCreateGeminiForm() {
    setEditingGeminiKeyId(null);
    setGeminiForm(createEmptyGeminiKeyForm());
    setIsGeminiFormOpen(true);
  }

  function openEditGeminiForm(key: GeminiProviderKey) {
    setEditingGeminiKeyId(key.key_id);
    setGeminiForm({
      label: key.label,
      apiKey: "",
      primaryModel: key.primary_model,
      cheapModel: key.cheap_model,
      highQualityModel: key.high_quality_model,
    });
    setIsGeminiFormOpen(true);
  }

  function closeGeminiForm() {
    setIsGeminiFormOpen(false);
    setEditingGeminiKeyId(null);
    setGeminiForm(createEmptyGeminiKeyForm());
  }

  async function handleSaveGeminiKey() {
    if (!selectedProjectId) {
      return;
    }
    setIsSavingGeminiKey(true);
    setErrorMessage(null);
    try {
      if (editingGeminiKeyId) {
        await api.updateGeminiProviderKey(selectedProjectId, editingGeminiKeyId, {
          label: geminiForm.label,
          primary_model: geminiForm.primaryModel,
          cheap_model: geminiForm.cheapModel,
          high_quality_model: geminiForm.highQualityModel,
        });
      } else {
        await api.createGeminiProviderKey(selectedProjectId, {
          label: geminiForm.label,
          api_key: geminiForm.apiKey,
          primary_model: geminiForm.primaryModel,
          cheap_model: geminiForm.cheapModel,
          high_quality_model: geminiForm.highQualityModel,
        });
      }
      await refreshGeminiKeys(selectedProjectId);
      closeGeminiForm();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsSavingGeminiKey(false);
    }
  }

  async function handleToggleGeminiKey(key: GeminiProviderKey) {
    if (!selectedProjectId) {
      return;
    }
    setTogglingGeminiKeyId(key.key_id);
    setErrorMessage(null);
    try {
      if (key.status === "disabled") {
        await api.enableGeminiProviderKey(selectedProjectId, key.key_id);
      } else {
        await api.disableGeminiProviderKey(selectedProjectId, key.key_id);
      }
      await refreshGeminiKeys(selectedProjectId);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setTogglingGeminiKeyId(null);
    }
  }

  const selectedEditingSegment =
    editingSession?.segments.find((segment) => segment.segment_id === selectedEditingSegmentId) ?? null;
  const selectedEditingDraft = selectedEditingSegmentId
    ? editingDrafts[selectedEditingSegmentId]
    : undefined;
  const selectedBrollAsset = selectedEditingDraft?.brollAssetId
    ? brollAssets.find((asset) => asset.asset_id === selectedEditingDraft.brollAssetId)
    : undefined;
  const filteredBrollAssets = useMemo(() => {
    const query = brollAssetFilter.trim().toLowerCase();
    if (!query) {
      return brollAssets;
    }
    return brollAssets.filter((asset) => formatBrollAssetLabel(asset).toLowerCase().includes(query));
  }, [brollAssetFilter, brollAssets]);
  const selectableBrollAssets = useMemo(() => {
    if (
      selectedBrollAsset &&
      !filteredBrollAssets.some((asset) => asset.asset_id === selectedBrollAsset.asset_id)
    ) {
      return [selectedBrollAsset, ...filteredBrollAssets];
    }
    return filteredBrollAssets;
  }, [filteredBrollAssets, selectedBrollAsset]);
  const activeEditingSessionId = editingSession?.session_id ?? null;
  const changedSegmentIds = useMemo(
    () =>
      new Set(
        (partialRegenerationRun?.delta?.regenerated_segments ?? [])
          .map((segment) => String(segment.segment_id ?? ""))
          .filter(Boolean),
      ),
    [partialRegenerationRun],
  );
  const preservedEditingSegments = useMemo(
    () =>
      (editingSession?.segments ?? []).filter((segment) => !changedSegmentIds.has(segment.segment_id)),
    [changedSegmentIds, editingSession],
  );
  const changedEditingSegments = useMemo(
    () => (editingSession?.segments ?? []).filter((segment) => changedSegmentIds.has(segment.segment_id)),
    [changedSegmentIds, editingSession],
  );
  const readyChangedSegments = useMemo(
    () => changedEditingSegments.filter((segment) => !segment.review_required),
    [changedEditingSegments],
  );
  const changedSegmentsNeedingReview = useMemo(
    () => changedEditingSegments.filter((segment) => segment.review_required),
    [changedEditingSegments],
  );
  const changedOutputChecklist = useMemo(
    () =>
      (partialRegenerationRun?.delta?.regenerated_segments ?? []).flatMap((segment) =>
        Array.isArray(segment.output_changes)
          ? (segment.output_changes as unknown[]).map((change) => String(change))
          : [],
      ),
    [partialRegenerationRun],
  );
  const changedCandidateReviewFlags = useMemo(
    () =>
      (timelineJob?.timeline.review_flags ?? []).filter((flag) =>
        changedSegmentIds.has(String(flag.segment_id ?? "")),
      ),
    [changedSegmentIds, timelineJob],
  );
  const changedCandidatePendingRecommendations = useMemo(
    () =>
      (timelineJob?.timeline.pending_recommendations ?? []).filter((item) =>
        changedSegmentIds.has(String(item.target_segment_id ?? "")),
      ),
    [changedSegmentIds, timelineJob],
  );
  const decisionBlockerSegmentIds = useMemo(
    () =>
      new Set([
        ...changedSegmentsNeedingReview.map((segment) => segment.segment_id),
        ...changedCandidateReviewFlags.map((flag) => String(flag.segment_id ?? "")),
        ...changedCandidatePendingRecommendations.map((item) =>
          String(item.target_segment_id ?? ""),
        ),
      ].filter(Boolean)),
    [
      changedCandidatePendingRecommendations,
      changedCandidateReviewFlags,
      changedSegmentsNeedingReview,
    ],
  );
  const decisionBlockerCount = decisionBlockerSegmentIds.size;
  const resumedScopeSegmentIds = partialRegenerationRun?.segment_ids ?? [];
  const resumedScopeFields = partialRegenerationRun?.fields ?? [];
  const hasFreshMatchingPreflight =
    !!editingSession &&
    !!selectedEditingSegmentId &&
    !!partialRegenerationPreflight &&
    partialRegenerationPreflight.session_id === editingSession.session_id &&
    haveSameMembers(partialRegenerationPreflight.segment_ids, [selectedEditingSegmentId]) &&
    haveSameMembers(partialRegenerationPreflight.fields, selectedRegenerationFields);
  const decisionCue = !partialRegenerationRun
    ? null
    : decisionBlockerCount > 0
      ? {
          title: "출력 보류",
          body: "재생성 권장",
        }
      : canApproveTimeline
        ? {
          title: "승인 가능",
          body: "변경 출력 준비",
        }
        : {
            title: "출력 보류",
            body: "검수 상태 없음",
          };
  const handleSelectEditingSegment = (segmentId: string) => {
    setSelectedEditingSegmentId(segmentId);
    const nextSegment =
      editingSession?.segments.find((segment) => segment.segment_id === segmentId) ?? null;
    setSelectedRegenerationFields(buildDefaultRegenerationFields(nextSegment));
    setPartialRegenerationRestoreWarning(null);
    setPartialRegenerationPreflight(null);
    setPartialRegenerationRun(null);
  };
  const openSegmentInEditor = (segmentId: string, fields?: string[]) => {
    setSelectedSection("editing");
    setSelectedEditingSegmentId(segmentId);
    if (fields) {
      setSelectedRegenerationFields(fields);
    } else {
      const nextSegment =
        editingSession?.segments.find((segment) => segment.segment_id === segmentId) ?? null;
      setSelectedRegenerationFields(buildDefaultRegenerationFields(nextSegment));
    }
    setPartialRegenerationRestoreWarning(null);
    setPartialRegenerationPreflight(null);
    setPartialRegenerationRun(null);
  };
  const regenerationFieldOptions = [
    "caption",
    "cut_action",
    "broll",
    "music",
    "visual_overlay",
    "explanation_card",
    "image_overlay",
    "table_overlay",
    "tts_replacement",
  ] as const;

  function handleProjectCreated(project: Project) {
    setProjects((current) => [project, ...current.filter((item) => item.project_id !== project.project_id)]);
    setSelectedProjectId(project.project_id);
    setLoadState("ready");
  }

  return (
    <div className="shell">
      <aside className="sidebar" aria-label="프로젝트 탐색">
        <div className="brand-card">
          <p className="eyebrow">로컬 검수</p>
          <h1>VideoBox 작업판</h1>
          <p className="lede">프로젝트 · 타임라인 · 검수 · 출력</p>
        </div>

        {projects.length === 0 && loadState === "ready" ? (
          <ProjectOnboarding onProjectCreated={handleProjectCreated} />
        ) : null}

        <section className="sidebar-section" aria-labelledby="projects-heading">
          <div className="sidebar-header">
            <p className="section-kicker">프로젝트</p>
            <h2 id="projects-heading">목록</h2>
          </div>
          <div className="project-list">
            {projects.map((project) => (
              <button
                key={project.project_id}
                className={`project-chip ${
                  project.project_id === selectedProjectId ? "is-selected" : ""
                }`}
                onClick={() => setSelectedProjectId(project.project_id)}
                type="button"
              >
                <strong>{formatDisplayText(project.name)}</strong>
                <span>{formatStatusLabel(project.status)}</span>
              </button>
            ))}
            {projects.length === 0 && loadState === "ready" ? (
              <p className="empty-state">로컬 프로젝트 없음</p>
            ) : null}
          </div>
        </section>

        <section className="sidebar-section" aria-labelledby="all-jobs-heading">
          <div className="sidebar-header">
            <p className="section-kicker">전체 프로젝트</p>
            <h2 id="all-jobs-heading">job 현황</h2>
          </div>
          <button className="action-button" onClick={() => void handleToggleAllJobsPanel()} type="button">
            {isAllJobsPanelOpen ? "전체 job 현황 닫기" : "전체 job 현황 보기"}
          </button>
          {isAllJobsPanelOpen ? (
            <div className="all-jobs-list">
              {isLoadingAllJobs ? <p className="meta-copy">불러오는 중...</p> : null}
              {allJobsError ? <p className="error-banner">{allJobsError}</p> : null}
              {!isLoadingAllJobs && allJobs.length === 0 ? (
                <p className="empty-state">등록된 job 없음</p>
              ) : null}
              {allJobs.map((job) => (
                <div className="all-jobs-row" key={job.job_id}>
                  <strong>{formatDisplayText(job.project_name)}</strong>
                  <span>{prettifyJobType(job.job_type)}</span>
                  <span className={job.status === "failed" ? "pill warning" : "pill okay"}>
                    {formatStatusLabel(job.status)}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      </aside>

      <main className="content">
        <section className="hero-card" aria-labelledby="detail-heading">
          <div>
            <p className="section-kicker">프로젝트</p>
            <h2 id="detail-heading">{formatDisplayText(projectDetail?.name) || "프로젝트 선택"}</h2>
            <p className="meta-copy">
              {projectDetail?.root_storage_uri ??
                "작업 · 타임라인 · 검수"}
            </p>
          </div>
          <nav className="section-tabs" aria-label="작업 영역">
            {[
              ["overview", "개요"],
              ["timeline", "타임라인"],
              ["review", "검수"],
              ["editing", "편집"],
              ["settings", "설정"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={selectedSection === value ? "tab-button is-active" : "tab-button"}
                onClick={() =>
                  setSelectedSection(
                    value as "overview" | "timeline" | "review" | "editing" | "settings",
                  )
                }
                type="button"
              >
                {label}
              </button>
            ))}
          </nav>
          <div className="hero-actions">
            <button
              className="action-button primary"
              disabled={!rebuildInputs || isRebuildingTimeline}
              onClick={() => void handleRebuildTimeline()}
              type="button"
            >
              {isRebuildingTimeline ? "타임라인 생성 중" : "타임라인 재생성"}
            </button>
            <button
              className="action-button"
              disabled={!canGenerateOutputs || isRenderingSubtitle}
              onClick={() => void handleRenderSubtitle()}
              type="button"
            >
              {isRenderingSubtitle ? "자막 생성 중" : "자막 생성"}
            </button>
            <button
              className="action-button"
              disabled={!canGenerateOutputs || isRenderingPreview}
              onClick={() => void handleRenderPreview()}
              type="button"
            >
              {isRenderingPreview ? "미리보기 생성 중" : "미리보기 생성"}
            </button>
            <button
              className="action-button"
              disabled={!canGenerateOutputs || isExportingCapcut}
              onClick={() => void handleExportCapcut()}
              type="button"
            >
              {isExportingCapcut ? "캡컷 내보내는 중" : "캡컷 내보내기"}
            </button>
            <button
              className="action-button"
              disabled={!canGenerateOutputs || isRenderingFinal}
              onClick={() => void handleFinalRender()}
              type="button"
            >
              {isRenderingFinal ? "완성본 렌더 중" : "완성본 렌더"}
            </button>
            <button
              className="action-button"
              disabled={!canGenerateOutputs || isExportingCapcutDraft}
              onClick={() => void handleCapcutDraftExport()}
              type="button"
            >
              {isExportingCapcutDraft ? "CapCut 초안 내보내는 중" : "CapCut 초안(실제)"}
            </button>
            {finalRenderJob?.status === "failed" ? (
              <button
                className="action-button subtle"
                disabled={!canGenerateOutputs || isRenderingFinal}
                onClick={() => void handleFinalRender()}
                type="button"
              >
                완성본 렌더 다시 시도
              </button>
            ) : null}
            {capcutDraftJob?.status === "failed" ? (
              <button
                className="action-button subtle"
                disabled={!canGenerateOutputs || isExportingCapcutDraft}
                onClick={() => void handleCapcutDraftExport()}
                type="button"
              >
                CapCut 초안 다시 시도
              </button>
            ) : null}
            <button
              className={canApproveTimeline ? "action-button success" : "action-button"}
              disabled={!canApproveTimeline || isApprovingTimeline}
              onClick={() => void handleApproveTimeline()}
              type="button"
            >
              {isApprovingTimeline ? "승인 중" : "타임라인 승인"}
            </button>
          </div>
          {isRenderingFinal ? (
            <div className="render-progress">
              <progress max={100} value={finalRenderProgress ?? undefined} />
              <span>
                {finalRenderProgress === null ? "렌더링 시작 중..." : `완성본 렌더 ${finalRenderProgress}%`}
              </span>
            </div>
          ) : null}
          <div className="hero-actions-secondary">
            <button
              className="action-button subtle"
              disabled={!canReopenTimeline || isReopeningTimeline}
              onClick={() => void handleReopenTimeline()}
              type="button"
            >
              {isReopeningTimeline ? "검수 재개 중" : "검수 재개"}
            </button>
          </div>
        </section>

        <div className={`readiness-banner readiness-hero readiness-${outputReadiness.tone}`}>
          <span className="pill">{outputReadiness.title}</span>
          <strong>{outputReadiness.next}</strong>
          <p>{outputReadiness.detail}</p>
        </div>

        {loadState === "loading" ? <p className="loading-banner">로컬 작업 로딩</p> : null}
        {loadState === "error" ? <p className="error-banner">{errorMessage}</p> : null}

        <section className="panel" aria-labelledby="status-heading">
          <div className="panel-header">
            <div>
              <p className="section-kicker">파이프라인</p>
              <h2 id="status-heading">진행</h2>
            </div>
          </div>
          <div className="pipeline-stepper">
            {stageStatus.map((stage, index) => (
              <Fragment key={stage.jobType}>
                <article
                  className={
                    stage.status === "succeeded"
                      ? "stepper-step is-done"
                      : stage.status === "running"
                        ? "stepper-step is-running"
                        : "stepper-step"
                  }
                >
                  <span className="stepper-dot" aria-hidden="true" />
                  <span className="stepper-label">{stage.label}</span>
                  <span className="stepper-status">{formatStatusLabel(stage.status)}</span>
                </article>
                {index < stageStatus.length - 1 ? (
                  <span className="stepper-connector" aria-hidden="true" />
                ) : null}
              </Fragment>
            ))}
          </div>
          <details className="stage-detail-toggle">
            <summary>단계별 job ID 보기</summary>
            <div className="stage-detail-list">
              {stageStatus.map((stage) => (
                <span key={stage.jobType}>
                  <strong>{`${stage.label}:`}</strong>
                  <span>{formatStatusLabel(stage.status)}</span>
                  <span>{formatJobValue(stage.jobId)}</span>
                  {stage.status === "failed" ? (
                    <button
                      type="button"
                      onClick={() => handleRetryJob(stage.jobId)}
                      disabled={retryingJobId === stage.jobId}
                    >
                      {retryingJobId === stage.jobId ? "재시도 중..." : "재시도"}
                    </button>
                  ) : null}
                </span>
              ))}
            </div>
          </details>
        </section>

        {selectedSection === "overview" ? (
          <section className="workspace-grid">
            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">최근</p>
                  <h2>타임라인</h2>
                </div>
              </div>
              {timelineJob ? (
                <dl className="summary-list">
                  <div>
                    <dt>타임라인 ID</dt>
                    <dd>{timelineJob.timeline.timeline_id}</dd>
                  </div>
                  <div>
                    <dt>출력 모드</dt>
                    <dd>{formatStatusLabel(timelineJob.timeline.output_mode)}</dd>
                  </div>
                  <div>
                    <dt>트랙 수</dt>
                    <dd>{timelineJob.timeline.tracks.length}</dd>
                  </div>
                </dl>
              ) : (
                <p className="empty-state">타임라인 없음</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">검수</p>
                  <h2>스냅샷</h2>
                </div>
              </div>
              {reviewSnapshot ? (
                <dl className="summary-list">
                  <div>
                    <dt>세그먼트</dt>
                    <dd>{reviewSnapshot.segments.length}</dd>
                  </div>
                  <div>
                    <dt>적용</dt>
                    <dd>{reviewSnapshot.applied_recommendations.length}</dd>
                  </div>
                  <div>
                    <dt>대기</dt>
                    <dd>{reviewSnapshot.pending_recommendations.length}</dd>
                  </div>
                  <div>
                    <dt>표시</dt>
                    <dd>{reviewSnapshot.review_flags.length}</dd>
                  </div>
                  <div>
                    <dt>상태</dt>
                    <dd>{formatStatusLabel(reviewSnapshot.review_status)}</dd>
                  </div>
                </dl>
              ) : (
                <p className="empty-state">검수 데이터 없음</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">출력</p>
                  <h2>파일</h2>
                </div>
              </div>
              <dl className="summary-list">
                <div>
                  <dt>자막 작업</dt>
                  <dd>{formatJobValue(subtitleJob?.job_id)}</dd>
                </div>
                <div>
                  <dt>자막 파일</dt>
                  <dd>{formatJobValue(subtitleJob?.subtitle.file_uri)}</dd>
                </div>
                <div>
                  <dt>미리보기 작업</dt>
                  <dd>{formatJobValue(previewJob?.job_id)}</dd>
                </div>
                <div>
                  <dt>미리보기 파일</dt>
                  <dd>
                    {previewJob ? formatDisplayText(previewJob.preview.artifact_kind) : "미시작"}
                  </dd>
                </div>
                <div>
                  <dt>내보내기 작업</dt>
                  <dd>{formatJobValue(exportJob?.job_id)}</dd>
                </div>
                <div>
                  <dt>내보내기 대상</dt>
                  <dd>{exportJob ? formatDisplayText(exportJob.export.export_type) : "미시작"}</dd>
                </div>
                <div>
                  <dt>완성본 렌더</dt>
                  <dd>{formatJobValue(finalRenderJob?.job_id)}</dd>
                </div>
                <div>
                  <dt>완성본 파일</dt>
                  <dd>
                    {finalRenderJob?.render
                      ? formatDisplayText(finalRenderJob.render.file_uri)
                      : finalRenderJob?.status === "failed"
                        ? "완성본 렌더 실패"
                        : "미시작"}
                  </dd>
                </div>
                <div>
                  <dt>CapCut 초안(실제)</dt>
                  <dd>{formatJobValue(capcutDraftJob?.job_id)}</dd>
                </div>
                <div>
                  <dt>CapCut 초안 파일</dt>
                  <dd>
                    {capcutDraftJob?.export
                      ? formatDisplayText(capcutDraftJob.export.file_uri)
                      : capcutDraftJob?.status === "failed"
                        ? "CapCut 초안 내보내기 실패"
                        : "미시작"}
                  </dd>
                </div>
              </dl>
              {finalRenderJob?.status === "failed" ? (
                <p className="error-banner">
                  완성본 렌더 실패: {finalRenderJob.error_message ?? "결과 파일을 만들지 못했습니다."}
                </p>
              ) : null}
              {capcutDraftJob?.status === "failed" ? (
                <p className="error-banner">
                  CapCut 초안 내보내기 실패: {capcutDraftJob.error_message ?? "결과 파일을 만들지 못했습니다."}
                </p>
              ) : null}
            </article>

          </section>
        ) : null}

        {selectedSection === "settings" ? (
          <section className="workspace-grid">
            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">TTS</p>
                  <h2>음성 샘플</h2>
                </div>
              </div>
              <label className="field">
                <span>음성 샘플 파일 경로</span>
                <input
                  onChange={(event) => setVoiceSamplePath(event.target.value)}
                  placeholder="C:\path\to\voice_sample.wav"
                  value={voiceSamplePath}
                />
              </label>
              <div className="action-row">
                <button
                  className="action-button primary"
                  disabled={!selectedProjectId || !voiceSamplePath.trim() || isRegisteringVoiceSample}
                  onClick={() => void handleRegisterVoiceSample()}
                  type="button"
                >
                  {isRegisteringVoiceSample ? "등록 중" : "음성 샘플 등록"}
                </button>
              </div>
              {voiceSampleMessage ? <p className="meta-copy">{voiceSampleMessage}</p> : null}
              {voiceSampleError ? <p className="error-banner">{voiceSampleError}</p> : null}
              <label className="field">
                <span>TTS 후보 생성에 쓸 음성 샘플 자산 ID</span>
                <input
                  onChange={(event) => setTtsCandidateVoiceSampleId(event.target.value)}
                  value={ttsCandidateVoiceSampleId || voiceSampleAssetId}
                />
              </label>
              <p className="meta-copy">
                편집 탭의 세그먼트에서 &quot;TTS 후보 생성&quot; 버튼으로 이 음성 샘플 기반 나레이션을
                만들 수 있습니다.
              </p>
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">제미나이</p>
                  <h2>키</h2>
                </div>
                <button
                  className="action-button"
                  onClick={openCreateGeminiForm}
                  type="button"
                >
                  키 추가
                </button>
              </div>
              {isGeminiFormOpen ? (
                <div className="provider-form">
                  <label className="field">
                    <span>이름</span>
                    <input
                      onChange={(event) =>
                        setGeminiForm((current) => ({
                          ...current,
                          label: event.target.value,
                        }))
                      }
                      value={geminiForm.label}
                    />
                  </label>
                  {!editingGeminiKeyId ? (
                    <label className="field">
                      <span>API 키</span>
                      <input
                        onChange={(event) =>
                          setGeminiForm((current) => ({
                            ...current,
                            apiKey: event.target.value,
                          }))
                        }
                        type="password"
                        value={geminiForm.apiKey}
                      />
                    </label>
                  ) : null}
                  <label className="field">
                    <span>기본 모델</span>
                    <input
                      onChange={(event) =>
                        setGeminiForm((current) => ({
                          ...current,
                          primaryModel: event.target.value,
                        }))
                      }
                      value={geminiForm.primaryModel}
                    />
                  </label>
                  <label className="field">
                    <span>저가 모델</span>
                    <input
                      onChange={(event) =>
                        setGeminiForm((current) => ({
                          ...current,
                          cheapModel: event.target.value,
                        }))
                      }
                      value={geminiForm.cheapModel}
                    />
                  </label>
                  <label className="field">
                    <span>고품질 모델</span>
                    <input
                      onChange={(event) =>
                        setGeminiForm((current) => ({
                          ...current,
                          highQualityModel: event.target.value,
                        }))
                      }
                      value={geminiForm.highQualityModel}
                    />
                  </label>
                  <div className="action-row">
                    <button
                      className="action-button primary"
                      disabled={
                        isSavingGeminiKey ||
                        !geminiForm.label ||
                        !geminiForm.primaryModel ||
                        !geminiForm.cheapModel ||
                        !geminiForm.highQualityModel ||
                        (!editingGeminiKeyId && !geminiForm.apiKey)
                      }
                      onClick={() => void handleSaveGeminiKey()}
                      type="button"
                    >
                      {editingGeminiKeyId ? "변경 저장" : "키 저장"}
                    </button>
                    <button className="action-button" onClick={closeGeminiForm} type="button">
                      취소
                    </button>
                  </div>
                </div>
              ) : null}
              {geminiLoadError ? <p className="empty-state">{geminiLoadError}</p> : null}
              <div className="provider-key-list">
                {geminiKeys.map((key) => (
                  <article className="provider-key-card" key={key.key_id}>
                    <div className="provider-key-header">
                      <div>
                        <h3>{formatDisplayText(key.label)}</h3>
                        <p className="meta-copy">{key.masked_api_key}</p>
                      </div>
                      <span className={`pill provider-status status-${key.status}`}>
                        {formatStatusLabel(key.status)}
                      </span>
                    </div>
                    <dl className="provider-key-details">
                      <div>
                        <dt>기본 모델</dt>
                        <dd>{key.primary_model}</dd>
                      </div>
                      <div>
                        <dt>저가 모델</dt>
                        <dd>{key.cheap_model}</dd>
                      </div>
                      <div>
                        <dt>고품질 모델</dt>
                        <dd>{key.high_quality_model}</dd>
                      </div>
                      <div>
                        <dt>연속 실패</dt>
                        <dd>{key.consecutive_failures}</dd>
                      </div>
                      <div>
                        <dt>대기 종료</dt>
                        <dd>{formatNullableValue(key.cooldown_until)}</dd>
                      </div>
                      <div>
                        <dt>최근 사용</dt>
                        <dd>{formatNullableValue(key.last_used_at)}</dd>
                      </div>
                      <div>
                        <dt>최근 오류</dt>
                        <dd>{formatNullableValue(key.last_error)}</dd>
                      </div>
                    </dl>
                    <div className="action-row">
                      <button
                        aria-label={`${formatDisplayText(key.label)} 수정`}
                        className="action-button"
                        onClick={() => openEditGeminiForm(key)}
                        type="button"
                      >
                        수정
                      </button>
                      <button
                        aria-label={`${formatDisplayText(key.label)} ${key.status === "disabled" ? "사용" : "중지"}`}
                        className="action-button"
                        disabled={togglingGeminiKeyId === key.key_id}
                        onClick={() => void handleToggleGeminiKey(key)}
                        type="button"
                      >
                        {key.status === "disabled" ? "사용" : "중지"}
                      </button>
                    </div>
                  </article>
                ))}
                {geminiKeys.length === 0 && !geminiLoadError ? (
                  <p className="empty-state">제미나이 키 없음</p>
                ) : null}
              </div>
            </article>
          </section>
        ) : null}

        {selectedSection === "timeline" ? (
          <section className="panel" aria-labelledby="timeline-heading">
            <div className="panel-header">
              <div>
                <p className="section-kicker">타임라인</p>
                <h2 id="timeline-heading">트랙 · 클립</h2>
              </div>
            </div>
            {timelineJob ? (
              <div className="track-stack">
                {previewJob ? (
                  <article className="artifact-card">
                    <h3>{formatDisplayText(previewJob.preview.artifact_kind)}</h3>
                    <p>{previewJob.preview.player_uri ?? previewJob.preview.file_uri}</p>
                  </article>
                ) : null}
                {subtitleJob ? (
                  <article className="artifact-card">
                    <h3>{subtitleJob.subtitle.format}</h3>
                    <p>{subtitleJob.subtitle.file_uri}</p>
                  </article>
                ) : null}
                {exportJob ? (
                  <article className="artifact-card">
                    <h3>{formatDisplayText(exportJob.export.export_type)}</h3>
                    <p>{exportJob.export.file_uri}</p>
                    <p>{exportJob.export.subtitle_file_uri ?? "자막 없음"}</p>
                    <p>{formatDisplayText(exportJob.export.notes[0])}</p>
                  </article>
                ) : null}
                {timelineJob.timeline.tracks.map((track) => (
                  <article className="track-card" key={track.track_id}>
                    <header className="track-header">
                      <div>
                        <h3>{formatTrackLabel(track.track_type)}</h3>
                        <p>{track.track_id}</p>
                      </div>
                      <span className="pill">{track.clips.length}개</span>
                    </header>
                    <div className="clip-list">
                      {track.clips.map((clip) => (
                        <div className="clip-card" key={clip.clip_id}>
                          <strong>{clip.clip_id}</strong>
                          <span>{clip.segment_id}</span>
                          <span>{formatSeconds(clip.start_sec, clip.end_sec)}</span>
                          <span>{clip.asset_uri}</span>
                          <span>
                            추천: {clip.recommendation_id ?? "수동 내레이션"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="empty-state">타임라인 없음</p>
            )}
          </section>
        ) : null}

        {selectedSection === "review" ? (
          <section className="workspace-grid review-layout">
            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">검수</p>
                  <h2>세그먼트</h2>
                </div>
              </div>
              <div className="segment-list">
                {reviewSnapshot?.segments.map((segment) => (
                  <div className="segment-card" key={segment.segment_id}>
                    <div className="segment-heading">
                      <strong>{segment.segment_id}</strong>
                      <span className={segment.review_required ? "pill warning" : "pill okay"}>
                        {segment.review_required ? "검수 필요" : "준비"}
                      </span>
                    </div>
                    <p>{formatDisplayText(segment.text)}</p>
                    <span>{formatSeconds(segment.start_sec, segment.end_sec)}</span>
                    <span>신뢰도 {segment.confidence.toFixed(2)}</span>
                    {segment.review_reasons && segment.review_reasons.length > 0 ? (
                      <div className="segment-review-reasons">
                        {segment.review_reasons.map((reason) => (
                          <span className="pill warning" key={reason}>
                            {formatSegmentReviewReason(reason)}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    <button
                      className="action-button"
                      onClick={() => openSegmentInEditor(segment.segment_id)}
                      type="button"
                    >
                      편집 열기 · {segment.segment_id}
                    </button>
                  </div>
                )) ?? <p className="empty-state">검수 데이터 없음</p>}
              </div>
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">검수</p>
                  <h2>추천 항목</h2>
                </div>
              </div>
              <div className="recommendation-groups">
                <div>
                  <h3>자동 적용</h3>
                  {(reviewSnapshot?.applied_recommendations ?? []).map((item) => (
                    <div className="recommendation-card applied" key={item.recommendation_id}>
                      <strong>{prettifyJobType(item.recommendation_type)}</strong>
                      <p>{formatOperatorNote(item.reason)}</p>
                      <span>{item.target_segment_id}</span>
                      {renderBrollRecommendationEvidence(
                        item,
                        brollAssets,
                        reviewSnapshot?.segments ?? [],
                      )}
                    </div>
                  ))}
                </div>
                <div>
                  <h3>검수 대기</h3>
                  {(reviewSnapshot?.pending_recommendations ?? []).map((item) => {
                    const mappedField = mapRecommendationTypeToEditingField(
                      item.recommendation_type,
                    );
                    return (
                      <div className="recommendation-card pending" key={item.recommendation_id}>
                        <strong>{prettifyJobType(item.recommendation_type)}</strong>
                        <p>{formatOperatorNote(item.reason)}</p>
                        <span>{item.target_segment_id}</span>
                        {renderBrollRecommendationEvidence(
                          item,
                          brollAssets,
                          reviewSnapshot?.segments ?? [],
                        )}
                        <button
                          className="action-button"
                          onClick={() =>
                            openSegmentInEditor(
                              item.target_segment_id,
                              mappedField ? [mappedField] : undefined,
                            )
                          }
                          type="button"
                        >
                          추천 검수 · {item.target_segment_id}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">검수</p>
                  <h2>플래그</h2>
                </div>
              </div>
              <div className="flag-list">
                {(reviewSnapshot?.review_flags ?? []).map((flag) => (
                  <div className="flag-card" key={`${flag.code}-${flag.segment_id}`}>
                    <strong>{formatReviewFlagCode(flag.code)}</strong>
                    <p>{formatOperatorNote(flag.message)}</p>
                    <span>{flag.segment_id}</span>
                    <button
                      className="action-button"
                      onClick={() => openSegmentInEditor(flag.segment_id)}
                      type="button"
                    >
                      편집 확인 · {flag.segment_id}
                    </button>
                  </div>
                ))}
              </div>
              <div className="action-row">
                {reviewActions.map((action) => {
                  if (action === "Approve recommendation") {
                    return (
                      <button
                        className="action-button"
                        disabled={!actionablePendingRecommendation}
                        key={action}
                        onClick={() => void handleApproveRecommendation()}
                        type="button"
                      >
                        {formatReviewActionLabel(action)}
                      </button>
                    );
                  }
                  if (action === "Mark for manual edit") {
                    return (
                      <button
                        className="action-button"
                        disabled={!actionablePendingRecommendation}
                        key={action}
                        onClick={handleMarkRecommendationForManualEdit}
                        type="button"
                      >
                        {formatReviewActionLabel(action)}
                      </button>
                    );
                  }
                  return (
                    <button className="action-button" key={action} type="button">
                      {formatReviewActionLabel(action)}
                    </button>
                  );
                })}
              </div>
            </article>
          </section>
        ) : null}

        {selectedSection === "editing" ? (
          <section className="workspace-grid review-layout">
            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">편집</p>
                  <h2>편집기</h2>
                </div>
              </div>
              <div className="action-row">
                <button
                  className="action-button primary"
                  disabled={!latestTimelineBuildJob || isStartingEditingSession}
                  onClick={() => void handleStartEditingSession()}
                  type="button"
                >
                  {isStartingEditingSession ? "편집 시작 중" : "편집 시작"}
                </button>
              </div>
              {editingSessionRestoreError ? (
                <p className="error-banner">{editingSessionRestoreError}</p>
              ) : null}
              {partialRegenerationRestoreWarning ? (
                <p className="error-banner">{partialRegenerationRestoreWarning}</p>
              ) : null}
              {editingSession ? (
                <>
                  <dl className="summary-list">
                    <div>
                      <dt>세션 ID</dt>
                      <dd>{editingSession.session_id}</dd>
                    </div>
                    <div>
                      <dt>타임라인 ID</dt>
                      <dd>{editingSession.timeline_id}</dd>
                    </div>
                    <div>
                      <dt>세그먼트</dt>
                      <dd>{editingSession.segments.length}</dd>
                    </div>
                    <div>
                      <dt>수정 기록</dt>
                      <dd>{editingSession.history.length}</dd>
                    </div>
                    <div>
                      <dt>변경</dt>
                      <dd>{changedSegmentIds.size}</dd>
                    </div>
                    <div>
                      <dt>유지 세그먼트</dt>
                      <dd>{preservedEditingSegments.length}</dd>
                    </div>
                  </dl>
                  <label className="field">
                    <span>대상 세그먼트</span>
                    <select
                      onChange={(event) => handleSelectEditingSegment(event.target.value)}
                      value={selectedEditingSegmentId ?? ""}
                    >
                      {editingSession.segments.map((segment) => (
                        <option key={segment.segment_id} value={segment.segment_id}>
                          {`대상 ${formatSeconds(segment.start_sec, segment.end_sec)}`}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="segment-list">
                    {editingSession.segments.map((segment) => (
                      <button
                        className={
                          selectedEditingSegmentId === segment.segment_id
                            ? "project-chip is-selected"
                            : "project-chip"
                        }
                        key={segment.segment_id}
                        onClick={() => handleSelectEditingSegment(segment.segment_id)}
                        type="button"
                      >
                        <strong>{segment.segment_id}</strong>
                        <span>
                          {changedSegmentIds.has(segment.segment_id) ? "변경" : "유지"}
                        </span>
                      </button>
                    ))}
                  </div>
                  <div className="action-row">
                    {regenerationFieldOptions.map((field) => (
                      <label className="pill" key={field}>
                        <input
                          checked={selectedRegenerationFields.includes(field)}
                          onChange={(event) => {
                            setSelectedRegenerationFields((current) =>
                              event.target.checked
                                ? [...current, field]
                                : current.filter((item) => item !== field),
                            );
                            setPartialRegenerationRestoreWarning(null);
                            setPartialRegenerationPreflight(null);
                            setPartialRegenerationRun(null);
                          }}
                          type="checkbox"
                        />
                        {formatFieldLabel(field)}
                      </label>
                    ))}
                  </div>
                  <div className="action-row">
                    <button
                      className="action-button"
                      disabled={
                        !selectedEditingSegmentId ||
                        selectedRegenerationFields.length === 0 ||
                        !!isSavingEditingMutation ||
                        isRequestingRegenerationPreflight
                      }
                      onClick={() => void handleRequestRegenerationPreflight()}
                      type="button"
                    >
                      {isRequestingRegenerationPreflight
                        ? "사전 확인 중"
                        : "사전 확인"}
                    </button>
                    <button
                      className="action-button primary"
                      disabled={
                        !selectedEditingSegmentId ||
                        selectedRegenerationFields.length === 0 ||
                        !!isSavingEditingMutation ||
                        !hasFreshMatchingPreflight ||
                        isRequestingRegenerationPreflight ||
                        isRunningPartialRegeneration
                      }
                      onClick={() => void handleRunPartialRegeneration()}
                      type="button"
                    >
                      {isRunningPartialRegeneration
                        ? "부분 재생성 중"
                        : "부분 재생성"}
                    </button>
                  </div>
                  {partialRegenerationPreflight ? (
                    <div className="track-card">
                      <h3>{formatPredictedReviewStatusLabel(partialRegenerationPreflight.predicted_review_status_after_rerun)}</h3>
                      <p>
                        {formatPredictedReviewStatusDescription(
                          partialRegenerationPreflight.predicted_review_status_after_rerun,
                        )}
                      </p>
                      <h3>사전 확인 범위</h3>
                      <div className="clip-list">
                        {partialRegenerationPreflight.segment_ids.map((segmentId) => (
                          <span key={segmentId}>{`${segmentId} 포함`}</span>
                        ))}
                      </div>
                      <div className="clip-list">
                        {partialRegenerationPreflight.fields.map((field) => (
                          <span key={field}>{`${formatFieldLabel(field)} 선택`}</span>
                        ))}
                      </div>
                      <p>
                        읽기 전용 · 타임라인 유지
                      </p>
                      {partialRegenerationPreflight.prediction_reasons.length > 0 ? (
                        <div className="clip-list">
                          {partialRegenerationPreflight.prediction_reasons.map((reason) => (
                            <span key={reason}>{formatOperatorNote(reason)}</span>
                          ))}
                        </div>
                      ) : null}
                      <h3>영향 출력</h3>
                      <div className="clip-list">
                        {partialRegenerationPreflight.affected_output_areas.map((area) => (
                          <span key={area}>{formatAffectedOutputArea(area)}</span>
                        ))}
                      </div>
                      <h3>다음 작업</h3>
                      <div className="clip-list">
                        {partialRegenerationPreflight.downstream_steps.map((step) => (
                          <span key={step}>{formatWorkflowStep(step)}</span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </>
              ) : (
                <p className="empty-state">편집 세션 없음</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">검증</p>
                  <h2>변경</h2>
                </div>
              </div>
              {editingSession ? (
                <>
                  {partialRegenerationRun ? (
                    <div className="track-card">
                      <h3>{partialRegenerationRun.job_id}</h3>
                      <p>{formatStatusLabel(partialRegenerationRun.status)}</p>
                      <p>{partialRegenerationRun.delta?.timeline_id ?? "타임라인 대기"}</p>
                      <h3>재개 범위</h3>
                      <p>{`범위 ${resumedScopeSegmentIds.length}개`}</p>
                      <div className="clip-list">
                        {resumedScopeSegmentIds.map((segmentId) => (
                          <span key={segmentId}>{`${segmentId} 포함`}</span>
                        ))}
                      </div>
                      <div className="clip-list">
                        {resumedScopeFields.map((field) => (
                          <span key={field}>{`${formatFieldLabel(field)} 재개`}</span>
                        ))}
                      </div>
                      {resumedScopeSegmentIds.length > 1 ? (
                        <p>
                          다중 세그먼트 · 수동 확인
                        </p>
                      ) : null}
                      <p>{`변경 ${changedSegmentIds.size}`}</p>
                      <p>{`유지 ${preservedEditingSegments.length}`}</p>
                      {(partialRegenerationRun.delta?.regenerated_segments ?? []).map((segment) => (
                        <div className="clip-card" key={String(segment.segment_id ?? Math.random())}>
                          <strong>{`${String(segment.segment_id ?? "세그먼트")} 변경`}</strong>
                          {Array.isArray(segment.output_changes)
                            ? (segment.output_changes as unknown[]).map((change) => (
                                <span key={String(change)}>{formatOperatorNote(String(change))}</span>
                              ))
                            : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="empty-state">재생성 필요</p>
                  )}
                  <div>
                    <h3>유지 영역</h3>
                    <div className="clip-list">
                      {preservedEditingSegments.map((segment) => (
                        <span key={segment.segment_id}>{`${segment.segment_id} 유지`}</span>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <p className="empty-state">편집 세션 없음</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">판단</p>
                  <h2>판단</h2>
                </div>
              </div>
              {editingSession ? (
                partialRegenerationRun ? (
                  <>
                    <dl className="summary-list">
                      <div>
                        <dt>준비 변경</dt>
                        <dd>{readyChangedSegments.length}</dd>
                      </div>
                      <div>
                        <dt>보류 항목</dt>
                        <dd>{decisionBlockerCount}</dd>
                      </div>
                    </dl>
                    <p>{`준비 ${readyChangedSegments.length}`}</p>
                    <p>{`보류 ${decisionBlockerCount}`}</p>
                    <div className="track-card">
                      <h3>변경 준비</h3>
                      <div className="clip-list">
                        {changedEditingSegments.map((segment) => (
                          <span key={segment.segment_id}>
                            {segment.review_required
                              ? `${segment.segment_id} 검수 필요`
                              : `${segment.segment_id} 승인 준비`}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="track-card">
                      <h3>출력 체크</h3>
                      <div className="clip-list">
                        {changedOutputChecklist.map((item) => (
                          <span key={item}>{formatOperatorNote(item)}</span>
                        ))}
                      </div>
                    </div>
                    <div className="track-card">
                      <h3>판단</h3>
                      <strong>{decisionCue?.title}</strong>
                      <p>{decisionCue?.body}</p>
                    </div>
                    <div className="track-card">
                      <h3>유지 안정</h3>
                      <div className="clip-list">
                        {preservedEditingSegments.map((segment) => (
                          <span key={segment.segment_id}>
                            {`${segment.segment_id} 유지`}
                          </span>
                        ))}
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="empty-state">
                    재생성 필요
                  </p>
                )
              ) : (
                <p className="empty-state">편집 세션 없음</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">선택</p>
                  <h2>상세</h2>
                </div>
              </div>
              {selectedEditingSegment && selectedEditingDraft ? (
                <div className="segment-card">
                  <div className="segment-heading">
                    <strong>선택 항목</strong>
                    <span
                      className={selectedEditingSegment.review_required ? "pill warning" : "pill okay"}
                    >
                      {selectedEditingSegment.review_required ? "검수 필요" : "준비"}
                    </span>
                  </div>
                  <span>{formatSeconds(selectedEditingSegment.start_sec, selectedEditingSegment.end_sec)}</span>
                  <p>{formatDisplayText(selectedEditingDraft.captionText)}</p>
                  <span>{selectedEditingDraft.brollAssetId ? "B롤 선택됨" : "B롤 없음"}</span>
                  <span>
                    {selectedEditingDraft.explanationText ? "설명 카드 있음" : "설명 카드 없음"}
                  </span>
                  <span>{selectedEditingDraft.imageAssetId || "이미지 없음"}</span>
                  <span>{selectedEditingDraft.tableText || "표 없음"}</span>
                  <span>{selectedEditingDraft.ttsAssetId || "TTS 없음"}</span>
                  {editingMutationFeedback ? (
                    <p
                      className={
                        editingMutationFeedback.kind === "error"
                          ? "error-copy"
                          : "meta-copy"
                      }
                    >
                      {editingMutationFeedback.message}
                    </p>
                  ) : null}
                  <label className="field">
                    <span>자막</span>
                    <input
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          captionText: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.captionText}
                    />
                  </label>
                  <button
                    className="action-button"
                    disabled={
                      !selectedProjectId ||
                      !activeEditingSessionId ||
                      isSavingEditingMutation === `${selectedEditingSegment.segment_id}-caption`
                    }
                    onClick={() =>
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-caption`, () =>
                        api.updateEditingSessionCaption(
                          selectedProjectId!,
                          activeEditingSessionId!,
                          selectedEditingSegment.segment_id,
                          { caption_text: selectedEditingDraft.captionText },
                        ),
                      )
                    }
                    type="button"
                  >
                    자막 저장
                  </button>
                  <label className="field">
                    <span>컷</span>
                    <select
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          cutAction: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.cutAction}
                    >
                      <option value="keep">유지</option>
                      <option value="remove">삭제</option>
                      <option value="trim">자르기</option>
                    </select>
                  </label>
                  <button
                    className="action-button"
                    disabled={
                      !selectedProjectId ||
                      !activeEditingSessionId ||
                      isSavingEditingMutation === `${selectedEditingSegment.segment_id}-cut`
                    }
                    onClick={() =>
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-cut`, () =>
                        api.updateEditingSessionCutAction(
                          selectedProjectId!,
                          activeEditingSessionId!,
                          selectedEditingSegment.segment_id,
                          { cut_action: selectedEditingDraft.cutAction },
                        ),
                      )
                    }
                    type="button"
                  >
                    컷 저장
                  </button>
                  <label className="field">
                    <span>B롤 폴더</span>
                    <input
                      onChange={(event) => setBrollFolderPath(event.target.value)}
                      value={brollFolderPath}
                    />
                  </label>
                  <label className="field">
                    <span>B롤 파일</span>
                    <textarea
                      onChange={(event) => setBrollSourcePaths(event.target.value)}
                      rows={3}
                      value={brollSourcePaths}
                    />
                  </label>
                  <label className="field">
                    <span>B롤 태그</span>
                    <input
                      onChange={(event) => setBrollImportTags(event.target.value)}
                      value={brollImportTags}
                    />
                  </label>
                  <button
                    className="action-button"
                    disabled={
                      !selectedProjectId ||
                      isImportingBroll ||
                      (!brollFolderPath.trim() && !brollSourcePaths.trim())
                    }
                    onClick={() => void handleImportBrollBatch()}
                    type="button"
                  >
                    {isImportingBroll ? "B롤 가져오는 중" : "B롤 가져오기"}
                  </button>
                  {brollImportError ? <p className="error-copy">{brollImportError}</p> : null}
                  {brollImportMessage ? <p className="meta-copy">{brollImportMessage}</p> : null}
                  <label className="field">
                    <span>B롤 검색</span>
                    <input
                      onChange={(event) => setBrollAssetFilter(event.target.value)}
                      value={brollAssetFilter}
                    />
                  </label>
                  <p className="meta-copy">
                    보임 {filteredBrollAssets.length}/{brollAssets.length}
                  </p>
                  <div className="broll-thumbnail-grid">
                    {filteredBrollAssets.map((asset) => (
                      <button
                        className={`broll-thumbnail-card ${
                          asset.asset_id === selectedEditingDraft.brollAssetId ? "is-selected" : ""
                        }`}
                        key={asset.asset_id}
                        onClick={() =>
                          updateEditingDraft(selectedEditingSegment.segment_id, {
                            brollAssetId: asset.asset_id,
                          })
                        }
                        title={formatBrollAssetLabel(asset)}
                        type="button"
                      >
                        {asset.metadata?.thumbnail_uri ? (
                          <img
                            alt={formatBrollAssetTitle(asset)}
                            src={api.assetThumbnailUrl(selectedProjectId!, asset.asset_id)}
                          />
                        ) : (
                          <span className="broll-thumbnail-placeholder">썸네일 없음</span>
                        )}
                        <span className="broll-thumbnail-title">{formatBrollAssetTitle(asset)}</span>
                      </button>
                    ))}
                  </div>
                  <label className="field">
                    <span>B롤 선택</span>
                    <select
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          brollAssetId: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.brollAssetId}
                    >
                      <option value="">B롤 미선택</option>
                      {selectedEditingDraft.brollAssetId &&
                      !brollAssets.some(
                        (asset) => asset.asset_id === selectedEditingDraft.brollAssetId,
                      ) ? (
                        <option value={selectedEditingDraft.brollAssetId}>
                          현재 수동 ID
                        </option>
                      ) : null}
                      {selectableBrollAssets.map((asset) => {
                        return (
                          <option key={asset.asset_id} value={asset.asset_id}>
                            {formatBrollAssetLabel(asset)}
                          </option>
                        );
                      })}
                    </select>
                  </label>
                  <div className="track-card">
                    <h3>선택 B롤</h3>
                    {selectedBrollAsset ? (
                      <>
                        <strong>{formatBrollAssetTitle(selectedBrollAsset)}</strong>
                        <span>{selectedBrollAsset.asset_id}</span>
                        {formatBrollAssetTags(selectedBrollAsset) ? (
                          <span>{formatBrollAssetTags(selectedBrollAsset)}</span>
                        ) : null}
                      </>
                    ) : selectedEditingDraft.brollAssetId ? (
                      <>
                        <strong>수동 ID</strong>
                        <span>{selectedEditingDraft.brollAssetId}</span>
                      </>
                    ) : (
                      <p className="empty-state">선택 없음</p>
                    )}
                  </div>
                  {brollAssetLoadError ? (
                    <p className="error-copy">{brollAssetLoadError}</p>
                  ) : null}
                  {!brollAssetLoadError && brollAssets.length === 0 ? (
                    <p className="empty-state">보관 B롤 없음</p>
                  ) : null}
                  <label className="field">
                    <span>B롤 자산 ID</span>
                    <input
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          brollAssetId: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.brollAssetId}
                    />
                  </label>
                  <button
                    className="action-button"
                    disabled={
                      !selectedProjectId ||
                      !activeEditingSessionId ||
                      !selectedEditingDraft.brollAssetId ||
                      isSavingEditingMutation === `${selectedEditingSegment.segment_id}-broll`
                    }
                    onClick={() =>
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-broll`, () =>
                        api.updateEditingSessionBroll(
                          selectedProjectId!,
                          activeEditingSessionId!,
                          selectedEditingSegment.segment_id,
                          { asset_id: selectedEditingDraft.brollAssetId },
                        ),
                      )
                    }
                    type="button"
                  >
                    B롤 저장
                  </button>
                  {selectedEditingSegment.broll_override ? (
                    <button
                      className="action-button"
                      disabled={
                        !selectedProjectId ||
                        !activeEditingSessionId ||
                        isSavingEditingMutation === `${selectedEditingSegment.segment_id}-broll`
                      }
                      onClick={() =>
                        void applyEditingMutation(
                          `${selectedEditingSegment.segment_id}-broll`,
                          () =>
                            api.clearEditingSessionBrollOverride(
                              selectedProjectId!,
                              activeEditingSessionId!,
                              selectedEditingSegment.segment_id,
                            ),
                          { feedbackAction: "해제", removeRegenerationField: "broll" },
                        )
                      }
                      type="button"
                    >
                      B롤 해제
                    </button>
                  ) : null}
                  <label className="field">
                    <span>음악 자산 ID</span>
                    <input
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          musicAssetId: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.musicAssetId}
                    />
                  </label>
                  <button
                    aria-describedby={
                      !selectedEditingDraft.musicAssetId
                        ? `${selectedEditingSegment.segment_id}-music-save-help`
                        : undefined
                    }
                    className="action-button"
                    disabled={
                      !selectedProjectId ||
                      !activeEditingSessionId ||
                      !selectedEditingDraft.musicAssetId ||
                      isSavingEditingMutation === `${selectedEditingSegment.segment_id}-music`
                    }
                    onClick={() =>
                      void applyEditingMutation(
                        `${selectedEditingSegment.segment_id}-music`,
                        () =>
                          api.updateEditingSessionMusicOverride(
                            selectedProjectId!,
                            activeEditingSessionId!,
                            selectedEditingSegment.segment_id,
                            { asset_id: selectedEditingDraft.musicAssetId },
                          ),
                        { addRegenerationField: "music" },
                      )
                    }
                    type="button"
                  >
                    음악 저장
                  </button>
                  {!selectedEditingDraft.musicAssetId ? (
                    <p className="meta-copy" id={`${selectedEditingSegment.segment_id}-music-save-help`}>
                      음악 ID 필요
                    </p>
                  ) : null}
                  {selectedEditingSegment.music_override ? (
                    <button
                      className="action-button"
                      disabled={
                        !selectedProjectId ||
                        !activeEditingSessionId ||
                        isSavingEditingMutation === `${selectedEditingSegment.segment_id}-music`
                      }
                      onClick={() =>
                        void applyEditingMutation(
                          `${selectedEditingSegment.segment_id}-music`,
                          () =>
                            api.clearEditingSessionMusicOverride(
                              selectedProjectId!,
                              activeEditingSessionId!,
                              selectedEditingSegment.segment_id,
                            ),
                          { feedbackAction: "해제", removeRegenerationField: "music" },
                        )
                      }
                      type="button"
                    >
                      음악 해제
                    </button>
                  ) : null}
                  <label className="field">
                    <span>설명 제목</span>
                    <input
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          explanationTitle: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.explanationTitle}
                    />
                  </label>
                  <label className="field">
                    <span>설명 본문</span>
                    <input
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          explanationBody: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.explanationBody}
                    />
                  </label>
                  <label className="field">
                    <span>설명 텍스트</span>
                    <textarea
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          explanationText: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.explanationText}
                    />
                  </label>
                  <button
                    aria-describedby={
                      !selectedEditingDraft.explanationText
                        ? `${selectedEditingSegment.segment_id}-explanation-save-help`
                        : undefined
                    }
                    className="action-button"
                    disabled={
                      !selectedProjectId ||
                      !activeEditingSessionId ||
                      !selectedEditingDraft.explanationText ||
                      isSavingEditingMutation === `${selectedEditingSegment.segment_id}-explanation`
                    }
                    onClick={() =>
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-explanation`, () =>
                        api.updateEditingSessionExplanationCard(
                          selectedProjectId!,
                          activeEditingSessionId!,
                          selectedEditingSegment.segment_id,
                          {
                            title: selectedEditingDraft.explanationTitle,
                            body: selectedEditingDraft.explanationBody,
                            text: selectedEditingDraft.explanationText,
                          },
                        ),
                      )
                    }
                    type="button"
                  >
                    설명 저장
                  </button>
                  {!selectedEditingDraft.explanationText ? (
                    <p
                      className="meta-copy"
                      id={`${selectedEditingSegment.segment_id}-explanation-save-help`}
                    >
                      설명 텍스트 필요
                    </p>
                  ) : null}
                  {selectedEditingSegment.visual_overlays.some(
                    (overlay) => String(overlay.overlay_type ?? "") === "explanation_card",
                  ) ? (
                    <button
                      className="action-button"
                      disabled={
                        !selectedProjectId ||
                        !activeEditingSessionId ||
                        isSavingEditingMutation === `${selectedEditingSegment.segment_id}-explanation`
                      }
                      onClick={() =>
                        void applyEditingMutation(
                          `${selectedEditingSegment.segment_id}-explanation`,
                          () =>
                            api.removeEditingSessionExplanationCard(
                              selectedProjectId!,
                              activeEditingSessionId!,
                              selectedEditingSegment.segment_id,
                            ),
                          { feedbackAction: "삭제" },
                        )
                      }
                      type="button"
                    >
                      설명 삭제
                    </button>
                  ) : null}
                  <label className="field">
                    <span>이미지 자산 ID</span>
                    <input
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          imageAssetId: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.imageAssetId}
                    />
                  </label>
                  <label className="field">
                    <span>이미지 텍스트</span>
                    <textarea
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          imageText: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.imageText}
                    />
                  </label>
                  <button
                    aria-describedby={
                      !selectedEditingDraft.imageAssetId
                        ? `${selectedEditingSegment.segment_id}-image-save-help`
                        : undefined
                    }
                    className="action-button"
                    disabled={
                      !selectedProjectId ||
                      !activeEditingSessionId ||
                      !selectedEditingDraft.imageAssetId ||
                      isSavingEditingMutation === `${selectedEditingSegment.segment_id}-image`
                    }
                    onClick={() =>
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-image`, () =>
                        api.updateEditingSessionImageOverlay(
                          selectedProjectId!,
                          activeEditingSessionId!,
                          selectedEditingSegment.segment_id,
                          {
                            asset_id: selectedEditingDraft.imageAssetId,
                            text: selectedEditingDraft.imageText,
                          },
                        ),
                      )
                    }
                    type="button"
                  >
                    이미지 저장
                  </button>
                  {!selectedEditingDraft.imageAssetId ? (
                    <p
                      className="meta-copy"
                      id={`${selectedEditingSegment.segment_id}-image-save-help`}
                    >
                      이미지 ID 필요
                    </p>
                  ) : null}
                  {Boolean(readOverlay(selectedEditingSegment, "image_overlay")) ? (
                    <button
                      className="action-button"
                      disabled={
                        !selectedProjectId ||
                        !activeEditingSessionId ||
                        isSavingEditingMutation === `${selectedEditingSegment.segment_id}-image`
                      }
                      onClick={() =>
                        void applyEditingMutation(`${selectedEditingSegment.segment_id}-image`, () =>
                          api.removeEditingSessionImageOverlay(
                            selectedProjectId!,
                            activeEditingSessionId!,
                            selectedEditingSegment.segment_id,
                          ),
                        { feedbackAction: "삭제" },
                        )
                      }
                      type="button"
                    >
                      이미지 삭제
                    </button>
                  ) : null}
                  <label className="field">
                    <span>표 열</span>
                    <input
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          tableColumns: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.tableColumns}
                    />
                  </label>
                  <label className="field">
                    <span>표 행</span>
                    <textarea
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          tableRows: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.tableRows}
                    />
                  </label>
                  <label className="field">
                    <span>표 텍스트</span>
                    <textarea
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          tableText: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.tableText}
                    />
                  </label>
                  <button
                    aria-describedby={
                      !selectedEditingDraft.tableText
                        ? `${selectedEditingSegment.segment_id}-table-save-help`
                        : undefined
                    }
                    className="action-button"
                    disabled={
                      !selectedProjectId ||
                      !activeEditingSessionId ||
                      !selectedEditingDraft.tableText ||
                      isSavingEditingMutation === `${selectedEditingSegment.segment_id}-table`
                    }
                    onClick={() =>
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-table`, () =>
                        api.updateEditingSessionTableOverlay(
                          selectedProjectId!,
                          activeEditingSessionId!,
                          selectedEditingSegment.segment_id,
                          {
                            columns: selectedEditingDraft.tableColumns
                              .split(",")
                              .map((item) => item.trim())
                              .filter(Boolean),
                            rows: selectedEditingDraft.tableRows
                              .split("\n")
                              .map((row) =>
                                row
                                  .split(",")
                                  .map((cell) => cell.trim())
                                  .filter(Boolean),
                              )
                              .filter((row) => row.length > 0),
                            text: selectedEditingDraft.tableText,
                          },
                        ),
                      )
                    }
                    type="button"
                  >
                    표 저장
                  </button>
                  {!selectedEditingDraft.tableText ? (
                    <p
                      className="meta-copy"
                      id={`${selectedEditingSegment.segment_id}-table-save-help`}
                    >
                      표 텍스트 필요
                    </p>
                  ) : null}
                  {Boolean(readOverlay(selectedEditingSegment, "table_overlay")) ? (
                    <button
                      className="action-button"
                      disabled={
                        !selectedProjectId ||
                        !activeEditingSessionId ||
                        isSavingEditingMutation === `${selectedEditingSegment.segment_id}-table`
                      }
                      onClick={() =>
                        void applyEditingMutation(`${selectedEditingSegment.segment_id}-table`, () =>
                          api.removeEditingSessionTableOverlay(
                            selectedProjectId!,
                            activeEditingSessionId!,
                            selectedEditingSegment.segment_id,
                          ),
                        { feedbackAction: "삭제" },
                        )
                      }
                      type="button"
                    >
                      표 삭제
                    </button>
                  ) : null}
                  <label className="field">
                    <span>TTS 추천 ID</span>
                    <input
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          ttsRecommendationId: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.ttsRecommendationId}
                    />
                  </label>
                  <label className="field">
                    <span>TTS 자산 ID</span>
                    <input
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          ttsAssetId: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.ttsAssetId}
                    />
                  </label>
                  <button
                    aria-describedby={
                      !selectedEditingDraft.ttsRecommendationId || !selectedEditingDraft.ttsAssetId
                        ? `${selectedEditingSegment.segment_id}-tts-save-help`
                        : undefined
                    }
                    className="action-button"
                    disabled={
                      !selectedProjectId ||
                      !activeEditingSessionId ||
                      !selectedEditingDraft.ttsRecommendationId ||
                      !selectedEditingDraft.ttsAssetId ||
                      isSavingEditingMutation === `${selectedEditingSegment.segment_id}-tts`
                    }
                    onClick={() =>
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-tts`, () =>
                        api.updateEditingSessionTtsReplacement(
                          selectedProjectId!,
                          activeEditingSessionId!,
                          selectedEditingSegment.segment_id,
                          {
                            recommendation_id: selectedEditingDraft.ttsRecommendationId,
                            asset_id: selectedEditingDraft.ttsAssetId,
                          },
                        ),
                      )
                    }
                    type="button"
                  >
                    TTS 저장
                  </button>
                  {!selectedEditingDraft.ttsRecommendationId || !selectedEditingDraft.ttsAssetId ? (
                    <p
                      className="meta-copy"
                      id={`${selectedEditingSegment.segment_id}-tts-save-help`}
                    >
                      TTS 추천 ID · 자산 ID 필요
                    </p>
                  ) : null}
                  <button
                    className="action-button"
                    disabled={
                      !selectedProjectId ||
                      !ttsCandidateVoiceSampleId.trim() ||
                      !selectedEditingSegment.caption_text.trim() ||
                      isGeneratingTtsCandidate
                    }
                    onClick={() =>
                      void handleGenerateTtsCandidate(
                        selectedEditingSegment.segment_id,
                        selectedEditingSegment.caption_text,
                      )
                    }
                    type="button"
                  >
                    {isGeneratingTtsCandidate ? "TTS 후보 생성 중" : "TTS 후보 생성 (음성 클로닝)"}
                  </button>
                  {!ttsCandidateVoiceSampleId.trim() ? (
                    <p className="meta-copy">설정 탭에서 음성 샘플을 먼저 등록하세요</p>
                  ) : null}
                  {ttsCandidateMessage ? <p className="meta-copy">{ttsCandidateMessage}</p> : null}
                  {ttsCandidateError ? <p className="error-banner">{ttsCandidateError}</p> : null}
                  <div className="tts-candidate-comparison">
                    <p className="section-kicker">TTS 후보 비교 (A/B)</p>
                    {isLoadingTtsCandidates ? <p className="meta-copy">불러오는 중...</p> : null}
                    {!isLoadingTtsCandidates && ttsCandidates.length === 0 ? (
                      <p className="empty-state">이 세그먼트의 TTS 후보가 아직 없습니다</p>
                    ) : null}
                    {ttsCandidates.map((candidate, index) => (
                      <div className="tts-candidate-row" key={candidate.candidate_id}>
                        <span>
                          {`후보 ${index + 1} · ${candidate.candidate_id}`}
                        </span>
                        <p className="meta-copy">{formatDisplayText(candidate.source_text)}</p>
                        <audio
                          controls
                          src={api.assetContentUrl(selectedProjectId!, candidate.asset_id)}
                        />
                        <button
                          className="action-button"
                          onClick={() =>
                            updateEditingDraft(selectedEditingSegment.segment_id, {
                              ttsAssetId: candidate.asset_id,
                            })
                          }
                          type="button"
                        >
                          이 후보 선택
                        </button>
                      </div>
                    ))}
                  </div>
                  {selectedEditingSegment.tts_replacement ? (
                    <button
                      className="action-button"
                      disabled={
                        !selectedProjectId ||
                        !activeEditingSessionId ||
                        isSavingEditingMutation === `${selectedEditingSegment.segment_id}-tts`
                      }
                      onClick={() =>
                        void applyEditingMutation(`${selectedEditingSegment.segment_id}-tts`, () =>
                          api.clearEditingSessionTtsReplacement(
                            selectedProjectId!,
                            activeEditingSessionId!,
                            selectedEditingSegment.segment_id,
                          ),
                        { feedbackAction: "해제" },
                        )
                      }
                      type="button"
                    >
                      TTS 해제
                    </button>
                  ) : null}
                </div>
              ) : (
                <p className="empty-state">세그먼트 선택</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">변경</p>
                  <h2>트랙</h2>
                </div>
              </div>
              {timelineJob ? (
                <div className="track-stack">
                  {timelineJob.timeline.tracks.map((track) => (
                    <article className="track-card" key={track.track_id}>
                      <header className="track-header">
                        <div>
                          <h3>{formatTrackLabel(track.track_type)}</h3>
                          <p>{track.track_id}</p>
                        </div>
                        <span className="pill">{track.clips.length}개</span>
                      </header>
                      <div className="clip-list">
                        {track.clips.map((clip) => (
                          <div className="clip-card" key={clip.clip_id}>
                            <strong>{clip.segment_id}</strong>
                            <span>
                              {changedSegmentIds.has(clip.segment_id)
                                ? "현재 변경"
                                : "기존 유지"}
                            </span>
                            <span>{clip.asset_uri}</span>
                          </div>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="empty-state">재생성 타임라인 없음</p>
              )}
            </article>
          </section>
        ) : null}
      </main>
    </div>
  );
}
