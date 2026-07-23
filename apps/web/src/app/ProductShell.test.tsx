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

    await router.navigate({ to: "/projects/first/home" });
    await screen.findByTestId("product-home");
    await router.navigate({ to: "/projects/first/editor", search: { session_id: "session-a" } });
    await screen.findByRole("region", { name: "편집 작업판" });
    expect(document.querySelector('[data-slot="sidebar"]')).toHaveAttribute("data-state", "collapsed");
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

  it("shows the latest local voice readiness without offering a mutation", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    vi.spyOn(api, "listVoiceSamples").mockResolvedValue([
      { asset_id: "voice_001", asset_type: "voice_sample_audio", storage_uri: "local://voice_001.wav" },
    ]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue({
      session_id: "session_001", project_id: "first", timeline_id: "timeline_001", session_revision: 1, history: [],
      segments: [{ segment_id: "segment_001", caption_text: "안녕하세요", start_sec: 0, end_sec: 1, cut_action: "keep", review_required: false, broll_override: null, visual_overlays: [], music_override: null, tts_replacement: null }],
    });
    vi.spyOn(api, "listTtsCandidates").mockResolvedValue({ candidates: [
      { candidate_id: "candidate_approved", project_id: "first", segment_id: "segment_001", asset_id: "tts_001", source_text: "안녕하세요", technical_status: "accepted", operator_review_status: "approved", created_at: "2026-07-23T00:00:00Z" },
      { candidate_id: "candidate_pending", project_id: "first", segment_id: "segment_001", asset_id: "tts_002", source_text: "안녕하세요", technical_status: "accepted", operator_review_status: "pending", created_at: "2026-07-23T00:00:00Z" },
    ] });
    const register = vi.spyOn(api, "registerVoiceSample");
    const upload = vi.spyOn(api, "uploadVoiceSample");
    const generate = vi.spyOn(api, "generateTtsCandidate");
    const review = vi.spyOn(api, "reviewTtsCandidate");
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/settings/ai-privacy"] }));
    render(<AppRouter router={router} />);

    expect(await screen.findByRole("region", { name: "내 목소리 준비 상태" })).toBeTruthy();
    expect(screen.getByText("저장한 내 목소리 1개")).toBeTruthy();
    expect(screen.getByText("들어 보고 승인한 후보 1개")).toBeTruthy();
    expect(screen.getByText("듣기 검수가 필요한 후보 1개")).toBeTruthy();
    expect(screen.getByText("음성 샘플 추가, 후보 만들기, 듣기 검수는 이 화면에서 변경할 수 없어요.")).toBeTruthy();
    expect(register).not.toHaveBeenCalled();
    expect(upload).not.toHaveBeenCalled();
    expect(generate).not.toHaveBeenCalled();
    expect(review).not.toHaveBeenCalled();
  });

  it("keeps the settings page usable when local voice readiness cannot be read", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    vi.spyOn(api, "listVoiceSamples").mockRejectedValue(new Error("local read failed"));
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/settings/ai-privacy"] }));
    render(<AppRouter router={router} />);

    expect(await screen.findByText("음성 준비 상태를 불러오지 못했어요. 편집 화면에서 다시 확인해 주세요.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "이 기기에서만 처리: 켜짐" })).toBeTruthy();
  });
});
