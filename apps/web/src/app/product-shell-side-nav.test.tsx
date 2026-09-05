import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";

import { ProductShell } from "./ProductShell";

afterEach(cleanup);

/** **왼쪽 세로 메뉴**(owner 지시 2026-09-05: "왼쪽 세로 메뉴 만들어").
 *
 *  2026-08-21에 왼쪽 기둥을 없애고 상단 띠 하나로 모았는데, 2026-09-05에
 *  캡컷과 다시 대조해 보니 캡컷은 첫 화면 왼쪽에 메뉴가 **상시** 보인다
 *  (`홈`·`AI로 만들기`·`템플릿`… 12항목). 우리 이동 수단은 상단의 접힌
 *  `전체 메뉴` 하나뿐이라, 자료실·촬영본이 한 번 접힌 뒤에 있었다.
 *
 *  **캡컷에 있는 항목을 흉내 내지 않는다**(§2.1). 우리에게 실제로 있는
 *  네 자리만 놓는다: 프로젝트 · 자료실 · 촬영본 정리 · 설정.
 */
const base = {
  projectId: "project-a",
  projects: [{ project_id: "project-a", name: "A" }],
  onNavigate: vi.fn(),
  onOpenSettings: vi.fn(),
  onBack: undefined,
  canvas: undefined,
  navigation: undefined,
};

describe("왼쪽 세로 메뉴", () => {
  it("편집기 밖 화면에서는 네 자리를 상시 보여 준다", () => {
    render(<ProductShell {...base} section="library" onNavigateGlobal={vi.fn()}>내용</ProductShell>);

    const nav = screen.getByRole("navigation", { name: "화면 이동" });
    expect(within(nav).getByRole("link", { name: "프로젝트" })).toBeVisible();
    expect(within(nav).getByRole("link", { name: "자료실" })).toBeVisible();
    expect(within(nav).getByRole("link", { name: "촬영본 정리" })).toBeVisible();
    expect(within(nav).getByRole("button", { name: "설정" })).toBeVisible();
  });

  it("지금 보고 있는 자리를 표시한다", () => {
    render(<ProductShell {...base} section="library" onNavigateGlobal={vi.fn()}>내용</ProductShell>);

    const nav = screen.getByRole("navigation", { name: "화면 이동" });
    expect(within(nav).getByRole("link", { name: "자료실" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "프로젝트" })).not.toHaveAttribute("aria-current");
  });

  /** **편집기에는 두지 않는다.** 편집기 왼쪽은 이미 편집 도구 띠가 쓰고 있고
   *  (미디어·오디오·텍스트·캡션·전환), 캡컷도 편집기에서는 그 자리를 편집
   *  도구에 내준다. 두 줄이 나란히 서면 어느 쪽이 화면 이동인지 알 수 없다. */
  it("편집기에서는 편집 도구 띠에 자리를 내준다", () => {
    render(<ProductShell {...base} section="editing" onNavigateGlobal={vi.fn()}>내용</ProductShell>);

    expect(screen.queryByRole("navigation", { name: "화면 이동" })).toBeNull();
  });

  it("이동을 앱 안에서 한다 -- 페이지를 통째로 새로 열지 않는다", () => {
    // 2026-08-27 owner 신고와 같은 사고를 막는다: 맨 `<a href>`로 두면
    // 페이지가 새로 열리고 그때 `이전 화면` 단추가 아예 사라졌다.
    const onNavigateGlobal = vi.fn();
    render(<ProductShell {...base} section="home" onNavigateGlobal={onNavigateGlobal}>내용</ProductShell>);

    const nav = screen.getByRole("navigation", { name: "화면 이동" });
    within(nav).getByRole("link", { name: "자료실" }).click();

    expect(onNavigateGlobal).toHaveBeenCalledWith("library");
  });
});
