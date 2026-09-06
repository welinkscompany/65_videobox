import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { ProductShell } from "./ProductShell";

afterEach(cleanup);

/** **`내 자산` 구역**(owner 승인 2026-09-04
 *  `docs/decisions/2026-09-04-capcut-shell-with-my-assets.ko.md` §2,
 *  착수 지시 2026-09-07).
 *
 *  캡컷 왼쪽 기둥의 `AI로 만들기` 자리에 우리는 `내 자산`을 놓는다. 제품의
 *  차이가 거기 있기 때문이다 -- 캡컷은 만들 때마다 다시 올리고, 우리는 한 번
 *  넣은 걸 계속 다시 쓴다.
 *
 *  승인 문서는 `내 B-roll`이라고 적었지만 **낱말은 나중 승인을 따른다**:
 *  2026-09-07에 화면에서 `B-roll`을 없애고 `영상`으로 통일하는 것이 승인됐다
 *  (`109e75b19`). 자료실 분류 목록도 이미 `영상`이다.
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

function sideNav() {
  return screen.getByRole("navigation", { name: "화면 이동" });
}

describe("왼쪽 세로 메뉴의 `내 자산` 구역", () => {
  it("승인된 세 자리를 한 구역으로 모아 보여 준다", () => {
    render(<ProductShell {...base} section="library" onNavigateGlobal={vi.fn()}>내용</ProductShell>);

    const group = within(sideNav()).getByRole("group", { name: "내 자산" });
    expect(within(group).getByRole("link", { name: /^내 영상/ })).toBeVisible();
    expect(within(group).getByRole("button", { name: /^내 목소리/ })).toBeVisible();
    expect(within(group).getByRole("link", { name: /^음악·효과음/ })).toBeVisible();
  });

  /** 새 화면을 만들지 않는다. 자료실이 이미 종류로 거를 수 있고, 의미검색·
   *  휴지통·사용처 검사가 전부 거기 붙어 있다. 그래서 이 자리는 **자료실을
   *  종류를 정한 채로 여는 문**이다. */
  it("자료실을 종류를 정한 채로 연다", () => {
    const onNavigateGlobal = vi.fn();
    render(<ProductShell {...base} section="home" onNavigateGlobal={onNavigateGlobal}>내용</ProductShell>);

    const group = within(sideNav()).getByRole("group", { name: "내 자산" });
    fireEvent.click(within(group).getByRole("link", { name: /^내 영상/ }));
    expect(onNavigateGlobal).toHaveBeenCalledWith("library", "broll");

    fireEvent.click(within(group).getByRole("link", { name: /^음악·효과음/ }));
    expect(onNavigateGlobal).toHaveBeenLastCalledWith("library", "audio");
  });

  /** 주소는 사람이 북마크하는 계약이다. 앱 안 이동과 별개로 남겨 둔다. */
  it("주소를 남겨 새 창으로도 열 수 있다", () => {
    render(<ProductShell {...base} section="library" onNavigateGlobal={vi.fn()}>내용</ProductShell>);

    const group = within(sideNav()).getByRole("group", { name: "내 자산" });
    expect(within(group).getByRole("link", { name: /^내 영상/ })).toHaveAttribute("href", "/library?kind=broll");
    expect(within(group).getByRole("link", { name: /^음악·효과음/ })).toHaveAttribute("href", "/library?kind=audio");
  });

  /** **한 자리만 "여기"라고 말한다.** 자료실 분류 목록에서 `전체`가 두 군데에
   *  남아 둘 다 선택돼 보였던 사고(2026-08-23)를 세로 메뉴에서 되풀이하지
   *  않는다. */
  it("자료실과 내 자산 중 한 자리만 지금 자리로 표시한다", () => {
    const { rerender } = render(<ProductShell {...base} section="library" onNavigateGlobal={vi.fn()}>내용</ProductShell>);
    expect(within(sideNav()).getByRole("link", { name: "자료실" })).toHaveAttribute("aria-current", "page");
    expect(within(sideNav()).getByRole("link", { name: /^내 영상/ })).not.toHaveAttribute("aria-current");

    rerender(<ProductShell {...base} section="library" assetKind="broll" onNavigateGlobal={vi.fn()}>내용</ProductShell>);
    expect(within(sideNav()).getByRole("link", { name: /^내 영상/ })).toHaveAttribute("aria-current", "page");
    expect(within(sideNav()).getByRole("link", { name: "자료실" })).not.toHaveAttribute("aria-current");
  });

  /** **눌렀는데 아무 일도 안 일어난다**가 이 저장소가 어제 고친 결함이다.
   *  목소리 보관함 뒷단은 아직 다른 사람이 만들고 있으므로, 자리는 두되
   *  못 쓴다는 것을 창작자 말로 먼저 말한다. */
  it("내 목소리는 아직 못 쓴다는 것을 눌러 보기 전에 말한다", () => {
    const onNavigateGlobal = vi.fn();
    render(<ProductShell {...base} section="library" onNavigateGlobal={onNavigateGlobal}>내용</ProductShell>);

    const group = within(sideNav()).getByRole("group", { name: "내 자산" });
    const voice = within(group).getByRole("button", { name: /^내 목소리/ });
    expect(voice).toHaveAttribute("aria-disabled", "true");
    expect(within(voice).getByText("준비 중")).toBeVisible();

    fireEvent.click(voice);
    expect(onNavigateGlobal).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("아직 준비 중이에요");
  });

  it("편집기에서는 내 자산 구역도 함께 접힌다", () => {
    render(<ProductShell {...base} section="editing" onNavigateGlobal={vi.fn()}>내용</ProductShell>);
    expect(screen.queryByRole("group", { name: "내 자산" })).toBeNull();
  });
});
