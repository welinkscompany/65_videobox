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
import { useEffect, useState, type ReactNode } from "react";
import { Archive, LayoutGrid, List, Mic, Scissors } from "lucide-react";

import { api, type Project, type ProjectWorkspaceSummary } from "../api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { CreationInterview } from "../features/creation/CreationInterview";
import { DraftGapMedia } from "../features/media/DraftGapMedia";
import { MediaWorkspacePage } from "../features/media/MediaWorkspacePage";
import { LibraryPage as PersonalLibraryPage } from "../features/library/LibraryPage";
import { FootageOrganizerPage } from "../features/footage/FootageOrganizerPage";
import { ProjectTitleDialog } from "../features/projects/ProjectTitleDialog";
import { useProjectManagement } from "../features/projects/projectManagement";
import { ReviewAndOutputPage } from "../features/review/ReviewAndOutputPage";
import { EditorWorkbenchRoute } from "../features/editor/workbench/EditorWorkbenchRoute";
import { HomePage, ProductShell, SettingsPage, type ProductShellProps } from "./ProductShell";
import { resolveLastValidProjectId } from "./projectSelection";
import { readableMoment } from "./readableMoment";
import {
  parseWorkspaceLocation,
  resolveNavigationContext,
  resolveGlobalLocation,
  resolveProjectStage,
  resolveWorkspaceLocation,
  type ProjectStage,
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
  // **첫 화면이 흰 채로 비어 있었다(owner 지적 2026-08-28).** 주소창에 `/`를
  // 치면 이 로더가 프로젝트 목록을 다 받아올 때까지 아무것도 안 그렸다 --
  // 창작자에게는 프로그램이 멈춘 것으로 보였다. `index.html`의 `<div
  // id="root">`도 비어 있어 그 앞 순간(JS 로딩)도 마찬가지였다. 그건 정적
  // 셸의 몫이라 여기서는 못 고친다 -- 이건 라우터가 데이터를 받는 동안만
  // 맡는다.
  pendingComponent: () => <main className="vb-app-loading" aria-busy="true"><p role="status">VideoBox를 여는 중이에요…</p></main>,
  pendingMs: 0,
  notFoundComponent: RecoveryPage,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  // **`/`는 이제 항상 홈이다(owner 결정 2026-08-28, 2026-08-19 결정을 뒤집음).**
  // 예전엔 마지막으로 열었던 프로젝트의 편집기로 조용히 건너뛰었다 -- 캡컷을
  // 근거로 owner가 직접 정한 것이었지만, 다시 보니 "시작하는 자리"가 아예
  // 없어서 owner 스스로도 답답해했다. `/projects`가 이제 그 자리다 -- 이어할
  // 프로젝트 카드들과, 새로 시작하는 여러 갈래(이야기부터·빈 편집판으로
  // 바로·목소리부터)를 한 화면에 같이 둔다. 마지막 프로젝트로 빠르게 가는
  // 길은 없앤 게 아니라 위 띠의 `편집기로 돌아가기` 단추로 옮겨져 있다
  // (`RoutedProductShell`의 `onResumeEditor`, `/library`·`/footage`에서도 보인다).
  beforeLoad: () => { throw redirect({ to: "/projects" }); },
});

const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/",
  component: ProjectsPage,
});

// **동료가 실제로 열어 볼 자리(owner 요청 2026-08-28, 갭검증으로 발견).**
// "동료에게 이 링크를 보내 주세요"라고 화면이 말해 놓고 그 주소를 처리하는
// 라우트가 없었다 -- 눌러 보면 `RecoveryPage`("프로젝트를 찾을 수 없어요")가
// 뜬다. 받는 사람은 VideoBox를 쓰는 사람이 아니므로 껍데기(로그인·프로젝트
// 목록 전제) 없이 영상 하나만 보여준다.
const previewShareRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/preview/$token",
  component: PreviewSharePage,
});

function PreviewSharePage() {
  const { token } = previewShareRoute.useParams();
  const [failed, setFailed] = useState(false);
  return (
    <main className="vb-preview-share" aria-label="공유된 미리보기">
      {failed ? (
        <p>이 링크를 열 수 없어요. 만료되었거나 취소된 링크일 수 있어요.</p>
      ) : (
        <video
          controls
          autoPlay
          aria-label="공유된 영상"
          src={`/api/preview-shares/${encodeURIComponent(token)}/content`}
          onError={() => setFailed(true)}
        >
          이 브라우저에서는 영상을 재생할 수 없어요.
        </video>
      )}
    </main>
  );
}

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
        throw redirect({ href: resolveWorkspaceLocation(params.projectId, "home"), replace: true });
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
      href: `${resolveProjectStage(params.projectId, "edit")}${nextSearch.size === 0 ? "" : `?${nextSearch.toString()}`}`,
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

const routeTree = rootRoute.addChildren([indexRoute, projectsRoute, previewShareRoute, libraryRoute, footageRoute, workspaceRoute, settingsRoute]);

export function createAppRouter(
  catalog = new ProjectCatalog(),
  history?: Parameters<typeof createRouter>[0]["history"],
) {
  return createRouter({ routeTree, context: { catalog }, history });
}

export function AppRouter({ router = createAppRouter() }: { router?: ReturnType<typeof createAppRouter> }) {
  return <RouterProvider router={router} />;
}

/** 실제 방문 이력이 있으면 그 길을 먼저 돌아가고, 주소를 직접 열었을 때만
 * routeManifest의 안전한 상위 화면으로 간다. 화면 컴포넌트는 이 선택을 몰라도 된다. */
function RoutedProductShell(props: ProductShellProps) {
  const router = useRouter();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (routerState) => routerState.location.pathname });
  const projectName = props.projects.find((project) => project.project_id === props.projectId)?.name;
  const navigation = resolveNavigationContext({ pathname, projectName });
  const hasVisitedPage = router.history.canGoBack();
  const canGoBack = hasVisitedPage || navigation.fallbackHref !== pathname;
  const onBack = () => {
    if (hasVisitedPage) {
      router.history.back();
      return;
    }
    void navigate({ href: navigation.fallbackHref });
  };
  // 전역 메뉴는 맨 `<a href>`라 페이지를 통째로 새로 열었고, 그때 앱 이력이 날아가
  // `이전 화면` 단추가 사라졌다(owner 신고 2026-08-27, 실측 확인). 라우터로 옮긴다.
  const onNavigateGlobal = (destination: "projects" | "library" | "footage") =>
    void navigate({ href: resolveGlobalLocation(destination) });
  // 편집기로 돌아가는 길(owner 결정 2026-08-27). 마지막으로 연 프로젝트를 이미
  // 기억하고 있으므로(`lastProjectKey`) 그걸 그대로 쓴다. **모르면 주지 않는다** --
  // 없는 길을 흉내 내면 눌렀을 때 빈 화면이 뜬다.
  const resumeProjectId = props.projectId
    || resolveLastValidProjectId(window.localStorage.getItem(lastProjectKey), props.projects);
  const onResumeEditor = resumeProjectId
    ? () => void navigate({ href: resolveWorkspaceLocation(resumeProjectId, "editing") })
    : undefined;
  return <ProductShell {...props} navigation={navigation} onBack={canGoBack ? onBack : undefined} onNavigateGlobal={onNavigateGlobal} onResumeEditor={onResumeEditor} />;
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
const catalogViewModeStorageKey = "videobox.catalog.view-mode";
/** 세션마다 다시 고르게 하지 않는다. `readActiveDrawer`(편집기 도크)와 같은
 *  방어적 패턴 -- 브라우저가 저장을 막아도(사생활 모드 등) 조용히 기본값으로. */
function readCatalogViewMode(): "grid" | "list" {
  try {
    return window.localStorage.getItem(catalogViewModeStorageKey) === "list" ? "list" : "grid";
  } catch {
    return "grid";
  }
}
function writeCatalogViewMode(mode: "grid" | "list"): void {
  try {
    window.localStorage.setItem(catalogViewModeStorageKey, mode);
  } catch {
    // 보기 방식은 화면 전용이라 최선만 한다.
  }
}

function ProjectsPage() {
  const projects = rootRoute.useLoaderData() as Project[];
  const navigate = useNavigate();
  const router = useRouter();
  const archive = useArchivedProjects(router);
  // 프로젝트 관리는 왼쪽 기둥이 아니라 **여기**에 산다(owner 결정 2026-08-21).
  // 기둥은 곧 위 띠로 바뀌고, 띠는 고르는 것만 맡는다.
  const management = useProjectManagement();
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  // **캡컷 홈에도 프로젝트 목록 위에 검색이 있다**(2026-08-22, `capcut-observed`
  // 기록 §1: "프로젝트 목록은 맨 아래. 오른쪽에 검색·보기전환·휴지통·프로젝트
  // 동기화"). 프로젝트가 쌓이면(owner는 지금도 16개) 스크롤로 찾아야 했다.
  // **동기화**는 클라우드 계정을 전제해 승인 없이 만들지 않는다.
  const [projectQuery, setProjectQuery] = useState("");
  // **보기전환은 백엔드가 필요 없다** -- 처음에 그렇게 적어 뒀다가 틀렸다고
  // 알아챘다. `projects` 목록을 다른 모양으로 그리기만 하면 된다(2026-08-22).
  // 고른 방식을 기억한다 -- 매번 새로고침할 때마다 격자로 돌아가면 캡컷과 달리
  // "전환"이 아니라 "매번 다시 고르기"가 된다.
  const [viewMode, setViewMode] = useState<"grid" | "list">(readCatalogViewMode);
  const chooseViewMode = (mode: "grid" | "list") => { setViewMode(mode); writeCatalogViewMode(mode); };
  const filteredProjects = projectQuery.trim()
    ? projects.filter((project) => project.name.toLowerCase().includes(projectQuery.trim().toLowerCase()))
    : projects;
  const [newProjectName, setNewProjectName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // 보관·영구 삭제는 이제 보관함 패널 하나에서 일어난다. 활성 목록은
  // `router.invalidate()`(각 `*AndRefresh` 함수 안)가 이미 갱신하지만, 보관함
  // 목록은 스스로 다시 부르지 않는 한 그대로 옛 상태다 -- 되돌리기가 이미 하던
  // 대로 여기서도 성공 뒤에 `archive.load()`를 같이 부른다.
  async function archiveAndReload(projectId: string) {
    await archiveProjectAndRefresh(router, projectId);
    await archive.load();
  }
  async function deletePermanentlyAndReload(projectId: string) {
    await deleteProjectPermanentlyAndRefresh(router, projectId);
    await archive.load();
  }

  // 캡컷의 "+ 프로젝트 만들기"는 이름을 안 물어도 바로 편집기로 들어간다 --
  // 이야기(대본) 화면을 거치지 않는다. owner가 이 자리를 그렇게 다시
  // 지시해(2026-08-30) `startBlankProject`와 같은 길(빈 편집 세션 생성 +
  // 편집기로 이동)로 바꾼다 -- 다른 점은 자동 이름 대신 여기서 입력받은
  // 이름을 쓰는 것뿐이다. "이야기부터 정하기"는 이 단추의 몫이 아니게
  // 됐다(2026-08-28 결정의 이 부분만 뒤집음, `startBlankProject`는 그대로).
  async function goToNewProject(project: Project) {
    const session = await api.createBlankEditingSession(project.project_id);
    await router.options.context.catalog.refresh();
    await router.invalidate();
    await navigate({
      to: "/projects/$projectId/$section",
      params: { projectId: project.project_id, section: "editor" },
      search: { session_id: session.session_id },
    });
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
      try {
        await goToNewProject(created);
      } catch {
        // 프로젝트 자체는 이미 서버에 만들어졌다 -- "만들지 못했다"고 하면
        // 목록에 안 보이는 채로 남은 프로젝트를 창작자가 또 만들려고 한다.
        // 목록만 새로고침해 orphan으로 남지 않게 하고, 사실대로 말한다.
        await router.options.context.catalog.refresh();
        await router.invalidate();
        setCreateError("프로젝트는 만들어졌지만 편집기를 열지 못했어요. 방금 만든 프로젝트에서 이어가 주세요.");
      }
    } catch {
      setCreateError("프로젝트를 만들지 못했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  }

  // **첫 화면이 "이어하기"와 이름부터 정하는 "새 프로젝트 만들기" 둘뿐이었다
  // (owner 지적 2026-08-28): "어떤 방식으로 편집할지 결정을 해야 되잖아".**
  // 대본부터 정하는 길은 위 `handleCreate`(-> 이야기 화면)가 이미 맡는다.
  // 여기 둘은 그 옆에 나란히 두는 지름길이다 -- 이름을 먼저 안 물어도 되는
  // 대신 자동으로 이름을 붙이고, 나중에 언제든 이름 바꾸기로 고칠 수 있다.
  const [quickStartBusy, setQuickStartBusy] = useState<"blank" | "voice" | null>(null);
  const [quickStartError, setQuickStartError] = useState<string | null>(null);
  const autoProjectName = (label: string) =>
    `${label} ${new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}`;
  async function startBlankProject() {
    setQuickStartBusy("blank");
    setQuickStartError(null);
    try {
      const created = await api.createProject({ name: autoProjectName("새 영상") });
      const session = await api.createBlankEditingSession(created.project_id);
      await router.options.context.catalog.refresh();
      await router.invalidate();
      await navigate({
        to: "/projects/$projectId/$section",
        params: { projectId: created.project_id, section: "editor" },
        search: { session_id: session.session_id },
      });
    } catch {
      setQuickStartError("빈 편집판을 열지 못했어요. 다시 시도해 주세요.");
    } finally {
      setQuickStartBusy(null);
    }
  }
  // 목소리 등록·클론은 프로젝트 자산이라(§10.15) 프로젝트 없이는 못 한다 --
  // 대신 눈에 안 띄게 하나 만들고 바로 그 등록 자리(미디어 단계)로 보낸다.
  async function startVoiceCloneProject() {
    setQuickStartBusy("voice");
    setQuickStartError(null);
    try {
      const created = await api.createProject({ name: autoProjectName("내 목소리") });
      await router.options.context.catalog.refresh();
      await router.invalidate();
      await navigate({ to: resolveProjectStage(created.project_id, "assets") });
    } catch {
      setQuickStartError("프로젝트를 만들지 못했어요. 다시 시도해 주세요.");
    } finally {
      setQuickStartBusy(null);
    }
  }

  return (
    <RoutedProductShell
      projectId=""
      projects={projects}
      section="home"
      onNavigate={(nextProjectId, nextSection) => void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) })}
      onOpenSettings={() => void navigate({ to: "/settings/general" })}
    >
    <main data-testid="projects-catalog" className="vb-catalog">
      {/* `VideoBox` 이름표를 뺐다 -- 위 띠가 이미 말한다. 캡컷 홈에도 가운데에
          제품 이름이 또 적혀 있지 않다. */}
      <h1>프로젝트</h1>
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
        <div className="vb-catalog-quick-start">
          <Button type="button" className="vb-catalog-create" onClick={() => setIsCreating(true)}>+ 새 프로젝트 만들기</Button>
          {/* 캡컷 첫 화면의 진입 카드 자리(owner 캡처 2026-08-29, `2026-08-29-capcut-
              full-structure-and-dark-theme.ko.md`). **VideoBox에 없는 기능(AI 이미지·
              동영상 생성 등)의 자리는 흉내 내지 않는다** — 이름부터 안 물어도 되는
              실제 지름길 둘만 카드로 놓는다(자동으로 이름을 붙이고 바로 해당 화면으로
              보낸다 — 나중에 언제든 이름 바꾸기로 고칠 수 있다). */}
          <div className="vb-catalog-entry-cards" role="group" aria-label="빠르게 시작하기">
            <div className="vb-catalog-entry-card">
              <Button
                type="button"
                variant="outline"
                className="vb-catalog-entry-card__button"
                disabled={quickStartBusy !== null}
                aria-describedby="quick-start-blank-desc"
                onClick={() => void startBlankProject()}
              >
                <Scissors aria-hidden="true" />
                {quickStartBusy === "blank" ? "편집판을 여는 중" : "빈 편집판으로 바로 시작"}
              </Button>
              <p id="quick-start-blank-desc" className="vb-catalog-entry-card__desc">기획 없이 편집기부터 열어요</p>
            </div>
            <div className="vb-catalog-entry-card">
              <Button
                type="button"
                variant="outline"
                className="vb-catalog-entry-card__button"
                disabled={quickStartBusy !== null}
                aria-describedby="quick-start-voice-desc"
                onClick={() => void startVoiceCloneProject()}
              >
                <Mic aria-hidden="true" />
                {quickStartBusy === "voice" ? "준비하는 중" : "내 목소리 등록·클론"}
              </Button>
              <p id="quick-start-voice-desc" className="vb-catalog-entry-card__desc">녹음해서 내 목소리로 내레이션해요</p>
            </div>
          </div>
        </div>
      )}
      {quickStartError ? <p className="text-sm text-destructive" role="alert">{quickStartError}</p> : null}
      {/* 프로젝트가 하나도 없을 때 격자만 비워 두면 화면이 고장 난 것처럼 보인다.
          예전에는 이 경우 제품 껍데기 밖의 옛 화면으로 빠져나가 **파일 경로를 손으로
          적으라고** 했다(2026-08-20, 진짜 백엔드에 e2e를 붙여 처음 돌려 보고 나왔다).
          첫 사용자에게 다른 문을 만들지 않는다 -- 시작하는 길은 위의 같은 단추다. */}
      {projects.length === 0 ? (
        <p className="vb-catalog-empty">아직 만든 영상이 없어요. 위에서 새 프로젝트를 시작하면 여기에 모아 드릴게요.</p>
      ) : (
        // 캡컷 첫 화면의 "최근 프로젝트" 그리드 자리(owner 캡처 2026-08-29). 목록
        // 자체는 이미 있던 그대로다 -- 그리드 위에 제목만 더한다.
        <h2 className="vb-catalog-recent-heading">최근 프로젝트</h2>
      )}
      {/* 검색·보기전환은 검색·전환할 프로젝트가 있을 때만 의미가 있어 목록이
          있을 때만 보인다. 보관함 단추는 그렇지 않다 -- **전부 보관하면
          프로젝트 목록이 0개가 된다**(2026-08-23 코드리뷰로 발견: 이전에는
          이 단추가 검색·보기전환과 함께 `projects.length > 0`에 묶여 있어서,
          마지막 프로젝트를 보관한 순간 되돌릴 길이 통째로 사라졌다 -- 이
          단추를 만든 원래 이유("목록 화면에서는 보관함에 닿을 방법이 아예
          없었다")가 그대로 재현되는 회귀였다). 그래서 이 줄은 항상 그리고,
          검색·보기전환만 안에서 조건을 건다. */}
      <div className="vb-catalog-controls">
        {projects.length > 0 ? (
          <>
            <label className="vb-catalog-search">
              <span className="sr-only">프로젝트 검색</span>
              <Input type="search" placeholder="프로젝트 이름으로 찾기" value={projectQuery} onChange={(event) => setProjectQuery(event.target.value)} />
            </label>
            {/* 격자·줄 보기 전환(2026-08-22, `capcut-observed` 기록 §1). 화면 배치는
                이미 맞혔으니 새 백엔드가 필요 없다. **크기·구성은 2026-08-30
                버튼 단위 벤치마킹으로 다시 맞춘다** -- 캡컷은 이 자리를 좁은
                아이콘 두 개로 쓰는데, 여기는 실측 결과 전체 폭 텍스트 단추
                두 개였다(§4단계). 접근성 이름은 시각적으로 숨기고 아이콘만
                남긴다 -- `title`이 마우스 오버로, `sr-only`가 스크린리더로
                같은 말을 한다. */}
            <div className="vb-catalog-view-toggle" role="group" aria-label="보기 방식">
              <Button type="button" size="icon" variant={viewMode === "grid" ? "default" : "outline"} title="격자로 보기" aria-pressed={viewMode === "grid"} onClick={() => chooseViewMode("grid")}><LayoutGrid aria-hidden="true" /><span className="sr-only">격자로 보기</span></Button>
              <Button type="button" size="icon" variant={viewMode === "list" ? "default" : "outline"} title="줄로 보기" aria-pressed={viewMode === "list"} onClick={() => chooseViewMode("list")}><List aria-hidden="true" /><span className="sr-only">줄로 보기</span></Button>
            </div>
          </>
        ) : null}
        {/* 보관함(휴지통)도 같은 줄, 같은 오른쪽 자리다(`capcut-observed` 기록
            §1: "오른쪽에 검색·보기전환·휴지통·프로젝트 동기화"). 예전엔 카드
            목록을 다 지나야 나오는 맨 아래 링크였다 -- 검색·보기전환 옆으로
            옮긴다. 여는 기능 자체는 그대로, 자리만 옮긴다. 크기도 옆
            보기전환과 맞춰 아이콘 단추로(2026-08-30). */}
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="vb-catalog-archive-toggle"
          title={archiveOpen ? "보관함 닫기" : "보관함 보기"}
          onClick={() => { if (archiveOpen) setArchiveOpen(false); else { setArchiveOpen(true); void archive.load(); } }}
        ><Archive aria-hidden="true" /><span className="sr-only">{archiveOpen ? "보관함 닫기" : "보관함 보기"}</span></Button>
      </div>
      {projectQuery.trim() && filteredProjects.length === 0 ? (
        <p className="vb-catalog-empty">"{projectQuery.trim()}"과 맞는 프로젝트가 없어요.</p>
      ) : (
      <div className={`vb-catalog-grid${viewMode === "list" ? " vb-catalog-grid--list" : ""}`}>
        {filteredProjects.map((project) => <ProjectCatalogCard
          key={project.project_id}
          project={project}
          onNavigateHref={(href) => void navigate({ href })}
          onRename={(id, name) => renameProjectAndRefresh(router, id, name)}
        />)}
      </div>
      )}
      {/* 보관은 되돌릴 수 있어야 뜻이 있다. 예전에는 되돌리는 길이 왼쪽 기둥
          안에만 있었는데, 그 기둥은 프로젝트를 연 뒤에만 나온다 -- 즉 **목록
          화면에서는 보관함에 닿을 방법이 아예 없었다.** 여는 단추는 위 검색·보기전환
          줄로 옮겼고, 여기는 열렸을 때 펼쳐지는 목록만 맡는다.

          **카드 관리 단추 축소(2026-08-27, owner 승인).** 카드는 이름·다음 할
          일·제목 바꾸기 셋만 남기고, 보관하기·완전 삭제는 이 패널 하나로 합친다
          (재설계안 §3.3의 2번). 완전 삭제는 보관된 프로젝트에만 뜬다 -- 활성
          프로젝트를 바로 영구 삭제하던 옛 경로는 없앴다. 보관 한 단계를 먼저
          거치게 해서, 실수로 지우기 전에 되돌릴 기회가 항상 있게 한다. */}
      {archiveOpen ? <section className="vb-catalog-archive" aria-label="보관함">
        {projects.length > 0 ? <div className="vb-catalog-archive-list" aria-label="보관하기">
          <h2>보관하기</h2>
          {projects.map((project) => <div key={project.project_id} className="vb-catalog-archive-row">
            <span>{project.name}</span>
            {management.archiveConfirmId === project.project_id ? (
              <Button
                type="button"
                variant="outline"
                disabled={management.busyKey === `archive:${project.project_id}`}
                aria-label={`${project.name} 보관 확인`}
                onClick={() => { management.setArchiveConfirmId(null); void management.run(`archive:${project.project_id}`, () => archiveAndReload(project.project_id)); }}
              >보관 확인</Button>
            ) : (
              <Button
                type="button"
                variant="outline"
                aria-label={`${project.name} 보관하기`}
                onClick={() => management.setArchiveConfirmId(project.project_id)}
              >보관하기</Button>
            )}
          </div>)}
        </div> : null}
        <div className="vb-catalog-archive-list" aria-label="보관한 프로젝트">
          <h2>보관한 프로젝트</h2>
          {archive.archivedProjects.length === 0
            ? <p>보관한 프로젝트가 없어요.</p>
            : archive.archivedProjects.map((archivedProject) => <div key={archivedProject.project_id} className="vb-catalog-archive-row">
              <span>{archivedProject.name}</span>
              <Button
                type="button"
                variant="outline"
                disabled={management.busyKey === `restore:${archivedProject.project_id}`}
                aria-label={`${archivedProject.name} 되돌리기`}
                onClick={() => void management.run(`restore:${archivedProject.project_id}`, () => archive.restore(archivedProject.project_id))}
              >되돌리기</Button>
              {management.deleteConfirm?.projectId === archivedProject.project_id && management.deleteConfirm.stage === 2 ? (
                <Button
                  type="button"
                  variant="destructive"
                  disabled={management.busyKey === `delete:${archivedProject.project_id}`}
                  aria-label={`${archivedProject.name} 영구 삭제 · 한 번 더 확인할게요`}
                  onClick={() => { management.setDeleteConfirm(null); void management.run(`delete:${archivedProject.project_id}`, () => deletePermanentlyAndReload(archivedProject.project_id)); }}
                >영구 삭제 · 한 번 더 확인할게요</Button>
              ) : management.deleteConfirm?.projectId === archivedProject.project_id && management.deleteConfirm.stage === 1 ? (
                <Button
                  type="button"
                  variant="destructive"
                  aria-label={`${archivedProject.name} 삭제 1차 확인 · 되돌릴 수 없어요`}
                  onClick={() => management.setDeleteConfirm({ projectId: archivedProject.project_id, stage: 2 })}
                >삭제 1차 확인 · 되돌릴 수 없어요</Button>
              ) : (
                <Button
                  type="button"
                  variant="ghost"
                  aria-label={`${archivedProject.name} 완전 삭제`}
                  onClick={() => management.setDeleteConfirm({ projectId: archivedProject.project_id, stage: 1 })}
                >완전 삭제</Button>
              )}
            </div>)}
        </div>
      </section> : null}
      {management.error ? <p className="vb-project-action-error" role="alert">{management.error}</p> : null}
    </main>
    </RoutedProductShell>
  );
}

/** 전역 목적지를 대시보드 껍데기 안에 넣는다.
 *
 * 2026-08-19 owner 지적: `내 라이브러리`를 누르면 좌측 메뉴가 통째로 사라져
 * **여기가 어느 화면인지도, 어떻게 돌아가는지도 알 수 없었다.** 프로젝트 목록과
 * 설정은 이미 껍데기 안에 있었고 이 둘만 밖에 있었다.
 *
 * 프로젝트에 매이지 않는 화면이므로 `projectId`는 비워 둔다 -- `ProductShell`이
 * `hasProject`로 그 경우를 이미 다룬다(프로젝트 단계 메뉴를 숨긴다).
 */
function GlobalShell({ section, children }: { section: "library" | "footage"; children: ReactNode }) {
  const projects = rootRoute.useLoaderData() as Project[];
  const navigate = useNavigate();
  return <RoutedProductShell
    projectId=""
    projects={projects}
    section={section}
    onNavigate={(nextProjectId, nextSection) => void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) })}
    onOpenSettings={() => void navigate({ to: "/settings/general" })}
  >{children}</RoutedProductShell>;
}

function LibraryPage() {
  return <GlobalShell section="library"><PersonalLibraryPage /></GlobalShell>;
}

function FootagePage() {
  return <GlobalShell section="footage"><FootageOrganizerPage /></GlobalShell>;
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
  assets: { blocked: "미디어를 넣다 막혔어요", attention: "빠진 미디어가 있어요", ready: "미디어를 모으는 중" },
  edit: { blocked: "편집하다 막혔어요", attention: "편집을 확인해 주세요", ready: "편집하는 중" },
  review: { blocked: "확인하다 막혔어요", attention: "확인이 필요해요", ready: "마지막 확인 중" },
  output: { blocked: "영상을 만들다 막혔어요", attention: "완성본을 확인해 주세요", ready: "영상으로 뽑는 중" },
};

function projectStateLabel(summary: ProjectWorkspaceSummary): string {
  const byState = projectStateSentence[summary.current_stage];
  if (!byState) return "상태 확인 중";
  return summary.state === "blocked" ? byState.blocked : summary.state === "attention" ? byState.attention : byState.ready;
}

function ProjectCatalogCard({ project, onNavigateHref, onRename }: { project: Project; onNavigateHref?: (href: string) => void; onRename?: (projectId: string, name: string) => void | Promise<void> }) {
  const [summary, setSummary] = useState<ProjectWorkspaceSummary | null>(null);
  const [summaryError, setSummaryError] = useState(false);
  const [requestNumber, setRequestNumber] = useState(0);
  // 목록 화면에서는 사이드바의 프로젝트 전환 목록이 나오지 않는다
  // (`hasProject`가 거짓). 카드에 길이 없으면 여기서는 제목을 못 바꾼다.
  const [renaming, setRenaming] = useState(false);
  //: 관리 단추(제목 바꾸기)를 접어 둔다. 아래 `···`가 연다.
  const [manageOpen, setManageOpen] = useState(false);
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
    // 이름이 바뀌면 요약도 다시 부른다. 카드에 보이는 제목은 목록이 아니라 이
    // 요약에서 오므로, 여기에 `project.name`이 없으면 제목을 바꿔도 카드는 옛
    // 이름을 계속 보여 준다 -- 브라우저에서 실제로 그렇게 나왔다.
  }, [project.project_id, project.name, requestNumber]);
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
    {/* 프로젝트를 고르면 **편집기**다(owner 지적 2026-08-19, 캡컷도 열면 바로
        편집판이다). 아래 단추는 백엔드가 정한 다음 할 일이라 `/plan`·`/review`
        같은 곳으로 가는데, 그것만 있으면 편집기로 가는 길이 아예 없었다.
        안내는 남기고 이름에 편집기를 건다. */}
    {/* **캡컷 카드 모양으로 줄인다(owner 지시 2026-08-22: "레이아웃을 아예 똑같이").**
        캡컷 카드는 `그림 · 이름 · 용량|길이` 두 줄이 전부이고, 카드를 누르면 열린다.
        우리 카드는 상태·날짜·완성본 수·다음 할 일 단추까지 다섯 줄이었다.

        **줄인 것은 글줄뿐이다.** 상태·날짜·완성본 수 세 줄을 한 줄로 합쳤다.
        이름을 누르면 편집기로 가는 것은 **그대로 둔다** -- owner가 2026-08-19에
        직접 정한 것이고(캡컷도 열면 바로 편집판이다), 처음에 이걸 `next_action`으로
        바꿨다가 시험 셋이 막았다. 시험이 막은 게 맞았다.
        다음 할 일 단추도 그대로다 -- 없애면 `/plan`·`/review`로 가는 길이 사라진다. */}
    <h2><a href={resolveProjectStage(project.project_id, "edit")} aria-label={`${summary.display_name} 편집기 열기`} onClick={(event) => {
      if (!onNavigateHref) return;
      event.preventDefault();
      onNavigateHref(resolveProjectStage(project.project_id, "edit"));
    }}>{summary.display_name}</a></h2>
    <p className="vb-catalog-card__meta">
      {[projectStateLabel(summary),
        readableMoment(summary.updated_at) ? `${readableMoment(summary.updated_at)} 편집` : null,
        `완성본 ${summary.finished_video_count}개`].filter(Boolean).join(" · ")}
    </p>
    <Button asChild type="button" variant="outline" aria-label={summary.next_action.label}><a href={summary.next_action.href} onClick={(event) => {
      if (!onNavigateHref) return;
      event.preventDefault();
      onNavigateHref(summary.next_action.href);
    }}>{summary.next_action.label}</a></Button>
    {/* **관리 단추는 제목 바꾸기 하나만 남는다(2026-08-27, owner 승인).** 보관하기·
        완전 삭제는 카드에서 빠지고 `보관함` 패널 하나로 합쳤다(재설계안 §3.3의
        2번) -- 카드 컨트롤이 이름·다음 할 일·제목 바꾸기 셋으로 준다. */}
    {onRename ? (
      <Button type="button" variant="ghost" className="vb-catalog-card__more" aria-expanded={manageOpen}
        aria-label={`${summary.display_name} 관리`} onClick={() => setManageOpen((open) => !open)}>···</Button>
    ) : null}
    {manageOpen && onRename ? <>
      <Button type="button" variant="ghost" className="vb-catalog-card__rename" aria-label={`${summary.display_name} 제목 바꾸기`} onClick={() => setRenaming(true)}>제목 바꾸기</Button>
      {renaming ? <ProjectTitleDialog
        projectId={project.project_id}
        currentName={summary.display_name}
        open
        onOpenChange={(next) => { if (!next) setRenaming(false); }}
        onRename={onRename}
      /> : null}
    </> : null}
  </article>;
}

async function archiveProjectAndRefresh(router: ReturnType<typeof createAppRouter>, projectId: string) {
  await api.archiveProject(projectId);
  await router.options.context.catalog.refresh();
  await router.invalidate();
}

async function renameProjectAndRefresh(router: ReturnType<typeof createAppRouter>, projectId: string, name: string) {
  await api.renameProject(projectId, name);
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
  // 주소에 옛 이름이 와도(`/media`·`/editing`·`/outputs`…) **여기부터는 단계 이름
  // 하나로만 말한다.** 예전에는 새 이름을 다시 옛 이름으로 되돌려서 화면을 골랐다.
  const stage = parsedLocation.stage;
  window.localStorage.setItem(lastProjectKey, projectId);
  const navigateTo = (nextProjectId: string, nextSection: WorkspaceSection) => {
    void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) });
  };
  const goToStage = (nextProjectId: string, nextStage: ProjectStage) => {
    void navigate({ to: resolveProjectStage(nextProjectId, nextStage) });
  };
  const openSettings = () => void navigate({
    to: "/settings/general",
    search: { project_id: projectId } as never,
  });
  // `/home`은 단계가 아니라 프로젝트 첫 화면이다. 같은 `plan` 단계로 읽히지만
  // 그리는 화면이 다르므로 주소 조각으로 가른다.
  if (section === "home") {
    return <RoutedProductShell projectId={projectId} projects={projects} section="home" onNavigate={navigateTo} onOpenSettings={openSettings}>
      <HomePage projectId={projectId} onNavigate={navigateTo} />
    </RoutedProductShell>;
  }
  if (stage === "plan") {
    return <RoutedProductShell projectId={projectId} projects={projects} section="create" onNavigate={navigateTo} onOpenSettings={openSettings}>
      <CreationInterview projectId={projectId} />
    </RoutedProductShell>;
  }
  if (stage === "assets") {
    const requestedReturn = typeof (routeSearch as { return_to?: unknown }).return_to === "string"
      ? (routeSearch as { return_to: string }).return_to
      : null;
    const safeReturn = resolveSafeCreationReturn(projectId, requestedReturn);
    if (safeReturn) return <RoutedProductShell projectId={projectId} projects={projects} section="media" onNavigate={navigateTo} onOpenSettings={openSettings}><DraftGapMedia projectId={projectId} returnTo={safeReturn} /></RoutedProductShell>;
    return <RoutedProductShell projectId={projectId} projects={projects} section="media" onNavigate={navigateTo} onOpenSettings={openSettings}>
      <MediaWorkspacePage projectId={projectId} />
    </RoutedProductShell>;
  }
  // 검토와 출력은 한 단계다. 두 주소를 모두 살려 둔 채 같은 화면을 그린다 --
  // 한쪽을 리다이렉트로 접으면 그 주소로 바로 들어오던 경로가 끊긴다.
  if (stage === "review" || stage === "output") {
    return <RoutedProductShell projectId={projectId} projects={projects} section={stage === "output" ? "outputs" : "review"} onNavigate={navigateTo} onOpenSettings={openSettings}>
      <ReviewAndOutputPage
        projectId={projectId}
        onOpenEditor={() => goToStage(projectId, "edit")}
        onOpenSegment={({ projectId: targetProjectId, sessionId, segmentId }) => void navigate({
          to: "/projects/$projectId/$section",
          params: { projectId: targetProjectId, section: "editor" },
          search: { session_id: sessionId, segment_id: segmentId } as never,
        })}
      />
    </RoutedProductShell>;
  }
  if (stage === "edit" && rawEditingSessionId !== null && !requestedEditingSessionId) {
    return <RoutedProductShell projectId={projectId} projects={projects} section="editing" onNavigate={navigateTo} onOpenSettings={openSettings}>
      <EditorWorkbenchRoute projectId={projectId} sessionId={null} requestedSegmentId={requestedSegmentId} />
    </RoutedProductShell>;
  }
  if (stage === "edit" && !requestedEditingSessionId) {
    return <RoutedProductShell projectId={projectId} projects={projects} section="editing" onNavigate={navigateTo} onOpenSettings={openSettings}>
      <CanonicalEditorEntry projectId={projectId} onNavigate={goToStage} />
    </RoutedProductShell>;
  }
  if (stage === "edit") {
    return <RoutedProductShell projectId={projectId} projects={projects} section="editing" onNavigate={navigateTo} onOpenSettings={openSettings}>
      <EditorWorkbenchRoute projectId={projectId} sessionId={requestedEditingSessionId} requestedSegmentId={requestedSegmentId} />
    </RoutedProductShell>;
  }
  // 다섯 단계를 위에서 다 다뤘으므로 여기까지 오지 않는다. 단계가 늘었는데
  // 그릴 화면을 붙이지 않은 경우에만 걸리는 안전망이다.
  return <RecoveryPage />;
}

function resolveSafeCreationReturn(projectId: string, requestedReturn: string | null) {
  if (!requestedReturn) return null;
  try {
    const parsed = new URL(requestedReturn, window.location.origin);
    const expectedPath = resolveProjectStage(projectId, "plan");
    if (parsed.origin !== window.location.origin || parsed.pathname !== expectedPath || parsed.hash) return null;
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return null;
  }
}

function CanonicalEditorEntry({ projectId, onNavigate }: { projectId: string; onNavigate: (projectId: string, stage: ProjectStage) => void }) {
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
      <Button type="button" onClick={() => onNavigate(projectId, "plan")}>영상 정하러 가기</Button>
      {/* 캡컷은 열면 바로 빈 편집판이다. 기획을 건너뛰고 여기서 시작할 수 있어야 한다. */}
      <Button type="button" variant="outline" disabled={isOpeningBlank} onClick={() => void openBlankBoard()}>
        {isOpeningBlank ? "편집판을 여는 중" : "빈 편집판으로 시작"}
      </Button>
      <Button type="button" variant="outline" onClick={() => onNavigate(projectId, "assets")}>먼저 미디어부터 모으기</Button>
      {blankError ? <p role="alert">{blankError}</p> : null}
    </> : null}
  </div>;
}

function SettingsRoutePage() {
  const { section } = settingsRoute.useParams();
  const projects = rootRoute.useLoaderData() as Project[];
  const navigate = useNavigate();
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
  return <RoutedProductShell projectId={projectId} projects={projects} section="settings" onNavigate={(nextProjectId, nextSection) => void navigate({ to: resolveWorkspaceLocation(nextProjectId, nextSection) })} onOpenSettings={() => void navigate({ to: settingsLocation("general") })}>
    <SettingsPage projectId={projectId} section={section as typeof validSections[number]} onNavigate={(nextSection) => void navigate({ to: settingsLocation(nextSection) })} />
  </RoutedProductShell>;
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
