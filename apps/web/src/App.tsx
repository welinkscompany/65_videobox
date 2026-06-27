import { useEffect, useMemo, useState } from "react";

import {
  api,
  type ExportJob,
  type JobRecord,
  type PreviewJob,
  type Project,
  type ReviewSnapshot,
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
  const candidates = jobs.filter(
    (job) => job.job_type === "timeline_build" && job.status === "succeeded",
  );
  return candidates.length > 0 ? candidates[candidates.length - 1] : null;
}

function findLatestSucceededJob(jobs: JobRecord[], jobType: string, inputRef?: string | null) {
  const candidates = jobs.filter(
    (job) =>
      job.job_type === jobType &&
      job.status === "succeeded" &&
      (inputRef == null || job.input_ref === inputRef),
  );
  return candidates.length > 0 ? candidates[candidates.length - 1] : null;
}

export function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedSection, setSelectedSection] = useState<
    "overview" | "timeline" | "review"
  >("overview");
  const [projectDetail, setProjectDetail] = useState<Project | null>(null);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [timelineJob, setTimelineJob] = useState<TimelineJob | null>(null);
  const [reviewSnapshot, setReviewSnapshot] = useState<ReviewSnapshot | null>(null);
  const [previewJob, setPreviewJob] = useState<PreviewJob | null>(null);
  const [exportJob, setExportJob] = useState<ExportJob | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRebuildingTimeline, setIsRebuildingTimeline] = useState(false);
  const [isRenderingPreview, setIsRenderingPreview] = useState(false);
  const [isExportingCapcut, setIsExportingCapcut] = useState(false);

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
      setPreviewJob(null);
      setExportJob(null);
      return;
    }

    let cancelled = false;
    const projectId = selectedProjectId;

    async function loadProjectWorkspace() {
      setLoadState("loading");
      setErrorMessage(null);
      try {
        const project = await api.getProject(projectId);
        const jobItems = await api.listJobs(projectId);
        const latestTimelineJob = findLatestTimelineJob(jobItems);
        const [timeline, review] = latestTimelineJob
          ? await Promise.all([
              api.getTimeline(projectId, latestTimelineJob.job_id),
              api.getReviewSnapshot(projectId, latestTimelineJob.job_id),
            ])
          : [null, null];
        const latestPreviewJob = latestTimelineJob
          ? findLatestSucceededJob(jobItems, "preview_render", latestTimelineJob.job_id)
          : null;
        const latestExportJob = latestTimelineJob
          ? findLatestSucceededJob(jobItems, "capcut_export", latestTimelineJob.job_id)
          : null;
        const preview = latestPreviewJob
          ? await api.getPreview(projectId, latestPreviewJob.job_id)
          : null;
        const capcutExport = latestExportJob
          ? await api.getExport(projectId, latestExportJob.job_id)
          : null;
        if (cancelled) {
          return;
        }
        setProjectDetail(project);
        setJobs(jobItems);
        setTimelineJob(timeline);
        setReviewSnapshot(review);
        setPreviewJob(preview);
        setExportJob(capcutExport);
        setLoadState("ready");
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

  const pipelineStages = useMemo(
    () => [
      { label: "Transcription", jobType: "transcription" },
      { label: "Segment analysis", jobType: "segment_analysis" },
      { label: "B-roll recommendation", jobType: "broll_recommendation" },
      { label: "Music recommendation", jobType: "music_recommendation" },
      { label: "Timeline build", jobType: "timeline_build" },
      { label: "Preview render", jobType: "preview_render" },
      { label: "CapCut export", jobType: "capcut_export" },
    ],
    [],
  );

  const stageStatus = useMemo(() => {
    return pipelineStages.map((stage) => {
      const matchingJobs = jobs.filter((job) => job.job_type === stage.jobType);
      const stageJob =
        matchingJobs.length > 0 ? matchingJobs[matchingJobs.length - 1] : undefined;
      return {
        ...stage,
        status: stageJob?.status ?? "pending",
        jobId: stageJob?.job_id ?? "not-started",
      };
    });
  }, [jobs, pipelineStages]);

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

  const latestTimelineBuildJob = useMemo(
    () => findLatestTimelineJob(jobs),
    [jobs],
  );
  const hasReviewBlockers = useMemo(() => {
    if (!timelineJob || !reviewSnapshot) {
      return true;
    }
    return (
      timelineJob.timeline.review_flags.length > 0 ||
      reviewSnapshot.pending_recommendations.length > 0
    );
  }, [reviewSnapshot, timelineJob]);

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
    if (!selectedProjectId || !latestTimelineBuildJob || hasReviewBlockers) {
      return;
    }
    setIsRenderingPreview(true);
    setErrorMessage(null);
    try {
      const renderResult = await api.renderPreview(selectedProjectId, {
        timeline_job_id: latestTimelineBuildJob.job_id,
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
    if (!selectedProjectId || !latestTimelineBuildJob || hasReviewBlockers) {
      return;
    }
    setIsExportingCapcut(true);
    setErrorMessage(null);
    try {
      const exportResult = await api.exportCapcut(selectedProjectId, {
        timeline_job_id: latestTimelineBuildJob.job_id,
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
            ].map(([value, label]) => (
              <button
                key={value}
                className={selectedSection === value ? "tab-button is-active" : "tab-button"}
                onClick={() => setSelectedSection(value as "overview" | "timeline" | "review")}
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
              disabled={!latestTimelineBuildJob || hasReviewBlockers || isRenderingPreview}
              onClick={() => void handleRenderPreview()}
              type="button"
            >
              {isRenderingPreview ? "Rendering preview..." : "Render preview artifact"}
            </button>
            <button
              className="action-button"
              disabled={!latestTimelineBuildJob || hasReviewBlockers || isExportingCapcut}
              onClick={() => void handleExportCapcut()}
              type="button"
            >
              {isExportingCapcut ? "Exporting CapCut..." : "Export CapCut payload"}
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
                    <p>{previewJob.preview.file_uri}</p>
                  </article>
                ) : null}
                {exportJob ? (
                  <article className="artifact-card">
                    <h3>{exportJob.export.export_type}</h3>
                    <p>{exportJob.export.file_uri}</p>
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
                  {(reviewSnapshot?.pending_recommendations ?? []).map((item) => (
                    <div className="recommendation-card pending" key={item.recommendation_id}>
                      <strong>{prettifyJobType(item.recommendation_type)}</strong>
                      <p>{item.reason}</p>
                      <span>{item.target_segment_id}</span>
                    </div>
                  ))}
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
      </main>
    </div>
  );
}
