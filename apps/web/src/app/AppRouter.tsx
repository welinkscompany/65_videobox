import {
  Outlet,
  RouterProvider,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
  useNavigate,
  useRouter,
  useRouterState,
} from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { api, type Project } from "../api";
import { Button } from "../components/ui/button";
import { ProjectOnboarding } from "../ProjectOnboarding";
import { CreationInterview } from "../features/creation/CreationInterview";
import { DraftGapMedia } from "../features/media/DraftGapMedia";
import { MediaWorkspacePage } from "../features/media/MediaWorkspacePage";
import { TimelineReviewPage } from "../features/review/TimelineReviewPage";
import { EditorWorkbenchRoute } from "../features/editor/workbench/EditorWorkbenchRoute";
import { HomePage, opensLastProjectOnStart, ProductShell, SettingsPage } from "./ProductShell";
import { OutputsPage } from "./OutputsPage";
import { resolveLastValidProjectId } from "./projectSelection";
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
  beforeLoad: async ({ context, params, search }) => {
    if (params.section === "settings") {
      const projects = await context.catalog.load();
      if (!projects.some((project) => project.project_id === params.projectId)) {
        throw redirect({ href: `/projects/${encodeURIComponent(params.projectId)}/home`, replace: true });
      }
      throw redirect({ href: `/settings/general?project_id=${encodeURIComponent(params.projectId)}`, replace: true });
    }
    if (params.section !== "editing") return;
    const routeSearch = search as { session_id?: unknown; segment_id?: unknown };
    const sessionId = typeof routeSearch.session_id === "string"
      ? routeSearch.session_id
      : null;
    const segmentId = typeof routeSearch.segment_id === "string" ? routeSearch.segment_id : null;
    const nextSearch = new URLSearchParams();
    if (sessionId !== null) nextSearch.set("session_id", sessionId);
    if (segmentId !== null) nextSearch.set("segment_id", segmentId);
    throw redirect({
      href: `/projects/${encodeURIComponent(params.projectId)}/editor${nextSearch.size === 0 ? "" : `?${nextSearch.toString()}`}`,
      replace: true,
    });
  },
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
        <Button key={project.project_id} type="button" onClick={() => void navigate({ to: resolveWorkspaceLocation(project.project_id, "home") })}>
          {project.name}
        </Button>
      ))}
    </main>
  );
}

function WorkspacePage() {
  const { projectId, section } = workspaceRoute.useParams();
  const projects = rootRoute.useLoaderData() as Project[];
  const navigate = useNavigate();
  const routeSearch = useRouterState({ select: (routerState) => routerState.location.search }) as {
    session_id?: unknown;
    segment_id?: unknown;
  };
  const rawEditingSessionId = typeof routeSearch.session_id === "string"
    ? routeSearch.session_id
    : null;
  const requestedEditingSessionId = rawEditingSessionId?.trim() || null;
  const rawRequestedSegmentId = typeof routeSearch.segment_id === "string"
    ? routeSearch.segment_id
    : null;
  const requestedSegmentId = rawRequestedSegmentId?.trim() || null;
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
  if (normalizedSection === "media") {
    const requestedReturn = typeof (routeSearch as { return_to?: unknown }).return_to === "string"
      ? (routeSearch as { return_to: string }).return_to
      : null;
    const safeReturn = resolveSafeCreationReturn(projectId, requestedReturn);
    if (safeReturn) return <ProductShell projectId={projectId} projects={projects} section={section} onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })}><DraftGapMedia projectId={projectId} returnTo={safeReturn} /></ProductShell>;
    return <ProductShell projectId={projectId} projects={projects} section={normalizedSection} onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })}>
      <MediaWorkspacePage projectId={projectId} />
    </ProductShell>;
  }
  if (normalizedSection === "outputs") {
    return <ProductShell projectId={projectId} projects={projects} section="outputs" onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })}>
      <OutputsPage projectId={projectId} onOpenEditor={() => navigateTo(projectId, "editing")} />
    </ProductShell>;
  }
  if (normalizedSection === "timeline" || normalizedSection === "review") {
    return <ProductShell projectId={projectId} projects={projects} section={normalizedSection} onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })}>
      <TimelineReviewPage
        projectId={projectId}
        onOpenSegment={({ projectId: targetProjectId, sessionId, segmentId }) => void navigate({
          to: "/projects/$projectId/$section",
          params: { projectId: targetProjectId, section: "editor" },
          search: { session_id: sessionId, segment_id: segmentId } as never,
        })}
      />
    </ProductShell>;
  }
  if (section === "editor" && rawEditingSessionId !== null && !requestedEditingSessionId) {
    return <ProductShell projectId={projectId} projects={projects} section="editing" onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })} forceCollapsed>
      <EditorWorkbenchRoute projectId={projectId} sessionId={null} requestedSegmentId={requestedSegmentId} />
    </ProductShell>;
  }
  if (section === "editor" && !requestedEditingSessionId) {
    return <CanonicalEditorEntry projectId={projectId} />;
  }
  if (section === "editor") {
    return <ProductShell projectId={projectId} projects={projects} section="editing" onNavigate={navigateTo} onOpenSettings={() => void navigate({ to: "/settings/general" })} forceCollapsed>
      <EditorWorkbenchRoute projectId={projectId} sessionId={requestedEditingSessionId} requestedSegmentId={requestedSegmentId} />
    </ProductShell>;
  }
  return <RecoveryPage />;
}

function resolveSafeCreationReturn(projectId: string, requestedReturn: string | null) {
  if (!requestedReturn) return null;
  try {
    const parsed = new URL(requestedReturn, window.location.origin);
    const expectedPath = `/projects/${encodeURIComponent(projectId)}/create`;
    if (parsed.origin !== window.location.origin || parsed.pathname !== expectedPath || parsed.hash) return null;
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return null;
  }
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
  const routeSearch = useRouterState({ select: (routerState) => routerState.location.search }) as {
    project_id?: unknown;
  };
  const validSections = ["general", "appearance", "ai-privacy", "voice", "storage", "output"] as const;
  if (!validSections.includes(section as typeof validSections[number])) return <RecoveryPage />;
  const requestedProjectId = typeof routeSearch.project_id === "string" ? routeSearch.project_id.trim() : "";
  if (requestedProjectId && !projects.some((project) => project.project_id === requestedProjectId)) return <RecoveryPage />;
  const projectId = requestedProjectId || resolveLastValidProjectId(window.localStorage.getItem(lastProjectKey), projects) || projects[0]?.project_id;
  if (!projectId) return <ProjectsPage />;
  const settingsLocation = (nextSection: typeof validSections[number]) => `/settings/${nextSection}?project_id=${encodeURIComponent(projectId)}`;
  return <ProductShell projectId={projectId} projects={projects} section="settings" onNavigate={(nextProjectId, nextSection) => void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) })} onOpenSettings={() => void navigate({ to: settingsLocation("general") })}>
    <SettingsPage projectId={projectId} section={section as typeof validSections[number]} onNavigate={(nextSection) => void navigate({ to: settingsLocation(nextSection) })} />
  </ProductShell>;
}

function RecoveryPage() {
  const navigate = useNavigate();
  const projects = rootRoute.useLoaderData() as Project[];
  return (
    <main data-testid="project-recovery">
      <h1>프로젝트를 찾을 수 없어요</h1>
      {projects.length > 0 ? projects.map((project) => (
        <Button key={project.project_id} type="button" onClick={() => void navigate({ to: resolveWorkspaceLocation(project.project_id, "home") })}>
          {project.name}
        </Button>
      )) : <Button type="button" onClick={() => void navigate({ to: "/projects" })}>프로젝트 목록으로</Button>}
    </main>
  );
}
