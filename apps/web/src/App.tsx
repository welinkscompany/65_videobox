import { useEffect, useMemo, useState } from "react";

import {
  api,
  type EditingSession,
  type EditingSessionSegment,
  type ExportJob,
  type GeminiProviderKey,
  type JobRecord,
  type PartialRegenerationPreflight,
  type PartialRegenerationRun,
  type PreviewJob,
  type Project,
  type ReviewSnapshot,
  type SubtitleJob,
  type TimelineJob,
} from "./api";

type LoadState = "idle" | "loading" | "ready" | "error";

const reviewActions = [
  "Approve recommendation",
  "Reject recommendation",
  "Mark for manual edit",
] as const;

function prettifyJobType(jobType: string) {
  return jobType.replace(/_/g, " ");
}

function formatSeconds(startSec: number, endSec: number) {
  return `${startSec.toFixed(1)}s - ${endSec.toFixed(1)}s`;
}

function findLatestTimelineJob(jobs: JobRecord[]) {
  const candidates = jobs
    .filter((job) => job.job_type === "timeline_build" && job.status === "succeeded")
    .sort((left, right) =>
      getLatestJobTimestamp(right).localeCompare(getLatestJobTimestamp(left)),
    );
  return candidates.length > 0 ? candidates[0] : null;
}

function findLatestSucceededJob(jobs: JobRecord[], jobType: string, inputRef?: string | null) {
  const candidates = jobs
    .filter(
      (job) =>
        job.job_type === jobType &&
        job.status === "succeeded" &&
        (inputRef == null || job.input_ref === inputRef),
    )
    .sort((left, right) =>
      getLatestJobTimestamp(right).localeCompare(getLatestJobTimestamp(left)),
    );
  return candidates.length > 0 ? candidates[0] : null;
}

function getLatestJobTimestamp(job: JobRecord) {
  return job.finished_at ?? job.started_at ?? "";
}

function canResumeCandidate(
  session: EditingSession,
  candidate: {
    session_id: string;
    session_updated_at?: string | null;
  },
) {
  return (
    candidate.session_id === session.session_id &&
    !!candidate.session_updated_at &&
    candidate.session_updated_at === session.updated_at
  );
}

type GeminiKeyFormState = {
  label: string;
  apiKey: string;
  primaryModel: string;
  cheapModel: string;
  highQualityModel: string;
};

function createEmptyGeminiKeyForm(): GeminiKeyFormState {
  return {
    label: "",
    apiKey: "",
    primaryModel: "",
    cheapModel: "",
    highQualityModel: "",
  };
}

function formatNullableValue(value: string | null) {
  return value ?? "not available";
}

type EditingSegmentDraft = {
  captionText: string;
  cutAction: string;
  brollAssetId: string;
  explanationTitle: string;
  explanationBody: string;
  explanationText: string;
  imageAssetId: string;
  imageText: string;
  tableColumns: string;
  tableRows: string;
  tableText: string;
  ttsRecommendationId: string;
  ttsAssetId: string;
};

function readOverlay(segment: EditingSessionSegment, overlayType: string) {
  return (
    segment.visual_overlays.find(
      (overlay) => String(overlay.overlay_type ?? "") === overlayType,
    ) ?? null
  );
}

function createEditingSegmentDraft(segment: EditingSessionSegment): EditingSegmentDraft {
  const explanationCard = readOverlay(segment, "explanation_card");
  const imageOverlay = readOverlay(segment, "image_overlay");
  const tableOverlay = readOverlay(segment, "table_overlay");
  const tableRows = Array.isArray(tableOverlay?.rows)
    ? (tableOverlay.rows as unknown[][])
        .map((row) => row.map((cell) => String(cell ?? "")).join(", "))
        .join("\n")
    : "";
  return {
    captionText: segment.caption_text,
    cutAction: segment.cut_action,
    brollAssetId: String(segment.broll_override?.asset_id ?? ""),
    explanationTitle: String(explanationCard?.title ?? ""),
    explanationBody: String(explanationCard?.body ?? ""),
    explanationText: String(explanationCard?.text ?? ""),
    imageAssetId: String(imageOverlay?.asset_id ?? ""),
    imageText: String(imageOverlay?.text ?? ""),
    tableColumns: Array.isArray(tableOverlay?.columns)
      ? (tableOverlay.columns as unknown[]).map((column) => String(column ?? "")).join(", ")
      : "",
    tableRows,
    tableText: String(tableOverlay?.text ?? ""),
    ttsRecommendationId: String(segment.tts_replacement?.recommendation_id ?? ""),
    ttsAssetId: String(segment.tts_replacement?.asset_id ?? ""),
  };
}

function buildEditingDrafts(session: EditingSession) {
  return Object.fromEntries(
    session.segments.map((segment) => [segment.segment_id, createEditingSegmentDraft(segment)]),
  ) as Record<string, EditingSegmentDraft>;
}

function buildDefaultRegenerationFields(segment: EditingSessionSegment | null) {
  if (!segment) {
    return [] as string[];
  }
  const defaultFields: string[] = [];
  if (segment.broll_override) {
    defaultFields.push("broll");
  }
  if (readOverlay(segment, "explanation_card")) {
    defaultFields.push("explanation_card");
  }
  if (readOverlay(segment, "image_overlay")) {
    defaultFields.push("image_overlay");
  }
  if (readOverlay(segment, "table_overlay")) {
    defaultFields.push("table_overlay");
  }
  if (segment.tts_replacement) {
    defaultFields.push("tts_replacement");
  }
  return defaultFields.length > 0 ? defaultFields : ["caption"];
}

function buildDefaultEditingSelection(session: EditingSession) {
  const selectedSegment =
    session.segments.find(
      (segment) =>
        segment.broll_override ||
        segment.tts_replacement ||
        segment.visual_overlays.length > 0 ||
        segment.review_required,
    ) ?? session.segments[0] ?? null;
  if (!selectedSegment) {
    return { segmentId: null, fields: [] as string[] };
  }
  return {
    segmentId: selectedSegment.segment_id,
    fields: buildDefaultRegenerationFields(selectedSegment),
  };
}

function formatFieldLabel(field: string) {
  return field.replace(/_/g, " ");
}

function mapRecommendationTypeToEditingField(recommendationType: string) {
  if (recommendationType === "tts_replacement") {
    return "tts_replacement";
  }
  if (recommendationType === "broll") {
    return "broll";
  }
  return null;
}

function haveSameMembers(left: string[], right: string[]) {
  const leftSet = new Set(left);
  const rightSet = new Set(right);
  return leftSet.size === rightSet.size && [...leftSet].every((item) => rightSet.has(item));
}

function formatAffectedOutputArea(area: string) {
  if (area === "capcut export") {
    return "CapCut handoff";
  }
  return area;
}

function formatTrackLabel(trackType: string) {
  if (trackType === "broll") {
    return "B-roll track";
  }
  return `${trackType.charAt(0).toUpperCase()}${trackType.slice(1)} track`;
}

function formatPredictedReviewStatusLabel(status: string) {
  if (status === "blocked") {
    return "Blocked after rerun";
  }
  if (status === "draft") {
    return "Draft after rerun";
  }
  return "Review status unknown after rerun";
}

function formatPredictedReviewStatusDescription(status: string) {
  if (status === "blocked") {
    return "This rerun is expected to keep review blockers in place until they are cleared.";
  }
  if (status === "draft") {
    return "This rerun is expected to create a new draft that still needs approval before output jobs run.";
  }
  return "The rerun scope could not be mapped to a safe post-rerun review prediction.";
}

export function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedSection, setSelectedSection] = useState<
    "overview" | "timeline" | "review" | "editing"
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
  const [geminiKeys, setGeminiKeys] = useState<GeminiProviderKey[]>([]);
  const [geminiLoadError, setGeminiLoadError] = useState<string | null>(null);
  const [editingSessionRestoreError, setEditingSessionRestoreError] = useState<string | null>(null);
  const [partialRegenerationRestoreWarning, setPartialRegenerationRestoreWarning] = useState<
    string | null
  >(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRebuildingTimeline, setIsRebuildingTimeline] = useState(false);
  const [isApprovingTimeline, setIsApprovingTimeline] = useState(false);
  const [isReopeningTimeline, setIsReopeningTimeline] = useState(false);
  const [isRenderingSubtitle, setIsRenderingSubtitle] = useState(false);
  const [isRenderingPreview, setIsRenderingPreview] = useState(false);
  const [isExportingCapcut, setIsExportingCapcut] = useState(false);
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
        setErrorMessage(error instanceof Error ? error.message : "Unknown error");
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
      setGeminiLoadError(null);
      setEditingSessionRestoreError(null);
      setPartialRegenerationRestoreWarning(null);
      try {
        const project = await api.getProject(projectId);
        const jobItems = await api.listJobs(projectId);
        let latestEditingSession: EditingSession | null = null;
        try {
          latestEditingSession = await api.getLatestEditingSession(projectId);
        } catch (error) {
          setEditingSessionRestoreError(
            error instanceof Error
              ? `Latest editing session could not be restored. Stable timeline data is still available below. (${error.message})`
              : "Latest editing session could not be restored. Stable timeline data is still available below.",
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
                    resumedPartialRegenerationPreflight = await api.previewPartialRegeneration(
                      projectId,
                      candidateResult.session_id,
                      {
                        segment_ids: candidateResult.segment_ids,
                        fields: candidateResult.fields,
                      },
                    );
                  } catch {
                    resumedPartialRegenerationPreflight = null;
                    resumedPartialRegenerationRestoreWarning =
                      "Resumed candidate preflight interpretation is unavailable. Candidate scope is visible, but review prediction details could not be reused.";
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
                "Resumed candidate could not be restored. Stable timeline data remains active below.";
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
          setGeminiLoadError("Gemini routing state unavailable.");
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Unknown error");
        setLoadState("error");
      }
    }

    void loadProjectWorkspace();
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId]);

  const latestTimelineBuildJob = useMemo(
    () => findLatestTimelineJob(jobs),
    [jobs],
  );
  const activeTimelineJobId = timelineJob?.job_id ?? latestTimelineBuildJob?.job_id ?? null;

  const pipelineStages = useMemo(
    () => [
      { label: "Transcription", jobType: "transcription" },
      { label: "Segment analysis", jobType: "segment_analysis" },
      { label: "B-roll recommendation", jobType: "broll_recommendation" },
      { label: "Music recommendation", jobType: "music_recommendation" },
      { label: "Timeline build", jobType: "timeline_build" },
      { label: "Subtitle render", jobType: "subtitle_render" },
      { label: "Preview render", jobType: "preview_render" },
      { label: "CapCut export", jobType: "capcut_export" },
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
  ) {
    setIsSavingEditingMutation(mutationKey);
    setErrorMessage(null);
    try {
      const session = await action();
      applyEditingSessionState(session);
      setPartialRegenerationPreflight(null);
      setPartialRegenerationRun(null);
      setTimelineJob(null);
      setReviewSnapshot(null);
      setSubtitleJob(null);
      setPreviewJob(null);
      setExportJob(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setIsExportingCapcut(false);
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setIsApprovingTimeline(false);
    }
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setIsRenderingSubtitle(false);
    }
  }

  async function refreshGeminiKeys(projectId: string) {
    const providerKeys = await api.listGeminiProviderKeys(projectId);
    setGeminiKeys(providerKeys);
    setGeminiLoadError(null);
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
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
      setErrorMessage(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setTogglingGeminiKeyId(null);
    }
  }

  const selectedEditingSegment =
    editingSession?.segments.find((segment) => segment.segment_id === selectedEditingSegmentId) ?? null;
  const selectedEditingDraft = selectedEditingSegmentId
    ? editingDrafts[selectedEditingSegmentId]
    : undefined;
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
          title: "Hold before preview/export",
          body: "Rerun suggested if the changed output is still incorrect.",
        }
      : canApproveTimeline
        ? {
          title: "Approve updated timeline",
          body: "All changed outputs are ready and the candidate timeline can now be approved.",
        }
        : {
            title: "Hold before preview/export",
            body: "Changed outputs look ready, but refreshed review state is still unavailable.",
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
    "explanation_card",
    "image_overlay",
    "table_overlay",
    "tts_replacement",
  ] as const;

  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Project navigation">
        <div className="brand-card">
          <p className="eyebrow">Local-first review shell</p>
          <h1>VideoBox Operator Dashboard</h1>
          <p className="lede">
            Inspect projects, verify draft timelines, and make review-first
            decisions before preview or export.
          </p>
        </div>

        <section className="sidebar-section" aria-labelledby="projects-heading">
          <div className="sidebar-header">
            <p className="section-kicker">Projects</p>
            <h2 id="projects-heading">Project list</h2>
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
                <strong>{project.name}</strong>
                <span>{project.status}</span>
              </button>
            ))}
            {projects.length === 0 && loadState === "ready" ? (
              <p className="empty-state">No local projects found yet.</p>
            ) : null}
          </div>
        </section>
      </aside>

      <main className="content">
        <section className="hero-card" aria-labelledby="detail-heading">
          <div>
            <p className="section-kicker">Project detail</p>
            <h2 id="detail-heading">{projectDetail?.name ?? "Select a project"}</h2>
            <p className="meta-copy">
              {projectDetail?.root_storage_uri ??
                "Choose a project to inspect job state, timeline output, and review flags."}
            </p>
          </div>
          <nav className="section-tabs" aria-label="Workspace sections">
            {[
              ["overview", "Overview"],
              ["timeline", "Timeline summary"],
              ["review", "Review snapshot"],
              ["editing", "Editing session"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={selectedSection === value ? "tab-button is-active" : "tab-button"}
                onClick={() =>
                  setSelectedSection(value as "overview" | "timeline" | "review" | "editing")
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
              {isRebuildingTimeline ? "Rebuilding timeline..." : "Rebuild timeline draft"}
            </button>
            <button
              className="action-button"
              disabled={!canGenerateOutputs || isRenderingSubtitle}
              onClick={() => void handleRenderSubtitle()}
              type="button"
            >
              {isRenderingSubtitle ? "Generating subtitles..." : "Generate subtitle file"}
            </button>
            <button
              className="action-button"
              disabled={!canGenerateOutputs || isRenderingPreview}
              onClick={() => void handleRenderPreview()}
              type="button"
            >
              {isRenderingPreview ? "Rendering preview..." : "Render preview artifact"}
            </button>
            <button
              className="action-button"
              disabled={!canGenerateOutputs || isExportingCapcut}
              onClick={() => void handleExportCapcut()}
              type="button"
            >
              {isExportingCapcut ? "Exporting CapCut..." : "Export CapCut payload"}
            </button>
            <button
              className="action-button"
              disabled={!canApproveTimeline || isApprovingTimeline}
              onClick={() => void handleApproveTimeline()}
              type="button"
            >
              {isApprovingTimeline ? "Approving..." : "Approve timeline"}
            </button>
            <button
              className="action-button"
              disabled={!canReopenTimeline || isReopeningTimeline}
              onClick={() => void handleReopenTimeline()}
              type="button"
            >
              {isReopeningTimeline ? "Reopening..." : "Reopen review"}
            </button>
          </div>
        </section>

        {loadState === "loading" ? <p className="loading-banner">Loading local workspace...</p> : null}
        {loadState === "error" ? <p className="error-banner">{errorMessage}</p> : null}

        <section className="panel" aria-labelledby="status-heading">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Pipeline status</p>
              <h2 id="status-heading">Job status visibility</h2>
            </div>
          </div>
          <div className="status-grid">
            {stageStatus.map((stage) => (
              <article className="status-card" key={stage.jobType}>
                <span className="status-label">{stage.label}</span>
                <strong>{stage.status}</strong>
                <span className="status-meta">{stage.jobId}</span>
              </article>
            ))}
          </div>
        </section>

        {selectedSection === "overview" ? (
          <section className="workspace-grid">
            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Latest timeline</p>
                  <h2>Timeline summary</h2>
                </div>
              </div>
              {timelineJob ? (
                <dl className="summary-list">
                  <div>
                    <dt>Timeline ID</dt>
                    <dd>{timelineJob.timeline.timeline_id}</dd>
                  </div>
                  <div>
                    <dt>Output mode</dt>
                    <dd>{timelineJob.timeline.output_mode}</dd>
                  </div>
                  <div>
                    <dt>Track count</dt>
                    <dd>{timelineJob.timeline.tracks.length}</dd>
                  </div>
                  <div>
                    <dt>Review flags</dt>
                    <dd>{timelineJob.timeline.review_flags.length}</dd>
                  </div>
                  <div>
                    <dt>Review status</dt>
                    <dd>{reviewStatus}</dd>
                  </div>
                </dl>
              ) : (
                <p className="empty-state">No succeeded timeline build job yet.</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Review queue</p>
                  <h2>Review snapshot</h2>
                </div>
              </div>
              {reviewSnapshot ? (
                <dl className="summary-list">
                  <div>
                    <dt>Segments</dt>
                    <dd>{reviewSnapshot.segments.length}</dd>
                  </div>
                  <div>
                    <dt>Applied</dt>
                    <dd>{reviewSnapshot.applied_recommendations.length}</dd>
                  </div>
                  <div>
                    <dt>Pending</dt>
                    <dd>{reviewSnapshot.pending_recommendations.length}</dd>
                  </div>
                  <div>
                    <dt>Flags</dt>
                    <dd>{reviewSnapshot.review_flags.length}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{reviewSnapshot.review_status}</dd>
                  </div>
                </dl>
              ) : (
                <p className="empty-state">Build a timeline to unlock review snapshot data.</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Output artifacts</p>
                  <h2>Preview and export</h2>
                </div>
              </div>
              <dl className="summary-list">
                <div>
                  <dt>Subtitle job</dt>
                  <dd>{subtitleJob?.job_id ?? "not-started"}</dd>
                </div>
                <div>
                  <dt>Subtitle file</dt>
                  <dd>{subtitleJob?.subtitle.file_uri ?? "pending"}</dd>
                </div>
                <div>
                  <dt>Preview job</dt>
                  <dd>{previewJob?.job_id ?? "not-started"}</dd>
                </div>
                <div>
                  <dt>Preview artifact</dt>
                  <dd>{previewJob?.preview.artifact_kind ?? "pending"}</dd>
                </div>
                <div>
                  <dt>Export job</dt>
                  <dd>{exportJob?.job_id ?? "not-started"}</dd>
                </div>
                <div>
                  <dt>Export target</dt>
                  <dd>{exportJob?.export.export_type ?? "pending"}</dd>
                </div>
              </dl>
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Provider routing</p>
                  <h2>Gemini provider keys</h2>
                </div>
                <button
                  className="action-button"
                  onClick={openCreateGeminiForm}
                  type="button"
                >
                  Add Gemini key
                </button>
              </div>
              {isGeminiFormOpen ? (
                <div className="provider-form">
                  <label className="field">
                    <span>Label</span>
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
                      <span>API key</span>
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
                    <span>Primary model</span>
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
                    <span>Cheap model</span>
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
                    <span>High quality model</span>
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
                      {editingGeminiKeyId ? "Save changes" : "Save Gemini key"}
                    </button>
                    <button className="action-button" onClick={closeGeminiForm} type="button">
                      Cancel
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
                        <h3>{key.label}</h3>
                        <p className="meta-copy">{key.masked_api_key}</p>
                      </div>
                      <span className={`pill provider-status status-${key.status}`}>{key.status}</span>
                    </div>
                    <dl className="provider-key-details">
                      <div>
                        <dt>Primary model</dt>
                        <dd>{key.primary_model}</dd>
                      </div>
                      <div>
                        <dt>Cheap model</dt>
                        <dd>{key.cheap_model}</dd>
                      </div>
                      <div>
                        <dt>High quality model</dt>
                        <dd>{key.high_quality_model}</dd>
                      </div>
                      <div>
                        <dt>Consecutive failures</dt>
                        <dd>{key.consecutive_failures}</dd>
                      </div>
                      <div>
                        <dt>Cooldown until</dt>
                        <dd>{formatNullableValue(key.cooldown_until)}</dd>
                      </div>
                      <div>
                        <dt>Last used at</dt>
                        <dd>{formatNullableValue(key.last_used_at)}</dd>
                      </div>
                      <div>
                        <dt>Last error</dt>
                        <dd>{formatNullableValue(key.last_error)}</dd>
                      </div>
                    </dl>
                    <div className="action-row">
                      <button
                        aria-label={`Edit ${key.label}`}
                        className="action-button"
                        onClick={() => openEditGeminiForm(key)}
                        type="button"
                      >
                        Edit
                      </button>
                      <button
                        aria-label={`${key.status === "disabled" ? "Enable" : "Disable"} ${key.label}`}
                        className="action-button"
                        disabled={togglingGeminiKeyId === key.key_id}
                        onClick={() => void handleToggleGeminiKey(key)}
                        type="button"
                      >
                        {key.status === "disabled" ? "Enable" : "Disable"}
                      </button>
                    </div>
                  </article>
                ))}
                {geminiKeys.length === 0 && !geminiLoadError ? (
                  <p className="empty-state">No Gemini routing keys configured for this project.</p>
                ) : null}
              </div>
            </article>
          </section>
        ) : null}

        {selectedSection === "timeline" ? (
          <section className="panel" aria-labelledby="timeline-heading">
            <div className="panel-header">
              <div>
                <p className="section-kicker">Timeline summary</p>
                <h2 id="timeline-heading">Tracks and clip metadata</h2>
              </div>
            </div>
            {timelineJob ? (
              <div className="track-stack">
                {previewJob ? (
                  <article className="artifact-card">
                    <h3>{previewJob.preview.artifact_kind}</h3>
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
                    <h3>{exportJob.export.export_type}</h3>
                    <p>{exportJob.export.file_uri}</p>
                    <p>{exportJob.export.subtitle_file_uri ?? "No subtitle linked yet"}</p>
                    <p>{exportJob.export.notes[0]}</p>
                  </article>
                ) : null}
                {timelineJob.timeline.tracks.map((track) => (
                  <article className="track-card" key={track.track_id}>
                    <header className="track-header">
                      <div>
                        <h3>{track.track_type}</h3>
                        <p>{track.track_id}</p>
                      </div>
                      <span className="pill">{track.clips.length} clips</span>
                    </header>
                    <div className="clip-list">
                      {track.clips.map((clip) => (
                        <div className="clip-card" key={clip.clip_id}>
                          <strong>{clip.clip_id}</strong>
                          <span>{clip.segment_id}</span>
                          <span>{formatSeconds(clip.start_sec, clip.end_sec)}</span>
                          <span>{clip.asset_uri}</span>
                          <span>
                            Recommendation origin: {clip.recommendation_id ?? "manual narration base"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="empty-state">No timeline available for inspection.</p>
            )}
          </section>
        ) : null}

        {selectedSection === "review" ? (
          <section className="workspace-grid review-layout">
            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Review snapshot</p>
                  <h2>Segments</h2>
                </div>
              </div>
              <div className="segment-list">
                {reviewSnapshot?.segments.map((segment) => (
                  <div className="segment-card" key={segment.segment_id}>
                    <div className="segment-heading">
                      <strong>{segment.segment_id}</strong>
                      <span className={segment.review_required ? "pill warning" : "pill okay"}>
                        {segment.review_required ? "review required" : "ready"}
                      </span>
                    </div>
                    <p>{segment.text}</p>
                    <span>{formatSeconds(segment.start_sec, segment.end_sec)}</span>
                    <span>Confidence {segment.confidence.toFixed(2)}</span>
                    <button
                      className="action-button"
                      onClick={() => openSegmentInEditor(segment.segment_id)}
                      type="button"
                    >
                      Open {segment.segment_id} in editor
                    </button>
                  </div>
                )) ?? <p className="empty-state">No review snapshot data.</p>}
              </div>
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Recommendation review</p>
                  <h2>Applied and pending recommendations</h2>
                </div>
              </div>
              <div className="recommendation-groups">
                <div>
                  <h3>Auto-applied</h3>
                  {(reviewSnapshot?.applied_recommendations ?? []).map((item) => (
                    <div className="recommendation-card applied" key={item.recommendation_id}>
                      <strong>{item.recommendation_type}</strong>
                      <p>{item.reason}</p>
                      <span>{item.target_segment_id}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <h3>Pending review</h3>
                  {(reviewSnapshot?.pending_recommendations ?? []).map((item) => {
                    const mappedField = mapRecommendationTypeToEditingField(
                      item.recommendation_type,
                    );
                    return (
                      <div className="recommendation-card pending" key={item.recommendation_id}>
                        <strong>{prettifyJobType(item.recommendation_type)}</strong>
                        <p>{item.reason}</p>
                        <span>{item.target_segment_id}</span>
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
                          Review {item.target_segment_id} in editor
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
                  <p className="section-kicker">Flags and actions</p>
                  <h2>Review flags</h2>
                </div>
              </div>
              <div className="flag-list">
                {(reviewSnapshot?.review_flags ?? []).map((flag) => (
                  <div className="flag-card" key={`${flag.code}-${flag.segment_id}`}>
                    <strong>{prettifyJobType(flag.code)}</strong>
                    <p>{flag.message}</p>
                    <span>{flag.segment_id}</span>
                    <button
                      className="action-button"
                      onClick={() => openSegmentInEditor(flag.segment_id)}
                      type="button"
                    >
                      Inspect {flag.segment_id} in editor
                    </button>
                  </div>
                ))}
              </div>
              <div className="action-row">
                {reviewActions.map((action) => (
                  <button className="action-button" key={action} type="button">
                    {action}
                  </button>
                ))}
              </div>
            </article>
          </section>
        ) : null}

        {selectedSection === "editing" ? (
          <section className="workspace-grid review-layout">
            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Editing session</p>
                  <h2>Timeline-centered editor shell</h2>
                </div>
              </div>
              <div className="action-row">
                <button
                  className="action-button primary"
                  disabled={!latestTimelineBuildJob || isStartingEditingSession}
                  onClick={() => void handleStartEditingSession()}
                  type="button"
                >
                  {isStartingEditingSession ? "Starting editing session..." : "Start editing session"}
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
                      <dt>Session ID</dt>
                      <dd>{editingSession.session_id}</dd>
                    </div>
                    <div>
                      <dt>Timeline ID</dt>
                      <dd>{editingSession.timeline_id}</dd>
                    </div>
                    <div>
                      <dt>Segments</dt>
                      <dd>{editingSession.segments.length}</dd>
                    </div>
                    <div>
                      <dt>Mutation history</dt>
                      <dd>{editingSession.history.length}</dd>
                    </div>
                    <div>
                      <dt>Changed segments</dt>
                      <dd>{changedSegmentIds.size}</dd>
                    </div>
                    <div>
                      <dt>Preserved segments</dt>
                      <dd>{preservedEditingSegments.length}</dd>
                    </div>
                  </dl>
                  <label className="field">
                    <span>Target segment</span>
                    <select
                      onChange={(event) => handleSelectEditingSegment(event.target.value)}
                      value={selectedEditingSegmentId ?? ""}
                    >
                      {editingSession.segments.map((segment) => (
                        <option key={segment.segment_id} value={segment.segment_id}>
                          {`Target ${formatSeconds(segment.start_sec, segment.end_sec)}`}
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
                          {changedSegmentIds.has(segment.segment_id) ? "changed" : "preserved"}
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
                        ? "Requesting preflight..."
                        : "Request regeneration preflight"}
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
                        ? "Running partial regeneration..."
                        : "Run partial regeneration"}
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
                      <h3>Preflight scope</h3>
                      <div className="clip-list">
                        {partialRegenerationPreflight.segment_ids.map((segmentId) => (
                          <span key={segmentId}>{`${segmentId} included in preflight scope`}</span>
                        ))}
                      </div>
                      <div className="clip-list">
                        {partialRegenerationPreflight.fields.map((field) => (
                          <span key={field}>{`${formatFieldLabel(field)} field selected for preflight`}</span>
                        ))}
                      </div>
                      <p>
                        Preflight is read-only. The timeline draft stays unchanged until you run
                        partial regeneration.
                      </p>
                      {partialRegenerationPreflight.prediction_reasons.length > 0 ? (
                        <div className="clip-list">
                          {partialRegenerationPreflight.prediction_reasons.map((reason) => (
                            <span key={reason}>{reason}</span>
                          ))}
                        </div>
                      ) : null}
                      <h3>Expected affected output areas</h3>
                      <div className="clip-list">
                        {partialRegenerationPreflight.affected_output_areas.map((area) => (
                          <span key={area}>{formatAffectedOutputArea(area)}</span>
                        ))}
                      </div>
                      <h3>Downstream rerun steps</h3>
                      <div className="clip-list">
                        {partialRegenerationPreflight.downstream_steps.map((step) => (
                          <span key={step}>{step}</span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </>
              ) : (
                <p className="empty-state">Start an editing session from the latest timeline draft.</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Run validation</p>
                  <h2>Changed segment focus</h2>
                </div>
              </div>
              {editingSession ? (
                <>
                  {partialRegenerationRun ? (
                    <div className="track-card">
                      <h3>{partialRegenerationRun.job_id}</h3>
                      <p>{partialRegenerationRun.status}</p>
                      <p>{partialRegenerationRun.delta?.timeline_id ?? "timeline pending"}</p>
                      <h3>Resumed rerun scope</h3>
                      <p>{`${resumedScopeSegmentIds.length} ${resumedScopeSegmentIds.length === 1 ? "segment" : "segments"} in scope`}</p>
                      <div className="clip-list">
                        {resumedScopeSegmentIds.map((segmentId) => (
                          <span key={segmentId}>{`${segmentId} included in resumed scope`}</span>
                        ))}
                      </div>
                      <div className="clip-list">
                        {resumedScopeFields.map((field) => (
                          <span key={field}>{`${formatFieldLabel(field)} field resumed`}</span>
                        ))}
                      </div>
                      {resumedScopeSegmentIds.length > 1 ? (
                        <p>
                          Multi-segment resumed scope is readable here, but not mapped into
                          single-segment editor defaults.
                        </p>
                      ) : null}
                      <p>{`Changed segments ${changedSegmentIds.size}`}</p>
                      <p>{`Preserved segments ${preservedEditingSegments.length}`}</p>
                      {(partialRegenerationRun.delta?.regenerated_segments ?? []).map((segment) => (
                        <div className="clip-card" key={String(segment.segment_id ?? Math.random())}>
                          <strong>{`${String(segment.segment_id ?? "segment")} changed in current run`}</strong>
                          {Array.isArray(segment.output_changes)
                            ? (segment.output_changes as unknown[]).map((change) => (
                                <span key={String(change)}>{String(change)}</span>
                              ))
                            : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="empty-state">Run partial regeneration to inspect changed outputs.</p>
                  )}
                  <div>
                    <h3>Preserved timeline area</h3>
                    <div className="clip-list">
                      {preservedEditingSegments.map((segment) => (
                        <span key={segment.segment_id}>{`${segment.segment_id} preserved from prior timeline`}</span>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <p className="empty-state">No editing session loaded yet.</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Decision support</p>
                  <h2>Operator review decision loop</h2>
                </div>
              </div>
              {editingSession ? (
                partialRegenerationRun ? (
                  <>
                    <dl className="summary-list">
                      <div>
                        <dt>Ready changed segments</dt>
                        <dd>{readyChangedSegments.length}</dd>
                      </div>
                      <div>
                        <dt>Review blockers</dt>
                        <dd>{decisionBlockerCount}</dd>
                      </div>
                    </dl>
                    <p>{`Ready changed segments ${readyChangedSegments.length}`}</p>
                    <p>{`Review blockers ${decisionBlockerCount}`}</p>
                    <div className="track-card">
                      <h3>Changed segment readiness</h3>
                      <div className="clip-list">
                        {changedEditingSegments.map((segment) => (
                          <span key={segment.segment_id}>
                            {segment.review_required
                              ? `${segment.segment_id} still needs operator review`
                              : `${segment.segment_id} ready for operator sign-off`}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="track-card">
                      <h3>Changed output checklist</h3>
                      <div className="clip-list">
                        {changedOutputChecklist.map((item) => (
                          <span key={item}>{item}</span>
                        ))}
                      </div>
                    </div>
                    <div className="track-card">
                      <h3>Decision cue</h3>
                      <strong>{decisionCue?.title}</strong>
                      <p>{decisionCue?.body}</p>
                    </div>
                    <div className="track-card">
                      <h3>Preserved segment stability</h3>
                      <div className="clip-list">
                        {preservedEditingSegments.map((segment) => (
                          <span key={segment.segment_id}>
                            {`${segment.segment_id} remains stable outside the current rerun`}
                          </span>
                        ))}
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="empty-state">
                    Run partial regeneration to open the operator decision loop.
                  </p>
                )
              ) : (
                <p className="empty-state">No editing session loaded yet.</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Selected segment</p>
                  <h2>Selected segment detail</h2>
                </div>
              </div>
              {selectedEditingSegment && selectedEditingDraft ? (
                <div className="segment-card">
                  <div className="segment-heading">
                    <strong>Selected focus</strong>
                    <span
                      className={selectedEditingSegment.review_required ? "pill warning" : "pill okay"}
                    >
                      {selectedEditingSegment.review_required ? "review required" : "ready"}
                    </span>
                  </div>
                  <span>{formatSeconds(selectedEditingSegment.start_sec, selectedEditingSegment.end_sec)}</span>
                  <p>{selectedEditingDraft.captionText}</p>
                  <span>{selectedEditingDraft.brollAssetId || "No B-roll override"}</span>
                  <span>
                    {selectedEditingDraft.explanationText ? "Explanation card loaded" : "No explanation card"}
                  </span>
                  <span>{selectedEditingDraft.imageAssetId || "No image overlay"}</span>
                  <span>{selectedEditingDraft.tableText || "No table overlay"}</span>
                  <span>{selectedEditingDraft.ttsAssetId || "No TTS replacement"}</span>
                  <label className="field">
                    <span>Caption</span>
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
                    Save caption
                  </button>
                  <label className="field">
                    <span>Cut action</span>
                    <select
                      onChange={(event) =>
                        updateEditingDraft(selectedEditingSegment.segment_id, {
                          cutAction: event.target.value,
                        })
                      }
                      value={selectedEditingDraft.cutAction}
                    >
                      <option value="keep">keep</option>
                      <option value="remove">remove</option>
                      <option value="trim">trim</option>
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
                    Save cut action
                  </button>
                  <label className="field">
                    <span>B-roll asset ID</span>
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
                    Save B-roll override
                  </button>
                  <label className="field">
                    <span>Explanation title</span>
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
                    <span>Explanation body</span>
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
                    <span>Explanation text</span>
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
                    Save explanation card
                  </button>
                  {!selectedEditingDraft.explanationText ? (
                    <p
                      className="meta-copy"
                      id={`${selectedEditingSegment.segment_id}-explanation-save-help`}
                    >
                      Explanation text required before saving.
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
                        )
                      }
                      type="button"
                    >
                      Remove explanation card
                    </button>
                  ) : null}
                  <label className="field">
                    <span>Image overlay asset ID</span>
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
                    <span>Image overlay text</span>
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
                    Save image overlay
                  </button>
                  {!selectedEditingDraft.imageAssetId ? (
                    <p
                      className="meta-copy"
                      id={`${selectedEditingSegment.segment_id}-image-save-help`}
                    >
                      Image overlay asset ID required before saving.
                    </p>
                  ) : null}
                  {selectedEditingSegment.visual_overlays.some(
                    (overlay) => String(overlay.overlay_type ?? "") === "image_overlay",
                  ) ? (
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
                        )
                      }
                      type="button"
                    >
                      Remove image overlay
                    </button>
                  ) : null}
                  <label className="field">
                    <span>Table columns</span>
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
                    <span>Table rows</span>
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
                    <span>Table text</span>
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
                    Save table overlay
                  </button>
                  {!selectedEditingDraft.tableText ? (
                    <p
                      className="meta-copy"
                      id={`${selectedEditingSegment.segment_id}-table-save-help`}
                    >
                      Table text required before saving.
                    </p>
                  ) : null}
                  {selectedEditingSegment.visual_overlays.some(
                    (overlay) => String(overlay.overlay_type ?? "") === "table_overlay",
                  ) ? (
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
                        )
                      }
                      type="button"
                    >
                      Remove table overlay
                    </button>
                  ) : null}
                  <label className="field">
                    <span>TTS recommendation ID</span>
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
                    <span>TTS asset ID</span>
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
                    Save TTS replacement
                  </button>
                  {!selectedEditingDraft.ttsRecommendationId || !selectedEditingDraft.ttsAssetId ? (
                    <p
                      className="meta-copy"
                      id={`${selectedEditingSegment.segment_id}-tts-save-help`}
                    >
                      TTS recommendation ID and asset ID required before saving.
                    </p>
                  ) : null}
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
                        )
                      }
                      type="button"
                    >
                      Clear TTS replacement
                    </button>
                  ) : null}
                </div>
              ) : (
                <p className="empty-state">Choose a session segment to inspect its draft state.</p>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <p className="section-kicker">Timeline delta</p>
                  <h2>Track impact summary</h2>
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
                        <span className="pill">{track.clips.length} clips</span>
                      </header>
                      <div className="clip-list">
                        {track.clips.map((clip) => (
                          <div className="clip-card" key={clip.clip_id}>
                            <strong>{clip.segment_id}</strong>
                            <span>
                              {changedSegmentIds.has(clip.segment_id)
                                ? "changed in current run"
                                : "preserved from prior timeline"}
                            </span>
                            <span>{clip.asset_uri}</span>
                          </div>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="empty-state">No regenerated timeline available yet.</p>
              )}
            </article>
          </section>
        ) : null}
      </main>
    </div>
  );
}
