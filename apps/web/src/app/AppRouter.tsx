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

import { api, type Project } from "../api";
import { ProjectOnboarding } from "../ProjectOnboarding";
import { LegacyWorkspacePage } from "./LegacyWorkspacePage";
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
    const saved = resolveLastValidProjectId(window.localStorage.getItem(lastProjectKey), projects);
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

const routeTree = rootRoute.addChildren([indexRoute, projectsRoute, workspaceRoute]);

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
  if (!isWorkspaceSection(section) || !projects.some((project) => project.project_id === projectId)) {
    return <RecoveryPage />;
  }
  window.localStorage.setItem(lastProjectKey, projectId);
  return (
    <ProjectWorkspaceProvider value={{ projectId, section, projects }}>
      <LegacyWorkspacePage
        projectId={projectId}
        section={section}
        catalogProjects={projects}
        onNavigate={(nextProjectId, nextSection) => {
          void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) });
        }}
        onProjectCreated={async (project) => {
          await router.options.context.catalog.refresh();
          await router.invalidate();
          await navigate({ to: resolveWorkspaceLocation(project.project_id, "create") });
        }}
      />
    </ProjectWorkspaceProvider>
  );
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
