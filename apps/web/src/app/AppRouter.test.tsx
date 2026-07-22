import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryHistory } from "@tanstack/react-router";

import { api } from "../api";
import { AppRouter, createAppRouter, ProjectCatalog } from "./AppRouter";
import { parseWorkspaceLocation, resolveWorkspaceLocation } from "./routeManifest";

beforeEach(() => { vi.stubGlobal("scrollTo", vi.fn()); vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false })); vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("ProjectCatalog", () => {
  it("shares one catalog request across simultaneous route loaders and refreshes only after creation", async () => {
    const listProjects = vi.spyOn(api, "listProjects")
      .mockResolvedValueOnce([{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }])
      .mockResolvedValueOnce([
        { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
        { project_id: "project_b", name: "B", status: "active", root_storage_uri: "local://b" },
      ]);
    const catalog = new ProjectCatalog();

    await Promise.all([catalog.load(), catalog.load(), catalog.load()]);
    expect(listProjects).toHaveBeenCalledTimes(1);

    await catalog.refresh();
    expect(listProjects).toHaveBeenCalledTimes(2);
  });

  it("does not let a pre-creation catalog response overwrite the refreshed catalog", async () => {
    let resolveFirst!: (projects: Awaited<ReturnType<typeof api.listProjects>>) => void;
    const first = new Promise<Awaited<ReturnType<typeof api.listProjects>>>((resolve) => { resolveFirst = resolve; });
    const listProjects = vi.spyOn(api, "listProjects")
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce([{ project_id: "project_created", name: "New", status: "active", root_storage_uri: "local://new" }]);
    const catalog = new ProjectCatalog();

    const initial = catalog.load();
    const afterCreate = catalog.refresh();
    await expect(afterCreate).resolves.toMatchObject([{ project_id: "project_created" }]);
    resolveFirst([{ project_id: "project_old", name: "Old", status: "active", root_storage_uri: "local://old" }]);
    await initial;

    await expect(catalog.load()).resolves.toMatchObject([{ project_id: "project_created" }]);
    expect(listProjects).toHaveBeenCalledTimes(2);
  });
});

describe("AppRouter URL ownership", () => {
  it("uses /editor for new editing links while continuing to read the prior editing URL", () => {
    expect(resolveWorkspaceLocation("project_a", "editing")).toBe("/projects/project_a/editor");
    expect(parseWorkspaceLocation("/projects/project_a/editor")).toEqual({ projectId: "project_a", section: "editing" });
    expect(parseWorkspaceLocation("/projects/project_a/editing")).toEqual({ projectId: "project_a", section: "editing" });
  });

  it("pins the latest session before opening a canonical editor URL without a session", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }]);
    const latest = vi.spyOn(api, "getLatestEditingSession").mockResolvedValue({ session_id: "editing_session_latest" } as never);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editor"] }));

    render(<AppRouter router={router} />);

    await waitFor(() => expect(latest).toHaveBeenCalledWith("project_a"));
    await waitFor(() => expect(router.state.location.href).toBe("/projects/project_a/editor?session_id=editing_session_latest"));
  });

  it("fails closed for a blank canonical editor session instead of resolving the latest session", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }]);
    const latest = vi.spyOn(api, "getLatestEditingSession");
    const manifest = vi.spyOn(api, "getEditorPlaybackManifest");
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editor?session_id=%20"] }));

    render(<AppRouter router={router} />);

    expect(await screen.findByText("편집 세션을 찾을 수 없어요. 다시 열어 주세요.")).toBeVisible();
    expect(latest).not.toHaveBeenCalled();
    expect(manifest).not.toHaveBeenCalled();
  });

  it("redirects / to the catalog-validated last project with only one catalog request", async () => {
    window.localStorage.setItem("videobox.last-valid-project", "project_b");
    const listProjects = vi.spyOn(api, "listProjects").mockResolvedValue([
      { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
      { project_id: "project_b", name: "B", status: "active", root_storage_uri: "local://b" },
    ]);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/"] }));

    render(<AppRouter router={router} />);

    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/project_b/home"));
    expect(listProjects).toHaveBeenCalledTimes(1);
  });

  it("renders recovery for an unknown project without any project-scoped request", async () => {
    const listProjects = vi.spyOn(api, "listProjects").mockResolvedValue([
      { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
    ]);
    const getProject = vi.spyOn(api, "getProject");
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/missing/editing"] }));

    render(<AppRouter router={router} />);

    await screen.findByTestId("project-recovery");
    expect(listProjects).toHaveBeenCalledTimes(1);
    expect(getProject).not.toHaveBeenCalled();
  });

  it("shows onboarding at /projects when the catalog is empty", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([]);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));

    render(<AppRouter router={router} />);

    await screen.findByText("영상 만들기 시작");
    expect(router.state.location.pathname).toBe("/projects");
  });

  it("keeps a valid direct workspace URL through a router remount", async () => {
    const projects = [{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }];
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const history = createMemoryHistory({ initialEntries: ["/projects/project_a/editing"] });
    const first = createAppRouter(new ProjectCatalog(), history);

    render(<AppRouter router={first} />);
    await waitFor(() => expect(first.state.location.pathname).toBe("/projects/project_a/editing"));
    await waitFor(() => expect(window.localStorage.getItem("videobox.last-valid-project")).toBe("project_a"));
    cleanup();

    const remounted = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editing"] }));
    render(<AppRouter router={remounted} />);
    await waitFor(() => expect(remounted.state.location.pathname).toBe("/projects/project_a/editing"));
  });

  it("mounts the canonical editor as a dense read-only workbench without legacy media", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1920 });
    const project = { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" };
    const atomicSession = { session_id: "editing_session_draft_1", project_id: "project_a", timeline_id: "timeline_draft_1", session_revision: 1, history: [], undo_count: 0, redo_count: 0, segments: [{ segment_id: "segment_1", caption_text: "소개", start_sec: 0, end_sec: 2, cut_action: "keep", review_required: false, broll_override: null, visual_overlays: [], music_override: null, sfx_override: null, tts_replacement: null }] } as never;
    vi.spyOn(api, "listProjects").mockResolvedValue([project]);
    vi.spyOn(api, "getProject").mockResolvedValue(project);
    vi.spyOn(api, "listJobs").mockResolvedValue([
      { job_id: "timeline_build_job_selected", job_type: "timeline_build", status: "succeeded", input_ref: "ready-selected", output_ref: "timeline_draft_1", error_message: null, started_at: "2026-07-18T00:00:00Z", finished_at: "2026-07-18T00:00:01Z" },
      { job_id: "timeline_build_job_other", job_type: "timeline_build", status: "succeeded", input_ref: "ready-other", output_ref: "timeline_other", error_message: null, started_at: "2026-07-18T00:02:00Z", finished_at: "2026-07-18T00:03:00Z" },
      { job_id: "final_render_from_session_a", job_type: "final_render", status: "succeeded", input_ref: "timeline_build_job_selected", output_ref: "final_from_session_a", error_message: null, started_at: "2026-07-18T00:04:00Z", finished_at: "2026-07-18T00:04:01Z" },
    ] as never);
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([]);
    const getTimeline = vi.spyOn(api, "getTimeline").mockResolvedValue({ job_id: "timeline_build_job_selected", status: "succeeded", timeline: { timeline_id: "timeline_draft_1", tracks: [], review_flags: [], pending_recommendations: [] } } as never);
    vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({ project_id: "project_a", timeline_id: "timeline_draft_1", review_status: "draft", segments: [], applied_recommendations: [], pending_recommendations: [], review_flags: [] } as never);
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: "final_render_from_session_a", status: "succeeded", render: {
        export_id: "final_from_session_a", timeline_id: "timeline_draft_1", export_type: "final_render", file_uri: "local://project_a/final-from-session-a.mp4", status: "succeeded", source_session_revision: 1, is_current: false,
      },
    } as never);
    const loadSession = vi.spyOn(api, "getEditingSession").mockResolvedValue(atomicSession);
    const split = vi.spyOn(api, "splitEditingSessionSegment").mockResolvedValue(atomicSession);
    const saveMusic = vi.spyOn(api, "updateEditingSessionMusicOverride").mockResolvedValue({ ...atomicSession, session_revision: 2 } as never);
    const previewPartialRegeneration = vi.spyOn(api, "previewPartialRegeneration");
    const runPartialRegeneration = vi.spyOn(api, "runPartialRegeneration");
    const importBrollBatch = vi.spyOn(api, "importBrollBatch");
    const generateTtsCandidate = vi.spyOn(api, "generateTtsCandidate");
    const listTtsCandidates = vi.spyOn(api, "listTtsCandidates");
    const loadLatest = vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    const loadManifest = vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue({
      project_id: "project_a", session_id: "editing_session_draft_1", timeline_id: "timeline_draft_1", session_revision: 1, timeline_version: "v1",
      timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 2 }, tracks: [{ track_id: "narration", track_type: "narration", clips: [{ clip_id: "clip_1", segment_id: "segment_1", clip_type: "narration", asset_id: null, asset_uri: null, start_sec: 0, end_sec: 2, media_controls: {} }] }, { track_id: "music", track_type: "bgm", clips: [{ clip_id: "music_1", segment_id: "segment_1", clip_type: "bgm", asset_id: "asset_music", asset_uri: null, start_sec: 0, end_sec: 2, media_controls: { volume: 0.6, fade_in_sec: 0.5, fade_out_sec: 0.25 } }] }], captions: [{ segment_id: "segment_1", text: "소개", start_sec: 0, end_sec: 2, style: { font_family: "Pretendard", font_size_px: 20, text_color: "#fff", outline_color: "#000", outline_width_px: 1, background_color: "#00000000", position_x_percent: 50, position_y_percent: 90, horizontal_align: "center", safe_area_enabled: true, shadow_blur_px: 0 } }], gap_slots: [],
      source_status: { status: "current", source_session_id: "editing_session_draft_1", source_session_revision: 1 }, audition: { asset_urls: { narration: "/api/projects/project_a/assets/narration/content" } },
      exact_preview: { status: "succeeded", url: "/api/projects/project_a/exact-previews/generation-1/content", source_session_id: "editing_session_draft_1", source_session_revision: 1, artifact_revision: 1, timeline_start_sec: 0, timeline_end_sec: 2 },
    });
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editor?session_id=editing_session_draft_1"] }));

    render(<AppRouter router={router} />);

    await waitFor(() => expect(loadManifest).toHaveBeenCalledWith("project_a", "editing_session_draft_1"));
    expect(loadLatest).not.toHaveBeenCalled();
    const workbench = await screen.findByRole("region", { name: "편집 작업판" });
    expect(workbench).toHaveAttribute("data-editor-density", "desktop-both");
    expect(screen.getByRole("region", { name: "미리보기" }).parentElement).toHaveAttribute("data-preview-min-width", "720");
    expect(screen.getByLabelText("편집본 미리보기")).toHaveAttribute("src", "/api/projects/project_a/exact-previews/generation-1/content");
    expect(document.querySelectorAll("audio,video")).toHaveLength(1);
    expect(screen.getByLabelText("유진에게 요청하기")).toBeDisabled();
    expect(screen.getByRole("button", { name: "요청 보내기" })).toBeDisabled();
    expect(screen.getByText("아직 추천이 없어요. 직접 편집을 계속하거나 유진에게 요청할 수 있어요.")).toBeVisible();
    expect(loadManifest).toHaveBeenCalledTimes(1);
    expect(loadSession).not.toHaveBeenCalled();
    expect(getTimeline).not.toHaveBeenCalled();
    expect(previewPartialRegeneration).not.toHaveBeenCalled();
    expect(runPartialRegeneration).not.toHaveBeenCalled();
    expect(importBrollBatch).not.toHaveBeenCalled();
    expect(generateTtsCandidate).not.toHaveBeenCalled();
    expect(listTtsCandidates).not.toHaveBeenCalled();
    expect(split).not.toHaveBeenCalled();
    expect(saveMusic).not.toHaveBeenCalled();
  });

  it("keeps pinned editing actions offline when its manifest cannot be loaded", async () => {
    const project = { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" };
    const session = { session_id: "editing_session_pinned", project_id: "project_a", timeline_id: "timeline_pinned", session_revision: 1, history: [], undo_count: 0, redo_count: 0, segments: [{ segment_id: "segment_pinned", caption_text: "소개", start_sec: 0, end_sec: 2, cut_action: "keep", review_required: false, broll_override: null, visual_overlays: [], music_override: null, sfx_override: null, tts_replacement: null }] } as never;
    vi.spyOn(api, "listProjects").mockResolvedValue([project]);
    vi.spyOn(api, "getProject").mockResolvedValue(project);
    vi.spyOn(api, "listJobs").mockResolvedValue([{ job_id: "timeline_build_pinned", job_type: "timeline_build", status: "succeeded", input_ref: "ready", output_ref: "timeline_pinned", error_message: null, started_at: "now", finished_at: "now" }] as never);
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([]);
    vi.spyOn(api, "getEditingSession").mockResolvedValue(session);
    vi.spyOn(api, "getEditorPlaybackManifest").mockRejectedValue(new Error("not ready"));
    vi.spyOn(api, "getTimeline").mockResolvedValue({ job_id: "timeline_build_pinned", status: "succeeded", timeline: { timeline_id: "timeline_pinned", tracks: [], review_flags: [], pending_recommendations: [] } } as never);
    vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({ project_id: "project_a", timeline_id: "timeline_pinned", review_status: "draft", segments: [], applied_recommendations: [], pending_recommendations: [], review_flags: [] } as never);
    const split = vi.spyOn(api, "splitEditingSessionSegment").mockResolvedValue(session);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editor?session_id=editing_session_pinned"] }));

    render(<AppRouter router={router} />);

    expect(await screen.findByText("재생 내용을 불러오지 못했어요. 새로고침 후 다시 확인해 주세요.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "분할" })).not.toBeInTheDocument();
    expect(split).not.toHaveBeenCalled();
  });

  it("refreshes the catalog and moves a newly created project to its create route", async () => {
    const created = { project_id: "project_new", name: "New", status: "active", root_storage_uri: "local://new" };
    const listProjects = vi.spyOn(api, "listProjects").mockResolvedValueOnce([]).mockResolvedValueOnce([created]);
    vi.spyOn(api, "createProject").mockResolvedValue(created);
    vi.spyOn(api, "registerNarrationAudio").mockResolvedValue({ asset_id: "narration" } as never);
    vi.spyOn(api, "registerScriptDocument").mockResolvedValue({ asset_id: "script" } as never);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));

    render(<AppRouter router={router} />);
    fireEvent.change(await screen.findByLabelText("프로젝트 이름"), { target: { value: "New" } });
    fireEvent.change(screen.getByLabelText("나레이션 로컬 경로"), { target: { value: "local://narration" } });
    fireEvent.change(screen.getByLabelText("스크립트 로컬 경로"), { target: { value: "local://script" } });
    fireEvent.click(screen.getByRole("button", { name: "프로젝트 만들고 소스 등록" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/project_new/create"));
    expect(listProjects).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("heading", { name: "영상 만들기 시작" })).toBeNull();
    expect(screen.queryByRole("button", { name: "프로젝트 만들고 소스 등록" })).toBeNull();
  });

  it("keeps onboarding at /projects when either required source registration fails", async () => {
    const created = { project_id: "project_retry", name: "Retry", status: "active", root_storage_uri: "local://retry" };
    const listProjects = vi.spyOn(api, "listProjects").mockResolvedValueOnce([]).mockResolvedValueOnce([created]);
    vi.spyOn(api, "createProject").mockResolvedValue(created);
    vi.spyOn(api, "registerNarrationAudio").mockRejectedValue(new Error("missing narration"));
    vi.spyOn(api, "registerScriptDocument").mockResolvedValue({ asset_id: "script" } as never);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);
    fireEvent.change(await screen.findByLabelText("프로젝트 이름"), { target: { value: "Retry" } });
    fireEvent.change(screen.getByLabelText("나레이션 로컬 경로"), { target: { value: "local://missing" } });
    fireEvent.change(screen.getByLabelText("스크립트 로컬 경로"), { target: { value: "local://script" } });
    fireEvent.click(screen.getByRole("button", { name: "프로젝트 만들고 소스 등록" }));

    await screen.findByRole("button", { name: "나레이션 다시 등록" });
    expect(router.state.location.pathname).toBe("/projects");
    expect(listProjects).toHaveBeenCalledTimes(1);
  });

  it("preserves the create leaf when a project switch navigates to another project", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([
      { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
      { project_id: "project_b", name: "B", status: "active", root_storage_uri: "local://b" },
    ]);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/create"] }));
    render(<AppRouter router={router} />);
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/project_a/create"));

    await act(async () => { await router.navigate({ to: "/projects/project_b/create" }); });

    expect(router.state.location.pathname).toBe("/projects/project_b/create");
  });

  it("renders the durable Eugene creation interview at the routed create leaf", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([
      { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
    ]);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/create"] }));

    render(<AppRouter router={router} />);

    await screen.findByRole("heading", { name: "유진과 영상 기획을 시작해요" });
    expect(screen.getByLabelText("대본 붙여넣기")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "영상 만들기 시작" })).toBeNull();
  });

  it("does not let a late A workspace response overwrite the currently routed B workspace", async () => {
    const projects = [
      { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
      { project_id: "project_b", name: "B", status: "active", root_storage_uri: "local://b" },
    ];
    let resolveA!: (project: typeof projects[number]) => void;
    let resolveB!: (project: typeof projects[number]) => void;
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    vi.spyOn(api, "getProject").mockImplementation((projectId) => new Promise((resolve) => {
      if (projectId === "project_a") resolveA = resolve;
      else resolveB = resolve;
    }));
    vi.spyOn(api, "listJobs").mockResolvedValue([]);
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editing"] }));
    render(<AppRouter router={router} />);
    await waitFor(() => expect(api.getProject).toHaveBeenCalledWith("project_a"));

    await act(async () => { await router.navigate({ to: "/projects/project_b/editing" }); });
    await waitFor(() => expect(api.getProject).toHaveBeenCalledWith("project_b"));
    await act(async () => { resolveB(projects[1]); });
    await screen.findByRole("heading", { name: "B" });

    await act(async () => { resolveA(projects[0]); });
    await waitFor(() => expect(screen.getByRole("heading", { name: "B" })).toBeTruthy());
    expect(screen.queryByRole("heading", { name: "A" })).toBeNull();
  });

  it("navigates catalog and recovery choices to a real project home", async () => {
    const projects = [{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }];
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const catalogRouter = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={catalogRouter} />);
    fireEvent.click(await screen.findByRole("button", { name: "A" }));
    await waitFor(() => expect(catalogRouter.state.location.pathname).toBe("/projects/project_a/home"));
    cleanup();

    const recoveryRouter = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/missing/editing"] }));
    render(<AppRouter router={recoveryRouter} />);
    fireEvent.click(await screen.findByRole("button", { name: "A" }));
    await waitFor(() => expect(recoveryRouter.state.location.pathname).toBe("/projects/project_a/home"));
  });
});
