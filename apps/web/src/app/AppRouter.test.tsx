import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryHistory } from "@tanstack/react-router";

import { api } from "../api";
import { AppRouter, createAppRouter, ProjectCatalog } from "./AppRouter";

beforeEach(() => vi.stubGlobal("scrollTo", vi.fn()));
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
