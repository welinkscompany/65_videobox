import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryHistory } from "@tanstack/react-router";

import { api } from "../api";
import { AppRouter, ProjectCatalog, createAppRouter } from "./AppRouter";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

/** **첫 화면이 프로젝트마다 요약을 따로 불렀다** (2026-09-05 실측).
 *
 *  owner: "영상 만들 때 어느 화면이 느린지 다시 재봐".
 *  재 보니 프로젝트 목록에서 요청이 **37개**, 그중 36개가 카드마다 부르는
 *  `workspace-summary`였다(평균 310ms, 첫 요청부터 마지막 응답까지 **1.56초**).
 *  **프로젝트가 늘수록 그대로 늘어난다** -- owner는 지금 36개다.
 *
 *  화면에 보이는 카드만 부른다. 첫 화면에 보이는 것은 대여섯 개뿐이다.
 */
function observerSpy() {
  const observed: Element[] = [];
  class FakeObserver {
    constructor(private readonly callback: IntersectionObserverCallback) {}
    observe(element: Element) { observed.push(element); }
    disconnect() {}
    unobserve() {}
    takeRecords() { return []; }
    // 시험이 원할 때 "보인다"고 알린다.
    reveal(element: Element) {
      this.callback([{ isIntersecting: true, target: element } as IntersectionObserverEntry], this as never);
    }
  }
  return { FakeObserver, observed };
}

describe("프로젝트 목록의 요약 부르기", () => {
  /** **첫 화면에 들어갈 만큼(열두 개)은 무조건 부른다.** 관찰자에만 기대면
   *  그것이 안 도는 환경에서 화면이 "상태 확인 중"으로 비어 버린다 -- 실제로
   *  그렇게 나오는 창에서 확인했다. 그 뒤 카드는 보일 때만 부른다. */
  it("첫 화면 뒤의 카드는 보일 때까지 요약을 부르지 않는다", async () => {
    const { FakeObserver } = observerSpy();
    vi.stubGlobal("IntersectionObserver", FakeObserver);
    const projects = Array.from({ length: 30 }, (_, index) => ({
      project_id: `project-${index}`, name: `프로젝트 ${index}`, status: "draft",
      root_storage_uri: `local://projects/project-${index}`,
    }));
    vi.spyOn(api, "listProjects").mockResolvedValue(projects as never);
    const summary = vi.spyOn(api, "getProjectWorkspaceSummary").mockResolvedValue({} as never);

    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);
    await screen.findByText("프로젝트 0");
    await new Promise((resolve) => setTimeout(resolve, 50));

    // 서른 개인데 열두 개만 부른다 -- 예전에는 서른 번 다 불렀다.
    expect(summary.mock.calls.length).toBeLessThanOrEqual(12);
    expect(summary).toHaveBeenCalledWith("project-0");
    expect(summary).not.toHaveBeenCalledWith("project-29");
  });

  it("관찰자를 못 쓰는 환경에서는 그냥 부른다 -- 화면이 비어 보이면 안 된다", async () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    vi.spyOn(api, "listProjects").mockResolvedValue([
      { project_id: "project-a", name: "프로젝트 A", status: "draft", root_storage_uri: "local://a" },
    ] as never);
    const summary = vi.spyOn(api, "getProjectWorkspaceSummary").mockResolvedValue({} as never);

    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
    render(<AppRouter router={router} />);

    await waitFor(() => expect(summary).toHaveBeenCalledWith("project-a"));
  });
});
