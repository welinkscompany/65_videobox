import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryHistory } from "@tanstack/react-router";

import { api } from "../api";
import { AppRouter, createAppRouter, ProjectCatalog } from "./AppRouter";
import { parseWorkspaceLocation, resolveWorkspaceLocation } from "./routeManifest";
import { editorUiStorageKey } from "../features/editor/workbench/editorUiState";

beforeEach(() => { vi.stubGlobal("scrollTo", vi.fn()); vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false })); vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// TimelineDock's clip selection button no longer shows the raw clip ID as
// its accessible name (F-3/Task 7) -- it shows a human-readable name like
// "내레이션 1번째 장면, 0초부터". Locating the button by data-clip-id keeps
// these fixtures decoupled from that display-only formatting.
function clipSelectionButton(clipId: string): HTMLElement {
  const clip = screen.getAllByTestId("timeline-clip").find((item) => item.getAttribute("data-clip-id") === clipId);
  if (!clip) throw new Error(`Missing timeline clip ${clipId}`);
  const button = clip.querySelector('[data-native-control="timeline-clip-select"]');
  if (!button) throw new Error(`Missing selection control for ${clipId}`);
  return button as HTMLElement;
}

async function findClipSelectionButton(clipId: string): Promise<HTMLElement> {
  return waitFor(() => clipSelectionButton(clipId));
}

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
  // 2026-08-19 owner 지적: `내 라이브러리`를 누르면 좌측 메뉴가 통째로 사라져서
  // **여기가 어느 화면인지도, 어떻게 돌아가는지도 알 수 없었다.** 프로젝트 목록과
  // 설정은 이미 껍데기 안에 있었고 라이브러리·촬영본 둘만 밖에 있었다.
  it.each(["/library", "/footage", "/projects"])("keeps the left menu on %s, so there is always a way back", async (path) => {
    // 프로젝트가 0개면 시작 화면이 따로 나온다. 여기서 보려는 것은 그게 아니라
    // **평소 상태에서 좌측 메뉴가 남아 있는가**이므로 하나 있는 상태로 둔다.
    vi.spyOn(api, "listProjects").mockResolvedValue([{ project_id: "project_a", name: "프로젝트 A", status: "draft", root_storage_uri: "local://projects/project_a" }]);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: [path] }));
    render(<AppRouter router={router} />);

    // 왼쪽 기둥은 없어졌고 전역 목적지는 위 띠의 전체 메뉴 안에 있다
    // (`docs/decisions/2026-08-21-capcut-shell-layout.ko.md`). 지키는 것은 같다 --
    // 어느 화면에서든 돌아갈 길이 있어야 한다.
    fireEvent.click(await screen.findByRole("button", { name: "전체 메뉴" }));
    const menu = screen.getByRole("navigation", { name: "전체 메뉴" });
    expect(within(menu).getByRole("link", { name: "프로젝트" })).toBeInTheDocument();
    expect(within(menu).getByRole("link", { name: "내 라이브러리" })).toBeInTheDocument();

    // 띠도 **어느 화면인지** 말해야 한다. 이 세 화면에는 보이는 제목이 따로 없어서,
    // 이 이름이 없으면 돌아갈 길이 있어도 자기가 어디 있는지 알 수 없다.
    const title = { "/library": "내 라이브러리", "/footage": "촬영본 정리", "/projects": "홈" }[path];
    expect(document.querySelector(".vb-top-bar__screen")).toHaveTextContent(title!);
  });

  // 진짜 백엔드에 e2e를 붙여 처음 돌려 보고 나왔다(2026-08-20). 프로젝트가 하나도
  // 없으면 `/projects`가 제품 껍데기 **밖으로** 빠져나가 옛 `ProjectOnboarding`을
  // 그렸다 -- 메뉴도 없고, 스타일도 없고, **창작자에게 파일 경로를 손으로 적으라고**
  // 했다. 이 제품이 벗어난 바로 그 방식이다. 새 기계에서 처음 켠 사람이 보는 첫
  // 화면이 그것이었고, 지금까지 아무도 못 본 이유는 모든 e2e가 자료가 심어진
  // 상태에서만 돌았기 때문이다.
  it("첫 설치에서도 제품 화면으로 맞이하고, 파일 경로를 묻지 않는다", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([]);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    // 껍데기 안이어야 한다 -- 여기가 어디인지, 어디로 갈 수 있는지 보여야 한다.
    fireEvent.click(await screen.findByRole("button", { name: "전체 메뉴" }));
    const menu = screen.getByRole("navigation", { name: "전체 메뉴" });
    expect(within(menu).getByRole("link", { name: "내 라이브러리" })).toBeInTheDocument();

    // 시작하는 길은 평소와 **같은 길**이다. 첫 사용자에게만 다른 문을 만들지 않는다.
    expect(await screen.findByRole("button", { name: "+ 새 프로젝트 만들기" })).toBeInTheDocument();

    // 파일 경로를 손으로 적으라고 하지 않는다.
    expect(screen.queryByLabelText(/파일이 있는 곳/)).toBeNull();
    expect(screen.queryByText("프로젝트 만들고 소스 등록")).toBeNull();
  });

  it("mounts the library workspace and keeps footage copy free of internal plan names", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([]);
    const libraryRouter = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/library"] }));
    render(<AppRouter router={libraryRouter} />);
    expect(await screen.findByTestId("global-library-page")).toHaveTextContent("내 라이브러리");
    expect(screen.getByTestId("library-results")).toBeVisible();
    cleanup();

    const footageRouter = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/footage"] }));
    render(<AppRouter router={footageRouter} />);
    expect(await screen.findByTestId("global-footage-page")).toHaveTextContent("촬영본 정리");
    // §10.13: dashboard copy names creator outcomes, never internal plan phases.
    expect(screen.queryByText(/Wave-?\s?2/i)).toBeNull();
    expect(screen.getByTestId("footage-workspace")).toHaveTextContent("VideoBox");
  });

  it("opens the editor when the creator picks a project by name", async () => {
    // 2026-08-19 owner 지적: "사이트에 들어가면 편집기부터"라고 했는데 유진과
    // 대화하는 화면이 먼저 나온다. 재 보니 **카드에서 편집기로 가는 길이 하나도
    // 없었다** -- 카드 단추는 백엔드가 정한 다음 할 일(`/plan`·`/review`·`/output`)
    // 로만 갔다. 다음 할 일 안내는 그대로 두고, 이름을 누르면 편집기로 간다.
    const projects = [{ project_id: "project_plan", name: "이야기 단계", status: "active", root_storage_uri: "local://plan" }];
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    vi.spyOn(api, "getProjectWorkspaceSummary").mockResolvedValue({
      project_id: "project_plan",
      display_name: "이야기 단계",
      updated_at: "2026-08-12T00:00:00Z",
      current_stage: "plan",
      state: "ready",
      thumbnail_url: null,
      finished_video_count: 0,
      next_action: { label: "계속 만들기", href: "/projects/project_plan/plan" },
    });
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    const card = await screen.findByRole("article", { name: "이야기 단계 프로젝트" });

    expect(within(card).getByRole("link", { name: "이야기 단계 편집기 열기" })).toHaveAttribute("href", "/projects/project_plan/editor");
    // 다음 할 일 안내는 없애지 않는다. 둘 다 있어야 한다.
    expect(within(card).getByRole("link", { name: "계속 만들기" })).toHaveAttribute("href", "/projects/project_plan/plan");
  });

  it("summarizes each project and exposes exactly one next action", async () => {
    const projects = [
      { project_id: "project_draft", name: "초안 프로젝트", status: "active", root_storage_uri: "local://draft" },
      { project_id: "project_assets", name: "자산 프로젝트", status: "active", root_storage_uri: "local://assets" },
      { project_id: "project_new", name: "새 프로젝트", status: "active", root_storage_uri: "local://new" },
    ];
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    vi.spyOn(api, "getProjectWorkspaceSummary").mockImplementation(async (projectId) => ({
      project_id: projectId,
      display_name: projects.find((item) => item.project_id === projectId)?.name ?? projectId,
      updated_at: "2026-08-12T00:00:00Z",
      current_stage: projectId === "project_draft" ? "edit" : projectId === "project_assets" ? "assets" : "plan",
      state: projectId === "project_assets" ? "attention" : "ready",
      thumbnail_url: null,
      finished_video_count: 0,
      next_action: projectId === "project_draft"
        ? { label: "계속 편집", href: "/projects/project_draft/edit" }
        : projectId === "project_assets"
          ? { label: "자산 준비", href: "/projects/project_assets/assets" }
        : { label: "계속 만들기", href: "/projects/project_new/plan" },
    }));
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));

    render(<AppRouter router={router} />);

    const draftCard = await screen.findByRole("article", { name: "초안 프로젝트 프로젝트" });
    const assetCard = await screen.findByRole("article", { name: "자산 프로젝트 프로젝트" });
    const newCard = await screen.findByRole("article", { name: "새 프로젝트 프로젝트" });
    // 첫 화면도 앱 안이어야 한다. 예전에는 사이드바가 없어서 프로그램이 아니라
    // 웹페이지 한 장으로 보였다(2026-08-17 owner 지적).
    expect(await screen.findByLabelText("전체 메뉴")).toBeInTheDocument();
    // 카드는 우리 내부 단계 이름(`기획`·`자산`)이 아니라, 그 프로젝트가 지금 어떤
    // 상태인지 사람 말로 적는다(§10.13). 2026-08-17 owner 지적.
    expect(draftCard).toHaveTextContent("편집하는 중");
    // 이 픽스처는 `attention`이라 "모으는 중"이 아니라 확인을 청하는 문장이 맞다.
    expect(assetCard).toHaveTextContent("빠진 재료가 있어요");
    expect(newCard).toHaveTextContent("이야기를 정하는 중");
    // 기계 시각을 그대로 내보내지 않는다.
    expect(newCard).not.toHaveTextContent("+00:00");
    // **다음 할 일은 카드마다 하나**다. 2026-08-19에 이름이 편집기 링크가 되면서
    // 카드의 링크는 둘이 됐지만, 안내 단추가 하나라는 이 규칙은 그대로다 --
    // 이름 링크는 "다음 할 일"이 아니라 그 프로젝트를 여는 문이다.
    const nextActions = (card: HTMLElement) =>
      within(card).getAllByRole("link").filter((link) => !link.getAttribute("aria-label")?.endsWith("편집기 열기"));
    expect(nextActions(draftCard)).toHaveLength(1);
    expect(nextActions(assetCard)).toHaveLength(1);
    expect(nextActions(newCard)).toHaveLength(1);
    expect(within(draftCard).getByRole("link", { name: "초안 프로젝트 편집기 열기" })).toBeInTheDocument();
    expect(within(draftCard).getByRole("link", { name: "계속 편집" })).toHaveAttribute("href", "/projects/project_draft/edit");
    expect(within(assetCard).getByRole("link", { name: "자산 준비" })).toHaveAttribute("href", "/projects/project_assets/assets");
    expect(within(newCard).getByRole("link", { name: "계속 만들기" })).toHaveAttribute("href", "/projects/project_new/plan");
  });

  it("lets the creator rename a video straight from its card", async () => {
    // 프로젝트 목록은 owner가 가장 먼저 여는 화면인데, 여기서는 사이드바의
    // 프로젝트 전환 목록이 나오지 않는다(`hasProject`가 거짓). 그래서 카드
    // 자체에 제목을 바꾸는 길이 없으면 목록 화면에서는 아예 못 바꾼다.
    const project = { project_id: "project_plan", name: "이야기 단계", status: "active", root_storage_uri: "local://plan" };
    const renamed = { ...project, name: "출근길 브이로그" };
    vi.spyOn(api, "listProjects")
      .mockResolvedValueOnce([project])
      .mockResolvedValue([renamed]);
    // 카드에 보이는 이름은 프로젝트 목록이 아니라 **카드가 따로 불러오는 요약**에서
    // 온다. 서버가 바뀌어도 이 요약을 다시 부르지 않으면 카드는 옛 제목을 계속
    // 보여 준다 -- 브라우저에서 실제로 그렇게 나왔다.
    let servedName = "이야기 단계";
    vi.spyOn(api, "getProjectWorkspaceSummary").mockImplementation(async (projectId) => ({
      project_id: projectId,
      display_name: servedName,
      updated_at: "2026-08-12T00:00:00Z",
      current_stage: "plan" as const,
      state: "ready" as const,
      thumbnail_url: null,
      finished_video_count: 0,
      next_action: { label: "계속 만들기", href: "/projects/project_plan/plan" },
    }));
    const renameProject = vi.spyOn(api, "renameProject").mockImplementation(async () => {
      servedName = "출근길 브이로그";
      return renamed;
    });
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    const card = await screen.findByRole("article", { name: "이야기 단계 프로젝트" });
    // **갱신 이유(2026-08-22).** 관리 단추가 `···` 뒤로 접혔다 -- 화면을
    // 찍어 보니 카드마다 단추가 4~5개씩이라 첫 화면이 단추 70개였다.
    // 지키려는 것은 "목록 화면에서 관리할 수 있다"이지 "항상 펼쳐져
    // 있다"가 아니었으므로, 여는 단추를 한 번 누르는 것만 더한다.
    fireEvent.click(within(card).getByRole("button", { name: "이야기 단계 관리" }));
    fireEvent.click(within(card).getByRole("button", { name: "이야기 단계 제목 바꾸기" }));

    const field = await screen.findByLabelText("새 제목");
    fireEvent.change(field, { target: { value: "출근길 브이로그" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(renameProject).toHaveBeenCalledWith("project_plan", "출근길 브이로그"));
    await waitFor(() => expect(screen.queryByLabelText("새 제목")).not.toBeInTheDocument());
    // 백엔드가 바뀐 것은 완료가 아니다. 카드가 새 제목을 보여야 한다.
    // `편집기 열기` 이름은 카드가 따로 불러오는 요약에서 나오므로, 이것이
    // 바뀌었다면 요약을 실제로 다시 불렀다는 뜻이다.
    await waitFor(() => expect(screen.getByRole("link", { name: "출근길 브이로그 편집기 열기" })).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: "이야기 단계 편집기 열기" })).not.toBeInTheDocument();
    expect(screen.getByRole("article", { name: "출근길 브이로그 프로젝트" })).toBeInTheDocument();
  });

  // 프로젝트 관리(보관·영구 삭제·보관함 되돌리기)는 왼쪽 기둥의 프로젝트 전환
  // 목록 안에만 있었다. 그런데 그 목록은 `hasProject`가 참일 때만 그려지므로
  // **프로젝트 목록 화면에서는 애초에 나오지 않는다.** 기둥을 위 띠로 옮기기로
  // 한 이상(`docs/decisions/2026-08-21-capcut-shell-layout.ko.md`) 관리는 여기서
  // 되어야 한다. 띠는 고르는 것만 맡는다.
  function catalogSummary(projectId: string, displayName: string) {
    return {
      project_id: projectId,
      display_name: displayName,
      updated_at: "2026-08-21T00:00:00Z",
      current_stage: "plan" as const,
      state: "ready" as const,
      thumbnail_url: null,
      finished_video_count: 0,
      next_action: { label: "계속 만들기", href: `/projects/${projectId}/plan` },
    };
  }

  const catalogNames: Record<string, string> = { project_a: "첫 영상", project_b: "둘째 영상" };

  function mockCatalogSummaries() {
    vi.spyOn(api, "getProjectWorkspaceSummary").mockImplementation(async (projectId: string) =>
      catalogSummary(projectId, catalogNames[projectId] ?? projectId));
  }

  const liveProjects = [
    { project_id: "project_a", name: "첫 영상", status: "active", root_storage_uri: "local://a" },
    { project_id: "project_b", name: "둘째 영상", status: "active", root_storage_uri: "local://b" },
  ];

  it("archives a video from its card after one confirm, and it drops off the list", async () => {
    vi.spyOn(api, "listProjects")
      .mockResolvedValueOnce(liveProjects as never)
      .mockResolvedValue([liveProjects[0]] as never);
    mockCatalogSummaries();
    const archiveProject = vi.spyOn(api, "archiveProject").mockResolvedValue({ ...liveProjects[1], status: "archived" } as never);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    const card = await screen.findByRole("article", { name: "둘째 영상 프로젝트" });
    // **갱신 이유(2026-08-22).** 관리 단추가 `···` 뒤로 접혔다 -- 화면을
    // 찍어 보니 카드마다 단추가 4~5개씩이라 첫 화면이 단추 70개였다.
    // 지키려는 것은 "목록 화면에서 관리할 수 있다"이지 "항상 펼쳐져
    // 있다"가 아니었으므로, 여는 단추를 한 번 누르는 것만 더한다.
    fireEvent.click(within(card).getByRole("button", { name: "둘째 영상 관리" }));
    fireEvent.click(within(card).getByRole("button", { name: "둘째 영상 보관하기" }));
    // 한 번 누른 것으로 사라지면 안 된다. 확인이 한 번 있다.
    expect(archiveProject).not.toHaveBeenCalled();
    fireEvent.click(within(card).getByRole("button", { name: "둘째 영상 보관 확인" }));

    await waitFor(() => expect(archiveProject).toHaveBeenCalledWith("project_b"));
    await waitFor(() => expect(screen.queryByRole("article", { name: "둘째 영상 프로젝트" })).not.toBeInTheDocument());
  });

  it("requires two separate confirmations before permanently deleting from a card", async () => {
    vi.spyOn(api, "listProjects")
      .mockResolvedValueOnce(liveProjects as never)
      .mockResolvedValue([liveProjects[0]] as never);
    mockCatalogSummaries();
    const deleteProjectPermanently = vi.spyOn(api, "deleteProjectPermanently").mockResolvedValue(undefined as never);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    const card = await screen.findByRole("article", { name: "둘째 영상 프로젝트" });
    // **갱신 이유(2026-08-22).** 관리 단추가 `···` 뒤로 접혔다 -- 화면을
    // 찍어 보니 카드마다 단추가 4~5개씩이라 첫 화면이 단추 70개였다.
    // 지키려는 것은 "목록 화면에서 관리할 수 있다"이지 "항상 펼쳐져
    // 있다"가 아니었으므로, 여는 단추를 한 번 누르는 것만 더한다.
    fireEvent.click(within(card).getByRole("button", { name: "둘째 영상 관리" }));
    fireEvent.click(within(card).getByRole("button", { name: "둘째 영상 완전 삭제" }));
    expect(deleteProjectPermanently).not.toHaveBeenCalled();
    // 첫 확인은 되돌릴 수 없다는 것을 말하고, 지우지는 않는다.
    expect(within(card).getByText(/되돌릴 수 없어요/)).toBeVisible();

    fireEvent.click(within(card).getByRole("button", { name: /삭제 1차 확인/ }));
    expect(deleteProjectPermanently).not.toHaveBeenCalled();
    expect(within(card).getByText(/한 번 더 확인/)).toBeVisible();

    fireEvent.click(within(card).getByRole("button", { name: /영구 삭제/ }));

    await waitFor(() => expect(deleteProjectPermanently).toHaveBeenCalledWith("project_b"));
    await waitFor(() => expect(screen.queryByRole("article", { name: "둘째 영상 프로젝트" })).not.toBeInTheDocument());
  });

  it("opens the archive on the projects screen and puts a video back", async () => {
    const archived = { project_id: "project_c", name: "보관한 영상", status: "archived", root_storage_uri: "local://c" };
    vi.spyOn(api, "listProjects").mockImplementation(async (includeArchived = false) =>
      (includeArchived ? [liveProjects[0], archived] : [liveProjects[0]]) as never);
    mockCatalogSummaries();
    const restoreProject = vi.spyOn(api, "restoreProject").mockResolvedValue({ ...archived, status: "active" } as never);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    await screen.findByRole("article", { name: "첫 영상 프로젝트" });
    fireEvent.click(screen.getByRole("button", { name: "보관함 보기" }));

    expect(await screen.findByText("보관한 영상")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "보관한 영상 되돌리기" }));

    await waitFor(() => expect(restoreProject).toHaveBeenCalledWith("project_c"));
  });

  it("says the archive is empty on the projects screen instead of showing nothing", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([liveProjects[0]] as never);
    mockCatalogSummaries();
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    await screen.findByRole("article", { name: "첫 영상 프로젝트" });
    fireEvent.click(screen.getByRole("button", { name: "보관함 보기" }));

    expect(await screen.findByText("보관한 프로젝트가 없어요.")).toBeVisible();
  });

  it("shows a retryable message when a project action fails on the projects screen", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(liveProjects as never);
    mockCatalogSummaries();
    vi.spyOn(api, "archiveProject").mockRejectedValue(new Error("network down"));
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    const card = await screen.findByRole("article", { name: "둘째 영상 프로젝트" });
    // **갱신 이유(2026-08-22).** 관리 단추가 `···` 뒤로 접혔다 -- 화면을
    // 찍어 보니 카드마다 단추가 4~5개씩이라 첫 화면이 단추 70개였다.
    // 지키려는 것은 "목록 화면에서 관리할 수 있다"이지 "항상 펼쳐져
    // 있다"가 아니었으므로, 여는 단추를 한 번 누르는 것만 더한다.
    fireEvent.click(within(card).getByRole("button", { name: "둘째 영상 관리" }));
    fireEvent.click(within(card).getByRole("button", { name: "둘째 영상 보관하기" }));
    fireEvent.click(within(card).getByRole("button", { name: "둘째 영상 보관 확인" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("프로젝트 작업에 실패했어요. 다시 시도해 주세요.");
  });

  it("keeps a failed workspace summary out of project creation", async () => {
    const project = { project_id: "project_broken", name: "확인 필요", status: "active", root_storage_uri: "local://broken" };
    vi.spyOn(api, "listProjects").mockResolvedValue([project]);
    vi.spyOn(api, "getProjectWorkspaceSummary").mockRejectedValue(new Error("unavailable"));
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    const card = await screen.findByRole("article", { name: "확인 필요 프로젝트" });
    expect(card).toHaveTextContent("상태 확인 필요");
    expect(within(card).getByRole("button", { name: "다시 확인" })).toBeVisible();
    expect(within(card).queryByText("새 영상 시작")).not.toBeInTheDocument();
  });

  it("owns ordinary media with the canonical workspace and keeps the creation return adapter narrow", async () => {
    const project = { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" };
    vi.spyOn(api, "listProjects").mockResolvedValue([project]);
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([]);
    vi.spyOn(api, "listMediaAnalysis").mockResolvedValue({ items: [] });
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/media"] }));
    render(<AppRouter router={router} />);

    expect(await screen.findByTestId("media-workspace-page")).toHaveAttribute("data-project-id", "project_a");
    expect(screen.queryByRole("heading", { name: "장면 영상 추가" })).not.toBeInTheDocument();
    cleanup();

    const safeRouter = createAppRouter(new ProjectCatalog(), createMemoryHistory({
      initialEntries: ["/projects/project_a/media?return_to=%2Fprojects%2Fproject_a%2Fcreate%3Fbrief_id%3Dbrief-1"],
    }));
    render(<AppRouter router={safeRouter} />);
    expect(await screen.findByRole("heading", { name: "장면 영상 추가" })).toBeVisible();
    cleanup();

    for (const unsafeReturn of [
      "https://example.com/projects/project_a/create",
      "/projects/project_b/create",
      "/projects/project_a/create-extra",
    ]) {
      const unsafeRouter = createAppRouter(new ProjectCatalog(), createMemoryHistory({
        initialEntries: [`/projects/project_a/media?return_to=${encodeURIComponent(unsafeReturn)}`],
      }));
      render(<AppRouter router={unsafeRouter} />);
      expect(await screen.findByTestId("media-workspace-page")).toBeVisible();
      expect(screen.queryByRole("heading", { name: "장면 영상 추가" })).not.toBeInTheDocument();
      cleanup();
    }
  });

  it("uses /editor for new editing links while continuing to read the prior editing URL", () => {
    expect(resolveWorkspaceLocation("project_a", "editing")).toBe("/projects/project_a/editor");
    expect(parseWorkspaceLocation("/projects/project_a/editor")).toEqual({ projectId: "project_a", stage: "edit", legacy: true });
    expect(parseWorkspaceLocation("/projects/project_a/editing")).toEqual({ projectId: "project_a", stage: "edit", legacy: true });
  });

  it("pins the latest session before opening a canonical editor URL without a session", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }]);
    const latest = vi.spyOn(api, "getLatestEditingSession").mockResolvedValue({ session_id: "editing_session_latest" } as never);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editor"] }));

    render(<AppRouter router={router} />);

    await waitFor(() => expect(latest).toHaveBeenCalledWith("project_a"));
    await waitFor(() => expect(router.state.location.href).toBe("/projects/project_a/editor?session_id=editing_session_latest"));
  });

  it("parses segment_id for a pinned editor without adding it to session resolution", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }]);
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue({
      project_id: "project_a", session_id: "session-a", timeline_id: "timeline-a", session_revision: 1, timeline_version: "v1",
      timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 2 },
      tracks: [{ track_id: "narration", track_type: "narration", clips: [{ clip_id: "clip-1", segment_id: "segment-1", clip_type: "narration", asset_id: null, asset_uri: null, start_sec: 0, end_sec: 2, media_controls: {} }] }],
      captions: [], gap_slots: [], source_status: { status: "current" }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable" },
    } as never);
    vi.spyOn(api, "getEditingSession").mockResolvedValue({
      project_id: "project_a", session_id: "session-a", timeline_id: "timeline-a", session_revision: 1,
      segments: [], history: [],
    } as never);
    const latest = vi.spyOn(api, "getLatestEditingSession");
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editor?session_id=session-a&segment_id=segment-1"] }));

    render(<AppRouter router={router} />);

    const requestedClip = await findClipSelectionButton("clip-1");
    await waitFor(() => expect(requestedClip).toHaveAttribute("aria-pressed", "true"));
    expect(router.state.location.href).toBe("/projects/project_a/editor?session_id=session-a&segment_id=segment-1");
    expect(latest).not.toHaveBeenCalled();
  });

  it("keeps one mounted editor while actual search transitions A to B to A refocus the active segment", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1920 });
    // Seed the project+session-scoped key directly: it takes priority over the
    // legacy unscoped key, so an earlier test's default-closed state for the
    // same project_a/session-a pair would otherwise shadow this seed.
    window.localStorage.setItem(editorUiStorageKey("project_a", "session-a"), JSON.stringify({ leftOpen: true, rightOpen: true, activeDrawer: null, leftSize: 280, rightSize: 320 }));
    vi.spyOn(api, "listProjects").mockResolvedValue([{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }]);
    const manifest = vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue({
      project_id: "project_a", session_id: "session-a", timeline_id: "timeline-a", session_revision: 1, timeline_version: "v1",
      timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 2 },
      tracks: [{ track_id: "narration", track_type: "narration", clips: [
        { clip_id: "clip-1", segment_id: "segment-1", clip_type: "narration", asset_id: null, asset_uri: null, start_sec: 0, end_sec: 1, media_controls: {} },
        { clip_id: "clip-2", segment_id: "segment-2", clip_type: "narration", asset_id: null, asset_uri: null, start_sec: 1, end_sec: 2, media_controls: {} },
      ] }],
      captions: [
        { segment_id: "segment-1", caption_id: "caption-1", placement_id: "caption:segment-1", text: "첫 장면", start_sec: 0, end_sec: 1, style: { font_family: "Pretendard", font_size_px: 20, text_color: "#fff", outline_color: "#000", outline_width_px: 1, background_color: "#00000000", position_x_percent: 50, position_y_percent: 90, horizontal_align: "center", safe_area_enabled: true, shadow_blur_px: 0 } },
        { segment_id: "segment-2", caption_id: "caption-2", placement_id: "caption:segment-2", text: "둘째 장면", start_sec: 1, end_sec: 2, style: { font_family: "Pretendard", font_size_px: 20, text_color: "#fff", outline_color: "#000", outline_width_px: 1, background_color: "#00000000", position_x_percent: 50, position_y_percent: 90, horizontal_align: "center", safe_area_enabled: true, shadow_blur_px: 0 } },
      ],
      gap_slots: [], source_status: { status: "current" }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable" },
    } as never);
    vi.spyOn(api, "getEditingSession").mockResolvedValue({
      project_id: "project_a", session_id: "session-a", timeline_id: "timeline-a", session_revision: 1,
      segments: [], history: [],
    } as never);
    const director = vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-a", project_id: "project_a", session_id: "session-a" },
      messages: [], proposal: null, references: [],
    } as never);
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([]);
    vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [] });
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editor?session_id=session-a&segment_id=segment-1"] }));
    render(<AppRouter router={router} />);

    const workbench = await screen.findByRole("region", { name: "편집 작업판" });
    const preview = screen.getByRole("region", { name: "미리보기" });
    const timeline = screen.getByTestId("timeline-track");
    const rightDock = screen.getByRole("complementary", { name: "세부 정보" });
    expect(screen.getByLabelText("segment-1 자막 텍스트")).toBeVisible();
    fireEvent.change(screen.getByLabelText("유진에게 요청하기"), { target: { value: "보존할 요청" } });
    fireEvent.click(clipSelectionButton("clip-2"));
    timeline.scrollLeft = 47;

    await act(async () => { await router.navigate({ to: "/projects/$projectId/$section", params: { projectId: "project_a", section: "editor" }, search: { session_id: "session-a", segment_id: "segment-2" } as never }); });
    expect(await screen.findByLabelText("segment-2 자막 텍스트")).toBeVisible();
    await act(async () => { await router.navigate({ to: "/projects/$projectId/$section", params: { projectId: "project_a", section: "editor" }, search: { session_id: "session-a", segment_id: "segment-1" } as never }); });
    expect(await screen.findByLabelText("segment-1 자막 텍스트")).toBeVisible();

    expect(screen.getByRole("region", { name: "편집 작업판" })).toBe(workbench);
    expect(screen.getByRole("region", { name: "미리보기" })).toBe(preview);
    expect(screen.getByTestId("timeline-track")).toBe(timeline);
    expect(screen.getByRole("complementary", { name: "세부 정보" })).toBe(rightDock);
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("보존할 요청");
    expect(screen.getByTestId("timeline-track").scrollLeft).toBe(47);
    expect(clipSelectionButton("clip-1")).toHaveAttribute("aria-pressed", "true");
    expect(clipSelectionButton("clip-2")).toHaveAttribute("aria-pressed", "false");
    expect(manifest).toHaveBeenCalledTimes(1);
    expect(director).toHaveBeenCalledTimes(1);
  });

  it.each(["timeline", "review"])("routes /%s to the canonical timeline review owner", async (section) => {
    vi.spyOn(api, "listProjects").mockResolvedValue([{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue({
      session_id: "session-a", project_id: "project_a", timeline_id: "timeline-a", session_revision: 1, segments: [], history: [],
    });
    vi.spyOn(api, "listJobs").mockResolvedValue([{
      job_id: "job-a", project_id: "project_a", job_type: "timeline_build", status: "succeeded", input_ref: null, output_ref: "timeline-a",
      error_message: null, started_at: "2026-07-23T00:00:00Z", finished_at: "2026-07-23T00:01:00Z",
    }]);
    vi.spyOn(api, "getTimeline").mockResolvedValue({ job_id: "job-a", status: "succeeded", timeline: { timeline_id: "timeline-a", project_id: "project_a", version: "v1", output_mode: "review", review_status: "draft", tracks: [], review_flags: [], applied_recommendations: [], pending_recommendations: [] } });
    vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({ project_id: "project_a", timeline_id: "timeline-a", review_status: "draft", segments: [], applied_recommendations: [], pending_recommendations: [], review_flags: [] });
    vi.spyOn(api, "getReviewApproval").mockResolvedValue({ project_id: "project_a", timeline_id: "timeline-a", review_status: "draft", approved_at: null, updated_at: "now", source_session_id: "session-a", source_session_revision: 1, is_current: true, invalidated_at: null, invalidated_reason: null });
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: [`/projects/project_a/${section}`] }));

    render(<AppRouter router={router} />);

    expect(await screen.findByTestId("timeline-review-page")).toHaveAttribute("data-project-id", "project_a");
    expect(screen.getByRole("heading", { name: "영상 검토" })).toBeVisible();
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

    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/project_b/editor"));
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

  it("does not run output mutations while the canonical output route mounts", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    vi.spyOn(api, "listJobs").mockResolvedValue([{ job_id: "final_a", project_id: "project_a", job_type: "final_render", status: "succeeded", input_ref: "timeline_a", output_ref: "final_a", error_message: null, started_at: "2026-07-23T09:00:00Z", finished_at: "2026-07-23T09:01:00Z" }]);
    vi.spyOn(api, "getFinalRender").mockResolvedValue({ job_id: "final_a", status: "succeeded", render: { export_id: "final_a", timeline_id: "timeline_a", export_type: "final_render", file_uri: "local://final.mp4", status: "succeeded", is_current: true } } as never);
    vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue({ status: "ready", is_supported: true, project_root_path: "local://capcut", project_root_exists: true, write_access: true, checked_at: "2026-07-23T09:01:00Z" });
    const startFinalRender = vi.spyOn(api, "startFinalRender");
    const startCapcutDraftExport = vi.spyOn(api, "startCapcutDraftExport");
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/outputs"] }));

    render(<AppRouter router={router} />);

    expect(await screen.findByRole("heading", { name: "완성본과 CapCut 초안" })).toBeVisible();
    expect(startFinalRender).not.toHaveBeenCalled();
    expect(startCapcutDraftExport).not.toHaveBeenCalled();
  });

  it("redirects project-scoped settings to the canonical general settings owner", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([
      { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
    ]);
    const getPreview = vi.spyOn(api, "getPreview");
    const getExport = vi.spyOn(api, "getExport");
    const router = createAppRouter(
      new ProjectCatalog(),
      createMemoryHistory({ initialEntries: ["/projects/project_a/settings"] }),
    );

    render(<AppRouter router={router} />);

    expect(await screen.findByTestId("settings-page")).toBeVisible();
    expect(screen.getByRole("heading", { name: "일반" })).toBeVisible();
    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/general"));
    expect(getPreview).not.toHaveBeenCalled();
    expect(getExport).not.toHaveBeenCalled();
  });

  it("preserves a validated project identity while redirecting project-scoped settings", async () => {
    window.localStorage.setItem("videobox.last-valid-project", "project_a");
    vi.spyOn(api, "listProjects").mockResolvedValue([
      { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
      { project_id: "project_b", name: "B", status: "active", root_storage_uri: "local://b" },
    ]);
    const router = createAppRouter(
      new ProjectCatalog(),
      createMemoryHistory({ initialEntries: ["/projects/project_b/settings"] }),
    );

    render(<AppRouter router={router} />);

    expect(await screen.findByTestId("settings-page")).toBeVisible();
    // 띠는 **지금 프로젝트만** 보여 준다 -- 보인다는 것이 곧 열려 있다는 뜻이다.
    expect(screen.getByRole("button", { name: "B" })).toBeVisible();
    await waitFor(() => expect(router.state.location.href).toBe("/settings/general?project_id=project_b"));
  });

  it("keeps the open project when the top bar settings entry is activated", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([
      { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
      { project_id: "project_b", name: "B", status: "active", root_storage_uri: "local://b" },
    ]);
    const router = createAppRouter(
      new ProjectCatalog(),
      createMemoryHistory({ initialEntries: ["/projects/project_b/home"] }),
    );

    render(<AppRouter router={router} />);

    fireEvent.click(await screen.findByRole("button", { name: "전체 메뉴" }));
    fireEvent.click(screen.getByRole("button", { name: "설정" }));

    await waitFor(() => expect(router.state.location.href).toBe("/settings/general?project_id=project_b"));
    expect(screen.getByRole("button", { name: "B" })).toBeVisible();
  });

  it("does not redirect an unknown project-scoped settings URL into another project's settings", async () => {
    window.localStorage.setItem("videobox.last-valid-project", "project_a");
    vi.spyOn(api, "listProjects").mockResolvedValue([
      { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
    ]);
    const router = createAppRouter(
      new ProjectCatalog(),
      createMemoryHistory({ initialEntries: ["/projects/missing/settings"] }),
    );

    render(<AppRouter router={router} />);

    expect(await screen.findByTestId("project-recovery")).toBeVisible();
    expect(screen.queryByTestId("settings-page")).not.toBeInTheDocument();
  });

  it("redirects the prior editing URL to the canonical workbench without mounting legacy workspace data", async () => {
    const projects = [{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }];
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const getProject = vi.spyOn(api, "getProject");
    const loadManifest = vi.spyOn(api, "getEditorPlaybackManifest").mockRejectedValue(new Error("not ready"));
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editing?session_id=legacy-session"] }));

    render(<AppRouter router={router} />);

    await waitFor(() => expect(router.state.location.href).toBe("/projects/project_a/editor?session_id=legacy-session"));
    await waitFor(() => expect(loadManifest).toHaveBeenCalledWith("project_a", "legacy-session"));
    expect(getProject).not.toHaveBeenCalled();
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
    // A fresh session opens with the preview alone -- the picture is what the
    // creator is judging, not the docks. Both open with one toolbar click.
    // **갱신 이유(2026-08-22).** 오른쪽 도크가 기본으로 펴지면서 넓은 화면의 기본
    // 밀도가 `desktop-single`에서 `desktop-both`가 됐다(캡컷은 소재와 세부 정보가
    // 둘 다 붙어 있다). 이 시험이 지키는 것은 **정식 편집기가 뜨고 옛 미디어 화면이
    // 안 섞인다**이지 밀도 값이 아니었으므로, 지키는 것은 그대로 두고 값만 맞춘다.
    expect(workbench).toHaveAttribute("data-editor-density", "desktop-both");
    // 밀도가 `desktop-both`가 되면서 미리보기 최소폭도 640에서 720으로 올라간다
    // (`bothPreviewMinPx`). 같은 갱신의 일부다 -- 위 주석 참고.
    expect(screen.getByRole("region", { name: "미리보기" }).parentElement).toHaveAttribute("data-preview-min-width", "720");
    expect(screen.getByLabelText("편집본 미리보기")).toHaveAttribute("src", "/api/projects/project_a/exact-previews/generation-1/content");
    expect(document.querySelectorAll("audio,video")).toHaveLength(1);
    // 세부 정보는 이제 기본으로 펴져 있다. **누르면 오히려 닫힌다.**
    if (!screen.queryByRole("complementary", { name: "세부 정보" })) {
      fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    }
    expect(screen.getByLabelText("유진에게 요청하기")).toBeEnabled();
    expect(screen.getByRole("button", { name: "요청 보내기" })).toBeDisabled();
    expect(screen.getByText("아직 추천이 없어요. 직접 편집을 계속하거나 유진에게 요청할 수 있어요.")).toBeVisible();
    expect(loadManifest).toHaveBeenCalledTimes(1);
    expect(loadSession).toHaveBeenCalledTimes(1);
    expect(loadSession).toHaveBeenCalledWith("project_a", "editing_session_draft_1");
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
    // 예전에는 옛 시작 화면을 거쳤다. 그 화면이 사라졌으므로 **평소 쓰는 길**로 잰다 --
    // 첫 사용자에게만 다른 문을 만들지 않는 것이 이번 변경의 요점이다.
    const created = { project_id: "project_new", name: "New", status: "active", root_storage_uri: "local://new" };
    const listProjects = vi.spyOn(api, "listProjects").mockResolvedValueOnce([]).mockResolvedValueOnce([created]);
    vi.spyOn(api, "createProject").mockResolvedValue(created);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));

    render(<AppRouter router={router} />);
    fireEvent.click(await screen.findByRole("button", { name: "+ 새 프로젝트 만들기" }));
    fireEvent.change(await screen.findByLabelText("새 프로젝트 이름"), { target: { value: "New" } });
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/project_new/create"));
    expect(listProjects).toHaveBeenCalledTimes(2);
  });

  it("lets the owner start a second project from a non-empty catalog", async () => {
    const existing = { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" };
    const created = { project_id: "project_second", name: "Second", status: "active", root_storage_uri: "local://second" };
    const listProjects = vi.spyOn(api, "listProjects")
      .mockResolvedValueOnce([existing])
      .mockResolvedValueOnce([existing, created]);
    const createProject = vi.spyOn(api, "createProject").mockResolvedValue(created);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    fireEvent.click(await screen.findByRole("button", { name: "+ 새 프로젝트 만들기" }));
    fireEvent.change(screen.getByLabelText("새 프로젝트 이름"), { target: { value: "Second" } });
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/project_second/create"));
    expect(createProject).toHaveBeenCalledWith({ name: "Second" });
    expect(listProjects).toHaveBeenCalledTimes(2);
  });

  it("keeps the workspace shell when a project has no draft yet", async () => {
    // CanonicalEditorEntry used to render a bare <main> with no sidebar, no
    // header, and no way back -- a dead end for a project that has not made
    // its first draft.
    const project = { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" };
    vi.spyOn(api, "listProjects").mockResolvedValue([project]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/editor"] }));

    render(<AppRouter router={router} />);

    // 편집기의 빈 상태는 잠긴 문이 아니라 시작하는 자리다.
    expect(await screen.findByText(/아직 편집할 영상이 없어요/)).toBeVisible();
    expect(screen.getByRole("button", { name: "영상 정하러 가기" })).toBeVisible();
    // 캡컷처럼 **기획을 건너뛰고 빈 편집판으로** 바로 들어갈 수도 있어야 한다.
    expect(screen.getByRole("button", { name: "빈 편집판으로 시작" })).toBeVisible();
    expect(screen.getByRole("button", { name: "이야기" })).toBeVisible();
    const createButtons = screen.getAllByRole("button", { name: "영상 정하러 가기" });
    expect(createButtons.length).toBeGreaterThan(0);

    fireEvent.click(createButtons[0]);

    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/project_a/create"));
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
    let resolveA!: (session: Awaited<ReturnType<typeof api.getLatestEditingSession>>) => void;
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const getLatest = vi.spyOn(api, "getLatestEditingSession").mockImplementation((projectId) => (
      projectId === "project_a"
        ? new Promise((resolve) => { resolveA = resolve; })
        : Promise.resolve({ session_id: "session-b", project_id: "project_b", timeline_id: "timeline-b", session_revision: 1, segments: [], history: [] })
    ));
    vi.spyOn(api, "listJobs").mockImplementation((projectId) => Promise.resolve(projectId === "project_b" ? [{
      job_id: "job-b", project_id: "project_b", job_type: "timeline_build", status: "succeeded", input_ref: null, output_ref: "timeline-b",
      error_message: null, started_at: "now", finished_at: "now",
    }] : []));
    vi.spyOn(api, "getTimeline").mockResolvedValue({ job_id: "job-b", status: "succeeded", timeline: { timeline_id: "timeline-b", project_id: "project_b", version: "v1", output_mode: "review", review_status: "draft", tracks: [], review_flags: [], applied_recommendations: [], pending_recommendations: [] } });
    vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({ project_id: "project_b", timeline_id: "timeline-b", review_status: "draft", segments: [], applied_recommendations: [], pending_recommendations: [], review_flags: [] });
    vi.spyOn(api, "getReviewApproval").mockResolvedValue({ project_id: "project_b", timeline_id: "timeline-b", review_status: "draft", approved_at: null, updated_at: "now", source_session_id: "session-b", source_session_revision: 1, is_current: true, invalidated_at: null, invalidated_reason: null });
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/project_a/timeline"] }));
    render(<AppRouter router={router} />);
    await waitFor(() => expect(getLatest).toHaveBeenCalledWith("project_a"));

    await act(async () => { await router.navigate({ to: "/projects/project_b/timeline" }); });
    await waitFor(() => expect(getLatest).toHaveBeenCalledWith("project_b"));
    expect(await screen.findByTestId("timeline-review-page")).toHaveAttribute("data-project-id", "project_b");

    await act(async () => { resolveA({ session_id: "session-a", project_id: "project_a", timeline_id: "timeline-a", session_revision: 1, segments: [], history: [] }); });
    expect(screen.getByTestId("timeline-review-page")).toHaveAttribute("data-project-id", "project_b");
  });

  it("navigates catalog and recovery choices to a real project home", async () => {
    const projects = [{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }];
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    vi.spyOn(api, "getProjectWorkspaceSummary").mockResolvedValue({
      project_id: "project_a", display_name: "A", updated_at: "2026-08-12T00:00:00Z",
      current_stage: "plan", state: "ready", thumbnail_url: null, finished_video_count: 0,
      next_action: { label: "프로젝트 열기", href: "/projects/project_a/plan" },
    });
    const catalogRouter = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={catalogRouter} />);
    fireEvent.click(await screen.findByRole("link", { name: "프로젝트 열기" }));
    await waitFor(() => expect(catalogRouter.state.location.pathname).toBe("/projects/project_a/plan"));
    cleanup();

    const recoveryRouter = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/missing/editing"] }));
    render(<AppRouter router={recoveryRouter} />);
    fireEvent.click(await screen.findByRole("button", { name: "A" }));
    await waitFor(() => expect(recoveryRouter.state.location.pathname).toBe("/projects/project_a/home"));
  });

  it("sends the voice settings route to where the voice work now lives", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([
      { project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" },
    ]);
    vi.spyOn(api, "listVoiceSamples").mockResolvedValue([]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/settings/voice"] }));

    render(<AppRouter router={router} />);

    // 목소리 만들기는 2026-08-16에 설정에서 자산 단계로 옮겼다. 옛 주소는 지우지 않고
    // 길만 알려 준다 — 즐겨찾기나 지난 문서로 들어오는 사람이 막다른 곳을 만나면 안 된다.
    expect(await screen.findByRole("heading", { name: "내 목소리" })).toBeVisible();
    expect(screen.getByRole("link", { name: "내레이션 열기" })).toHaveAttribute("href", "/projects/project_a/assets");
    // 같은 일을 두 곳에서 하게 두지 않는다.
    expect(screen.queryByRole("region", { name: "내 목소리와 읽어보기 후보" })).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/settings/voice");
    expect(screen.queryByTestId("project-recovery")).not.toBeInTheDocument();
  });
});
