import {
  Outlet,
  RouterProvider,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
  useNavigate,
  useRouter,
} from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { api, type Project } from "../api";
import { ProjectOnboarding } from "../ProjectOnboarding";
import { CreationInterview } from "../features/creation/CreationInterview";
import { DraftGapMedia } from "../features/media/DraftGapMedia";
import { LegacyWorkspacePage } from "./LegacyWorkspacePage";
import { EditorWorkbenchRoute } from "../features/editor/workbench/EditorWorkbenchRoute";
import { HomePage, opensLastProjectOnStart, ProductEmptyPage, ProductShell, SettingsPage } from "./ProductShell";
import { ProjectWorkspaceProvider, resolveLastValidProjectId } from "./ProjectWorkspaceProvider";
import { isWorkspaceSection, resolveWorkspaceLocation, type WorkspaceSection } from "./routeManifest";

const lastProjectKey = "videobox.last-valid-project";

export class ProjectCatalog {
  private cached: Project[] | null = null;
  private inFlight: { generation: number; promise: Promise<Project[]> } | null = null;
  private generation = 0;

  load() {
    if (this.cached) return Promise.resolve(this.cached);
    if (!this.inFlight || this.inFlight.generation !== this.generation) {
      const generation = this.generation;
      const promise = api.listProjects().then((projects) => {
        if (generation === this.generation) this.cached = projects;
        return projects;
      }).finally(() => {
        if (this.inFlight?.generation === generation) this.inFlight = null;
      });
      this.inFlight = { generation, promise };
    }
    return this.inFlight.promise;
  }

  async refresh() {
    this.generation += 1;
    this.cached = null;
    return this.load();
  }
}

export type RouterContext = { catalog: ProjectCatalog };

const rootRoute = createRootRouteWithContext<RouterContext>()({
  loader: ({ context }) => context.catalog.load(),
  component: Outlet,
  notFoundComponent: RecoveryPage,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: async ({ context }) => {
    const projects = await context.catalog.load();
    const saved = opensLastProjectOnStart() ? resolveLastValidProjectId(window.localStorage.getItem(lastProjectKey), projects) : null;
    throw redirect({ to: saved ? resolveWorkspaceLocation(saved, "home") : "/projects" });
  },
});

const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/",
  component: ProjectsPage,
});

const workspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/$projectId/$section",
  component: WorkspacePage,
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/$section",
  component: SettingsRoutePage,
});

const routeTree = rootRoute.addChildren([indexRoute, projectsRoute, workspaceRoute, settingsRoute]);

export function createAppRouter(
  catalog = new ProjectCatalog(),
  history?: Parameters<typeof createRouter>[0]["history"],
) {
  return createRouter({ routeTree, context: { catalog }, history });
}

export function AppRouter({ router = createAppRouter() }: { router?: ReturnType<typeof createAppRouter> }) {
  return <RouterProvider router={router} />;
}

function ProjectsPage() {
  const projects = rootRoute.useLoaderData() as Project[];
  const navigate = useNavigate();
  const router = useRouter();
  if (projects.length === 0) {
    return <ProjectOnboarding onProjectCreated={async (project) => {
      await router.options.context.catalog.refresh();
      await router.invalidate();
      await navigate({ to: resolveWorkspaceLocation(project.project_id, "create") });
    }} />;
  }
  return (
    <main data-testid="projects-catalog">
      <h1>프로젝트</h1>
      {projects.map((project) => (
        <button key={project.project_id} type="button" onClick={() => void navigate({ to: resolveWorkspaceLocation(project.project_id, "home") })}>
          {project.name}
        </button>
      ))}
    </main>
  );
}

function WorkspacePage() {
  const { projectId, section } = workspaceRoute.useParams();
  const projects = rootRoute.useLoaderData() as Project[];
  const navigate = useNavigate();
  const router = useRouter();
  const requestedEditingSessionId = typeof router.state.location.search.session_id === "string"
    ? router.state.location.search.session_id
    : null;
  const normalizedSection = section === "editor" ? "editing" : section;
  if (!isWorkspaceSection(normalizedSection) || !projects.some((project) => project.project_id === projectId)) {
    return <RecoveryPage />;
  }
  window.localStorage.setItem(lastProjectKey, projectId);
  const navigateTo = (nextProjectId: string, nextSection: WorkspaceSection) => {
    void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) });
  };
  if (normalizedSection === "home") {
    return <ProductShell projectId={projectId} projects={projects} section="home" onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })}>
      <HomePage projectId={projectId} onNavigate={navigateTo} />
    </ProductShell>;
  }
  if (normalizedSection === "create") {
    return <ProductShell projectId={projectId} projects={projects} section="create" onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })}>
      <CreationInterview projectId={projectId} />
    </ProductShell>;
  }
  if (normalizedSection === "media" || normalizedSection === "outputs") {
    const isMedia = normalizedSection === "media";
    const requestedReturn = isMedia ? new URLSearchParams(window.location.search).get("return_to") : null;
    const safeReturn = requestedReturn && requestedReturn.startsWith(`/projects/${projectId}/create`) ? requestedReturn : null;
    if (isMedia && safeReturn) return <ProductShell projectId={projectId} projects={projects} section={section} onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })}><DraftGapMedia projectId={projectId} returnTo={safeReturn} /></ProductShell>;
    return <ProductShell projectId={projectId} projects={projects} section={normalizedSection} onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })}>
      <ProductEmptyPage title={isMedia ? "자산을 준비해 주세요" : "아직 완성본이 없어요"} description={isMedia ? "영상에 넣을 사진, 영상, 소리를 추가하면 여기에서 고를 수 있어요." : "편집을 마치면 이곳에서 완성본을 확인할 수 있어요."} action={safeReturn ? "기획으로 돌아가기" : isMedia ? "새 영상 만들기" : "편집 열기"} onClick={() => safeReturn ? window.location.assign(safeReturn) : navigateTo(projectId, isMedia ? "create" : "editing")} />
    </ProductShell>;
  }
  if (section === "editor" && !requestedEditingSessionId) {
    return <CanonicalEditorEntry projectId={projectId} />;
  }
  if (section === "editor") {
    return <ProductShell projectId={projectId} projects={projects} section="editing" onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })} forceCollapsed>
      <EditorWorkbenchRoute projectId={projectId} sessionId={requestedEditingSessionId} />
    </ProductShell>;
  }
  return (
    <ProjectWorkspaceProvider value={{ projectId, section, projects }}>
      <LegacyWorkspacePage
        projectId={projectId}
        section={normalizedSection}
        editingSessionId={normalizedSection === "editing" ? requestedEditingSessionId : null}
        catalogProjects={projects}
        onNavigate={navigateTo}
        onProjectCreated={async (project) => {
          await router.options.context.catalog.refresh();
          await router.invalidate();
          await navigate({ to: resolveWorkspaceLocation(project.project_id, "create") });
        }}
      />
    </ProjectWorkspaceProvider>
  );
}

function CanonicalEditorEntry({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [message, setMessage] = useState("편집할 초안을 불러오는 중이에요.");
  useEffect(() => {
    let cancelled = false;
    void api.getLatestEditingSession(projectId).then((session) => {
      if (cancelled) return;
      if (!session) {
        setMessage("먼저 영상 초안을 만들어 주세요.");
        return;
      }
      void navigate({
        to: "/projects/$projectId/$section",
        params: { projectId, section: "editor" },
        search: { session_id: session.session_id },
        replace: true,
      });
    }).catch(() => {
      if (!cancelled) setMessage("초안을 불러오지 못했어요. 다시 시도해 주세요.");
    });
    return () => { cancelled = true; };
  }, [navigate, projectId]);
  return <main aria-live="polite"><p>{message}</p></main>;
}

function SettingsRoutePage() {
  const { section } = settingsRoute.useParams();
  const projects = rootRoute.useLoaderData() as Project[];
  const navigate = useNavigate();
  const validSections = ["general", "appearance", "ai-privacy", "storage", "output"] as const;
  if (!validSections.includes(section as typeof validSections[number])) return <RecoveryPage />;
  const projectId = resolveLastValidProjectId(window.localStorage.getItem(lastProjectKey), projects) ?? projects[0]?.project_id;
  if (!projectId) return <ProjectsPage />;
  return <ProductShell projectId={projectId} projects={projects} section="settings" onNavigate={(nextProjectId, nextSection) => void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) })} onOpenSettings={() => void navigate({ to: "/settings/general" })}>
    <SettingsPage section={section as typeof validSections[number]} onNavigate={(nextSection) => void navigate({ to: `/settings/${nextSection}` })} />
  </ProductShell>;
}

function RecoveryPage() {
  const navigate = useNavigate();
  const projects = rootRoute.useLoaderData() as Project[];
  return (
    <main data-testid="project-recovery">
      <h1>프로젝트를 찾을 수 없어요</h1>
      {projects.length > 0 ? projects.map((project) => (
        <button key={project.project_id} type="button" onClick={() => void navigate({ to: resolveWorkspaceLocation(project.project_id, "home") })}>
          {project.name}
        </button>
      )) : <button type="button" onClick={() => void navigate({ to: "/projects" })}>프로젝트 목록으로</button>}
    </main>
  );
}
