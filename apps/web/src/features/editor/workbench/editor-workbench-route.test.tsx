import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { startTransition, Suspense, useState } from "react";

import { ApiConflictError, api } from "../../../api";
import { EditorWorkbenchRoute } from "./EditorWorkbenchRoute";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const manifest = (projectId: string, sessionId: string) => ({ project_id: projectId, session_id: sessionId, timeline_id: `timeline-${sessionId}`, session_revision: 1, timeline_version: "v1", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 1 }, tracks: [], captions: [], gap_slots: [], source_status: { status: "current", source_session_id: sessionId, source_session_revision: 1 }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: sessionId, source_session_revision: 1 } });

const narrationManifest = (revision: number, startSec = 0) => ({
  ...manifest("project-a", "session-a"),
  session_revision: revision,
  output: { ...manifest("project-a", "session-a").output, duration_sec: 5 },
  source_status: { status: "current" as const, source_session_id: "session-a", source_session_revision: revision },
  tracks: [{
    track_id: "narration",
    track_type: "narration" as const,
    clips: [{
      clip_id: "n-1", segment_id: "segment-1", clip_type: "narration" as const,
      asset_id: null, asset_uri: null, start_sec: startSec, end_sec: 5,
      media_controls: {},
    }],
  }],
});

const twoNarrationManifest = (revision: number) => ({
  ...narrationManifest(revision),
  output: { ...narrationManifest(revision).output, duration_sec: 2 },
  tracks: [{
    track_id: "narration",
    track_type: "narration" as const,
    clips: [
      { clip_id: "n-1", segment_id: "segment-1", clip_type: "narration" as const, asset_id: null, asset_uri: null, start_sec: 0, end_sec: 1, media_controls: {} },
      { clip_id: "n-2", segment_id: "segment-2", clip_type: "narration" as const, asset_id: null, asset_uri: null, start_sec: 1, end_sec: 2, media_controls: {} },
    ],
  }],
});

const captionManifest = (revision: number, text = "원래 자막") => ({
  ...narrationManifest(revision),
  captions: [{
    segment_id: "segment-1", caption_id: "caption-1", placement_id: "caption:segment-1", text, start_sec: 0, end_sec: 5,
    style: { font_family: "Pretendard", font_size_px: 42, text_color: "#ffffff", outline_color: "#000000", outline_width_px: 2, background_color: "#00000000", position_x_percent: 50, position_y_percent: 85, horizontal_align: "center" as const, safe_area_enabled: true, shadow_blur_px: 0 },
  }],
});

const broll = {
  asset_id: "broll-1",
  asset_type: "broll_video",
  storage_uri: "file:///broll-1.mp4",
  created_at: "2026-07-23T00:00:00Z",
  metadata: { title: "B-roll 1", duration_seconds: 5, analysis_status: "succeeded", review_required: false },
};

const music = {
  library_asset_id: "library-bgm-1",
  asset_id: "starter-bgm-1",
  media_type: "music" as const,
  duration_seconds: 12,
  version: "v1",
  verified: true,
  available: true,
  tags: [],
  source: "Starter",
  creator: "VideoBox",
  official_license_url: "https://license.invalid/bgm-1",
  attribution_required: false,
  attribution_text: "",
};

const directorProposal = (proposalId = "proposal-1") => ({
  proposal_id: proposalId,
  revision_code: "P01",
  revision: 1,
  base_session_revision: 1,
  asset_index_revision: 1,
  source_session_id: "session-a",
  target_segment_ids: ["segment-1"],
  source_script_segment_ids: ["segment-1"],
  status: "ready",
  diff: {},
  expires_at: null,
  candidates: [{ candidate_id: "candidate-1", visible_reference_code: "P01-B-01", media_type: "broll", asset_id: "broll-1", library_asset_id: null, reason_chips: [], scores: {}, availability: "available", review_status: "ready", preview_uri: "https://preview.invalid/candidate-1.mp4", controls: {}, expected_content_sha256: null, media_revision: "r1", canonical_metadata: {}, license_policy: "local", warning_provenance: [] }],
});

function pointer(target: Element, type: string, clientX: number) {
  fireEvent(target, new MouseEvent(type, { bubbles: true, cancelable: true, clientX }));
}

async function openAssetBrowser() {
  fireEvent.click(await screen.findByRole("button", { name: "자산과 대본" }));
  return screen.findByRole("dialog", { name: "자산과 대본" });
}

describe("EditorWorkbenchRoute", () => {
  beforeEach(() => {
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(narrationManifest(1) as never);
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([] as never);
    vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [] } as never);
  });

  it("materializes verified BGM before one current-revision music command while saving disables apply", async () => {
    let resolveMaterialized!: (value: { asset_id: string }) => void;
    let resolveApply!: (value: unknown) => void;
    const materialize = vi.spyOn(api, "materializeMediaLibraryAsset")
      .mockImplementation(() => new Promise((resolve) => { resolveMaterialized = resolve; }) as never);
    const apply = vi.spyOn(api, "updateEditingSessionMusicOverride")
      .mockImplementation(() => new Promise((resolve) => { resolveApply = resolve; }) as never);
    vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [music] } as never);

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await openAssetBrowser();
    expect(await screen.findByRole("button", { name: "BGM 1 적용" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const applyButton = screen.getByRole("button", { name: "BGM 1 적용" });
    fireEvent.click(applyButton);

    await waitFor(() => expect(materialize).toHaveBeenCalledWith("library-bgm-1", "project-a"));
    expect(apply).not.toHaveBeenCalled();
    expect(applyButton).toBeDisabled();
    await act(async () => { resolveMaterialized({ asset_id: "materialized-bgm" }); });
    await waitFor(() => expect(apply).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
      asset_id: "materialized-bgm",
      media_controls: undefined,
      expected_revision: 1,
    }));
    expect(apply).toHaveBeenCalledTimes(1);
    await act(async () => { resolveApply({}); });
  });

  it("does not call any media endpoint when library materialization fails and refreshes safely", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(narrationManifest(1) as never);
    vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [music] } as never);
    vi.spyOn(api, "materializeMediaLibraryAsset").mockRejectedValue(new Error("disk full"));
    const updateMusic = vi.spyOn(api, "updateEditingSessionMusicOverride");
    const updateSfx = vi.spyOn(api, "updateEditingSessionSfxOverride");
    const updateBroll = vi.spyOn(api, "updateEditingSessionBroll");

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await openAssetBrowser();
    await screen.findByRole("button", { name: "BGM 1 적용" });
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    fireEvent.click(screen.getByRole("button", { name: "BGM 1 적용" }));

    expect(await screen.findByText("변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(updateMusic).not.toHaveBeenCalled();
    expect(updateSfx).not.toHaveBeenCalled();
    expect(updateBroll).not.toHaveBeenCalled();
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });

  it("applies B-roll through the current revision fence without materializing it", async () => {
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([broll] as never);
    const materialize = vi.spyOn(api, "materializeMediaLibraryAsset");
    const apply = vi.spyOn(api, "updateEditingSessionBroll").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await openAssetBrowser();
    await screen.findByRole("button", { name: "B-roll 1 적용" });
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    fireEvent.click(screen.getByRole("button", { name: "B-roll 1 적용" }));

    await waitFor(() => expect(apply).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
      asset_id: "broll-1",
      media_controls: undefined,
      expected_revision: 1,
    }));
    expect(materialize).not.toHaveBeenCalled();
  });

  it("ignores a stale A asset load after route navigation to B", async () => {
    let resolveA!: (value: typeof broll[]) => void;
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => Promise.resolve(manifest(projectId, sessionId)) as never);
    vi.spyOn(api, "listBrollAssets").mockImplementation((projectId) => projectId === "project-a"
      ? new Promise((resolve) => { resolveA = resolve; }) as never
      : Promise.resolve([{ ...broll, asset_id: "broll-b", metadata: { ...broll.metadata, title: "B 자산" } }] as never));

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    await openAssetBrowser();
    expect(await screen.findByRole("button", { name: "B 자산 적용" })).toBeVisible();

    await act(async () => { resolveA([broll]); });
    expect(screen.queryByRole("button", { name: "B-roll 1 적용" })).toBeNull();
    expect(screen.getByRole("button", { name: "B 자산 적용" })).toBeVisible();
  });

  it("does not apply a materialized A library asset after navigation to B", async () => {
    let resolveMaterialized!: (value: { asset_id: string }) => void;
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => Promise.resolve(
      sessionId === "session-a" ? narrationManifest(1) : manifest(projectId, sessionId),
    ) as never);
    vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [music] } as never);
    const materialize = vi.spyOn(api, "materializeMediaLibraryAsset")
      .mockImplementation(() => new Promise((resolve) => { resolveMaterialized = resolve; }) as never);
    const updateMusic = vi.spyOn(api, "updateEditingSessionMusicOverride");
    const updateSfx = vi.spyOn(api, "updateEditingSessionSfxOverride");
    const updateBroll = vi.spyOn(api, "updateEditingSessionBroll");

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await openAssetBrowser();
    await screen.findByRole("button", { name: "BGM 1 적용" });
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    fireEvent.click(screen.getByRole("button", { name: "BGM 1 적용" }));
    await waitFor(() => expect(materialize).toHaveBeenCalledWith("library-bgm-1", "project-a"));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    await act(async () => { resolveMaterialized({ asset_id: "materialized-bgm" }); });

    expect(updateMusic).not.toHaveBeenCalled();
    expect(updateSfx).not.toHaveBeenCalled();
    expect(updateBroll).not.toHaveBeenCalled();
    expect(screen.getByText("timeline-session-b · revision 1")).toBeVisible();
    expect(screen.queryByText("변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeNull();
  });

  it("keeps the manifest editor usable when an asset list fails and gives contained retry-safe guidance", async () => {
    vi.spyOn(api, "listMediaLibraryAssets").mockRejectedValue(new Error("offline"));

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);

    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    expect(await screen.findByText("일부 자산을 불러오지 못했어요. 편집은 계속할 수 있어요. 잠시 후 다시 확인해 주세요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "n-1 클립 선택" })).toBeEnabled();
  });

  it("never displays the old A session while B is loading", async () => {
    let resolveB!: (value: ReturnType<typeof manifest>) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => sessionId === "session-a" ? Promise.resolve(manifest(projectId, sessionId)) : new Promise((resolve) => { resolveB = resolve; }));
    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(screen.queryByText("timeline-session-a · revision 1")).toBeNull();
    expect(screen.getByText("편집 내용을 불러오는 중이에요.")).toBeVisible();
    resolveB(manifest("project-b", "session-b"));
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("fails closed for missing or mismatched session identity", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(manifest("wrong-project", "session-a") as never);
    const { rerender } = render(<EditorWorkbenchRoute projectId="project-a" sessionId={null} />);
    expect(screen.getByText("편집 세션을 찾을 수 없어요. 다시 열어 주세요.")).toBeVisible();
    rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("편집 세션 정보가 일치하지 않아요. 다시 열어 주세요.")).toBeVisible();
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("commits one current-revision narration trim on release and refreshes the manifest", async () => {
    let resolveUpdate!: (value: unknown) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(narrationManifest(2, 1) as never);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds")
      .mockImplementation(() => new Promise((resolve) => { resolveUpdate = resolve; }) as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "n-1 시작 자르기" });

    pointer(trim, "pointerdown", 100);
    expect(update).not.toHaveBeenCalled();
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
      end_sec: 5,
      expected_revision: 1,
      start_sec: 1,
    });
    expect(await screen.findByText("변경 내용을 저장하고 있어요.")).toBeVisible();
    expect(trim).toBeDisabled();
    resolveUpdate({});
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("timeline-session-a · revision 2")).toBeVisible();
  });

  it("saves linked caption text through the same revision fence and refreshes the manifest", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(captionManifest(4) as never)
      .mockResolvedValueOnce(captionManifest(5, "새 자막") as never);
    const update = vi.spyOn(api, "updateEditingSessionCaption").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 4")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));
    expect(await screen.findByRole("dialog", { name: "자산과 대본" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "원래 자막 대본 선택" }));
    fireEvent.change(screen.getByRole("textbox", { name: "segment-1 자막 텍스트" }), { target: { value: "새 자막" } });
    fireEvent.click(screen.getByRole("button", { name: "자막 저장" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith("project-a", "session-a", "segment-1", { caption_text: "새 자막", expected_revision: 4 }));
    expect(await screen.findByText("timeline-session-a · revision 5")).toBeVisible();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("refreshes after a linked-caption revision conflict without retrying the caption command", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(captionManifest(4) as never)
      .mockResolvedValueOnce(captionManifest(5, "다른 변경 자막") as never);
    const update = vi.spyOn(api, "updateEditingSessionCaption").mockRejectedValue(
      new ApiConflictError({}, "/api/projects/project-a/editing-sessions/session-a/segments/segment-1/caption"),
    );

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 4")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));
    expect(await screen.findByRole("dialog", { name: "자산과 대본" })).toBeVisible();
    fireEvent.change(screen.getByRole("textbox", { name: "segment-1 자막 텍스트" }), { target: { value: "새 자막" } });
    fireEvent.click(screen.getByRole("button", { name: "자막 저장" }));

    expect(await screen.findByText("다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(update).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("timeline-session-a · revision 5")).toBeVisible();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("keeps the current view, refreshes after a revision conflict, and does not retry the command", async () => {
    let resolveRefresh!: (value: ReturnType<typeof narrationManifest>) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve as typeof resolveRefresh; }));
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds").mockRejectedValue(
      new ApiConflictError({}, "/api/projects/project-a/editing-sessions/session-a/segments/segment-1/bounds"),
    );

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    expect(await screen.findByText("다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(screen.getByText("timeline-session-a · revision 1")).toBeVisible();
    expect(update).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(update).toHaveBeenCalledTimes(1);

    resolveRefresh(narrationManifest(2, 0));
    expect(await screen.findByText("timeline-session-a · revision 2")).toBeVisible();
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("commits one complete narration reorder layout on pointer release", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(twoNarrationManifest(3) as never)
      .mockResolvedValueOnce(twoNarrationManifest(4) as never);
    const reorder = vi.spyOn(api, "reorderEditingSessionSegments").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 3")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const control = screen.getByRole("button", { name: "n-1 순서 바꾸기" });

    pointer(control, "pointerdown", 0);
    expect(reorder).not.toHaveBeenCalled();
    pointer(control, "pointermove", 200);
    pointer(control, "pointerup", 200);

    await waitFor(() => expect(reorder).toHaveBeenCalledTimes(1));
    expect(reorder).toHaveBeenCalledWith("project-a", "session-a", {
      bounds_by_id: {
        "segment-1": { start_sec: 1, end_sec: 2 },
        "segment-2": { start_sec: 0, end_sec: 1 },
      },
      expected_revision: 3,
      segment_ids: ["segment-2", "segment-1"],
    });
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });

  it("refreshes after an ordinary save failure and gives safe retry guidance", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(5) as never)
      .mockResolvedValueOnce(narrationManifest(5) as never);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds").mockRejectedValue(new Error("offline"));

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 5")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    expect(await screen.findByText("변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(update).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("ignores an old A mutation after navigating A to B to A while a new A mutation is saving", async () => {
    let resolveOldUpdate!: (value: unknown) => void;
    let resolveNewUpdate!: (value: unknown) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(manifest("project-b", "session-b") as never)
      .mockResolvedValueOnce(narrationManifest(10) as never)
      .mockResolvedValueOnce(narrationManifest(11, 1) as never);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds")
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOldUpdate = resolve; }) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNewUpdate = resolve; }) as never);

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    let track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    let trim = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 10")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    trim = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);
    await waitFor(() => expect(update).toHaveBeenCalledTimes(2));
    expect(screen.getByText("변경 내용을 저장하고 있어요.")).toBeVisible();

    await act(async () => { resolveOldUpdate({}); });
    expect(load).toHaveBeenCalledTimes(3);
    expect(screen.getByText("timeline-session-a · revision 10")).toBeVisible();
    expect(screen.getByText("변경 내용을 저장하고 있어요.")).toBeVisible();
    expect(trim).toBeDisabled();

    resolveNewUpdate({});
    await waitFor(() => expect(load).toHaveBeenCalledTimes(4));
    expect(await screen.findByText("timeline-session-a · revision 11")).toBeVisible();
    expect(screen.getByText("변경 내용을 저장했어요.")).toBeVisible();
  });

  it("keeps the committed A mutation current when an uncommitted B render is abandoned", async () => {
    let navigate!: (route: "a" | "b") => void;
    let resolveUpdate!: (value: unknown) => void;
    const never = new Promise<never>(() => undefined);
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(twoNarrationManifest(1) as never)
      .mockResolvedValueOnce(twoNarrationManifest(2) as never);
    vi.spyOn(api, "reorderEditingSessionSegments")
      .mockImplementation(() => new Promise((resolve) => { resolveUpdate = resolve; }) as never);

    function SuspendAbandonedRoute({ route }: { route: "a" | "b" }) {
      if (route === "b") throw never;
      return null;
    }

    function Harness() {
      const [route, setRoute] = useState<"a" | "b">("a");
      navigate = setRoute;
      return <Suspense fallback={<p>전환 중</p>}>
        <EditorWorkbenchRoute
          projectId={route === "a" ? "project-a" : "project-b"}
          sessionId={route === "a" ? "session-a" : "session-b"}
        />
        <SuspendAbandonedRoute route={route} />
      </Suspense>;
    }

    render(<Harness />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const reorder = screen.getByRole("button", { name: "n-1 순서 바꾸기" });
    fireEvent.keyDown(reorder, { key: "ArrowRight" });
    await waitFor(() => expect(screen.getByText("변경 내용을 저장하고 있어요.")).toBeVisible());

    act(() => {
      startTransition(() => navigate("b"));
    });
    expect(screen.getByText("timeline-session-a · revision 1")).toBeVisible();

    await act(async () => { resolveUpdate({}); });
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("timeline-session-a · revision 2")).toBeVisible();
    expect(screen.getByText("변경 내용을 저장했어요.")).toBeVisible();
    expect(reorder).not.toBeDisabled();
  });

  it("ignores an old exact-preview completion after navigating A to B to A", async () => {
    let resolveOldPreview!: (value: unknown) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(manifest("project-b", "session-b") as never)
      .mockResolvedValueOnce(narrationManifest(10) as never)
      .mockResolvedValueOnce(narrationManifest(2) as never);
    const startPreview = vi.spyOn(api, "startExactPreview")
      .mockImplementation(() => new Promise((resolve) => { resolveOldPreview = resolve; }) as never);

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "미리보기 새로 만들기" }));
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 10")).toBeVisible();

    await act(async () => { resolveOldPreview({}); });
    expect(load).toHaveBeenCalledTimes(3);
    expect(screen.getByText("timeline-session-a · revision 10")).toBeVisible();
  });

  it("adapts the recovered Eugene conversation into the dock, keeps manual edit available when blocked, and auditions a candidate through the sole PreviewStage", async () => {
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => Promise.resolve(manifest(projectId, sessionId)) as never);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [
        { message_id: "user-1", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "B-roll을 추천해 줘", proposal_id: null, metadata: {}, client_message_id: null, created_at: "now" },
        { message_id: "assistant-1", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "한 가지를 골랐어요.", proposal_id: "proposal-1", metadata: {}, client_message_id: null, created_at: "now" },
      ],
      proposal: directorProposal(), references: [],
    } as never);

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "유진과 Inspector" }));
    expect(await screen.findByText("한 가지를 골랐어요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "추천 미리 듣기" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "추천 미리 듣기" }));
    expect(document.querySelectorAll(".vb-preview-stage")).toHaveLength(1);
    expect(document.querySelectorAll(".vb-editor-right-dock audio, .vb-editor-right-dock video")).toHaveLength(0);

    vi.spyOn(api, "reloadDirectorSession").mockRejectedValueOnce(new Error("blocked"));
    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "유진과 Inspector" }));
    fireEvent.click(await screen.findByRole("button", { name: "직접 편집하기" }));
    expect(await screen.findByRole("button", { name: "자산과 대본" })).toBeVisible();
  });

  it("preflights then batch-applies only the current route proposal and ignores an old A send after navigation", async () => {
    let resolveOldSend!: (value: unknown) => void;
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => Promise.resolve(manifest(projectId, sessionId)) as never);
    vi.spyOn(api, "reloadDirectorSession").mockImplementation((projectId, sessionId) => Promise.resolve({
      conversation: { conversation_id: `conversation-${sessionId}`, project_id: String(projectId), session_id: String(sessionId) }, messages: [], proposal: directorProposal(`proposal-${sessionId}`), references: [],
    }) as never);
    const prepared = vi.spyOn(api, "prepareDirectorMessage").mockImplementation(() => ({ clientMessageId: "stable", send: () => new Promise((resolve) => { resolveOldSend = resolve; }) }) as never);
    const preflight = vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal").mockResolvedValue({} as never);
    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "유진과 Inspector" }));
    fireEvent.change(await screen.findByLabelText("유진에게 요청하기"), { target: { value: "A 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await waitFor(() => expect(prepared).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    await act(async () => { resolveOldSend({ kind: "exchange", exchange: { user_message: {}, assistant_message: { proposal_id: "proposal-session-a", text: "stale A" } } }); });
    expect(screen.queryByText("stale A")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "유진과 Inspector" }));
    fireEvent.click(await screen.findByRole("button", { name: "선택한 추천 적용" }));
    await waitFor(() => expect(preflight).toHaveBeenCalledWith("project-b", "proposal-session-b"));
    expect(batchApply).toHaveBeenCalledWith("project-b", "proposal-session-b", { candidate_ids: ["candidate-1"], expected_revision: 1 });
  });

  it("keeps reload read-only until the creator explicitly starts Eugene, then creates one conversation and proposal", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({ conversation: null, messages: [], proposal: null, references: [] } as never);
    const createConversation = vi.spyOn(api, "createDirectorConversation").mockResolvedValue({ conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" } as never);
    const createProposal = vi.spyOn(api, "createDirectorProposal").mockResolvedValue(directorProposal() as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    expect(createConversation).not.toHaveBeenCalled();
    expect(createProposal).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "유진과 Inspector" }));
    fireEvent.click(await screen.findByRole("button", { name: "유진에게 추천받기" }));

    await waitFor(() => expect(createConversation).toHaveBeenCalledWith("project-a", { session_id: "session-a" }));
    expect(createConversation).toHaveBeenCalledTimes(1);
    expect(createProposal).toHaveBeenCalledWith("project-a", { session_id: "session-a" });
    expect(createProposal).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("textbox", { name: "유진에게 요청하기" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "선택한 추천 적용" })).toBeEnabled();
  });

  it("does not repeat an explicit apply while its preflight and batch apply are in flight", async () => {
    let resolvePreflight!: (value: { status: string }) => void;
    let resolveBatch!: (value: unknown) => void;
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" }, messages: [], proposal: directorProposal(), references: [],
    } as never);
    const preflight = vi.spyOn(api, "preflightDirectorProposal").mockImplementation(() => new Promise((resolve) => { resolvePreflight = resolve; }) as never);
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal").mockImplementation(() => new Promise((resolve) => { resolveBatch = resolve; }) as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "유진과 Inspector" }));
    const apply = await screen.findByRole("button", { name: "선택한 추천 적용" });
    fireEvent.click(apply);
    fireEvent.click(apply);
    await waitFor(() => expect(preflight).toHaveBeenCalledTimes(1));
    expect(apply).toBeDisabled();
    expect(batchApply).not.toHaveBeenCalled();
    await act(async () => { resolvePreflight({ status: "ready" }); });
    await waitFor(() => expect(batchApply).toHaveBeenCalledTimes(1));
    await act(async () => { resolveBatch({}); });
    expect(batchApply).toHaveBeenCalledTimes(1);
  });

  it("locks the composer while Eugene is sending and reuses its client ID only for the explicit Retry-After retry", async () => {
    let resolveSend!: (value: { kind: "in_progress"; retryAfterSeconds: number }) => void;
    const retry = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: { message_id: "user-2", text: "A 요청" }, assistant_message: { message_id: "assistant-2", proposal_id: null, text: "다시 확인했어요." } } });
    const prepare = vi.spyOn(api, "prepareDirectorMessage").mockImplementation(() => ({ clientMessageId: "stable-a", send: () => new Promise((resolve) => { resolveSend = resolve; }), retry }) as never);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" }, messages: [], proposal: null, references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "유진과 Inspector" }));
    const composer = await screen.findByRole("textbox", { name: "유진에게 요청하기" });
    fireEvent.change(composer, { target: { value: "A 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    expect(prepare).toHaveBeenCalledTimes(1);
    expect(composer).toBeDisabled();
    fireEvent.change(composer, { target: { value: "B 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    expect(prepare).toHaveBeenCalledTimes(1);

    await act(async () => { resolveSend({ kind: "in_progress", retryAfterSeconds: 0 }); });
    fireEvent.click(await screen.findByRole("button", { name: "같은 요청 다시 보내기" }));
    expect(retry).toHaveBeenCalledTimes(1);
    expect(prepare).toHaveBeenCalledTimes(1);
  });

  it("ignores a stale Retry-After exchange after the route moves from A to B", async () => {
    let resolveSend!: (value: { kind: "in_progress"; retryAfterSeconds: number }) => void;
    let resolveRetry!: (value: { kind: "exchange"; exchange: { user_message: { message_id: string; text: string }; assistant_message: { message_id: string; proposal_id: null; text: string } } }) => void;
    const retry = vi.fn().mockImplementation(() => new Promise((resolve) => { resolveRetry = resolve; }));
    vi.spyOn(api, "prepareDirectorMessage").mockImplementation(() => ({ clientMessageId: "stable-a", send: () => new Promise((resolve) => { resolveSend = resolve; }), retry }) as never);
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => Promise.resolve(manifest(projectId, sessionId)) as never);
    vi.spyOn(api, "reloadDirectorSession").mockImplementation((projectId, sessionId) => Promise.resolve({
      conversation: { conversation_id: `conversation-${sessionId}`, project_id: String(projectId), session_id: String(sessionId) }, messages: [], proposal: null, references: [],
    }) as never);
    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "유진과 Inspector" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "유진에게 요청하기" }), { target: { value: "A 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await act(async () => { resolveSend({ kind: "in_progress", retryAfterSeconds: 0 }); });
    fireEvent.click(await screen.findByRole("button", { name: "같은 요청 다시 보내기" }));
    expect(retry).toHaveBeenCalledTimes(1);

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    await act(async () => { resolveRetry({ kind: "exchange", exchange: { user_message: { message_id: "user-a", text: "A 요청" }, assistant_message: { message_id: "assistant-a", proposal_id: null, text: "stale retry" } } }); });
    expect(screen.queryByText("stale retry")).toBeNull();
    expect(screen.getByText("timeline-session-b · revision 1")).toBeVisible();
  });
});
