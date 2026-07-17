import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryHistory } from "@tanstack/react-router";

import { api } from "../api";
import { AppRouter, createAppRouter, ProjectCatalog } from "./AppRouter";

beforeEach(() => { vi.stubGlobal("scrollTo", vi.fn()); vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false })); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.localStorage.clear(); });

const projects = [
  { project_id: "first", name: "첫 번째 영상", status: "active", root_storage_uri: "local://first" },
  { project_id: "second", name: "두 번째 영상", status: "active", root_storage_uri: "local://second" },
];

describe("product shell", () => {
  it("shows creator navigation, a project switcher, and an action-only home", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/home"] }));
    render(<AppRouter router={router} />);

    await screen.findByRole("navigation", { name: "영상 제작" });
    expect(screen.getAllByRole("button", { name: "새 영상 만들기" }).length).toBeGreaterThan(0);
    expect(screen.getByText("작업 중인 초안 계속하기")).toBeTruthy();
    expect(screen.getByText("최근 완성본")).toBeTruthy();
    expect(screen.queryByText(/provider|job metric/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /두 번째 영상/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/second/home"));
  });

  it("persists a working appearance setting and only exposes local privacy choices", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/settings/appearance"] }));
    render(<AppRouter router={router} />);

    const compact = await screen.findByRole("button", { name: "조밀한 화면: 꺼짐" });
    fireEvent.click(compact);
    expect(window.localStorage.getItem("videobox.settings")).toContain("compact");
    expect(screen.getByText("설정은 이 기기에서만 관리됩니다.")).toBeTruthy();
    expect(screen.queryByText(/billing|team|account/i)).toBeNull();
  });
});
