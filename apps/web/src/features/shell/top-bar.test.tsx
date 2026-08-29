import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { TopBar } from "./TopBar";

beforeEach(() => { vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const projects = [
  { project_id: "a", name: "첫 영상" },
  { project_id: "b", name: "둘째 영상" },
];

function renderBar(overrides: Partial<Parameters<typeof TopBar>[0]> = {}) {
  return render(
    <TopBar
      projectId="a"
      projects={projects}
      section="editing"
      onNavigate={vi.fn()}
      onSelectProject={vi.fn()}
      onOpenSettings={vi.fn()}
      {...overrides}
    />,
  );
}

/** 캡컷은 왼쪽 기둥이 없고 위 띠 하나로 끝난다. owner가 그 배치를 고른 이유는
 *  둘이다 — 지금 자기가 아는 배치라 바로 쓸 수 있고, 나중에 남에게 팔 때도
 *  처음 켠 사람이 설명 없이 쓸 수 있다
 *  (`docs/decisions/2026-08-21-capcut-shell-layout.ko.md`).
 *
 *  왼쪽 기둥이 없어지면서 **거기 있던 것이 조용히 사라지면 안 된다** — 단계 이동,
 *  프로젝트 전환, 설정이 전부 여기로 온다. */
describe("위 띠", () => {
  it("현재 위치를 보여 주고 안전한 이전 동작을 쓴다", () => {
    const onBack = vi.fn();
    renderBar({
      onBack,
      navigation: {
        screenName: "편집",
        fallbackHref: "/projects/a/media",
        crumbs: [
          { label: "프로젝트", href: "/projects" },
          { label: "첫 영상", href: "/projects/a/home" },
          { label: "편집" },
        ],
      },
    });

    const breadcrumb = screen.getByRole("navigation", { name: "현재 위치" });
    expect(breadcrumb).toHaveTextContent("프로젝트첫 영상편집");
    expect(screen.getByRole("link", { name: "프로젝트" })).toHaveAttribute("href", "/projects");
    expect(within(breadcrumb).getByText("편집").closest("a")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "이전 화면" }));
    expect(onBack).toHaveBeenCalledOnce();
  });

  it("작은 전체 메뉴 버튼은 키보드에도 설명을 준다", async () => {
    renderBar();

    fireEvent.focus(screen.getByRole("button", { name: "전체 메뉴" }));

    expect(await screen.findByRole("tooltip")).toHaveTextContent("프로젝트와 도구 메뉴 열기");
  });

  it("경로가 있으면 전역 화면 이름을 한 번만 말한다", () => {
    renderBar({
      projects: [],
      projectId: "",
      section: "library",
      screenName: "미디어",
      navigation: {
        screenName: "미디어",
        fallbackHref: "/projects",
        crumbs: [{ label: "프로젝트", href: "/projects" }, { label: "미디어" }],
      },
      onBack: vi.fn(),
    });

    expect(screen.getAllByText("미디어")).toHaveLength(1);
  });

  it("만드는 순서대로 단계를 늘어놓는다", () => {
    renderBar();

    const stages = within(screen.getByRole("navigation", { name: "프로젝트 단계" }))
      .getAllByRole("button")
      .map((button) => button.textContent);

    // 이야기(대본) → 미디어 → 편집 → 확인과 내보내기. 일이 실제로 흐르는 순서다.
    expect(stages).toEqual(["이야기", "미디어", "편집", "확인과 내보내기"]);
  });

  it("지금 어느 단계인지 띠가 말한다", () => {
    renderBar({ section: "editing" });

    expect(screen.getByRole("button", { name: "편집" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "미디어" })).not.toHaveAttribute("aria-current");
  });

  it("단계를 누르면 그 단계로 간다", () => {
    const onNavigate = vi.fn();
    renderBar({ onNavigate });

    fireEvent.click(screen.getByRole("button", { name: "미디어" }));

    expect(onNavigate).toHaveBeenCalledWith("a", "media");
  });

  it("프로젝트 이름이 보이고 거기서 바꿀 수 있다", () => {
    // 왼쪽 기둥에서는 프로젝트 목록이 29개 단추로 펼쳐져 가운데를 다 차지했다.
    // 위 띠에서는 **지금 것만** 보이고 나머지는 눌러야 나온다.
    const onSelectProject = vi.fn();
    renderBar({ onSelectProject });

    expect(screen.getByRole("button", { name: /첫 영상/ })).toBeVisible();
    expect(screen.queryByRole("button", { name: /둘째 영상/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /첫 영상/ }));
    fireEvent.click(screen.getByRole("button", { name: "둘째 영상" }));
    expect(onSelectProject).toHaveBeenCalledWith("b");
  });

  it("왼쪽 기둥에 있던 전체 메뉴 넷이 하나도 안 사라진다", () => {
    // 기둥을 없애는 변경에서 가장 흔한 사고다. 빼먹으면 내 라이브러리와 촬영본
    // 정리가 **갈 수 없는 곳**이 된다.
    const onOpenSettings = vi.fn();
    renderBar({ onOpenSettings });

    fireEvent.click(screen.getByRole("button", { name: "전체 메뉴" }));

    const menu = screen.getByRole("navigation", { name: "전체 메뉴" });
    for (const label of ["프로젝트", "미디어", "촬영본 정리"]) {
      expect(within(menu).getByRole("link", { name: label })).toBeVisible();
    }
    fireEvent.click(within(menu).getByRole("button", { name: "설정" }));
    expect(onOpenSettings).toHaveBeenCalled();
  });

  it("전체 메뉴는 접혀 있다 — 띠가 다시 목록이 되지 않는다", () => {
    renderBar();

    expect(screen.queryByRole("navigation", { name: "전체 메뉴" })).toBeNull();
  });

  it("단계로 말할 수 없는 화면에서는 이름으로 말한다", () => {
    // 왼쪽 기둥 시절에는 머리말이 "여기가 어디인지"를 말했다. 그 머리말이
    // 없어지면 내 라이브러리·촬영본 정리·설정에서 화면 이름이 통째로 사라진다 --
    // 그 화면들에는 보이는 제목이 따로 없다.
    renderBar({ projects: [], projectId: "", section: "library", screenName: "미디어" });

    expect(screen.getByText("미디어")).toBeVisible();
  });

  it("단계가 켜져 있으면 같은 말을 두 번 하지 않는다", () => {
    // 켜진 단계 단추가 이미 어느 화면인지 말한다. 옆에 이름을 또 적으면 첫 화면에
    // "누를 것처럼 보이는 것"이 하나 더 늘어난다 -- owner가 막혔던 바로 그 문제다.
    renderBar({ section: "editing", screenName: "편집" });

    expect(screen.getAllByText("편집")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "편집" })).toHaveAttribute("aria-current", "page");
  });

  it("프로젝트가 아직 없으면 단계를 보여 주지 않는다", () => {
    // 갈 수 없는 곳을 띠에 띄워 두면 눌렀을 때 빈 화면이 뜬다.
    renderBar({ projects: [], projectId: "" });

    expect(screen.queryByRole("navigation", { name: "프로젝트 단계" })).toBeNull();
    // 프로젝트가 없어도 전체 메뉴로는 갈 수 있어야 한다.
    expect(screen.getByRole("button", { name: "전체 메뉴" })).toBeVisible();
  });
});

/** 캡컷 위 툴바에서 가장 눈에 띄는 둘이 **화면 비율**과 **내보내기**다. 우리 띠엔
 *  없었다. 다만 승인 기록이 못박은 원칙이 있다 -- 띠에는 **우리가 실제로 하는 일만**
 *  올린다(`docs/decisions/2026-08-21-capcut-shell-layout.ko.md`).
 *
 *  아래 시험들은 그 선을 지킨다. 다음 사람이 "캡컷엔 고르는 단추가 있으니 우리도"
 *  하고 손대면 여기서 걸린다. */
describe("위 띠 — 화면 비율과 내보내기", () => {
  it("지금 만드는 모양을 띠가 말한다", () => {
    renderBar({ canvas: { width: 1080, height: 1920 } });

    expect(screen.getByText("세로 9:16")).toBeVisible();
  });

  it("가로도 같은 자리에서 말한다", () => {
    renderBar({ canvas: { width: 1920, height: 1080 } });

    expect(screen.getByText("가로 16:9")).toBeVisible();
  });

  it("아직 모르면 아무것도 말하지 않는다", () => {
    // 짐작해서 `가로 16:9`라고 적어 두면 세로 초안에서 띠가 거짓말을 한다.
    renderBar();

    expect(screen.queryByText(/\d+:\d+/)).toBeNull();
  });

  it("비율은 말하기만 하고 고르게 하지 않는다", () => {
    // **이 시험이 이 자리의 이유다.** 마스터 편집본의 비율을 바꾸는 길은 서버에
    // 아예 없다 -- 비율은 초안을 만들 때 기획 화면에서 한 번 정해진다. 여기에
    // 고르는 단추를 놓으면 눌러도 아무 일이 없거나, 기획 화면의 체크와 **두 벌**이
    // 된다. 캡컷과 똑같이 생긴 자리에 없는 기능을 걸어 두면 배치가 거짓말을 한다.
    renderBar({ canvas: { width: 1920, height: 1080 } });

    const ratio = screen.getByText("가로 16:9");
    expect(ratio.closest("button")).toBeNull();
    expect(ratio.closest("a")).toBeNull();
  });

  it("내보내기로 가는 문은 띠 안에 하나뿐이다", () => {
    // 캡컷은 내보내기를 위 툴바 오른쪽 끝에 둔다. 우리는 그 일을 이미 단계 넷의
    // `확인과 내보내기`가 한다. 띠에 단추를 하나 더 놓으면 **같은 화면으로 가는
    // 문이 둘**이 되고, owner를 막았던 그 문제 -- "다음에 할 일로 보이는 것이
    // 여러 개" -- 를 띠에서 되풀이한다.
    renderBar();

    expect(screen.getAllByRole("button", { name: /내보내기/ })).toHaveLength(1);
  });
});

/** owner(2026-08-27): "심지어 프로젝트 메뉴나 다른메뉴에 들어가면 다시 설정 버튼을
 *  누르지 않는이상 뒤로가기가 안되"
 *
 *  실측으로 확인: `/projects`에 가면 `이전 화면` 단추가 **아예 사라졌다**. 브라우저
 *  이력은 4개나 있었는데도.
 *
 *  원인은 전체 메뉴의 세 항목이 **맨 `<a href>`**여서 페이지를 통째로 새로
 *  로드했기 때문이다. 그러면 앱이 들고 있던 이력이 날아가고 `이전 화면`이 설 자리를
 *  잃는다. **설정만 정상이었던 이유**도 같다 -- 그것만 앱 안에서 이동하는 콜백이었다.
 *
 *  여기서 지키는 것은 **앱 안에서 이동한다**이다. 주소는 그대로 두되(사람이
 *  북마크하는 계약) 이동은 라우터가 맡는다. */
describe("전체 메뉴는 앱 안에서 이동한다", () => {
  it("전역 화면으로 갈 때 페이지를 통째로 새로 열지 않는다", () => {
    const onNavigateGlobal = vi.fn();
    renderBar({ onNavigateGlobal });

    for (const [label, destination] of [["프로젝트", "projects"], ["미디어", "library"], ["촬영본 정리", "footage"]] as const) {
      // 고르면 메뉴가 닫히는 것이 정상이라 매번 다시 연다.
      fireEvent.click(screen.getByRole("button", { name: "전체 메뉴" }));
      const menu = screen.getByRole("navigation", { name: "전체 메뉴" });
      const link = within(menu).getByRole("link", { name: label });
      // 주소는 그대로 남는다 -- 새 창에서 열기와 북마크가 계속 되어야 한다.
      expect(link).toHaveAttribute("href", `/${destination}`);
      fireEvent.click(link);
      expect(onNavigateGlobal).toHaveBeenCalledWith(destination);
      expect(screen.queryByRole("navigation", { name: "전체 메뉴" })).toBeNull();
    }
    expect(onNavigateGlobal).toHaveBeenCalledTimes(3);
  });
});

/** owner(2026-08-27): "그리고 편집기 화면 바로가기가 없고"
 *
 *  `/projects`·`/library`·`/footage`에서는 위 띠에 단계 단추가 안 나온다
 *  (프로젝트에 매이지 않은 화면이라 `hasProject`가 false다). 그래서 **편집기로
 *  돌아갈 길이 없었다** -- 프로젝트 목록에서 카드를 다시 찾아 눌러야 했다.
 *
 *  캡컷도 편집기가 중심이다. 마지막으로 편집하던 곳으로 한 번에 돌아가는 단추를
 *  위 띠에 둔다(owner 결정 2026-08-27). 돌아갈 곳을 모르면 만들지 않는다 --
 *  없는 길을 흉내 내면 눌렀을 때 빈 화면이 뜬다. */
describe("위 띠 — 편집기로 돌아가기", () => {
  it("돌아갈 편집본이 있으면 한 번에 간다", () => {
    const onResumeEditor = vi.fn();
    renderBar({ projects: [], projectId: "", section: "library", onResumeEditor });

    fireEvent.click(screen.getByRole("button", { name: "편집기로 돌아가기" }));

    expect(onResumeEditor).toHaveBeenCalledOnce();
  });

  it("돌아갈 곳을 모르면 단추를 만들지 않는다", () => {
    renderBar({ projects: [], projectId: "", section: "library" });

    expect(screen.queryByRole("button", { name: "편집기로 돌아가기" })).toBeNull();
  });

  it("이미 프로젝트 안이면 단계 단추가 그 일을 하므로 두지 않는다", () => {
    // 같은 곳으로 가는 문이 둘이 되면 owner를 막았던 문제를 띠에서 되풀이한다.
    renderBar({ onResumeEditor: vi.fn() });

    expect(screen.queryByRole("button", { name: "편집기로 돌아가기" })).toBeNull();
    expect(screen.getByRole("button", { name: "편집" })).toBeVisible();
  });
});
