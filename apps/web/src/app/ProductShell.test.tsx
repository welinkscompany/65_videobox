import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryHistory } from "@tanstack/react-router";

import { api } from "../api";
import { AppRouter, createAppRouter, ProjectCatalog } from "./AppRouter";
import { HomePage, ProductShell, SettingsPage } from "./ProductShell";

beforeEach(() => { vi.stubGlobal("scrollTo", vi.fn()); vi.stubGlobal("PointerEvent", MouseEvent); vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false })); vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.localStorage.clear(); });

const projects = [
  { project_id: "first", name: "첫 번째 영상", status: "active", root_storage_uri: "local://first" },
  { project_id: "second", name: "두 번째 영상", status: "active", root_storage_uri: "local://second" },
];

describe("product shell", () => {
  it("separates the four global destinations from the five project stages", () => {
    const view = render(<ProductShell projectId="first" projects={projects as never} section="home" onNavigate={vi.fn()} onOpenSettings={vi.fn()}><p>본문</p></ProductShell>);

    const global = screen.getByRole("navigation", { name: "전체 메뉴" });
    expect(within(global).getAllByRole("link")).toHaveLength(4);
    for (const label of ["프로젝트", "내 라이브러리", "촬영본 정리", "설정"]) {
      expect(within(global).getByRole("link", { name: label })).toBeInTheDocument();
    }
    const stages = screen.getByRole("navigation", { name: "프로젝트 단계" });
    expect(within(stages).getAllByRole("button")).toHaveLength(5);
    for (const label of ["기획", "자산", "편집", "검토", "출력"]) {
      expect(within(stages).getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(view.container.querySelectorAll("main")).toHaveLength(1);
  });

  it("does not render project stages when no project is open", () => {
    render(<ProductShell projectId="" projects={[]} section="home" onNavigate={vi.fn()} onOpenSettings={vi.fn()}><p>본문</p></ProductShell>);

    expect(screen.getByRole("navigation", { name: "전체 메뉴" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "프로젝트 단계" })).not.toBeInTheDocument();
  });

  it("keeps dashboard copy in creator language", () => {
    const { container } = render(<ProductShell projectId="first" projects={projects as never} section="home" onNavigate={vi.fn()} onOpenSettings={vi.fn()}><p>영상</p></ProductShell>);
    const copy = container.textContent ?? "";
    for (const prohibited of ["provider", "runtime", "fallback", "loopback", "API key", "model", "context", "revision", "pipeline", "job"]) {
      expect(copy.toLowerCase()).not.toContain(prohibited.toLowerCase());
    }
  });

  it("gives primary navigation icons and keeps project actions behind one more menu", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/home"] }));
    render(<AppRouter router={router} />);

    const navigation = await screen.findByRole("navigation", { name: "프로젝트 단계" });
    const navButtons = within(navigation).getAllByRole("button");
    expect(navButtons).toHaveLength(5);
    for (const label of ["기획", "자산", "편집", "검토", "출력"]) {
      const button = within(navigation).getByRole("button", { name: label });
      expect(button.querySelector("svg")).toBeTruthy();
      expect(button.querySelector(".vb-nav-label")).toHaveTextContent(label);
    }

    const picker = screen.getByLabelText("프로젝트 전환");
    const projectRow = picker.querySelector('[data-testid="project-row-first"]');
    expect(projectRow).toBeTruthy();
    expect(within(projectRow as HTMLElement).getAllByRole("button")).toHaveLength(2);
    expect(within(projectRow as HTMLElement).getByRole("button", { name: "첫 번째 영상 더보기" })).toBeInTheDocument();
    expect(within(projectRow as HTMLElement).queryByRole("button", { name: /보관|삭제/ })).not.toBeInTheDocument();
  });

  it("provides a readable icon-only name when the sidebar is collapsed", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/home"] }));
    render(<AppRouter router={router} />);
    await screen.findByRole("navigation", { name: "프로젝트 단계" });
    fireEvent.click(screen.getByRole("button", { name: "사이드바 접기" }));

    const navigation = screen.getByRole("navigation", { name: "프로젝트 단계" });
    const plan = within(navigation).getByRole("button", { name: "기획" });
    expect(plan).toHaveAttribute("aria-label", "기획");
    expect(plan.querySelector(".vb-nav-label")).toHaveClass("group-data-[collapsible=icon]:hidden");
  });
  it("opens the current-project recovery surface only when the user asks for job status", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const getYujinStatus = vi.spyOn(api, "getHermesYujinStatus").mockResolvedValue({
      state: "chat_verified",
      http_ready: true,
      provider_ready: true,
      chat_verified: true,
      checked_at: "2026-07-30T12:00:00Z",
      last_chat_verified_at: "2026-07-30T11:59:59Z",
      restart_available: false,
      status_basis: "application_path",
    });
    const listJobs = vi.spyOn(api, "listJobs").mockResolvedValue([{
      job_id: "job-internal",
      project_id: "first",
      job_type: "transcription",
      status: "failed",
      input_ref: "asset-internal",
      output_ref: null,
      error_message: "provider internal",
      started_at: "now",
      finished_at: "now",
    }]);
    const retry = vi.spyOn(api, "retryJob");
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/home"] }));
    render(<AppRouter router={router} />);

    const trigger = await screen.findByRole("button", { name: "작업 상태" });
    expect(listJobs).not.toHaveBeenCalled();
    expect(getYujinStatus).not.toHaveBeenCalled();
    expect(retry).not.toHaveBeenCalled();
    fireEvent.click(trigger);

    expect(await screen.findByRole("dialog", { name: "작업 상태" })).toBeVisible();
    expect(screen.getByText("로컬 작업 상태를 확인하고 실패한 작업을 다시 시작할 수 있어요.")).toBeVisible();
    expect(await screen.findByRole("region", { name: "유진 연결 상태" })).toBeVisible();
    expect(screen.getByText("유진과 대화할 준비가 확인됐어요.")).toBeVisible();
    expect(screen.getByRole("region", { name: "작업 복구" })).toBeVisible();
    expect(screen.getByText("음성 받아쓰기")).toBeVisible();
    expect(getYujinStatus).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /재시작/ })).not.toBeInTheDocument();
    expect(retry).not.toHaveBeenCalled();
  });

  it("keeps the recovery dialog mounted while a retry is pending and allows close after it settles", async () => {
    let releaseRetry!: (value: { job_id: string; status: string }) => void;
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    vi.spyOn(api, "listJobs")
      .mockResolvedValueOnce([{
        job_id: "job-old",
        project_id: "first",
        job_type: "transcription",
        status: "failed",
        input_ref: "asset-lineage",
        output_ref: null,
        error_message: "local failure",
        started_at: "2026-07-23T00:00:00Z",
        finished_at: "2026-07-23T00:00:01Z",
      }])
      .mockResolvedValueOnce([{
        job_id: "job-old",
        project_id: "first",
        job_type: "transcription",
        status: "failed",
        input_ref: "asset-lineage",
        output_ref: null,
        error_message: "local failure",
        started_at: "2026-07-23T00:00:00Z",
        finished_at: "2026-07-23T00:00:01Z",
      }, {
        job_id: "job-new",
        project_id: "first",
        job_type: "transcription",
        status: "running",
        input_ref: "asset-lineage",
        output_ref: null,
        error_message: null,
        started_at: "2026-07-23T00:00:02Z",
        finished_at: null,
      }]);
    const retry = vi.spyOn(api, "retryJob").mockImplementation(() => new Promise((resolve) => {
      releaseRetry = resolve;
    }));
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/home"] }));
    render(<AppRouter router={router} />);

    fireEvent.click(await screen.findByRole("button", { name: "작업 상태" }));
    const retryButton = await screen.findByRole("button", { name: "다시 실행" });
    fireEvent.click(retryButton);
    expect(retry).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("dialog", { name: "작업 상태" })).toBeVisible();
    fireEvent.click(retryButton);
    expect(retry).toHaveBeenCalledTimes(1);

    await act(async () => releaseRetry({ job_id: "job-new", status: "running" }));
    const close = await screen.findByRole("button", { name: "Close" });
    fireEvent.click(close);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "작업 상태" })).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "작업 상태" }));
    expect(await screen.findByRole("dialog", { name: "작업 상태" })).toBeVisible();
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("starts collapsed only for the canonical editor and allows an explicit reopen", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue({ project_id: "first", session_id: "session-a", timeline_id: "timeline-a", session_revision: 1, timeline_version: "v1", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 1 }, tracks: [], captions: [], gap_slots: [], source_status: { status: "current", source_session_id: "session-a", source_session_revision: 1 }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: "session-a", source_session_revision: 1 } } as never);
    vi.spyOn(api, "getEditingSession").mockResolvedValue({
      project_id: "first", session_id: "session-a", timeline_id: "timeline-a", session_revision: 1,
      segments: [], history: [],
    } as never);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/editor?session_id=session-a"] }));
    render(<AppRouter router={router} />);
    await screen.findByRole("region", { name: "편집 작업판" });
    const sidebar = document.querySelector('[data-slot="sidebar"]');
    expect(sidebar).toHaveAttribute("data-state", "collapsed");
    fireEvent.click(screen.getByRole("button", { name: "사이드바 펼치기" }));
    expect(sidebar).toHaveAttribute("data-state", "expanded");

    await router.navigate({ to: "/projects/first/home" });
    await screen.findByTestId("product-home");
    await router.navigate({ to: "/projects/first/editor", search: { session_id: "session-a" } });
    await screen.findByRole("region", { name: "편집 작업판" });
    expect(document.querySelector('[data-slot="sidebar"]')).toHaveAttribute("data-state", "collapsed");
  });

  it("keeps a single '새 영상 만들기' entry point outside the home screen (F-7)", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([]);
    vi.spyOn(api, "listMediaAnalysis").mockResolvedValue({ items: [] });
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/media"] }));
    render(<AppRouter router={router} />);

    await screen.findByTestId("media-workspace-page");

    expect(screen.getByRole("button", { name: "자산" })).toBeInTheDocument();
    expect(document.querySelectorAll("main")).toHaveLength(1);
  });

  it("shows creator navigation, a project switcher, and an action-only home", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/home"] }));
    render(<AppRouter router={router} />);

    await screen.findByRole("navigation", { name: "프로젝트 단계" });
    expect(screen.getAllByRole("link", { name: "내 라이브러리" })).toHaveLength(1);
    const home = screen.getByTestId("product-home");
    expect(within(home).getByText("편집")).toBeTruthy();
    expect(within(home).getByText("완성본")).toBeTruthy();
    expect(screen.queryByText(/provider|job metric/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "두 번째 영상" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/second/home"));
  });

  it("archives a project from the switcher after a confirm step, and it drops off the list (F-5)", async () => {
    vi.spyOn(api, "listProjects")
      .mockResolvedValueOnce(projects)
      .mockResolvedValueOnce([projects[0]]);
    const archiveProject = vi.spyOn(api, "archiveProject").mockResolvedValue({ ...projects[1], status: "archived" });
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/home"] }));
    render(<AppRouter router={router} />);
    await screen.findByRole("navigation", { name: "프로젝트 단계" });

    fireEvent.pointerDown(screen.getByRole("button", { name: "두 번째 영상 더보기" }), { button: 0 });
    fireEvent.click(screen.getByRole("menuitem", { name: "보관하기" }));
    expect(archiveProject).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("menuitem", { name: "보관 확인" }));

    await waitFor(() => expect(archiveProject).toHaveBeenCalledWith("second"));
    await waitFor(() => expect(screen.queryByRole("button", { name: /두 번째 영상/ })).not.toBeInTheDocument());
  });

  it("requires two separate confirmations before permanently deleting a project", async () => {
    vi.spyOn(api, "listProjects")
      .mockResolvedValueOnce(projects)
      .mockResolvedValueOnce([projects[0]]);
    const deleteProjectPermanently = vi.spyOn(api, "deleteProjectPermanently").mockResolvedValue(undefined);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/home"] }));
    render(<AppRouter router={router} />);
    await screen.findByRole("navigation", { name: "프로젝트 단계" });

    fireEvent.pointerDown(screen.getByRole("button", { name: "두 번째 영상 더보기" }), { button: 0 });
    fireEvent.click(screen.getByRole("menuitem", { name: "완전 삭제" }));
    expect(deleteProjectPermanently).not.toHaveBeenCalled();
    expect(screen.getByText(/되돌릴 수 없어요/)).toBeVisible();

    fireEvent.click(screen.getByRole("menuitem", { name: /삭제 1차 확인/ }));
    expect(deleteProjectPermanently).not.toHaveBeenCalled();
    expect(screen.getByText(/한 번 더 확인/)).toBeVisible();

    fireEvent.click(screen.getByRole("menuitem", { name: /영구 삭제/ }));

    await waitFor(() => expect(deleteProjectPermanently).toHaveBeenCalledWith("second"));
    await waitFor(() => expect(screen.queryByRole("button", { name: /두 번째 영상/ })).not.toBeInTheDocument());
  });

  it("shows a retryable error when a project action fails", async () => {
    const onArchiveProject = vi.fn().mockRejectedValue(new Error("network down"));
    render(<ProductShell projectId="first" projects={projects as never} section="home" onNavigate={vi.fn()} onOpenSettings={vi.fn()} onArchiveProject={onArchiveProject}><p>본문</p></ProductShell>);

    fireEvent.pointerDown(screen.getByRole("button", { name: "두 번째 영상 더보기" }), { button: 0 });
    fireEvent.click(screen.getByRole("menuitem", { name: "보관하기" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "보관 확인" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("프로젝트 작업에 실패했어요. 다시 시도해 주세요.");
    expect(onArchiveProject).toHaveBeenCalledWith("second");
  });

  it("persists a working appearance setting and only exposes local privacy choices", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/settings/appearance"] }));
    render(<AppRouter router={router} />);

    const compact = await screen.findByRole("button", { name: "조밀한 화면: 꺼짐" });
    fireEvent.click(compact);
    expect(window.localStorage.getItem("videobox.settings")).toContain("compact");
    expect(screen.getByText("설정은 이 기기에서만 관리됩니다.")).toBeTruthy();
    expect(screen.queryByText(/billing|team|account/i)).toBeNull();
  });

  it("keeps AI privacy separate and opens the canonical voice settings owner", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/settings/ai-privacy"] }));
    render(<AppRouter router={router} />);

    expect(await screen.findByText("모든 처리는 이 기기 안에서만 이뤄집니다.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "내 목소리 준비 상태" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "내 목소리" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/voice"));
  });

  it("synchronously replaces project A voice controls before project B passive loading", async () => {
    const samplesB = new Promise<Awaited<ReturnType<typeof api.listVoiceSamples>>>(() => {});
    const sessionB = new Promise<Awaited<ReturnType<typeof api.getLatestEditingSession>>>(() => {});
    vi.spyOn(api, "listVoiceSamples").mockImplementation((projectId) => (
      projectId === "first"
        ? Promise.resolve([{ asset_id: "sample-a", asset_type: "voice_sample_audio", storage_uri: "local://voice/a.wav" }])
        : samplesB
    ));
    vi.spyOn(api, "getLatestEditingSession").mockImplementation((projectId) => (
      projectId === "first"
        ? Promise.resolve({
          session_id: "session-a",
          project_id: "first",
          timeline_id: "timeline-a",
          session_revision: 1,
          history: [],
          segments: [{ segment_id: "segment-a", caption_text: "A 프로젝트 문장", start_sec: 0, end_sec: 1, cut_action: "keep", review_required: false, broll_override: null, visual_overlays: [], music_override: null, tts_replacement: null }],
        })
        : sessionB
    ));
    const view = render(<SettingsPage projectId="first" section="voice" onNavigate={vi.fn()} />);
    await screen.findByText("저장한 내 목소리 1개");
    const pathA = screen.getByLabelText("음성 파일이 있는 곳");
    fireEvent.change(pathA, { target: { value: "D:\\voices\\project-a.wav" } });

    view.rerender(<SettingsPage projectId="second" section="voice" onNavigate={vi.fn()} />);

    const pathB = screen.getByLabelText("음성 파일이 있는 곳");
    expect(pathA).not.toBeInTheDocument();
    expect(pathB).not.toBe(pathA);
    expect(pathB).toHaveValue("");
    expect(pathB).toBeDisabled();
    expect(screen.queryByText("A 프로젝트 문장")).not.toBeInTheDocument();
    expect(screen.queryByText("저장한 내 목소리 1개")).not.toBeInTheDocument();
  });
});

describe("archived projects", () => {
  it("lets the owner see archived projects and put one back", async () => {
    // Task 32: archiving removed a project from the sidebar with no way back.
    // The restore endpoint existed the whole time; nothing called it.
    const onRestoreProject = vi.fn();
    const onLoadArchivedProjects = vi.fn().mockResolvedValue(undefined);
    render(
      <ProductShell
        projectId="project-a"
        projects={[{ project_id: "project-a", name: "살아있는 프로젝트", status: "draft" } as never]}
        archive={{
          archivedProjects: [{ project_id: "project-b", name: "보관한 프로젝트", status: "archived" } as never],
          load: onLoadArchivedProjects,
          restore: onRestoreProject,
        }}
        section="home"
        onNavigate={vi.fn()}
        onOpenSettings={vi.fn()}
      >
        <p>본문</p>
      </ProductShell>,
    );

    fireEvent.pointerDown(screen.getByRole("button", { name: "프로젝트 더보기" }), { button: 0 });
    fireEvent.click(screen.getByRole("menuitem", { name: "보관함 보기" }));
    expect(onLoadArchivedProjects).toHaveBeenCalled();
    expect(await screen.findByText("보관한 프로젝트")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "보관한 프로젝트 되돌리기" }));
    expect(onRestoreProject).toHaveBeenCalledWith("project-b");
  });

  it("shows a retryable error when restoring an archived project fails", async () => {
    const onRestoreProject = vi.fn().mockRejectedValue(new Error("network down"));
    render(
      <ProductShell
        projectId="project-a"
        projects={[{ project_id: "project-a", name: "살아있는 프로젝트", status: "draft" } as never]}
        archive={{ archivedProjects: [{ project_id: "project-b", name: "보관한 프로젝트", status: "archived" } as never], load: vi.fn(), restore: onRestoreProject }}
        section="home"
        onNavigate={vi.fn()}
        onOpenSettings={vi.fn()}
      >
        <p>본문</p>
      </ProductShell>,
    );
    fireEvent.pointerDown(screen.getByRole("button", { name: "프로젝트 더보기" }), { button: 0 });
    fireEvent.click(screen.getByRole("menuitem", { name: "보관함 보기" }));
    fireEvent.click(await screen.findByRole("button", { name: "보관한 프로젝트 되돌리기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("프로젝트 작업에 실패했어요. 다시 시도해 주세요.");
  });

  it("says so when the archive is empty instead of showing nothing", async () => {
    render(
      <ProductShell
        projectId="project-a"
        projects={[{ project_id: "project-a", name: "살아있는 프로젝트", status: "draft" } as never]}
        archive={{ archivedProjects: [], load: vi.fn().mockResolvedValue(undefined), restore: vi.fn() }}
        section="home"
        onNavigate={vi.fn()}
        onOpenSettings={vi.fn()}
      >
        <p>본문</p>
      </ProductShell>,
    );

    fireEvent.pointerDown(screen.getByRole("button", { name: "프로젝트 더보기" }), { button: 0 });
    fireEvent.click(screen.getByRole("menuitem", { name: "보관함 보기" }));
    expect(await screen.findByText("보관한 프로젝트가 없어요.")).toBeVisible();
  });
});


describe("home dashboard", () => {
  it("stops claiming there are no finished videos, and does not poll jobs to say so", async () => {
    // Task 35: the card asserted "완성된 영상이 아직 없어요" unconditionally, so it
    // was false the moment the owner finished one. Home deliberately does not
    // fetch the job list -- the recovery surface test above pins that -- so the
    // fix is to stop asserting a state home cannot know, not to add a fetch.
    const listJobs = vi.spyOn(api, "listJobs");
    vi.spyOn(api, "getHomeSummary").mockResolvedValue({
      finished_video_count: 0, has_draft: false, asset_gap_count: 0,
    } as never);
    render(<HomePage projectId="project-a" onNavigate={vi.fn()} />);

    expect(screen.queryByText("완성된 영상이 아직 없어요.")).toBeNull();
    expect(listJobs).not.toHaveBeenCalled();
  });

  it("tells the owner what is actually there, in one request", async () => {
    // The owner asked twice whether the dashboard was done. It was a menu:
    // all three cards stated their text unconditionally, so each could be
    // false. Home still must not poll the job list, so this is one call.
    const listJobs = vi.spyOn(api, "listJobs");
    const summary = vi.spyOn(api, "getHomeSummary").mockResolvedValue({
      finished_video_count: 3, has_draft: true, asset_gap_count: 2,
    } as never);

    render(<HomePage projectId="project-a" onNavigate={vi.fn()} />);

    expect(await screen.findByText("3개")).toBeVisible();
    expect(screen.getAllByText("초안 있음").length).toBeGreaterThan(0);
    expect(screen.getAllByText("부족 2곳").length).toBeGreaterThan(0);
    expect(summary).toHaveBeenCalledTimes(1);
    expect(listJobs).not.toHaveBeenCalled();
  });

  it("says the current status once per fact, not repeated across a keyword line, a checklist, and a card", async () => {
    // Home used to say "초안 있음" up to three times (a keyword line under
    // "다음 할 일", a checklist item, and the 편집 card) and put the same
    // "편집 계속하기" text on both a heading and the button right under it.
    vi.spyOn(api, "getHomeSummary").mockResolvedValue({
      finished_video_count: 3, has_draft: true, asset_gap_count: 2,
    } as never);

    render(<HomePage projectId="project-a" onNavigate={vi.fn()} />);

    await screen.findByText("3개");
    expect(screen.getAllByText("초안 있음")).toHaveLength(1);
    expect(screen.getAllByText("부족 2곳")).toHaveLength(1);
    expect(screen.getAllByText("3개")).toHaveLength(1);
    expect(screen.getAllByText("편집 계속하기")).toHaveLength(1);
  });

  it("says so plainly when the project is still empty", async () => {
    vi.spyOn(api, "getHomeSummary").mockResolvedValue({
      finished_video_count: 0, has_draft: false, asset_gap_count: 0,
    } as never);

    render(<HomePage projectId="project-a" onNavigate={vi.fn()} />);

    expect(await screen.findByText("0개")).toBeVisible();
    expect(screen.getAllByText("초안 없음").length).toBeGreaterThan(0);
    expect(screen.getAllByText("준비 완료").length).toBeGreaterThan(0);
  });

  it("keeps the cards usable when the summary cannot be read", async () => {
    // A home that cannot count must not block the owner from navigating, and
    // must not go back to asserting a state it does not know.
    vi.spyOn(api, "getHomeSummary").mockRejectedValue(new Error("offline"));

    render(<HomePage projectId="project-a" onNavigate={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "출력 확인" })).toBeVisible();
    expect(screen.queryByText("아직 완성한 영상이 없어요.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    expect(api.getHomeSummary).toHaveBeenCalledTimes(2);
  });
});

describe("settings that claim to change the screen", () => {
  const shell = () => render(
    <ProductShell
      projectId="project-a"
      projects={[{ project_id: "project-a", name: "프로젝트", status: "draft" } as never]}
      section="home"
      onNavigate={vi.fn()}
      onOpenSettings={vi.fn()}
    >
      <p>본문</p>
    </ProductShell>,
  );

  it("actually makes the shell compact and calms motion when asked", () => {
    // These wrote to localStorage and flipped their own label; nothing read
    // them back, so the screen never changed and the toggle was a decoration.
    window.localStorage.setItem(
      "videobox.settings",
      JSON.stringify({ compact: true, reducedMotion: true }),
    );

    const { container } = shell();

    const root = container.querySelector(".vb-product-shell");
    expect(root).toHaveAttribute("data-compact", "true");
    expect(root).toHaveAttribute("data-reduced-motion", "true");
  });

  it("leaves the shell alone when they are off", () => {
    window.localStorage.setItem(
      "videobox.settings",
      JSON.stringify({ compact: false, reducedMotion: false }),
    );

    const { container } = shell();

    const root = container.querySelector(".vb-product-shell");
    expect(root).toHaveAttribute("data-compact", "false");
    expect(root).toHaveAttribute("data-reduced-motion", "false");
  });
});

describe("output format setting", () => {
  it("states the format instead of offering a choice that does not exist", () => {
    // The renderer always writes output.mp4 (h264) and the output request
    // carries no format field, so picking MOV changed nothing at all.
    render(<SettingsPage section="output" onNavigate={vi.fn()} projectId="project-a" />);

    expect(screen.getByText("완성본은 MP4(H.264)로 만듭니다.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "MOV" })).toBeNull();
  });
});

describe("settings that cannot do what they offered", () => {
  it("states the local-only fact instead of a switch that cannot be turned off", () => {
    // VideoBox processes everything on this machine regardless, so the toggle
    // could never be false. A fact is useful; a dead switch is not.
    render(<SettingsPage section="ai-privacy" onNavigate={vi.fn()} projectId="project-a" />);

    expect(screen.getByText("모든 처리는 이 기기 안에서만 이뤄집니다.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /이 기기에서만 처리/ })).toBeNull();
  });

  it("drops the storage alert entirely, since nothing ever alerts", () => {
    render(<SettingsPage section="general" onNavigate={vi.fn()} projectId="project-a" />);

    expect(screen.queryByRole("button", { name: "저장공간" })).toBeNull();
    expect(screen.queryByRole("button", { name: /저장 공간 알림/ })).toBeNull();
  });
});

describe("사이드바 손잡이", () => {
  it("가져온 부품의 영어 문구 대신 우리 문구를 쓴다", () => {
    // shadcn 원본은 "Toggle Sidebar"를 넣는다. 원본 파일은 출처 핀이 걸려
    // 있어 고칠 수 없으므로, 호출부에서 덮어쓴 것이 유지되는지 잠근다.
    render(
      <ProductShell
        projectId="project-a"
        projects={[{ project_id: "project-a", name: "프로젝트", status: "draft" } as never]}
        section="home"
        onNavigate={vi.fn()}
        onOpenSettings={vi.fn()}
      >
        <p>본문</p>
      </ProductShell>,
    );

    expect(screen.getByRole("button", { name: "작업실 접기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Toggle Sidebar/i })).toBeNull();
  });
});
