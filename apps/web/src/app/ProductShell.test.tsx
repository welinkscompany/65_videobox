import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryHistory } from "@tanstack/react-router";

import { api } from "../api";
import { AppRouter, createAppRouter, ProjectCatalog } from "./AppRouter";

beforeEach(() => { vi.stubGlobal("scrollTo", vi.fn()); vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false })); vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.localStorage.clear(); });

const projects = [
  { project_id: "first", name: "첫 번째 영상", status: "active", root_storage_uri: "local://first" },
  { project_id: "second", name: "두 번째 영상", status: "active", root_storage_uri: "local://second" },
];

describe("product shell", () => {
  it("starts collapsed only for the canonical editor and allows an explicit reopen", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue({ project_id: "first", session_id: "session-a", timeline_id: "timeline-a", session_revision: 1, timeline_version: "v1", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 1 }, tracks: [], captions: [], gap_slots: [], source_status: { status: "current", source_session_id: "session-a", source_session_revision: 1 }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: "session-a", source_session_revision: 1 } } as never);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects/first/editor?session_id=session-a"] }));
    render(<AppRouter router={router} />);
    await screen.findByRole("region", { name: "편집 작업판" });
    const sidebar = document.querySelector('[data-slot="sidebar"]');
    expect(sidebar).toHaveAttribute("data-state", "collapsed");
    fireEvent.click(screen.getByRole("button", { name: "사이드바 접기" }));
    expect(sidebar).toHaveAttribute("data-state", "expanded");
  });

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
