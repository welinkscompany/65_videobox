import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { TopBar } from "./TopBar";

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
  it("만드는 순서대로 단계를 늘어놓는다", () => {
    renderBar();

    const stages = within(screen.getByRole("navigation", { name: "프로젝트 단계" }))
      .getAllByRole("button")
      .map((button) => button.textContent);

    // 이야기(대본) → 재료 → 편집 → 확인과 내보내기. 일이 실제로 흐르는 순서다.
    expect(stages).toEqual(["이야기", "재료", "편집", "확인과 내보내기"]);
  });

  it("지금 어느 단계인지 띠가 말한다", () => {
    renderBar({ section: "editing" });

    expect(screen.getByRole("button", { name: "편집" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "재료" })).not.toHaveAttribute("aria-current");
  });

  it("단계를 누르면 그 단계로 간다", () => {
    const onNavigate = vi.fn();
    renderBar({ onNavigate });

    fireEvent.click(screen.getByRole("button", { name: "재료" }));

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

  it("설정으로 가는 길이 남아 있다", () => {
    // 왼쪽 기둥이 없어지면서 여기 있던 것이 조용히 사라지면 안 된다.
    const onOpenSettings = vi.fn();
    renderBar({ onOpenSettings });

    fireEvent.click(screen.getByRole("button", { name: "설정" }));

    expect(onOpenSettings).toHaveBeenCalled();
  });

  it("프로젝트가 아직 없으면 단계를 보여 주지 않는다", () => {
    // 갈 수 없는 곳을 띠에 띄워 두면 눌렀을 때 빈 화면이 뜬다.
    renderBar({ projects: [], projectId: "" });

    expect(screen.queryByRole("navigation", { name: "프로젝트 단계" })).toBeNull();
    expect(screen.getByRole("button", { name: "설정" })).toBeVisible();
  });
});
