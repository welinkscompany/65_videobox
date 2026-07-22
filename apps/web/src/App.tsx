import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  ApiConflictError,
  type BrollAsset,
  type CapCutDraftExportJob,
  type CapCutHandoffDiagnostics,
  type CaptionStyleScope,
  type CaptionStyleScopePreflight,
  type EditorFavorite,
  type EditorPreset,
  type EditingSession,
  type EditingSessionSegment,
  type ExportJob,
  type FinalRenderJob,
  type JobRecord,
  type PartialRegenerationPreflight,
  type PartialRegenerationRun,
  type PreviewJob,
  type Project,
  type RecommendationItem,
  type ReviewSnapshot,
  type SelectedRangePreview,
  type SubtitleJob,
  type TimelineJob,
  type TtsCandidateRecord,
  type JobRecordWithProject,
  type MediaLibraryAsset,
  type MediaLibraryInstallState,
  type AssetResponse,
} from "./api";
import { MediaAnalysisPanel } from "./features/media/MediaAnalysisPanel";
import { ManualMediaLibrary } from "./features/media/ManualMediaLibrary";
import { DirectorWorkspacePanel } from "./features/director/DirectorWorkspacePanel";
import type { DirectorWorkspaceState } from "./features/director/directorTypes";
import {
  buildDefaultEditingSelection,
  buildDefaultRegenerationFields,
  buildEditingDrafts,
  canResumeCandidate,
  type EditingMutationFeedback,
  type EditingSegmentDraft,
  findLatestSucceededJob,
  findLatestJob,
  findLatestTimelineJob,
  formatAffectedOutputArea,
  formatDisplayText,
  formatEditingMutationFeedbackLabel,
  formatFieldLabel,
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
import type { WorkspaceSection } from "./app/routeManifest";
import { VideoBoxEditorAdapter, type EditorControls, type EditorViewModel } from "./features/editor/editorViewModel";
import { createEditorCommandPort } from "./features/editor/editorCommandPort";
import { projectLegacySession } from "./features/editor/legacySessionProjection";

type LegacySection = "overview" | "timeline" | "review" | "editing" | "settings";

export type LegacyWorkspacePageProps = {
  /** Undefined retains the pre-router test harness; a route value is authoritative. */
  projectId?: string | null;
  section?: WorkspaceSection;
  /** A route-selected durable session takes precedence over the latest session. */
  editingSessionId?: string | null;
  onNavigate?: (projectId: string, section: WorkspaceSection) => void;
  catalogProjects?: Project[];
  onProjectCreated?: (project: Project) => void | Promise<void>;
};

const routeSectionToLegacy: Record<WorkspaceSection, LegacySection> = {
  home: "overview",
  create: "overview",
  timeline: "timeline",
  review: "review",
  editing: "editing",
  settings: "settings",
  media: "timeline",
  outputs: "review",
};

const legacySectionToRoute: Record<LegacySection, WorkspaceSection> = {
  overview: "home",
  timeline: "timeline",
  review: "review",
  editing: "editing",
  settings: "settings",
};

function readEditorControls(override: Record<string, unknown> | null | undefined): EditorControls | undefined {
  const controls = readRecordValue(override?.media_controls);
  if (!controls) return undefined;
  return {
    volume: typeof controls.volume === "number" ? controls.volume : undefined,
    crop: typeof controls.crop === "string" ? controls.crop : undefined,
    speed: typeof controls.speed === "number" ? controls.speed : undefined,
    fadeInSec: typeof controls.fade_in_sec === "number" ? controls.fade_in_sec : undefined,
    fadeOutSec: typeof controls.fade_out_sec === "number" ? controls.fade_out_sec : undefined,
  };
}

export function App({
  projectId: routeProjectId,
  section: routeSection,
  editingSessionId: routeEditingSessionId,
  onNavigate,
  catalogProjects,
  onProjectCreated,
}: LegacyWorkspacePageProps = {}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [onboardingProject, setOnboardingProject] = useState<Project | null>(null);
  const [legacyProjectId, setLegacyProjectId] = useState<string | null>(null);
  const [legacySection, setLegacySection] = useState<LegacySection>("overview");
  const selectedProjectId = routeProjectId === undefined ? legacyProjectId : routeProjectId;
  const selectedSection = routeSection === undefined ? legacySection : routeSectionToLegacy[routeSection];
  const activeRouteSection = routeSection ?? legacySectionToRoute[selectedSection];

  function selectProject(projectId: string, section: WorkspaceSection = "home") {
    if (onNavigate) {
      onNavigate(projectId, section);
      return;
    }
    setLegacyProjectId(projectId);
    setLegacySection(routeSectionToLegacy[section]);
  }

  function selectSection(section: LegacySection) {
    if (onNavigate && selectedProjectId) {
      onNavigate(selectedProjectId, legacySectionToRoute[section]);
      return;
    }
    setLegacySection(section);
  }
  const [projectDetail, setProjectDetail] = useState<Project | null>(null);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [timelineJob, setTimelineJob] = useState<TimelineJob | null>(null);
  const [reviewSnapshot, setReviewSnapshot] = useState<ReviewSnapshot | null>(null);
  const [editingSession, setEditingSession] = useState<EditingSession | null>(null);
  const [routedEditorView, setRoutedEditorView] = useState<EditorViewModel | null>(null);
  const [routedEditorViewMessage, setRoutedEditorViewMessage] = useState<string | null>(null);
  const [editingDrafts, setEditingDrafts] = useState<Record<string, EditingSegmentDraft>>({});
  const editingDraftsRef = useRef<Record<string, EditingSegmentDraft>>({});
  const editingUserEditsRef = useRef<Record<string, Partial<EditingSegmentDraft>>>({});
  const preserveEditingDraftsForSessionIdRef = useRef<string | null>(null);
  const [selectedEditingSegmentId, setSelectedEditingSegmentId] = useState<string | null>(null);
  const [selectedRegenerationFields, setSelectedRegenerationFields] = useState<string[]>([]);
  const [partialRegenerationPreflight, setPartialRegenerationPreflight] =
    useState<PartialRegenerationPreflight | null>(null);
  const [partialRegenerationRun, setPartialRegenerationRun] =
    useState<PartialRegenerationRun | null>(null);
  const [subtitleJob, setSubtitleJob] = useState<SubtitleJob | null>(null);
  const [previewJob, setPreviewJob] = useState<PreviewJob | null>(null);
  const [lastSuccessfulPreviewJob, setLastSuccessfulPreviewJob] = useState<PreviewJob | null>(null);
  const [exportJob, setExportJob] = useState<ExportJob | null>(null);
  const [finalRenderJob, setFinalRenderJob] = useState<FinalRenderJob | null>(null);
  const [lastSuccessfulFinalRenderJob, setLastSuccessfulFinalRenderJob] = useState<FinalRenderJob | null>(null);
  const [capcutDraftJob, setCapcutDraftJob] = useState<CapCutDraftExportJob | null>(null);
  const [lastSuccessfulCapcutDraftJob, setLastSuccessfulCapcutDraftJob] = useState<CapCutDraftExportJob | null>(null);
  const playableFinalRenderJob = [finalRenderJob, lastSuccessfulFinalRenderJob].find((job) => {
    const render = job?.render;
    return job?.status === "succeeded" && render && render.is_current === true &&
      (!editingSession || (render.timeline_id === editingSession.timeline_id &&
        (render.source_session_revision != null && render.source_session_revision === editingSession.session_revision)));
  }) ?? null;
  const finalRenderNeedsRefresh = Boolean(
    ([finalRenderJob, lastSuccessfulFinalRenderJob].some((job) =>
      job?.status === "succeeded" && job.render && !(
        job.render.is_current === true &&
        (!editingSession || (
          job.render.timeline_id === editingSession.timeline_id &&
          job.render.source_session_revision != null &&
          job.render.source_session_revision === editingSession.session_revision
        ))
      ),
    )),
  );
  // A route-pinned editor session may share a timeline/revision with an older
  // legacy render. Only its manifest has session provenance, so that route
  // owns exact playback and the legacy fallback remains for unpinned views.
  const canShowLegacyFinalRender = !routeEditingSessionId;
  const routedEditorCommandPort = useMemo(
    () => routedEditorView
      ? createEditorCommandPort({
          projectId: routedEditorView.projectId,
          sessionId: routedEditorView.sessionId,
          expectedRevision: routedEditorView.expectedRevision,
        })
      : null,
    [routedEditorView],
  );
  const [isRegisteringCapcutHandoff, setIsRegisteringCapcutHandoff] = useState(false);
  const [capcutHandoffDiagnostics, setCapcutHandoffDiagnostics] = useState<CapCutHandoffDiagnostics | null>(null);
  const [isLoadingCapcutHandoffDiagnostics, setIsLoadingCapcutHandoffDiagnostics] = useState(false);
  const [capcutHandoffDiagnosticsError, setCapcutHandoffDiagnosticsError] = useState<string | null>(null);
  const [voiceSamplePath, setVoiceSamplePath] = useState("");
  const [voiceSampleFile, setVoiceSampleFile] = useState<File | null>(null);
  const [voiceSamples, setVoiceSamples] = useState<AssetResponse[]>([]);
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
  const [isReviewingTtsCandidate, setIsReviewingTtsCandidate] = useState<string | null>(null);
  const [brollAssets, setBrollAssets] = useState<BrollAsset[]>([]);
  const [brollAssetLoadError, setBrollAssetLoadError] = useState<string | null>(null);
  const [brollFolderPath, setBrollFolderPath] = useState(
    "D:\\AI_Workspace_louis_office_50\\20_project\\65_videobox-project\\비롤_라이브러리\\검수완료",
  );
  const [brollSourcePaths, setBrollSourcePaths] = useState("");
  const [brollImportTags, setBrollImportTags] = useState("");
  const [brollImportError, setBrollImportError] = useState<string | null>(null);
  const [brollImportMessage, setBrollImportMessage] = useState<string | null>(null);
  const [isImportingBroll, setIsImportingBroll] = useState(false);
  const [editingSessionRestoreError, setEditingSessionRestoreError] = useState<string | null>(null);
  const [partialRegenerationRestoreWarning, setPartialRegenerationRestoreWarning] = useState<
    string | null
  >(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [editingMutationFeedback, setEditingMutationFeedback] =
    useState<EditingMutationFeedback>(null);
  const [pendingEditingConflict, setPendingEditingConflict] = useState<{
    session: EditingSession;
    drafts: Record<string, Partial<EditingSegmentDraft>>;
  } | null>(null);
  const [editorPresets, setEditorPresets] = useState<EditorPreset[]>([]);
  const [editorFavorites, setEditorFavorites] = useState<EditorFavorite[]>([]);
  const [recentPresetIds, setRecentPresetIds] = useState<string[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const [captionStyleScope, setCaptionStyleScope] = useState<CaptionStyleScope>("current_caption");
  const [captionStylePreflight, setCaptionStylePreflight] = useState<CaptionStyleScopePreflight | null>(null);
  const [brollFit, setBrollFit] = useState<"fit" | "crop">("fit");
  const [brollLoop, setBrollLoop] = useState(true);
  const [brollPad, setBrollPad] = useState(false);
  const [brollTrimStartSec, setBrollTrimStartSec] = useState(0);
  const [audioGainDb, setAudioGainDb] = useState(0);
  const [audioFadeInSec, setAudioFadeInSec] = useState(0);
  const [audioFadeOutSec, setAudioFadeOutSec] = useState(0);
  const [audioDucking, setAudioDucking] = useState(false);
  const [mediaLibraryAssets, setMediaLibraryAssets] = useState<MediaLibraryAsset[]>([]);
  const [mediaLibraryFavoriteIds, setMediaLibraryFavoriteIds] = useState<string[]>([]);
  const [recentMediaLibraryAssetIds, setRecentMediaLibraryAssetIds] = useState<string[]>([]);
  const [mediaLibraryError, setMediaLibraryError] = useState<string | null>(null);
  const [directorWorkspaceState, setDirectorWorkspaceState] = useState<DirectorWorkspaceState>("idle");
  const [mediaLibraryInstallState, setMediaLibraryInstallState] = useState<MediaLibraryInstallState | null>(null);
  const [mediaLibraryFilter, setMediaLibraryFilter] = useState("");
  const [mediaLibraryView, setMediaLibraryView] = useState<"all" | "favorites" | "recent">("all");
  const [previewLibraryAssetId, setPreviewLibraryAssetId] = useState<string | null>(null);
  const [selectedRangeStartSec, setSelectedRangeStartSec] = useState(0);
  const [selectedRangeEndSec, setSelectedRangeEndSec] = useState(0);
  const [selectedRangePreview, setSelectedRangePreview] = useState<SelectedRangePreview | null>(null);
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

  async function refreshCapcutHandoffDiagnostics() {
    setIsLoadingCapcutHandoffDiagnostics(true);
    try {
      const diagnostics = await api.getCapcutHandoffDiagnostics();
      setCapcutHandoffDiagnostics(diagnostics);
      setCapcutHandoffDiagnosticsError(null);
    } catch (error) {
      setCapcutHandoffDiagnosticsError(
        "연결 상태를 확인하지 못했어요. 다시 시도해 주세요.",
      );
    } finally {
      setIsLoadingCapcutHandoffDiagnostics(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function loadProjects() {
      if (catalogProjects) {
        setProjects(catalogProjects);
        setLoadState("ready");
        return;
      }
      setLoadState("loading");
      setErrorMessage(null);
      try {
        const projectItems = await api.listProjects();
        if (cancelled) {
          return;
        }
        setProjects(projectItems);
        // The standalone compatibility export is only retained for the legacy suite.
        // AppRoot always supplies a route project id and never falls back to this value.
        if (routeProjectId === undefined) {
          setLegacyProjectId((current) => current ?? projectItems[0]?.project_id ?? null);
        }
        setLoadState("ready");
      } catch (error) {
        if (cancelled) {
          return;
        }
        setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
        setLoadState("error");
      }
    }

    void loadProjects();
    return () => {
      cancelled = true;
    };
  }, [catalogProjects, routeProjectId]);

  useEffect(() => {
    void refreshCapcutHandoffDiagnostics();
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!selectedProjectId) return () => { cancelled = true; };
    void Promise.all([api.getMediaLibraryInstallState(), api.listMediaLibraryAssets(), api.listProjectMediaLibraryFavorites(selectedProjectId), api.listProjectRecentMediaLibraryAssetIds(selectedProjectId)]).then(
      ([installState, assets, favorites, recent]) => {
        if (cancelled) return;
        setMediaLibraryAssets(assets.assets);
        setMediaLibraryInstallState(installState);
        setMediaLibraryFavoriteIds(favorites.asset_ids);
        setRecentMediaLibraryAssetIds(recent.asset_ids);
        setMediaLibraryError(null);
      },
      () => {
        if (!cancelled) setMediaLibraryError("미디어 라이브러리를 사용할 수 없습니다. 프로젝트 편집은 계속할 수 있습니다.");
      },
    );
    return () => { cancelled = true; };
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) {
      setEditorPresets([]);
      setEditorFavorites([]);
      setRecentPresetIds([]);
      return;
    }
    let cancelled = false;
    void Promise.all([
      api.listEditorPresets(selectedProjectId),
      api.listEditorFavorites(selectedProjectId),
      api.listRecentEditorPresetIds(selectedProjectId),
    ]).then(([presets, favorites, recent]) => {
      if (cancelled) return;
      setEditorPresets(presets);
      setEditorFavorites(favorites);
      setRecentPresetIds(recent);
      setSelectedPresetId((current) => current || presets[0]?.preset_id || "");
    }).catch((error) => {
      if (!cancelled) setErrorMessage("프리셋을 불러오지 못했어요. 다시 시도해 주세요.");
    });
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId || !editingSession || !selectedPresetId) return;
    const preset = editorPresets.find((item) => item.preset_id === selectedPresetId);
    if (!preset) return;
    const timer = window.setTimeout(() => {
      const segmentIds = captionStyleScope === "whole_project" || captionStyleScope === "project_default"
        ? []
        : selectedEditingSegmentId ? [selectedEditingSegmentId] : [];
      void api.previewEditingSessionCaptionStyleScope(selectedProjectId, editingSession.session_id, {
        expected_revision: editingSession.session_revision,
        scope: captionStyleScope,
        segment_ids: segmentIds,
        style: preset.style,
      }).then(setCaptionStylePreflight).catch(() => undefined);
    }, 800);
    return () => window.clearTimeout(timer);
  }, [captionStyleScope, editingSession, editorPresets, selectedEditingSegmentId, selectedPresetId, selectedProjectId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedProjectId) {
      return () => {
        cancelled = true;
      };
    }
    void api.listVoiceSamples(selectedProjectId).then(
      (assets) => {
        if (cancelled) {
          return;
        }
        setVoiceSamples(assets);
        if (assets.length === 0) return;
        const latestAssetId = assets[0].asset_id;
        setVoiceSampleAssetId((current) => current || latestAssetId);
        setTtsCandidateVoiceSampleId((current) => current || latestAssetId);
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) {
      setProjectDetail(null);
      setJobs([]);
      setTimelineJob(null);
      setReviewSnapshot(null);
      setEditingSession(null);
      setRoutedEditorView(null);
      setRoutedEditorViewMessage(null);
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
      setBrollImportError(null);
      setBrollImportMessage(null);
      return;
    }

    let cancelled = false;
    const projectId = selectedProjectId;

    async function loadProjectWorkspace() {
      setLoadState("loading");
      setErrorMessage(null);
      setBrollAssetLoadError(null);
      setBrollImportError(null);
      setBrollImportMessage(null);
      setEditingSessionRestoreError(null);
      setRoutedEditorView(null);
      setRoutedEditorViewMessage(null);
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
          latestEditingSession = routeEditingSessionId
            ? await api.getEditingSession(projectId, routeEditingSessionId)
            : await api.getLatestEditingSession(projectId);
        } catch (error) {
          setEditingSessionRestoreError(
            "편집 세션 복구 실패 · 기존 타임라인 유지",
          );
          latestEditingSession = null;
        }
        let selectedEditorView: EditorViewModel | null = null;
        let selectedEditorViewMessage: string | null = null;
        if (routeEditingSessionId && latestEditingSession) {
          try {
            const manifest = await api.getEditorPlaybackManifest(projectId, routeEditingSessionId);
            if (manifest.project_id !== projectId || manifest.session_id !== routeEditingSessionId) {
              throw new Error("The selected editing session does not match its playback manifest.");
            }
            selectedEditorView = new VideoBoxEditorAdapter(manifest).viewModel;
          } catch {
            selectedEditorViewMessage = "재생 내용을 불러오지 못했어요. 새로고침 후 다시 확인해 주세요.";
          }
        }
        const latestTimelineJob = findLatestTimelineJob(
          routeEditingSessionId && latestEditingSession
            ? jobItems.filter((job) => (
              job.job_type === "timeline_build" &&
              job.output_ref === latestEditingSession.timeline_id
            ))
            : jobItems,
        );
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
        const latestFinalRenderJob = latestTimelineJob
          ? findLatestSucceededJob(jobItems, "final_render", latestTimelineJob.job_id)
          : null;
        const latestCapcutDraftJob = latestTimelineJob
          ? findLatestSucceededJob(jobItems, "capcut_draft_export", latestTimelineJob.job_id)
          : null;
        const latestCapcutDraftAttemptJob = latestTimelineJob
          ? findLatestJob(jobItems, "capcut_draft_export", latestTimelineJob.job_id)
          : null;
        const [subtitle, preview, capcutExport, finalRender, capcutDraft, lastSuccessfulCapcutDraft] = await Promise.all([
          latestSubtitleJob ? api.getSubtitle(projectId, latestSubtitleJob.job_id) : Promise.resolve(null),
          latestPreviewJob ? api.getPreview(projectId, latestPreviewJob.job_id) : Promise.resolve(null),
          latestExportJob ? api.getExport(projectId, latestExportJob.job_id) : Promise.resolve(null),
          latestFinalRenderJob ? api.getFinalRender(projectId, latestFinalRenderJob.job_id) : Promise.resolve(null),
          latestCapcutDraftAttemptJob
            ? api.getCapcutDraftExport(projectId, latestCapcutDraftAttemptJob.job_id)
            : Promise.resolve(null),
          latestCapcutDraftJob && latestCapcutDraftJob.job_id !== latestCapcutDraftAttemptJob?.job_id
            ? api.getCapcutDraftExport(projectId, latestCapcutDraftJob.job_id)
            : Promise.resolve(null),
        ]);
        let activeTimeline = stableTimeline;
        let activeReview = stableReview;
        let resumedSelection: { segmentId: string | null; fields: string[] } | null = null;
        let resumedPartialRegenerationPreflight: PartialRegenerationPreflight | null = null;
        let resumedPartialRegeneration: PartialRegenerationRun | null = null;
        let resumedPartialRegenerationRestoreWarning: string | null = null;
        let activeSubtitle = subtitle;
        let activePreview = preview;
        let activeExport = capcutExport;
        if (latestEditingSession && !routeEditingSessionId) {
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
        setRoutedEditorView(selectedEditorView);
        setRoutedEditorViewMessage(selectedEditorViewMessage);
        if (latestEditingSession && (!routeEditingSessionId || selectedEditorView)) {
          applyEditingSessionState(routeEditingSessionId && selectedEditorView
            ? projectLegacySession(selectedEditorView)
            : latestEditingSession);
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
        setFinalRenderJob(finalRender);
        setLastSuccessfulFinalRenderJob(finalRender?.status === "succeeded" ? finalRender : null);
        setCapcutDraftJob(capcutDraft);
        setLastSuccessfulCapcutDraftJob(
          capcutDraft?.status === "succeeded" ? capcutDraft : lastSuccessfulCapcutDraft,
        );
        setBrollAssets(archivedBrollAssets);
        setLoadState("ready");
      } catch (error) {
        if (cancelled) {
          return;
        }
        setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
        setLoadState("error");
      }
    }

    void loadProjectWorkspace();
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId, routeEditingSessionId]);

  useEffect(() => {
    if (routeEditingSessionId || !selectedProjectId || !selectedEditingSegmentId) {
      setTtsCandidates([]);
      return;
    }
    void loadTtsCandidates(selectedEditingSegmentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeEditingSessionId, selectedProjectId, selectedEditingSegmentId]);

  const latestTimelineBuildJob = useMemo(
    () => findLatestTimelineJob(
      routeEditingSessionId && editingSession
        ? jobs.filter((job) => (
          job.job_type === "timeline_build" &&
          job.output_ref === editingSession.timeline_id
        ))
        : jobs,
    ),
    [editingSession, jobs, routeEditingSessionId],
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
    const drafts = buildEditingDrafts(session);
    if (preserveEditingDraftsForSessionIdRef.current === session.session_id) {
      const merged = Object.fromEntries(
        Object.entries(drafts).map(([segmentId, draft]) => [
          segmentId,
          editingDraftsRef.current[segmentId] ?? draft,
        ]),
      ) as Record<string, EditingSegmentDraft>;
      editingDraftsRef.current = merged;
      setEditingDrafts(merged);
    } else {
      editingDraftsRef.current = drafts;
      setEditingDrafts(drafts);
    }
    const selection = buildDefaultEditingSelection(session);
    setSelectedEditingSegmentId((current) => current ?? selection.segmentId);
    setSelectedRegenerationFields((current) =>
      current.length > 0 ? current : selection.fields,
    );
  }

  function applyLatestEditingSessionAfterConflict(
    session: EditingSession,
    preservedEdits: Record<string, Partial<EditingSegmentDraft>>,
  ) {
    preserveEditingDraftsForSessionIdRef.current = session.session_id;
    setEditingSession(session);
    const refreshed = buildEditingDrafts(session);
    const next = Object.fromEntries(
      Object.entries(refreshed).map(([segmentId, draft]) => [
        segmentId,
        { ...draft, ...preservedEdits[segmentId] },
      ]),
    ) as Record<string, EditingSegmentDraft>;
    editingDraftsRef.current = next;
    setEditingDrafts(next);
    const preservedSegmentId = session.segments.find((segment) => {
      const latestDraft = refreshed[segment.segment_id];
      const preserved = preservedEdits[segment.segment_id];
      return Boolean(preserved && Object.keys(preserved).length > 0);
    })?.segment_id;
    setSelectedEditingSegmentId(
      preservedSegmentId ??
        (selectedEditingSegmentId &&
        session.segments.some((segment) => segment.segment_id === selectedEditingSegmentId)
          ? selectedEditingSegmentId
          : buildDefaultEditingSelection(session).segmentId),
    );
  }

  function updateEditingDraft(
    segmentId: string,
    patch: Partial<EditingSegmentDraft>,
  ) {
    const next = {
      ...editingDraftsRef.current,
      [segmentId]: {
        ...editingDraftsRef.current[segmentId],
        ...patch,
      },
    };
    editingUserEditsRef.current = {
      ...editingUserEditsRef.current,
      [segmentId]: {
        ...editingUserEditsRef.current[segmentId],
        ...patch,
      },
    };
    editingDraftsRef.current = next;
    setEditingDrafts(next);
  }

  async function applyEditingMutation(
    mutationKey: string,
    action: () => Promise<EditingSession>,
    options?: {
      addRegenerationField?: string;
      feedbackAction?: "저장" | "해제" | "삭제";
      removeRegenerationField?: string;
      onSuccess?: () => void;
    },
  ) {
    if (routeEditingSessionId && !routedEditorCommandPort) {
      setEditingMutationFeedback({ kind: "error", message: "편집 내용을 불러온 뒤 다시 시도해 주세요." });
      return null as never;
    }
    const feedbackLabel = formatEditingMutationFeedbackLabel(mutationKey);
    const feedbackAction = options?.feedbackAction ?? "저장";
    setIsSavingEditingMutation(mutationKey);
    setErrorMessage(null);
    setEditingMutationFeedback(null);
    try {
      const session = await action();
      editingUserEditsRef.current = {};
      if (routeEditingSessionId) {
        setRoutedEditorView((current) => current
          ? {
              ...current,
              expectedRevision: session.session_revision,
              source: { ...current.source, status: "stale" },
              playback: { ...current.playback, exactPreview: { ...current.playback.exactPreview, status: "stale", url: null } },
            }
          : current);
      }
      applyEditingSessionState(session);
      options?.onSuccess?.();
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
      return session;
    } catch (error) {
      if (error instanceof ApiConflictError) {
        setPendingEditingConflict({
          session: error.latestSession as EditingSession,
          drafts: { ...editingUserEditsRef.current },
        });
        setEditingMutationFeedback({
          kind: "error",
          message: "다른 편집 내용이 있습니다 · 내 입력은 유지됩니다",
        });
      } else {
        const message = "요청을 완료하지 못했어요. 다시 시도해 주세요.";
        setErrorMessage(message);
        setEditingMutationFeedback({
          kind: "error",
          message: `${feedbackLabel} ${feedbackAction} 실패 · ${message}`,
        });
      }
      return null;
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
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
    } finally {
      setIsStartingEditingSession(false);
    }
  }

  async function handleRequestRegenerationPreflight() {
    if (
      routeEditingSessionId ||
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
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
    } finally {
      setIsRequestingRegenerationPreflight(false);
    }
  }

  async function handleRunPartialRegeneration() {
    if (
      routeEditingSessionId ||
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
          expected_revision: editingSession.session_revision,
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
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
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
    selectSection("timeline");
    } catch (error) {
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
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
      if (preview.status === "succeeded") setLastSuccessfulPreviewJob(preview);
      if (preview.status === "failed") setErrorMessage("미리보기 실패: 결과 파일을 만들지 못했습니다.");
    } catch (error) {
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
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
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
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
      if (finalRender.status === "succeeded") setLastSuccessfulFinalRenderJob(finalRender);
      if (finalRender.status === "failed") {
        setErrorMessage("완성본을 만들지 못했어요. 다시 시도해 주세요.");
      }
    } catch (error) {
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
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
      if (capcutDraftExport.status === "succeeded") setLastSuccessfulCapcutDraftJob(capcutDraftExport);
      if (capcutDraftExport.status === "failed") {
        setErrorMessage(
          "초안을 만들지 못했어요. 다시 시도해 주세요.",
        );
      }
    } catch (error) {
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
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
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
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
      setAllJobsError("작업 목록을 불러오지 못했어요. 다시 시도해 주세요.");
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
      setVoiceSampleMessage("내 목소리를 추가했어요.");
    } catch (error) {
      setVoiceSampleError(
        "내 목소리를 추가하지 못했어요. 다시 시도해 주세요.",
      );
    } finally {
      setIsRegisteringVoiceSample(false);
    }
  }

  async function loadTtsCandidates(segmentId: string) {
    if (routeEditingSessionId) {
      return;
    }
    if (routeEditingSessionId || !selectedProjectId) {
      return;
    }
    setIsLoadingTtsCandidates(true);
    try {
      const result = await api.listTtsCandidates(selectedProjectId, segmentId);
      setTtsCandidates(result.candidates);
    } catch (error) {
      setTtsCandidateError(
        "목소리 후보를 불러오지 못했어요. 다시 시도해 주세요.",
      );
    } finally {
      setIsLoadingTtsCandidates(false);
    }
  }

  async function handleGenerateTtsCandidate(segmentId: string, segmentText: string, targetDurationSec: number) {
    if (routeEditingSessionId || !selectedProjectId || !ttsCandidateVoiceSampleId.trim() || !segmentText.trim()) {
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
        target_duration_sec: targetDurationSec,
      });
      if (asset.technical_status === "accepted") {
        setTtsCandidateMessage("후보를 만들었어요. 들어 보고 사용할지 골라주세요.");
      } else {
        setTtsCandidateMessage("목소리 후보를 지금은 만들지 못했어요. 다른 후보를 만들어 보세요.");
      }
      await loadTtsCandidates(segmentId);
    } catch (error) {
      setTtsCandidateError(
        "목소리 후보를 만들지 못했어요. 다시 시도해 주세요.",
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
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
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
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
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
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
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
      setErrorMessage("요청을 완료하지 못했어요. 다시 시도해 주세요.");
    } finally {
      setIsRenderingSubtitle(false);
    }
  }

  async function refreshBrollAssets(projectId: string) {
    const assets = await api.listBrollAssets(projectId);
    setBrollAssets(assets);
    setBrollAssetLoadError(null);
  }

  async function handleImportBrollBatch() {
    if (routeEditingSessionId || !selectedProjectId) {
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
        "B롤을 가져오지 못했어요. 다시 시도해 주세요.",
      );
      setBrollImportMessage(null);
    } finally {
      setIsImportingBroll(false);
    }
  }

  const selectedEditingSegment =
    editingSession?.segments.find((segment) => segment.segment_id === selectedEditingSegmentId) ?? null;
  const selectedEditingDraft = selectedEditingSegmentId
    ? editingDrafts[selectedEditingSegmentId]
    : undefined;
  const selectedBrollControls = readEditorControls(selectedEditingSegment?.broll_override);
  const selectedMusicControls = readEditorControls(selectedEditingSegment?.music_override);
  const selectedSfxControls = readEditorControls(selectedEditingSegment?.sfx_override);
  const activeEditingSessionId = editingSession?.session_id ?? null;

  useEffect(() => {
    const audioControls = selectedMusicControls ?? selectedSfxControls;
    setAudioFadeInSec(audioControls?.fadeInSec ?? 0);
    setAudioFadeOutSec(audioControls?.fadeOutSec ?? 0);
    setBrollFit(selectedBrollControls?.crop === "crop" ? "crop" : "fit");
  }, [selectedBrollControls?.crop, selectedMusicControls?.fadeInSec, selectedMusicControls?.fadeOutSec, selectedSfxControls?.fadeInSec, selectedSfxControls?.fadeOutSec]);
  const visibleMediaLibraryAssets = useMemo(() => {
    const search = mediaLibraryFilter.trim().toLowerCase();
    return mediaLibraryAssets.filter((asset) => {
      if (mediaLibraryView === "favorites" && !mediaLibraryFavoriteIds.includes(asset.library_asset_id)) return false;
      if (mediaLibraryView === "recent" && !recentMediaLibraryAssetIds.includes(asset.library_asset_id)) return false;
      const searchTerms = [asset.asset_id, asset.media_type === "music" ? "bgm music" : "sfx", ...asset.tags, String(asset.duration_seconds)].join(" ").toLowerCase();
      return !search || searchTerms.includes(search);
    });
  }, [mediaLibraryAssets, mediaLibraryFavoriteIds, mediaLibraryFilter, mediaLibraryView, recentMediaLibraryAssetIds]);

  async function toggleMediaLibraryFavorite(asset: MediaLibraryAsset) {
    if (!selectedProjectId) return;
    try {
      const result = await api.setProjectMediaLibraryFavorite(selectedProjectId, asset.library_asset_id, !mediaLibraryFavoriteIds.includes(asset.library_asset_id));
      setMediaLibraryFavoriteIds(result.asset_ids);
    } catch {
      setMediaLibraryError("미디어 즐겨찾기를 저장할 수 없습니다. 프로젝트 편집은 계속할 수 있습니다.");
    }
  }

  async function applyMediaLibraryAsset(asset: MediaLibraryAsset) {
    if (!selectedProjectId || !activeEditingSessionId || !selectedEditingSegment || !editingSession || !asset.available || !asset.verified) return;
    const field = asset.media_type === "music" ? "music" : "sfx";
    await applyEditingMutation(
      `${selectedEditingSegment.segment_id}-${field}`,
      async () => {
        const materialized = await api.materializeMediaLibraryAsset(asset.library_asset_id, selectedProjectId);
        const recent = await api.listProjectRecentMediaLibraryAssetIds(selectedProjectId);
        setRecentMediaLibraryAssetIds(recent.asset_ids);
        return asset.media_type === "music"
          ? api.updateEditingSessionMusicOverride(selectedProjectId, activeEditingSessionId, selectedEditingSegment.segment_id, { expected_revision: editingSession.session_revision, asset_id: materialized.asset_id })
          : api.updateEditingSessionSfxOverride(selectedProjectId, activeEditingSessionId, selectedEditingSegment.segment_id, { expected_revision: editingSession.session_revision, asset_id: materialized.asset_id });
      },
      { addRegenerationField: field, feedbackAction: "저장" },
    );
  }
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
    if (nextSegment) {
      setSelectedRangeStartSec(nextSegment.start_sec);
      setSelectedRangeEndSec(nextSegment.end_sec);
      setSelectedRangePreview(null);
    }
    setPartialRegenerationRestoreWarning(null);
    setPartialRegenerationPreflight(null);
    setPartialRegenerationRun(null);
  };
  const openSegmentInEditor = (segmentId: string, fields?: string[]) => {
    selectSection("editing");
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
    "timeline_structure",
  ] as const;

  function moveSelectedTimelineSegment(offset: -1 | 1) {
    if (!editingSession || !selectedEditingSegmentId || !selectedProjectId || !activeEditingSessionId) return;
    const currentIndex = editingSession.segments.findIndex((segment) => segment.segment_id === selectedEditingSegmentId);
    const destinationIndex = currentIndex + offset;
    if (currentIndex < 0 || destinationIndex < 0 || destinationIndex >= editingSession.segments.length) return;
    const reordered = [...editingSession.segments];
    const [moved] = reordered.splice(currentIndex, 1);
    reordered.splice(destinationIndex, 0, moved);
    let cursor = Math.min(...editingSession.segments.map((segment) => segment.start_sec));
    const bounds_by_id: Record<string, { start_sec: number; end_sec: number }> = {};
    for (const segment of reordered) {
      const duration = segment.end_sec - segment.start_sec;
      bounds_by_id[segment.segment_id] = { start_sec: cursor, end_sec: cursor + duration };
      cursor += duration;
    }
    const boundsById = Object.fromEntries(Object.entries(bounds_by_id).map(([segmentId, bounds]) => [segmentId, {
      startSec: bounds.start_sec,
      endSec: bounds.end_sec,
    }]));
    void applyEditingMutation("timeline-reorder", () => routedEditorCommandPort
      ? routedEditorCommandPort.reorderNarration({ segmentIds: reordered.map((segment) => segment.segment_id), boundsById })
      : api.reorderEditingSessionSegments(selectedProjectId, activeEditingSessionId, {
          expected_revision: editingSession.session_revision,
          segment_ids: reordered.map((segment) => segment.segment_id),
          bounds_by_id,
        }), { addRegenerationField: "timeline_structure" });
  }

  async function handleCapcutDraftHandoff() {
    if (!selectedProjectId || !capcutDraftJob?.export) return;
    setIsRegisteringCapcutHandoff(true);
    try {
      const result = await api.registerCapcutDraftHandoff(selectedProjectId, capcutDraftJob.job_id);
      setCapcutDraftJob((current) =>
        current?.export ? { ...current, export: { ...current.export, handoff: result.handoff } } : current,
      );
      if (result.handoff.status === "failed") {
        setErrorMessage("CapCut 등록을 완료하지 못했어요. 다시 시도해 주세요.");
      }
    } catch (error) {
      setErrorMessage("초안 등록을 완료하지 못했어요. 다시 시도해 주세요.");
    } finally {
      setIsRegisteringCapcutHandoff(false);
    }
  }

  async function handleProjectCreated(project: Project) {
    setProjects((current) => [project, ...current.filter((item) => item.project_id !== project.project_id)]);
    if (onProjectCreated) {
      await onProjectCreated(project);
      return;
    } else {
      selectProject(project.project_id, "create");
    }
    setLoadState("ready");
    setOnboardingProject(project);
  }

  async function handleUploadVoiceSample() {
    if (!selectedProjectId || !voiceSampleFile) {
      return;
    }
    setIsRegisteringVoiceSample(true);
    setVoiceSampleError(null);
    setVoiceSampleMessage(null);
    try {
      const asset = await api.uploadVoiceSample(selectedProjectId, voiceSampleFile);
      setVoiceSampleAssetId(asset.asset_id);
      setTtsCandidateVoiceSampleId(asset.asset_id);
      setVoiceSampleMessage("내 목소리를 추가했어요.");
    } catch (error) {
      setVoiceSampleError(
        "내 목소리를 추가하지 못했어요. 다시 시도해 주세요.",
      );
    } finally {
      setIsRegisteringVoiceSample(false);
    }
  }

  async function handleReviewTtsCandidate(
    candidateId: string,
    decision: "approved" | "rejected",
  ) {
    if (routeEditingSessionId || !selectedProjectId) {
      return;
    }
    setIsReviewingTtsCandidate(candidateId);
    setTtsCandidateError(null);
    try {
      const candidate = await api.reviewTtsCandidate(selectedProjectId, candidateId, decision);
      setTtsCandidates((current) => {
        const matched = current.some((item) => item.candidate_id === candidate.candidate_id);
        return matched
          ? current.map((item) => (item.candidate_id === candidate.candidate_id ? candidate : item))
          : [candidate, ...current];
      });
      setTtsCandidateMessage(
        decision === "approved"
          ? "청취 승인을 저장했어요. 이 후보를 선택해 나레이션에 적용하세요."
          : "청취 거부를 저장했어요. 기존 나레이션을 유지합니다.",
      );
    } catch (error) {
      setTtsCandidateError(
        "청취 승인을 저장하지 못했어요. 다시 시도해 주세요.",
      );
    } finally {
      setIsReviewingTtsCandidate(null);
    }
  }

  return (
    <div className="vb-legacy shell">
      <aside className="sidebar" aria-label="프로젝트 탐색">
        <div className="brand-card">
          <p className="eyebrow">영상 만들기</p>
          <h1>VideoBox 작업판</h1>
          <p className="lede">프로젝트 · 타임라인 · 검수 · 출력</p>
        </div>

        {(projects.length === 0 || onboardingProject !== null) && loadState === "ready" ? (
          <ProjectOnboarding
            onProjectCreated={handleProjectCreated}
            onIngestComplete={() => setOnboardingProject(null)}
            existingProject={onboardingProject ?? undefined}
          />
        ) : null}

        <section className="sidebar-section" aria-labelledby="projects-heading">
          <div className="sidebar-header">
            <p className="section-kicker">프로젝트</p>
            <h2 id="projects-heading">목록</h2>
            {selectedProjectId ? (
              <button
                className="action-button subtle"
                onClick={() => {
                  const project = projects.find((item) => item.project_id === selectedProjectId);
                  if (project) {
                    setOnboardingProject(project);
                  }
                }}
                type="button"
              >
                소스 등록
              </button>
            ) : null}
          </div>
          <div className="project-list">
            {projects.map((project) => (
              <button
                key={project.project_id}
                className={`project-chip ${
                  project.project_id === selectedProjectId ? "is-selected" : ""
                }`}
                aria-pressed={project.project_id === selectedProjectId}
                onClick={() => selectProject(project.project_id, activeRouteSection)}
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
            <h2 id="all-jobs-heading">작업 진행</h2>
          </div>
          <button className="action-button" onClick={() => void handleToggleAllJobsPanel()} type="button">
            {isAllJobsPanelOpen ? "전체 작업 진행 닫기" : "전체 작업 진행 보기"}
          </button>
          {isAllJobsPanelOpen ? (
            <div className="all-jobs-list">
              {isLoadingAllJobs ? <p className="meta-copy">불러오는 중...</p> : null}
              {allJobsError ? <p className="error-banner">{allJobsError}</p> : null}
              {!isLoadingAllJobs && allJobs.length === 0 ? (
                <p className="empty-state">진행 중인 작업이 없어요</p>
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
                aria-pressed={selectedSection === value}
                onClick={() =>
                  selectSection(value as LegacySection)
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
            {capcutDraftJob?.export && capcutDraftJob.export.handoff?.status !== "ready" ? (
              <button
                className="action-button subtle"
                disabled={isRegisteringCapcutHandoff}
                onClick={() => void handleCapcutDraftHandoff()}
                type="button"
              >
            {isRegisteringCapcutHandoff
              ? "CapCut 등록 중"
              : capcutDraftJob.export.handoff?.status === "failed"
                ? "CapCut 등록 다시 시도"
                : "CapCut에 등록"}
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
              <p className="section-kicker">영상 만들기</p>
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
            <summary>단계별 진행 보기</summary>
            <div className="stage-detail-list">
              {stageStatus.map((stage) => (
                <span key={stage.jobType}>
                  <strong>{`${stage.label}:`}</strong>
                  <span>{formatStatusLabel(stage.status)}</span>
                  <span>{stage.jobId === "not-started" ? "대기" : "준비됨"}</span>
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

        {selectedProjectId ? <MediaAnalysisPanel projectId={selectedProjectId} onSelectAsset={() => selectSection("editing")} /> : null}

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
                  <dd>{subtitleJob ? "준비됨" : "대기"}</dd>
                </div>
                <div>
                  <dt>자막 파일</dt>
                  <dd>{subtitleJob?.subtitle ? "준비됨" : "대기"}</dd>
                </div>
                <div>
                  <dt>미리보기 작업</dt>
                  <dd>{previewJob ? "준비됨" : "대기"}</dd>
                </div>
                <div>
                  <dt>미리보기 파일</dt>
                  <dd>
                    {previewJob?.status === "succeeded"
                      ? formatDisplayText(previewJob.preview.artifact_kind)
                      : lastSuccessfulPreviewJob
                        ? `마지막 성공 유지 · ${formatDisplayText(lastSuccessfulPreviewJob.preview.artifact_kind)}`
                        : "미시작"}
                  </dd>
                </div>
                <div>
                  <dt>내보내기 작업</dt>
                  <dd>{exportJob ? "준비됨" : "대기"}</dd>
                </div>
                <div>
                  <dt>내보내기 대상</dt>
                  <dd>{exportJob ? formatDisplayText(exportJob.export.export_type) : "미시작"}</dd>
                </div>
                <div>
                  <dt>완성본 렌더</dt>
                  <dd>{finalRenderJob ? "준비됨" : "대기"}</dd>
                </div>
                <div>
                  <dt>완성본 파일</dt>
                  <dd>
                    {finalRenderJob?.render
                      ? "완성본 준비됨"
                      : lastSuccessfulFinalRenderJob?.render
                        ? "마지막 완성본 유지"
                        : finalRenderJob?.status === "failed"
                          ? "완성본 렌더 실패"
                        : "미시작"}
                  </dd>
                </div>
                <div>
                  <dt>CapCut 초안(실제)</dt>
                  <dd>{capcutDraftJob ? "준비됨" : "대기"}</dd>
                </div>
                <div>
                  <dt>CapCut 초안 파일</dt>
                  <dd>
                    {capcutDraftJob?.export
                      ? "초안 준비됨"
                      : lastSuccessfulCapcutDraftJob?.export
                        ? "마지막 초안 유지"
                        : capcutDraftJob?.status === "failed"
                          ? "CapCut 초안 내보내기 실패"
                        : "미시작"}
                  </dd>
                </div>
              </dl>
              {canShowLegacyFinalRender && finalRenderNeedsRefresh ? (
                <p className="status-copy">완성본이 최신 편집본과 달라 다시 만들 수 있어요.</p>
              ) : null}
              {canShowLegacyFinalRender && playableFinalRenderJob?.render && selectedProjectId ? (
                <section className="panel" aria-label="완성본 미리보기">
                  <h3>완성본 미리보기</h3>
                  <video
                    aria-label="완성본 재생"
                    controls
                    preload="metadata"
                    src={`/api/projects/${encodeURIComponent(selectedProjectId)}/final-renders/${encodeURIComponent(playableFinalRenderJob.job_id)}/content`}
                  >
                    이 브라우저에서는 완성본을 재생할 수 없어요.
                  </video>
                </section>
              ) : null}
              {(capcutDraftJob?.export?.notes ?? lastSuccessfulCapcutDraftJob?.export?.notes ?? []).length > 0 ? (
                <div className="warning-banner" role="status">
                  <strong>CapCut에서 후처리 필요</strong>
                  <ul>
                    {(capcutDraftJob?.export?.notes ?? lastSuccessfulCapcutDraftJob?.export?.notes ?? []).map((note) => (
                      <li key={note}>후처리가 필요해요. CapCut에서 확인해 주세요.</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div className="diagnostics-card" role="status">
                <div className="panel-header">
                  <div>
                    <p className="section-kicker">CapCut</p>
                    <h3>CapCut 연결 진단</h3>
                  </div>
                  <button
                    className="action-button subtle"
                    type="button"
                    disabled={isLoadingCapcutHandoffDiagnostics}
                    onClick={() => void refreshCapcutHandoffDiagnostics()}
                  >
                    {isLoadingCapcutHandoffDiagnostics ? "진단 중" : "다시 진단"}
                  </button>
                </div>
                {capcutHandoffDiagnostics ? (
                  <>
                    <strong>
                      {capcutHandoffDiagnostics.status === "ready" ? "연결 준비 완료" : "연결 준비 필요"}
                    </strong>
                    <dl className="summary-list">
                      <div>
                        <dt>설치 버전</dt>
                        <dd>
                          {capcutHandoffDiagnostics.is_supported ? "지원됨" : "확인 필요"}
                        </dd>
                      </div>
                      <div>
                        <dt>쓰기 권한</dt>
                        <dd>{capcutHandoffDiagnostics.write_access ? "확인됨" : "확인 필요"}</dd>
                      </div>
                    </dl>
                    {capcutHandoffDiagnostics.status !== "ready" ? (
                      <p className="error-banner">
                        CapCut 연결 상태를 다시 확인해 주세요.
                      </p>
                    ) : null}
                  </>
                ) : capcutHandoffDiagnosticsError ? (
                  <p className="error-banner">{capcutHandoffDiagnosticsError}</p>
                ) : (
                  <p>CapCut 연결 상태를 확인하는 중입니다.</p>
                )}
              </div>
          {capcutDraftJob?.export?.handoff?.status === "ready" ? (
                <div className="loading-banner" role="status">
                  <strong>CapCut에 열기 준비</strong>
                  <p>CapCut에서 초안을 열 수 있어요.</p>
                </div>
          ) : null}
              {capcutDraftJob?.export?.handoff?.status === "failed" ? (
                <p className="error-banner">
                  CapCut 등록을 완료하지 못했어요. 다시 시도해 주세요.
                </p>
              ) : null}
              {capcutDraftJob?.status === "failed" ? (
                <p className="error-banner">
                  초안 내보내기를 완료하지 못했어요. 다시 시도해 주세요.
                </p>
              ) : null}
              {finalRenderJob?.status === "failed" ? (
                <p className="error-banner">
                  완성본을 만들지 못했어요. 다시 시도해 주세요.
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
                  <p className="section-kicker">음성</p>
                  <h2>내 목소리</h2>
                </div>
              </div>
              <label className="field">
                <span>내 목소리 고르기</span>
                <input
                  accept="audio/*,.m4a,.webm"
                  onChange={(event) => {
                    setVoiceSampleFile(event.target.files?.[0] ?? null);
                    setVoiceSampleError(null);
                  }}
                  type="file"
                />
              </label>
              {voiceSampleFile ? <p className="meta-copy">선택됨 · {voiceSampleFile.name}</p> : null}
              <div className="action-row">
                <button
                  className="action-button primary"
                  disabled={!selectedProjectId || !voiceSampleFile || isRegisteringVoiceSample}
                  onClick={() => void handleUploadVoiceSample()}
                  type="button"
                >
                  {isRegisteringVoiceSample ? "추가 중" : "내 목소리 추가"}
                </button>
              </div>
              {voiceSamples.length > 0 ? (
                <div className="tts-candidate-comparison">
                  <p className="section-kicker">저장한 목소리</p>
                  {voiceSamples.map((sample, index) => (
                    <button
                      aria-pressed={ttsCandidateVoiceSampleId === sample.asset_id}
                      className="action-button"
                      key={sample.asset_id}
                      onClick={() => {
                        setVoiceSampleAssetId(sample.asset_id);
                        setTtsCandidateVoiceSampleId(sample.asset_id);
                      }}
                      type="button"
                    >
                      {`내 목소리 ${index + 1} 사용`}
                    </button>
                  ))}
                  {ttsCandidateVoiceSampleId ? (
                    <p className="meta-copy">
                      {`현재 사용할 목소리: 내 목소리 ${voiceSamples.findIndex((sample) => sample.asset_id === ttsCandidateVoiceSampleId) + 1}`}
                    </p>
                  ) : null}
                </div>
              ) : null}
              {voiceSampleMessage ? <p className="meta-copy">{voiceSampleMessage}</p> : null}
              {voiceSampleError ? <p className="error-banner">{voiceSampleError}</p> : null}
              <p className="meta-copy">
                편집에서 내 목소리로 나레이션을 만들 수 있어요.
              </p>
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
                    <h3>미리보기</h3>
                    <p>미리보기 준비됨</p>
                  </article>
                ) : null}
                {subtitleJob ? (
                  <article className="artifact-card">
                    <h3>자막</h3>
                    <p>자막 파일 준비됨</p>
                  </article>
                ) : null}
                {exportJob ? (
                  <article className="artifact-card">
                    <h3>캡컷 내보내기</h3>
                    <p>내보낸 영상 준비됨</p>
                    <p>{exportJob.export.subtitle_file_uri ? "자막 포함" : "자막 없음"}</p>
                    {exportJob.export.notes.length > 0 ? <p>내보낸 영상에서 확인할 내용이 있어요.</p> : null}
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
                {!routeEditingSessionId ? (
                  <button
                    className="action-button primary"
                    disabled={!latestTimelineBuildJob || isStartingEditingSession}
                    onClick={() => void handleStartEditingSession()}
                    type="button"
                  >
                    {isStartingEditingSession ? "편집 시작 중" : "편집 시작"}
                  </button>
                ) : null}
              </div>
                  {editingSessionRestoreError ? (
                    <p className="error-banner">{editingSessionRestoreError}</p>
                  ) : null}
                  {routedEditorViewMessage ? (
                    <p className="error-banner">{routedEditorViewMessage}</p>
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
                  {canShowLegacyFinalRender && finalRenderNeedsRefresh ? (
                    <p className="status-copy">완성본이 최신 편집본과 달라 다시 만들 수 있어요.</p>
                  ) : null}
                  {routedEditorView ? (
                    <section className="panel" aria-label="재생 확인">
                      <h3>재생 확인</h3>
                      {Object.entries(routedEditorView.playback.auditionUrls).map(([assetId, url]) => (
                        <audio aria-label="소리 미리 듣기" controls key={assetId} preload="metadata" src={url}>
                          이 브라우저에서는 소리를 재생할 수 없어요.
                        </audio>
                      ))}
                      {routedEditorView.playback.exactPreview.status === "current" && routedEditorView.playback.exactPreview.url ? (
                        <section aria-label="현재 편집본">
                          <h4>현재 편집본 재생</h4>
                          <video aria-label="현재 편집본 재생" controls preload="metadata" src={routedEditorView.playback.exactPreview.url}>
                            이 브라우저에서는 영상을 재생할 수 없어요.
                          </video>
                        </section>
                      ) : routedEditorView.playback.exactPreview.status === "stale" ? (
                        <p className="status-copy">완성본을 다시 만들어 주세요.</p>
                      ) : (
                        <p className="status-copy">완성본을 만들면 여기서 확인할 수 있어요.</p>
                      )}
                    </section>
                  ) : null}
                  {canShowLegacyFinalRender && playableFinalRenderJob?.render && selectedProjectId ? (
                    <section className="panel" aria-label="완성본 미리보기">
                      <h3>완성본 미리보기</h3>
                      <video
                        aria-label="완성본 재생"
                        controls
                        preload="metadata"
                        src={`/api/projects/${encodeURIComponent(selectedProjectId)}/final-renders/${encodeURIComponent(playableFinalRenderJob.job_id)}/content`}
                      >
                        이 브라우저에서는 완성본을 재생할 수 없어요.
                      </video>
                    </section>
                  ) : null}
                  {selectedProjectId && !routeEditingSessionId ? <DirectorWorkspacePanel projectId={selectedProjectId} sessionId={editingSession.session_id} sessionRevision={editingSession.session_revision} selectedSegment={selectedEditingSegment ? { segmentId: selectedEditingSegment.segment_id, startSec: selectedEditingSegment.start_sec, endSec: selectedEditingSegment.end_sec, draftApplied: changedSegmentIds.has(selectedEditingSegment.segment_id) } : undefined} onStateChange={setDirectorWorkspaceState} applyEditingMutation={(action) => applyEditingMutation("director-proposal-apply", action as () => Promise<EditingSession>)} /> : null}
                  <section className="editor-library" aria-label="고정 트랙 타임라인">
                    <h3>고정 트랙 타임라인</h3>
                    <p className="meta-copy">나레이션·B롤·BGM·SFX·오버레이만 사용합니다. 임의 트랙은 추가할 수 없습니다.</p>
                    <div className="segment-list" aria-label="고정 역할 트랙">
                      {[
                        ["narration", "나레이션"],
                        ["broll", "B롤"],
                        ["bgm", "BGM"],
                        ["sfx", "SFX"],
                        ["overlay", "오버레이"],
                      ].map(([role, label]) => (
                        <span className="pill" key={role}>{label}</span>
                      ))}
                    </div>
                    <div className="action-row">
                      <button
                        className="action-button subtle"
                        disabled={!selectedEditingSegment || !selectedProjectId || !activeEditingSessionId || Boolean(isSavingEditingMutation) || Boolean(routeEditingSessionId && !routedEditorCommandPort)}
                        onClick={() => selectedEditingSegment && void applyEditingMutation("timeline-split", () => routedEditorCommandPort
                          ? routedEditorCommandPort.splitNarration({ segmentId: selectedEditingSegment.segment_id, splitSec: (selectedEditingSegment.start_sec + selectedEditingSegment.end_sec) / 2 })
                          : api.splitEditingSessionSegment(selectedProjectId!, activeEditingSessionId!, selectedEditingSegment.segment_id, {
                              expected_revision: editingSession.session_revision,
                              split_sec: (selectedEditingSegment.start_sec + selectedEditingSegment.end_sec) / 2,
                            }), { addRegenerationField: "timeline_structure" })}
                        type="button"
                      >분할</button>
                      <button
                        className="action-button subtle"
                        hidden={Boolean(routeEditingSessionId)}
                        disabled={!selectedEditingSegment || editingSession.segments[0]?.segment_id === selectedEditingSegment.segment_id || Boolean(isSavingEditingMutation)}
                        onClick={() => moveSelectedTimelineSegment(-1)}
                        type="button"
                      >앞으로 이동</button>
                      <button
                        className="action-button subtle"
                        disabled={!selectedEditingSegment || editingSession.segments[editingSession.segments.length - 1]?.segment_id === selectedEditingSegment.segment_id || Boolean(isSavingEditingMutation)}
                        onClick={() => moveSelectedTimelineSegment(1)}
                        type="button"
                      >뒤로 이동</button>
                      <button
                        className="action-button subtle"
                        disabled={!selectedEditingSegment || !selectedProjectId || !activeEditingSessionId || editingSession.segments[editingSession.segments.length - 1]?.segment_id === selectedEditingSegment?.segment_id || Boolean(isSavingEditingMutation)}
                        onClick={() => {
                          if (!selectedEditingSegment || !selectedProjectId || !activeEditingSessionId) return;
                          const index = editingSession.segments.findIndex((segment) => segment.segment_id === selectedEditingSegment.segment_id);
                          const right = editingSession.segments[index + 1];
                          if (right) void applyEditingMutation("timeline-merge", () => routedEditorCommandPort
                            ? routedEditorCommandPort.mergeNarration({ leftSegmentId: selectedEditingSegment.segment_id, rightSegmentId: right.segment_id })
                            : api.mergeEditingSessionSegments(selectedProjectId, activeEditingSessionId, {
                                expected_revision: editingSession.session_revision, left_segment_id: selectedEditingSegment.segment_id, right_segment_id: right.segment_id,
                              }), { addRegenerationField: "timeline_structure" });
                        }}
                        type="button"
                      >다음과 병합</button>
                      <button
                        className="action-button subtle"
                        hidden={Boolean(routeEditingSessionId)}
                        disabled={!selectedProjectId || !activeEditingSessionId || !(editingSession.undo_count ?? editingSession.history.some((entry) => entry.inverse_payload)) || Boolean(isSavingEditingMutation)}
                        onClick={() => void applyEditingMutation("timeline-undo", () => api.undoEditingSession(selectedProjectId!, activeEditingSessionId!, editingSession.session_revision), { addRegenerationField: "timeline_structure" })}
                        type="button"
                      >실행 취소</button>
                      <button
                        className="action-button subtle"
                        hidden={Boolean(routeEditingSessionId)}
                        disabled={!selectedProjectId || !activeEditingSessionId || !(editingSession.redo_count ?? 0) || Boolean(isSavingEditingMutation)}
                        onClick={() => void applyEditingMutation("timeline-redo", () => api.redoEditingSession(selectedProjectId!, activeEditingSessionId!, editingSession.session_revision), { addRegenerationField: "timeline_structure" })}
                        type="button"
                      >다시 실행</button>
                    </div>
                    <div className="action-row">
                      <label className="field"><span>선택 시작(초)</span><input min="0" onChange={(event) => setSelectedRangeStartSec(Number(event.target.value))} step="0.1" type="number" value={selectedRangeStartSec} /></label>
                      <label className="field"><span>선택 종료(초)</span><input min="0" onChange={(event) => setSelectedRangeEndSec(Number(event.target.value))} step="0.1" type="number" value={selectedRangeEndSec} /></label>
                      <button
                        className="action-button"
                        disabled={!selectedEditingSegment || !selectedProjectId || !activeEditingSessionId || Boolean(isSavingEditingMutation)}
                        onClick={() => selectedEditingSegment && void applyEditingMutation("timeline-bounds", () => routedEditorCommandPort
                          ? routedEditorCommandPort.setNarrationBounds({ segmentId: selectedEditingSegment.segment_id, startSec: selectedRangeStartSec, endSec: selectedRangeEndSec })
                          : api.updateEditingSessionSegmentBounds(selectedProjectId!, activeEditingSessionId!, selectedEditingSegment.segment_id, {
                              expected_revision: editingSession.session_revision, start_sec: selectedRangeStartSec, end_sec: selectedRangeEndSec,
                            }), { addRegenerationField: "timeline_structure" })}
                        type="button"
                      >구간 길이 저장</button>
                      <button
                        className="action-button"
                        hidden={Boolean(routeEditingSessionId)}
                        disabled={!selectedProjectId || !activeEditingSessionId}
                        onClick={() => void api.previewEditingSessionSelectedRange(selectedProjectId!, activeEditingSessionId!, { start_sec: selectedRangeStartSec, end_sec: selectedRangeEndSec }).then(setSelectedRangePreview).catch(() => setErrorMessage("선택 구간 미리보기를 만들지 못했어요. 다시 시도해 주세요."))}
                        type="button"
                      >선택 구간 미리보기</button>
                    </div>
                    {selectedRangePreview ? <div className="confirmation-card"><p>{`선택 ${formatSeconds(selectedRangePreview.start_sec, selectedRangePreview.end_sec)} · 자막 ${selectedRangePreview.captions.length}개 · 오버레이 ${selectedRangePreview.overlays.length}개`}</p><div aria-label="범위 미리보기" className="range-preview-stage">{selectedRangePreview.overlays.map((overlay, index) => <span className="range-preview-overlay" key={`${String(overlay.segment_id ?? "overlay")}-${index}`}>{String(overlay.text ?? overlay.title ?? overlay.overlay_type ?? "오버레이")}</span>)}{selectedRangePreview.captions.map((caption) => <p className="range-preview-caption" key={caption.segment_id} style={{ color: String(caption.caption_style.text_color ?? caption.caption_style.font_color ?? "#ffffff"), fontSize: Number(caption.caption_style.font_size_px ?? caption.caption_style.font_size ?? 32) }}>{caption.caption_text}</p>)}</div><p className="meta-copy">적용 자막 스타일과 관련 오버레이를 포함한 범위 미리보기입니다.</p></div> : null}
                  </section>
                  {selectedProjectId ? <ManualMediaLibrary
                    projectId={selectedProjectId}
                    assets={mediaLibraryAssets}
                    brollAssets={brollAssets}
                    favoriteIds={mediaLibraryFavoriteIds}
                    unavailableMessage={mediaLibraryError}
                    directorState={directorWorkspaceState}
                    localFavoriteIds={editorFavorites.filter((item) => item.favorite_type === "media" && item.favorite_id.startsWith("pack:local:")).map((item) => item.favorite_id.slice("pack:local:".length))}
                    recentIds={recentMediaLibraryAssetIds}
                    selectedSegment={selectedEditingSegment ? { segmentId: selectedEditingSegment.segment_id, startSec: selectedEditingSegment.start_sec, endSec: selectedEditingSegment.end_sec } : null}
                    activeBrollAssetId={typeof selectedEditingSegment?.broll_override?.asset_id === "string" ? selectedEditingSegment.broll_override.asset_id : null}
                    busy={Boolean(isSavingEditingMutation)}
                    allowLegacyMutations={!routeEditingSessionId}
                    allowPreferences={!routeEditingSessionId}
                    onToggleFavorite={(libraryAssetId) => { const asset = mediaLibraryAssets.find((item) => item.library_asset_id === libraryAssetId); if (asset) void toggleMediaLibraryFavorite(asset); }}
                    onToggleLocalFavorite={(assetId) => {
                      const favoriteId = `pack:local:${assetId}`;
                      const enabled = !editorFavorites.some((item) => item.favorite_id === favoriteId);
                      void api.toggleEditorFavorite(selectedProjectId, favoriteId, { favorite_type: "media", enabled }).then(() => setEditorFavorites((current) => enabled ? [...current.filter((item) => item.favorite_id !== favoriteId), { favorite_id: favoriteId, favorite_type: "media" }] : current.filter((item) => item.favorite_id !== favoriteId)));
                    }}
                    onApplyGlobal={(asset) => void applyMediaLibraryAsset(asset)}
                    onApplyBroll={(asset) => {
                      if (!activeEditingSessionId || !selectedEditingSegment || !editingSession) return;
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-broll`, () => routedEditorCommandPort
                        ? routedEditorCommandPort.applyMedia({ kind: "broll", segmentId: selectedEditingSegment.segment_id, assetId: asset.asset_id, controls: selectedBrollControls })
                        : api.updateEditingSessionBroll(selectedProjectId, activeEditingSessionId, selectedEditingSegment.segment_id, {
                            expected_revision: editingSession.session_revision,
                            asset_id: asset.asset_id,
                            media_controls: { expected_content_sha256: String(asset.metadata.content_sha256 ?? asset.metadata.sha256 ?? ""), media_revision: asset.created_at },
                          }), {
                        onSuccess: () => void api.listProjectRecentMediaLibraryAssetIds(selectedProjectId).then((recent) => setRecentMediaLibraryAssetIds(recent.asset_ids)).catch(() => undefined),
                      });
                    }}
                    onClearBroll={() => {
                      if (!activeEditingSessionId || !selectedEditingSegment || !editingSession) return;
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-broll`, () => routedEditorCommandPort
                        ? routedEditorCommandPort.clearMedia({ kind: "broll", segmentId: selectedEditingSegment.segment_id })
                        : api.clearEditingSessionBrollOverride(selectedProjectId, activeEditingSessionId, selectedEditingSegment.segment_id, editingSession.session_revision), { feedbackAction: "해제", removeRegenerationField: "broll" });
                    }}
                  /> : null}
                  <div className="editor-library" aria-label="자막 스타일 라이브러리">
                    <h3>자막 스타일</h3>
                    <label className="field">
                      <span>프리셋</span>
                      <select
                        onChange={(event) => {
                          setSelectedPresetId(event.target.value);
                          setCaptionStylePreflight(null);
                        }}
                        value={selectedPresetId}
                      >
                        {editorPresets.map((preset) => (
                          <option key={preset.preset_id} value={preset.preset_id}>
                            {preset.name}{recentPresetIds.includes(preset.preset_id) ? " · 최근" : ""}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="action-button subtle"
                      hidden={Boolean(routeEditingSessionId)}
                      disabled={!selectedProjectId || !selectedPresetId}
                      onClick={() => {
                        if (!selectedProjectId || !selectedPresetId) return;
                        const favoriteId = `project:${selectedProjectId}:${selectedPresetId}`;
                        const enabled = !editorFavorites.some((item) => item.favorite_id === favoriteId);
                        void api.toggleEditorFavorite(selectedProjectId, favoriteId, {
                          favorite_type: "preset",
                          enabled,
                        }).then(() => setEditorFavorites((current) => enabled
                          ? [...current.filter((item) => item.favorite_id !== favoriteId), { favorite_id: favoriteId, favorite_type: "preset" }]
                          : current.filter((item) => item.favorite_id !== favoriteId),
                        )).catch(() => setErrorMessage("즐겨찾기를 저장하지 못했어요. 다시 시도해 주세요."));
                      }}
                      type="button"
                    >
                      {editorFavorites.some((item) => item.favorite_id === `project:${selectedProjectId}:${selectedPresetId}`)
                        ? "프리셋 즐겨찾기 해제"
                        : "프리셋 즐겨찾기"}
                    </button>
                    <label className="field">
                      <span>적용 범위</span>
                      <select
                        onChange={(event) => {
                          setCaptionStyleScope(event.target.value as CaptionStyleScope);
                          setCaptionStylePreflight(null);
                        }}
                        value={captionStyleScope}
                      >
                        <option value="current_caption">현재 자막</option>
                        <option value="selected_captions">선택 자막</option>
                        <option value="from_current">현재부터</option>
                        <option value="whole_project">전체 프로젝트</option>
                        <option value="project_default">프로젝트 기본값</option>
                      </select>
                    </label>
                    {selectedPresetId && !editorPresets.some((preset) => preset.preset_id === selectedPresetId) ? (
                      <p className="error-copy">선택한 프리셋을 찾을 수 없습니다.</p>
                    ) : null}
                    <button
                      className="action-button subtle"
                      disabled={!selectedProjectId || !activeEditingSessionId || !selectedPresetId}
                      onClick={() => {
                        const preset = editorPresets.find((item) => item.preset_id === selectedPresetId);
                        if (!preset || !selectedProjectId || !activeEditingSessionId) return;
                        const segmentIds = captionStyleScope === "whole_project" || captionStyleScope === "project_default"
                          ? []
                          : captionStyleScope === "selected_captions"
                            ? selectedRegenerationFields.length > 0 && selectedEditingSegmentId ? [selectedEditingSegmentId] : []
                            : selectedEditingSegmentId ? [selectedEditingSegmentId] : [];
                        void api.previewEditingSessionCaptionStyleScope(selectedProjectId, activeEditingSessionId, {
                          expected_revision: editingSession.session_revision,
                          scope: captionStyleScope,
                          segment_ids: segmentIds,
                          style: preset.style,
                        }).then(setCaptionStylePreflight).catch(() => setErrorMessage("범위를 확인하지 못했어요. 다시 시도해 주세요."));
                      }}
                      type="button"
                    >
                      적용 범위 확인
                    </button>
                    {captionStylePreflight ? (
                      <div className="confirmation-card">
                        <p>{`영향 자막 ${captionStylePreflight.affected_segment_ids.length}개`}</p>
                        <button
                          className="action-button primary"
                          onClick={() => {
                            const preset = editorPresets.find((item) => item.preset_id === selectedPresetId);
                            if (!preset || !selectedProjectId || !activeEditingSessionId) return;
                            void applyEditingMutation("caption-style", () => routedEditorCommandPort
                              ? routedEditorCommandPort.setCaptionStyle({ segmentIds: captionStylePreflight.affected_segment_ids, scope: captionStyleScope, style: preset.style as never })
                              : api.updateEditingSessionCaptionStyle(selectedProjectId, activeEditingSessionId, {
                                  expected_revision: editingSession.session_revision,
                                  scope: captionStyleScope,
                                  segment_ids: captionStylePreflight.affected_segment_ids,
                                  style: preset.style,
                                }));
                            if (!routeEditingSessionId) void api.markRecentEditorPreset(selectedProjectId, preset.preset_id).then(setRecentPresetIds);
                          }}
                          type="button"
                        >
                          영향 범위에 적용
                        </button>
                      </div>
                    ) : null}
                  </div>
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
                  <div className="action-row" hidden={Boolean(routeEditingSessionId)}>
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
                      hidden={Boolean(routeEditingSessionId)}
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
                      hidden={Boolean(routeEditingSessionId)}
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
                  {!routeEditingSessionId && partialRegenerationPreflight ? (
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
                <>{selectedProjectId ? <DirectorWorkspacePanel projectId={selectedProjectId} sessionId={null} sessionRevision={0} onStateChange={setDirectorWorkspaceState} /> : null}<p className="empty-state">편집 세션 없음</p></>
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
                  {!routeEditingSessionId && partialRegenerationRun ? (
                    <div className="track-card">
                      <h3>재생성 결과</h3>
                      <p>{formatStatusLabel(partialRegenerationRun.status)}</p>
                      <p>{partialRegenerationRun.delta ? "변경 내용을 확인해 주세요." : "타임라인 대기"}</p>
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
                !routeEditingSessionId && partialRegenerationRun ? (
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
                  <span>{selectedEditingDraft.imageAssetId ? "이미지 선택됨" : "이미지 없음"}</span>
                  <span>{selectedEditingDraft.tableText || "표 없음"}</span>
                  <span>{selectedEditingDraft.sfxAssetId ? "효과음 선택됨" : "효과음 없음"}</span>
                  <span>{selectedEditingDraft.ttsAssetId ? "내 목소리 선택됨" : "내 목소리 없음"}</span>
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
                  {pendingEditingConflict ? (
                    <button
                      className="action-button subtle"
                      onClick={() => {
                        applyLatestEditingSessionAfterConflict(
                          pendingEditingConflict.session,
                          pendingEditingConflict.drafts,
                        );
                        setPendingEditingConflict(null);
                      }}
                      type="button"
                    >
                      최신 내용 적용
                    </button>
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
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-caption`, () => routedEditorCommandPort
                        ? routedEditorCommandPort.setCaptionText({ segmentId: selectedEditingSegment.segment_id, text: selectedEditingDraft.captionText })
                        : api.updateEditingSessionCaption(
                            selectedProjectId!,
                            activeEditingSessionId!,
                            selectedEditingSegment.segment_id,
                            {
                              expected_revision: editingSession!.session_revision,
                              caption_text: selectedEditingDraft.captionText,
                            },
                          ),
                      )
                    }
                    type="button"
                  >
                    자막 저장
                  </button>
                  <label className="field" hidden={Boolean(routeEditingSessionId)}>
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
                    hidden={Boolean(routeEditingSessionId)}
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
                          {
                            expected_revision: editingSession!.session_revision,
                            cut_action: selectedEditingDraft.cutAction,
                          },
                        ),
                      )
                    }
                    type="button"
                  >
                    컷 저장
                  </button>
                  <label className="field" hidden={Boolean(routeEditingSessionId)}>
                    <span>B롤 폴더</span>
                    <input
                      onChange={(event) => setBrollFolderPath(event.target.value)}
                      value={brollFolderPath}
                    />
                  </label>
                  <label className="field" hidden={Boolean(routeEditingSessionId)}>
                    <span>B롤 파일</span>
                    <textarea
                      onChange={(event) => setBrollSourcePaths(event.target.value)}
                      rows={3}
                      value={brollSourcePaths}
                    />
                  </label>
                  <label className="field" hidden={Boolean(routeEditingSessionId)}>
                    <span>B롤 태그</span>
                    <input
                      onChange={(event) => setBrollImportTags(event.target.value)}
                      value={brollImportTags}
                    />
                  </label>
                  <button
                    className="action-button"
                    hidden={Boolean(routeEditingSessionId)}
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
                        () => routedEditorCommandPort
                          ? routedEditorCommandPort.updateMediaControls({ kind: "bgm", segmentId: selectedEditingSegment.segment_id, assetId: selectedEditingDraft.musicAssetId, controls: selectedMusicControls })
                          : api.updateEditingSessionMusicOverride(
                            selectedProjectId!,
                            activeEditingSessionId!,
                            selectedEditingSegment.segment_id,
                            {
                              expected_revision: editingSession!.session_revision,
                              asset_id: selectedEditingDraft.musicAssetId,
                              ...(audioGainDb !== 0 || audioFadeInSec !== 0 || audioFadeOutSec !== 0 || audioDucking ? { media_controls: { gain_db: audioGainDb, fade_in_sec: audioFadeInSec, fade_out_sec: audioFadeOutSec, ducking: audioDucking } } : {}),
                            },
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
                      수동 미디어 라이브러리에서 음악을 골라주세요.
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
                          routedEditorCommandPort
                            ? routedEditorCommandPort.clearMedia({ kind: "bgm", segmentId: selectedEditingSegment.segment_id })
                            : api.clearEditingSessionMusicOverride(
                              selectedProjectId!,
                              activeEditingSessionId!,
                              selectedEditingSegment.segment_id,
                              editingSession!.session_revision,
                            ),
                          { feedbackAction: "해제", removeRegenerationField: "music" },
                        )
                      }
                      type="button"
                    >
                      음악 해제
                    </button>
                  ) : null}
                  <div className="action-row" aria-label="오디오 재생 제어">
                    <label className="field"><span>Gain dB</span><input onChange={(event) => setAudioGainDb(Number(event.target.value))} step="1" type="number" value={audioGainDb} /></label>
                    <label className="field"><span>Fade in(초)</span><input min="0" onChange={(event) => setAudioFadeInSec(Number(event.target.value))} step="0.1" type="number" value={audioFadeInSec} /></label>
                    <label className="field"><span>Fade out(초)</span><input min="0" onChange={(event) => setAudioFadeOutSec(Number(event.target.value))} step="0.1" type="number" value={audioFadeOutSec} /></label>
                    <label className="pill"><input checked={audioDucking} onChange={(event) => setAudioDucking(event.target.checked)} type="checkbox" />나레이션 ducking</label>
                  </div>
                  <div className="action-row" aria-label="B롤 재생 제어">
                    <label className="field"><span>화면 맞춤</span><select onChange={(event) => setBrollFit(event.target.value as "fit" | "crop")} value={brollFit}><option value="fit">fit</option><option value="crop">crop</option></select></label>
                    <label className="pill"><input checked={brollLoop} onChange={(event) => setBrollLoop(event.target.checked)} type="checkbox" />반복</label>
                    <label className="pill"><input checked={brollPad} onChange={(event) => setBrollPad(event.target.checked)} type="checkbox" />패드</label>
                    <label className="field"><span>시작 trim(초)</span><input min="0" onChange={(event) => setBrollTrimStartSec(Number(event.target.value))} step="0.1" type="number" value={brollTrimStartSec} /></label>
                  </div>
                  <button
                    className="action-button"
                    hidden={Boolean(routeEditingSessionId)}
                    disabled={
                      !selectedProjectId ||
                      !activeEditingSessionId ||
                      !selectedEditingDraft.sfxAssetId ||
                      isSavingEditingMutation === `${selectedEditingSegment.segment_id}-sfx`
                    }
                    onClick={() =>
                      void applyEditingMutation(
                        `${selectedEditingSegment.segment_id}-sfx`,
                        () => routedEditorCommandPort
                          ? routedEditorCommandPort.updateMediaControls({ kind: "sfx", segmentId: selectedEditingSegment.segment_id, assetId: selectedEditingDraft.sfxAssetId, controls: selectedSfxControls })
                          : api.updateEditingSessionSfxOverride(
                            selectedProjectId!,
                            activeEditingSessionId!,
                            selectedEditingSegment.segment_id,
                            {
                              expected_revision: editingSession!.session_revision,
                              asset_id: selectedEditingDraft.sfxAssetId,
                              ...(audioGainDb !== 0 || audioFadeInSec !== 0 || audioFadeOutSec !== 0 || audioDucking ? { media_controls: { gain_db: audioGainDb, fade_in_sec: audioFadeInSec, fade_out_sec: audioFadeOutSec, ducking: audioDucking } } : {}),
                            },
                          ),
                        { addRegenerationField: "sfx", feedbackAction: "저장" },
                      )
                    }
                    type="button"
                  >
                    효과음 저장
                  </button>
                  {!selectedEditingDraft.sfxAssetId ? (
                    <p className="meta-copy">수동 미디어 라이브러리에서 효과음을 골라주세요.</p>
                  ) : null}
                  {selectedEditingSegment.sfx_override ? (
                    <button
                      className="action-button"
                      disabled={
                        !selectedProjectId ||
                        !activeEditingSessionId ||
                        isSavingEditingMutation === `${selectedEditingSegment.segment_id}-sfx`
                      }
                      onClick={() =>
                        void applyEditingMutation(
                          `${selectedEditingSegment.segment_id}-sfx`,
                          () =>
                          routedEditorCommandPort
                            ? routedEditorCommandPort.clearMedia({ kind: "sfx", segmentId: selectedEditingSegment.segment_id })
                            : api.clearEditingSessionSfxOverride(
                              selectedProjectId!,
                              activeEditingSessionId!,
                              selectedEditingSegment.segment_id,
                              editingSession!.session_revision,
                            ),
                          { feedbackAction: "해제", removeRegenerationField: "sfx" },
                        )
                      }
                      type="button"
                    >
                      효과음 해제
                    </button>
                  ) : null}
                  <div hidden={Boolean(routeEditingSessionId)}>
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
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-explanation`, () => routedEditorCommandPort
                        ? routedEditorCommandPort.applyOverlay({ kind: "explanation-card", segmentId: selectedEditingSegment.segment_id, title: selectedEditingDraft.explanationTitle, body: selectedEditingDraft.explanationBody, text: selectedEditingDraft.explanationText })
                        : api.updateEditingSessionExplanationCard(
                          selectedProjectId!,
                          activeEditingSessionId!,
                          selectedEditingSegment.segment_id,
                          {
                            expected_revision: editingSession!.session_revision,
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
                          () => routedEditorCommandPort
                            ? routedEditorCommandPort.clearOverlay({ kind: "explanation-card", segmentId: selectedEditingSegment.segment_id })
                            : api.removeEditingSessionExplanationCard(
                              selectedProjectId!,
                              activeEditingSessionId!,
                              selectedEditingSegment.segment_id,
                              editingSession!.session_revision,
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
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-image`, () => routedEditorCommandPort
                        ? routedEditorCommandPort.applyOverlay({ kind: "image", segmentId: selectedEditingSegment.segment_id, assetId: selectedEditingDraft.imageAssetId, text: selectedEditingDraft.imageText })
                        : api.updateEditingSessionImageOverlay(
                          selectedProjectId!,
                          activeEditingSessionId!,
                          selectedEditingSegment.segment_id,
                          {
                            expected_revision: editingSession!.session_revision,
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
                      이미지를 먼저 선택해 주세요.
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
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-image`, () => routedEditorCommandPort
                          ? routedEditorCommandPort.clearOverlay({ kind: "image", segmentId: selectedEditingSegment.segment_id })
                          : api.removeEditingSessionImageOverlay(
                            selectedProjectId!,
                            activeEditingSessionId!,
                            selectedEditingSegment.segment_id,
                            editingSession!.session_revision,
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
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-table`, () => routedEditorCommandPort
                        ? routedEditorCommandPort.applyOverlay({ kind: "table", segmentId: selectedEditingSegment.segment_id, columns: selectedEditingDraft.tableColumns.split(",").map((item) => item.trim()).filter(Boolean), rows: selectedEditingDraft.tableRows.split("\n").map((row) => row.split(",").map((cell) => cell.trim()).filter(Boolean)).filter((row) => row.length > 0), text: selectedEditingDraft.tableText })
                        : api.updateEditingSessionTableOverlay(
                          selectedProjectId!,
                          activeEditingSessionId!,
                          selectedEditingSegment.segment_id,
                          {
                            expected_revision: editingSession!.session_revision,
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
                      void applyEditingMutation(`${selectedEditingSegment.segment_id}-table`, () => routedEditorCommandPort
                          ? routedEditorCommandPort.clearOverlay({ kind: "table", segmentId: selectedEditingSegment.segment_id })
                          : api.removeEditingSessionTableOverlay(
                            selectedProjectId!,
                            activeEditingSessionId!,
                            selectedEditingSegment.segment_id,
                            editingSession!.session_revision,
                          ),
                        { feedbackAction: "삭제" },
                        )
                      }
                      type="button"
                    >
                      표 삭제
                    </button>
                  ) : null}
                  </div>
                  <button
                    aria-describedby={
                      !selectedEditingDraft.ttsRecommendationId || !selectedEditingDraft.ttsAssetId
                        ? `${selectedEditingSegment.segment_id}-tts-save-help`
                        : undefined
                    }
                    className="action-button"
                    hidden={Boolean(routeEditingSessionId)}
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
                            expected_revision: editingSession!.session_revision,
                            recommendation_id: selectedEditingDraft.ttsRecommendationId,
                            asset_id: selectedEditingDraft.ttsAssetId,
                          },
                        ),
                      )
                    }
                    type="button"
                  >
                    내 목소리로 저장
                  </button>
                  {!selectedEditingDraft.ttsRecommendationId || !selectedEditingDraft.ttsAssetId ? (
                    <p
                      className="meta-copy"
                      id={`${selectedEditingSegment.segment_id}-tts-save-help`}
                    >
                      아래에서 마음에 드는 목소리 후보를 골라주세요.
                    </p>
                  ) : null}
                  <button
                    className="action-button"
                    hidden={Boolean(routeEditingSessionId)}
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
                        selectedEditingSegment.end_sec - selectedEditingSegment.start_sec,
                      )
                    }
                    type="button"
                  >
                    {isGeneratingTtsCandidate ? "목소리 후보 만드는 중" : "내 목소리 후보 만들기"}
                  </button>
                  {!ttsCandidateVoiceSampleId.trim() ? (
                    <p className="meta-copy">설정 탭에서 음성 샘플을 먼저 등록하세요</p>
                  ) : null}
                  {ttsCandidateMessage ? <p className="meta-copy">{ttsCandidateMessage}</p> : null}
                  {ttsCandidateError ? <p className="error-banner">{ttsCandidateError}</p> : null}
                  <div className="tts-candidate-comparison" hidden={Boolean(routeEditingSessionId)}>
                    <p className="section-kicker">내 목소리 후보 비교</p>
                    {isLoadingTtsCandidates ? <p className="meta-copy">불러오는 중...</p> : null}
                    {!isLoadingTtsCandidates && ttsCandidates.length === 0 ? (
                      <p className="empty-state">이 세그먼트의 TTS 후보가 아직 없습니다</p>
                    ) : null}
                    {ttsCandidates.map((candidate, index) => (
                      <div className="tts-candidate-row" key={candidate.candidate_id}>
                        <span>
                          {`후보 ${index + 1}`}
                        </span>
                        <p className="meta-copy">{formatDisplayText(candidate.source_text)}</p>
                        <p className="meta-copy">
                          {candidate.technical_status !== "accepted"
                            ? "이 후보는 아직 사용할 수 없어요. 다른 후보를 골라주세요."
                            : candidate.operator_review_status === "approved"
                              ? "기술 검증 통과 · 청취 승인됨"
                              : candidate.operator_review_status === "rejected"
                                ? "청취 거부됨 · 기존 나레이션 유지"
                                : "기술 검증 통과 · 청취 승인 대기"}
                        </p>
                        <audio
                          controls
                          src={api.assetContentUrl(selectedProjectId!, candidate.asset_id)}
                        />
                        <button
                          className="action-button"
                          disabled={
                            candidate.technical_status !== "accepted" ||
                            candidate.operator_review_status !== "approved"
                          }
                          onClick={() =>
                            updateEditingDraft(selectedEditingSegment.segment_id, {
                              ttsRecommendationId: candidate.candidate_id,
                              ttsAssetId: candidate.asset_id,
                            })
                          }
                          type="button"
                        >
                          이 후보 선택
                        </button>
                        {candidate.technical_status === "accepted" &&
                        candidate.operator_review_status === "pending" ? (
                          <>
                            <button
                              className="action-button"
                              disabled={isReviewingTtsCandidate === candidate.candidate_id}
                              onClick={() =>
                                void handleReviewTtsCandidate(
                                  candidate.candidate_id,
                                  "approved",
                                )
                              }
                              type="button"
                            >
                              {isReviewingTtsCandidate === candidate.candidate_id
                                ? "청취 결정 저장 중"
                                : "청취 승인"}
                            </button>
                            <button
                              className="action-button"
                              disabled={isReviewingTtsCandidate === candidate.candidate_id}
                              onClick={() =>
                                void handleReviewTtsCandidate(
                                  candidate.candidate_id,
                                  "rejected",
                                )
                              }
                              type="button"
                            >
                              청취 거부
                            </button>
                          </>
                        ) : null}
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
                            editingSession!.session_revision,
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
