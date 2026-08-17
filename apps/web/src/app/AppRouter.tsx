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

import { api, type Project, type ProjectWorkspaceSummary } from "../api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { ProjectOnboarding } from "../ProjectOnboarding";
import { CreationInterview } from "../features/creation/CreationInterview";
import { DraftGapMedia } from "../features/media/DraftGapMedia";
import { MediaWorkspacePage } from "../features/media/MediaWorkspacePage";
import { LibraryPage as PersonalLibraryPage } from "../features/library/LibraryPage";
import { FootageOrganizerPage } from "../features/footage/FootageOrganizerPage";
import { ReviewAndOutputPage } from "../features/review/ReviewAndOutputPage";
import { EditorWorkbenchRoute } from "../features/editor/workbench/EditorWorkbenchRoute";
import { HomePage, opensLastProjectOnStart, ProductShell, SettingsPage } from "./ProductShell";
import { resolveLastValidProjectId } from "./projectSelection";
import { readableMoment } from "./readableMoment";
import {
  parseWorkspaceLocation,
  resolveGlobalLocation,
  resolveWorkspaceLocation,
  type WorkspaceSection,
} from "./routeManifest";

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
    // 프로젝트를 열면 **편집 화면이 먼저**다. 캡컷은 열면 바로 편집판이다.
    throw redirect({ to: saved ? resolveWorkspaceLocation(saved, "editing") : "/projects" });
  },
});

const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/",
  component: ProjectsPage,
});

const libraryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/library",
  component: LibraryPage,
});

const footageRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/footage",
  component: FootagePage,
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

const routeTree = rootRoute.addChildren([indexRoute, projectsRoute, libraryRoute, footageRoute, workspaceRoute, settingsRoute]);

export function createAppRouter(
  catalog = new ProjectCatalog(),
  history?: Parameters<typeof createRouter>[0]["history"],
) {
  return createRouter({ routeTree, context: { catalog }, history });
}

export function AppRouter({ router = createAppRouter() }: { router?: ReturnType<typeof createAppRouter> }) {
  return <RouterProvider router={router} />;
}

/** 첫 화면도 **앱 껍데기 안**이다.
 *
 * 예전에는 `/projects`가 껍데기 밖의 맨 `<main>`이라 사이드바가 없었고, 프로젝트를
 * 하나 만들고 나서야 나타났다. 그래서 처음 여는 사람에게는 프로그램이 아니라
 * 웹페이지 한 장으로 보였다(2026-08-17 owner 지적).
 *
 * `ProductShell`은 이미 `hasProject`로 프로젝트 없는 상태를 다룬다 -- 전환 목록과
 * 단계 메뉴만 숨기고 나머지는 그대로 그린다. 새로 만들지 않고 그것을 쓴다.
 */
function ProjectsPage() {
  const projects = rootRoute.useLoaderData() as Project[];
  const navigate = useNavigate();
  const router = useRouter();
  const archive = useArchivedProjects(router);
  const [isCreating, setIsCreating] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function goToNewProject(project: Project) {
    await router.options.context.catalog.refresh();
    await router.invalidate();
    await navigate({ to: resolveWorkspaceLocation(project.project_id, "create") });
  }

  if (projects.length === 0) {
    return <ProjectOnboarding onProjectCreated={goToNewProject} />;
  }

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newProjectName.trim()) {
      setCreateError("프로젝트 이름을 입력하세요.");
      return;
    }
    setIsSubmitting(true);
    setCreateError(null);
    try {
      const created = await api.createProject({ name: newProjectName.trim() });
      await goToNewProject(created);
    } catch {
      setCreateError("프로젝트를 만들지 못했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <ProductShell
      projectId=""
      projects={projects}
      section="home"
      archive={archive}
      onNavigate={(nextProjectId, nextSection) => void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) })}
      onOpenSettings={() => void navigate({ to: "/settings/general" })}
      onArchiveProject={(id) => archiveProjectAndRefresh(router, id)}
      onDeleteProjectPermanently={(id) => deleteProjectPermanentlyAndRefresh(router, id)}
    >
    <main data-testid="projects-catalog" className="vb-catalog">
      <p className="vb-eyebrow">VideoBox</p>
      <h1>프로젝트</h1>
      <p>영상을 만들 프로젝트를 선택하거나, 새 프로젝트를 시작하세요.</p>
      {/* 새 프로젝트 입력은 **목록 위**에 둔다. 예전에는 카드 6개를 지나 맨 아래로
          스크롤해야 나왔다. */}
      {isCreating ? (
        <form className="vb-catalog-form" onSubmit={(event) => void handleCreate(event)}>
          <label className="grid gap-2 text-sm">
            새 프로젝트 이름
            <Input value={newProjectName} onChange={(event) => setNewProjectName(event.target.value)} autoFocus />
          </label>
          <div className="flex gap-2">
            <Button disabled={isSubmitting} type="submit">{isSubmitting ? "만드는 중" : "만들기"}</Button>
            <Button variant="outline" type="button" onClick={() => { setIsCreating(false); setNewProjectName(""); setCreateError(null); }}>취소</Button>
          </div>
          {createError ? <p className="text-sm text-destructive" role="alert">{createError}</p> : null}
        </form>
      ) : (
        <Button type="button" className="vb-catalog-create" onClick={() => setIsCreating(true)}>새 프로젝트 만들기</Button>
      )}
      <div className="vb-catalog-grid">
        {projects.map((project) => <ProjectCatalogCard key={project.project_id} project={project} onNavigateHref={(href) => void navigate({ href })} />)}
      </div>
    </main>
    </ProductShell>
  );
}

function LibraryPage() {
  return <PersonalLibraryPage />;
}

function FootagePage() {
  return <FootageOrganizerPage />;
}

function GlobalDestinationPage({ testId, title, description, readiness }: { testId: string; title: string; description: string; readiness: string }) {
  return <main data-testid={testId}>
    <h1>{title}</h1>
    <p>{description}</p>
    <p>{readiness}</p>
    <a href={resolveGlobalLocation("projects")}>프로젝트로 돌아가기</a>
  </main>;
}

/** 카드에 적히던 `기획 · 준비됨`은 **우리 내부 단계 이름**이었다. 무엇을 하면
 * 되는지가 아니라 시스템이 그 프로젝트를 어느 칸에 넣어 뒀는지를 말한다.
 * 사람이 읽고 바로 아는 한 문장으로 바꾼다(§10.13). */
const projectStateSentence: Record<ProjectWorkspaceSummary["current_stage"], Record<"blocked" | "attention" | "ready", string>> = {
  plan: { blocked: "이야기를 정하다 막혔어요", attention: "이야기를 확인해 주세요", ready: "이야기를 정하는 중" },
  assets: { blocked: "재료를 넣다 막혔어요", attention: "빠진 재료가 있어요", ready: "재료를 모으는 중" },
  edit: { blocked: "편집하다 막혔어요", attention: "편집을 확인해 주세요", ready: "편집하는 중" },
  review: { blocked: "확인하다 막혔어요", attention: "확인이 필요해요", ready: "마지막 확인 중" },
  output: { blocked: "영상을 만들다 막혔어요", attention: "완성본을 확인해 주세요", ready: "영상으로 뽑는 중" },
};

function projectStateLabel(summary: ProjectWorkspaceSummary): string {
  const byState = projectStateSentence[summary.current_stage];
  if (!byState) return "상태 확인 중";
  return summary.state === "blocked" ? byState.blocked : summary.state === "attention" ? byState.attention : byState.ready;
}

function ProjectCatalogCard({ project, onNavigateHref }: { project: Project; onNavigateHref?: (href: string) => void }) {
  const [summary, setSummary] = useState<ProjectWorkspaceSummary | null>(null);
  const [summaryError, setSummaryError] = useState(false);
  const [requestNumber, setRequestNumber] = useState(0);
  useEffect(() => {
    let active = true;
    setSummary(null);
    setSummaryError(false);
    void api.getProjectWorkspaceSummary(project.project_id).then((next) => {
      if (active) setSummary(next);
    }).catch(() => {
      if (active) setSummaryError(true);
    });
    return () => { active = false; };
  }, [project.project_id, requestNumber]);
  if (summaryError) {
    return <article className="vb-catalog-card" aria-label={`${project.name} 프로젝트`}>
      <h2>{project.name}</h2>
      <p>상태 확인 필요</p>
      <Button type="button" variant="outline" onClick={() => setRequestNumber((value) => value + 1)}>다시 확인</Button>
    </article>;
  }
  if (!summary) {
    return <article className="vb-catalog-card" aria-label={`${project.name} 프로젝트`}>
      <h2>{project.name}</h2>
      <p>상태 확인 중</p>
    </article>;
  }
  return <article className="vb-catalog-card" aria-label={`${project.name} 프로젝트`}>
    {summary.thumbnail_url ? <img src={summary.thumbnail_url} alt={`${summary.display_name} 대표 이미지`} loading="lazy" /> : null}
    <h2>{summary.display_name}</h2>
    <p>{projectStateLabel(summary)}</p>
    {readableMoment(summary.updated_at) ? <time dateTime={summary.updated_at}>최근 편집 {readableMoment(summary.updated_at)}</time> : null}
    <p className="vb-catalog-card__finished">완성본 {summary.finished_video_count}개</p>
    <Button asChild type="button" variant="outline" aria-label={summary.next_action.label}><a href={summary.next_action.href} onClick={(event) => {
      if (!onNavigateHref) return;
      event.preventDefault();
      onNavigateHref(summary.next_action.href);
    }}>{summary.next_action.label}</a></Button>
  </article>;
}

async function archiveProjectAndRefresh(router: ReturnType<typeof createAppRouter>, projectId: string) {
  await api.archiveProject(projectId);
  await router.options.context.catalog.refresh();
  await router.invalidate();
}

async function deleteProjectPermanentlyAndRefresh(router: ReturnType<typeof createAppRouter>, projectId: string) {
  await api.deleteProjectPermanently(projectId);
  await router.options.context.catalog.refresh();
  await router.invalidate();
}

async function restoreProjectAndRefresh(router: ReturnType<typeof createAppRouter>, projectId: string) {
  await api.restoreProject(projectId);
  await router.options.context.catalog.refresh();
  await router.invalidate();
}

/** Task 32: the archive is loaded only when opened, so the ordinary path keeps
 * its single project request. Shared by both places that render the sidebar. */
function useArchivedProjects(router: ReturnType<typeof useRouter>) {
  const [archivedProjects, setArchivedProjects] = useState<Project[]>([]);
  const load = async () => {
    try {
      const all = await api.listProjects(true);
      setArchivedProjects(all.filter((project) => project.status === "archived"));
    } catch {
      setArchivedProjects([]);
    }
  };
  const restore = async (projectId: string) => {
    await restoreProjectAndRefresh(router as ReturnType<typeof createAppRouter>, projectId);
    await load();
  };
  return { archivedProjects, load, restore };
}

function WorkspacePage() {
  const { projectId, section } = workspaceRoute.useParams();
  const projects = rootRoute.useLoaderData() as Project[];
  const navigate = useNavigate();
  const router = useRouter();
  const handleArchiveProject = (id: string) => archiveProjectAndRefresh(router, id);
  const handleDeleteProjectPermanently = (id: string) => deleteProjectPermanentlyAndRefresh(router, id);
  const archive = useArchivedProjects(router);
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
  const parsedLocation = parseWorkspaceLocation(`/projects/${encodeURIComponent(projectId)}/${section}`);
  if (!parsedLocation || !projects.some((project) => project.project_id === projectId)) {
    return <RecoveryPage />;
  }
  const normalizedSection: WorkspaceSection = section === "editor" || parsedLocation.stage === "edit"
    ? "editing"
    : section === "media" || parsedLocation.stage === "assets"
      ? "media"
      : section === "outputs" || parsedLocation.stage === "output"
        ? "outputs"
        : section === "timeline" || parsedLocation.stage === "review"
          ? "review"
          : section === "create" || parsedLocation.stage === "plan"
            ? "create"
            : "home";
  window.localStorage.setItem(lastProjectKey, projectId);
  const navigateTo = (nextProjectId: string, nextSection: WorkspaceSection) => {
    void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) });
  };
  const openSettings = () => void navigate({
    to: "/settings/general",
    search: { project_id: projectId } as never,
  });
  if (section === "home") {
    return <ProductShell projectId={projectId} projects={projects} section="home" onNavigate={navigateTo} onOpenSettings={openSettings} onArchiveProject={handleArchiveProject} onDeleteProjectPermanently={handleDeleteProjectPermanently} archive={archive}>
      <HomePage projectId={projectId} onNavigate={navigateTo} />
    </ProductShell>;
  }
  if (section === "create" || section === "plan") {
    return <ProductShell projectId={projectId} projects={projects} section="create" onNavigate={navigateTo} onOpenSettings={openSettings} onArchiveProject={handleArchiveProject} onDeleteProjectPermanently={handleDeleteProjectPermanently} archive={archive}>
      <CreationInterview projectId={projectId} />
    </ProductShell>;
  }
  if (section === "media" || section === "assets") {
    const requestedReturn = typeof (routeSearch as { return_to?: unknown }).return_to === "string"
      ? (routeSearch as { return_to: string }).return_to
      : null;
    const safeReturn = resolveSafeCreationReturn(projectId, requestedReturn);
    if (safeReturn) return <ProductShell projectId={projectId} projects={projects} section={section} onNavigate={navigateTo} onOpenSettings={openSettings} onArchiveProject={handleArchiveProject} onDeleteProjectPermanently={handleDeleteProjectPermanently} archive={archive}><DraftGapMedia projectId={projectId} returnTo={safeReturn} /></ProductShell>;
    return <ProductShell projectId={projectId} projects={projects} section={normalizedSection} onNavigate={navigateTo} onOpenSettings={openSettings} onArchiveProject={handleArchiveProject} onDeleteProjectPermanently={handleDeleteProjectPermanently} archive={archive}>
      <MediaWorkspacePage projectId={projectId} />
    </ProductShell>;
  }
  // 검토와 출력은 한 단계다. 두 주소를 모두 살려 둔 채 같은 화면을 그린다 --
  // 한쪽을 리다이렉트로 접으면 그 주소로 바로 들어오던 경로가 끊긴다.
  if (section === "outputs" || section === "output" || section === "timeline" || section === "review") {
    return <ProductShell projectId={projectId} projects={projects} section={section === "outputs" || section === "output" ? "outputs" : normalizedSection} onNavigate={navigateTo} onOpenSettings={openSettings} onArchiveProject={handleArchiveProject} onDeleteProjectPermanently={handleDeleteProjectPermanently} archive={archive}>
      <ReviewAndOutputPage
        projectId={projectId}
        onOpenEditor={() => navigateTo(projectId, "editing")}
        onOpenSegment={({ projectId: targetProjectId, sessionId, segmentId }) => void navigate({
          to: "/projects/$projectId/$section",
          params: { projectId: targetProjectId, section: "editor" },
          search: { session_id: sessionId, segment_id: segmentId } as never,
        })}
      />
    </ProductShell>;
  }
  if ((section === "editor" || section === "edit") && rawEditingSessionId !== null && !requestedEditingSessionId) {
    return <ProductShell projectId={projectId} projects={projects} section="editing" onNavigate={navigateTo} onOpenSettings={openSettings} onArchiveProject={handleArchiveProject} onDeleteProjectPermanently={handleDeleteProjectPermanently} archive={archive} forceCollapsed>
      <EditorWorkbenchRoute projectId={projectId} sessionId={null} requestedSegmentId={requestedSegmentId} />
    </ProductShell>;
  }
  if ((section === "editor" || section === "edit") && !requestedEditingSessionId) {
    return <ProductShell projectId={projectId} projects={projects} section="editing" onNavigate={navigateTo} onOpenSettings={openSettings} onArchiveProject={handleArchiveProject} onDeleteProjectPermanently={handleDeleteProjectPermanently} archive={archive} forceCollapsed>
      <CanonicalEditorEntry projectId={projectId} onNavigate={navigateTo} />
    </ProductShell>;
  }
  if (section === "editor" || section === "edit") {
    return <ProductShell projectId={projectId} projects={projects} section="editing" onNavigate={navigateTo} onOpenSettings={openSettings} onArchiveProject={handleArchiveProject} onDeleteProjectPermanently={handleDeleteProjectPermanently} archive={archive} forceCollapsed>
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

function CanonicalEditorEntry({ projectId, onNavigate }: { projectId: string; onNavigate: (projectId: string, section: WorkspaceSection) => void }) {
  const navigate = useNavigate();
  const [message, setMessage] = useState("편집할 초안을 불러오는 중이에요.");
  const [hasNoDraft, setHasNoDraft] = useState(false);
  const [isOpeningBlank, setIsOpeningBlank] = useState(false);
  const [blankError, setBlankError] = useState<string | null>(null);
  const openBlankBoard = async () => {
    setIsOpeningBlank(true);
    setBlankError(null);
    try {
      const session = await api.createBlankEditingSession(projectId);
      await navigate({
        to: "/projects/$projectId/$section",
        params: { projectId, section: "editor" },
        search: { session_id: session.session_id },
        replace: true,
      });
    } catch {
      setBlankError("편집판을 열지 못했어요. 다시 시도해 주세요.");
      setIsOpeningBlank(false);
    }
  };
  useEffect(() => {
    let cancelled = false;
    void api.getLatestEditingSession(projectId).then((session) => {
      if (cancelled) return;
      if (!session) {
        // 예전 문구는 `먼저 영상 초안을 만들어 주세요.`였다. 편집기를 열었는데
        // **잠긴 문**을 만난 것처럼 읽혔다. 지금은 여기가 시작하는 자리다.
        setMessage("아직 편집할 영상이 없어요. 어떤 영상을 만들지 정하면 여기에 펼쳐 드릴게요.");
        setHasNoDraft(true);
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
  return <div aria-live="polite">
    <p>{message}</p>
    {hasNoDraft ? <>
      <Button type="button" onClick={() => onNavigate(projectId, "create")}>영상 정하러 가기</Button>
      {/* 캡컷은 열면 바로 빈 편집판이다. 기획을 건너뛰고 여기서 시작할 수 있어야 한다. */}
      <Button type="button" variant="outline" disabled={isOpeningBlank} onClick={() => void openBlankBoard()}>
        {isOpeningBlank ? "편집판을 여는 중" : "빈 편집판으로 시작"}
      </Button>
      <Button type="button" variant="outline" onClick={() => onNavigate(projectId, "media")}>먼저 재료부터 모으기</Button>
      {blankError ? <p role="alert">{blankError}</p> : null}
    </> : null}
  </div>;
}

function SettingsRoutePage() {
  const { section } = settingsRoute.useParams();
  const projects = rootRoute.useLoaderData() as Project[];
  const navigate = useNavigate();
  const router = useRouter();
  const handleArchiveProject = (id: string) => archiveProjectAndRefresh(router, id);
  const handleDeleteProjectPermanently = (id: string) => deleteProjectPermanentlyAndRefresh(router, id);
  const archive = useArchivedProjects(router);
  const routeSearch = useRouterState({ select: (routerState) => routerState.location.search }) as {
    project_id?: unknown;
  };
  const validSections = ["general", "appearance", "ai-privacy", "voice", "output", "conversations"] as const;
  if (!validSections.includes(section as typeof validSections[number])) return <RecoveryPage />;
  const requestedProjectId = typeof routeSearch.project_id === "string" ? routeSearch.project_id.trim() : "";
  if (requestedProjectId && !projects.some((project) => project.project_id === requestedProjectId)) return <RecoveryPage />;
  const projectId = requestedProjectId || resolveLastValidProjectId(window.localStorage.getItem(lastProjectKey), projects) || projects[0]?.project_id;
  if (!projectId) return <ProjectsPage />;
  const settingsLocation = (nextSection: typeof validSections[number]) => `/settings/${nextSection}?project_id=${encodeURIComponent(projectId)}`;
  return <ProductShell projectId={projectId} projects={projects} section="settings" onNavigate={(nextProjectId, nextSection) => void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) })} onOpenSettings={() => void navigate({ to: settingsLocation("general") })} onArchiveProject={handleArchiveProject} onDeleteProjectPermanently={handleDeleteProjectPermanently} archive={archive}>
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
