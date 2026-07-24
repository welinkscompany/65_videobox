import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { startTransition, Suspense, useState } from "react";

import { ApiConflictError, api } from "../../../api";
import { EditorWorkbenchRoute } from "./EditorWorkbenchRoute";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const manifest = (projectId: string, sessionId: string) => ({ project_id: projectId, session_id: sessionId, timeline_id: `timeline-${sessionId}`, session_revision: 1, timeline_version: "v1", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 1 }, tracks: [], captions: [], gap_slots: [], source_status: { status: "current", source_session_id: sessionId, source_session_revision: 1 }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: sessionId, source_session_revision: 1 } });
const editingSession = (projectId: string, sessionId: string, revision = 1) => ({
  project_id: projectId,
  session_id: sessionId,
  timeline_id: `timeline-${sessionId}`,
  session_revision: revision,
  segments: [],
  history: [],
  undo_count: 0,
  redo_count: 0,
  updated_at: `2026-07-23T00:00:${String(revision).padStart(2, "0")}Z`,
});

function mockEditingSessionRevisions(...revisions: number[]) {
  const load = vi.mocked(api.getEditingSession);
  load.mockReset();
  for (const revision of revisions) {
    load.mockImplementationOnce(
      (projectId, sessionId) => Promise.resolve(editingSession(projectId, sessionId, revision)) as never,
    );
  }
  return load;
}

async function expectEditorRevision(revision: number) {
  const workbench = await screen.findByRole("region", { name: "편집 작업판" });
  await waitFor(() => expect(workbench).toHaveAttribute("data-editor-revision", String(revision)));
}

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

const inspectorStyle = {
  font_family: "Pretendard",
  font_size_px: 28,
  text_color: "#ffffff",
  outline_color: "#000000",
  outline_width_px: 2,
  background_color: "#00000000",
  position_x_percent: 50,
  position_y_percent: 90,
  horizontal_align: "center" as const,
  safe_area_enabled: true,
  shadow_blur_px: 0,
};

const inspectorSession = (revision: number) => ({
  ...editingSession("project-a", "session-a", revision),
  undo_count: 1,
  redo_count: 1,
  segments: [
    {
      segment_id: "segment-1", start_sec: 0, end_sec: 1, caption_text: "연결 자막",
      cut_action: "keep", review_required: false, broll_override: null, visual_overlays: [],
      music_override: null, sfx_override: null, tts_replacement: null, caption_style: inspectorStyle,
    },
    {
      segment_id: "segment-2", start_sec: 1, end_sec: 2, caption_text: "다음 자막",
      cut_action: "keep", review_required: false, broll_override: null, visual_overlays: [],
      music_override: null, sfx_override: null, tts_replacement: null, caption_style: inspectorStyle,
    },
  ],
});

type InspectorFixture = "narration" | "broll" | "bgm" | "sfx" | "caption" | "explanation" | "image" | "table";

function inspectorManifest(revision: number, fixture: InspectorFixture = "narration") {
  const base = twoNarrationManifest(revision);
  const mediaKind = fixture === "broll" || fixture === "bgm" || fixture === "sfx" ? fixture : null;
  const overlayType = fixture === "explanation"
    ? "explanation_card"
    : fixture === "image"
      ? "image_overlay"
      : fixture === "table"
        ? "table_overlay"
        : null;
  return {
    ...base,
    tracks: [
      ...base.tracks,
      ...(mediaKind ? [{
        track_id: mediaKind,
        track_type: mediaKind,
        clips: [{
          clip_id: `${mediaKind}-1`, segment_id: "segment-1", clip_type: mediaKind,
          asset_id: `asset-${mediaKind}`, asset_uri: `file:///asset-${mediaKind}`,
          start_sec: 0, end_sec: 1,
          media_controls: { gain_db: -8, fade_in_sec: 0.5, fade_out_sec: 1, ducking: true },
        }],
      }] : []),
      ...(overlayType ? [{
        track_id: "overlay",
        track_type: "overlay" as const,
        clips: [{
          clip_id: `${fixture}-1`, segment_id: "segment-1", clip_type: "overlay" as const,
          asset_id: fixture === "image" ? "asset-image" : null,
          asset_uri: fixture === "image" ? "file:///asset-image.png" : null,
          start_sec: 0, end_sec: 1, media_controls: {}, overlay_type: overlayType,
          overlay_payload: fixture === "explanation"
            ? { title: "제목", body: "본문", text: "설명" }
            : fixture === "image"
              ? { asset_id: "asset-image", text: "이미지 설명" }
              : { columns: ["항목", "값"], rows: [["길이", "10초"]], text: "요약표" },
        }],
      }] : []),
    ],
    captions: fixture === "caption" ? [{
      segment_id: "segment-1", caption_id: "caption-1", placement_id: "caption:segment-1",
      text: "연결 자막", start_sec: 0, end_sec: 1, style: inspectorStyle,
    }] : [],
  };
}

const partialPreflight = {
  session_id: "session-a",
  segment_ids: ["segment-1"],
  fields: ["caption", "music"],
  downstream_steps: ["segment_refresh", "music_refresh", "timeline_build"],
  targeted_segments: [{ segment_id: "segment-1" }],
  affected_output_areas: ["segment copy", "music track", "timeline preview"],
  predicted_review_status_after_rerun: "draft",
  prediction_reasons: [],
};

const partialRun = {
  ...partialPreflight,
  job_id: "partial-job-1",
  status: "succeeded",
  delta: { regenerated_segments: [{ segment_id: "segment-1" }], timeline_id: "timeline-partial-1" },
};

const partialJob = (sessionUpdatedAt: string) => ({
  job_id: "partial-job-1", status: "succeeded", partial_regeneration_id: "partial-run-1",
  session_id: "session-a", session_updated_at: sessionUpdatedAt,
  source_timeline_id: "timeline-session-a", timeline_id: "timeline-partial-1",
  segment_ids: ["segment-1"], fields: ["caption", "music"],
  downstream_steps: partialPreflight.downstream_steps,
  regenerated_segments: [{ segment_id: "segment-1" }],
  timeline: {},
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

async function openInspector() {
  fireEvent.click(await screen.findByRole("button", { name: "n-1 클립 선택" }));
  fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
  await screen.findByRole("dialog", { name: "유진과 편집 항목" });
  fireEvent.click(screen.getByRole("button", { name: "편집 항목 열기" }));
  return screen.findByRole("region", { name: "편집 항목" });
}

describe("EditorWorkbenchRoute", () => {
  beforeEach(() => {
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(narrationManifest(1) as never);
    vi.spyOn(api, "getEditingSession").mockImplementation(
      (projectId, sessionId) => Promise.resolve(editingSession(projectId, sessionId)) as never,
    );
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([] as never);
    vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [] } as never);
    vi.spyOn(api, "listJobs").mockResolvedValue([]);
    vi.spyOn(api, "listTtsCandidates").mockResolvedValue({ candidates: [] });
  });

  it("publishes nothing until the matching manifest and session arrive together", async () => {
    let resolveSession!: (value: unknown) => void;
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(narrationManifest(4) as never);
    vi.mocked(api.getEditingSession).mockImplementation(() => new Promise((resolve) => { resolveSession = resolve; }) as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryByRole("region", { name: "편집 작업판" })).toBeNull();
    expect(screen.getByText("편집 내용을 불러오는 중이에요.")).toBeVisible();

    await act(async () => { resolveSession(editingSession("project-a", "session-a", 4)); });
    await expectEditorRevision(4);
  });

  it("fails closed instead of publishing a mixed manifest and editing session", async () => {
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(narrationManifest(2) as never);
    vi.mocked(api.getEditingSession).mockResolvedValue(editingSession("project-a", "session-a", 1) as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);

    expect(await screen.findByText("편집 세션 정보가 일치하지 않아요. 다시 열어 주세요.")).toBeVisible();
    expect(screen.queryByRole("region", { name: "편집 작업판" })).toBeNull();
  });

  it("focuses a valid requested segment once without reloading or resetting editor-local state", async () => {
    const load = vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(twoNarrationManifest(1) as never);
    const reloadDirector = vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-a", project_id: "project-a", session_id: "session-a" },
      messages: [],
      proposal: null,
      references: [],
    } as never);
    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-2" />);
    const workbench = await screen.findByRole("region", { name: "편집 작업판" });
    const timeline = screen.getByTestId("timeline-track");
    const preview = screen.getByRole("region", { name: "미리보기" });
    await waitFor(() => expect(screen.getByRole("button", { name: "n-2 클립 선택" })).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
    fireEvent.change(await screen.findByLabelText("유진에게 요청하기"), { target: { value: "작성 중인 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    timeline.scrollLeft = 31;

    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-2" />);

    expect(screen.getByRole("button", { name: "n-1 클립 선택" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("작성 중인 요청");
    expect(screen.getByTestId("timeline-track")).toBe(timeline);
    expect(screen.getByRole("region", { name: "미리보기" })).toBe(preview);
    expect(screen.getByRole("region", { name: "편집 작업판" })).toBe(workbench);
    expect(screen.getByTestId("timeline-track").scrollLeft).toBe(31);
    expect(load).toHaveBeenCalledTimes(1);
    expect(reloadDirector).toHaveBeenCalledTimes(1);

    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-1" />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole("button", { name: "n-1 클립 선택" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "n-2 클립 선택" })).toHaveAttribute("aria-pressed", "false");
    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-2" />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole("button", { name: "n-1 클립 선택" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "n-2 클립 선택" })).toHaveAttribute("aria-pressed", "true");
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("does not focus a blank or unknown requested segment", async () => {
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(twoNarrationManifest(1) as never);
    const blank = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId=" " />);
    await expectEditorRevision(1);
    expect(screen.getByRole("button", { name: "n-2 클립 선택" })).toHaveAttribute("aria-pressed", "false");
    blank.unmount();

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-missing" />);
    await expectEditorRevision(1);
    expect(screen.getByRole("button", { name: "n-2 클립 선택" })).toHaveAttribute("aria-pressed", "false");
    expect(api.getEditorPlaybackManifest).toHaveBeenLastCalledWith("project-a", "session-a");
  });

  it.each([" ", "segment-missing"])(
    "resets only the active timeline selection when valid segment A re-enters after %j",
    async (intermediateSegmentId) => {
      const load = vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(twoNarrationManifest(1) as never);
      const rendered = render(
        <EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-1" />,
      );
      const workbench = await screen.findByRole("region", { name: "편집 작업판" });
      const timeline = screen.getByTestId("timeline-track");
      await waitFor(() => expect(screen.getByRole("button", { name: "n-1 클립 선택" })).toHaveAttribute("aria-pressed", "true"));

      rendered.rerender(
        <EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId={intermediateSegmentId} />,
      );
      fireEvent.click(screen.getByRole("button", { name: "n-2 클립 선택" }));
      timeline.scrollLeft = 43;

      rendered.rerender(
        <EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-1" />,
      );

      await waitFor(() => expect(screen.getByRole("button", { name: "n-1 클립 선택" })).toHaveAttribute("aria-pressed", "true"));
      expect(screen.getByRole("button", { name: "n-2 클립 선택" })).toHaveAttribute("aria-pressed", "false");
      expect(screen.getByRole("region", { name: "편집 작업판" })).toBe(workbench);
      expect(screen.getByTestId("timeline-track")).toBe(timeline);
      expect(screen.getByTestId("timeline-track").scrollLeft).toBe(43);
      expect(load).toHaveBeenCalledTimes(1);
    },
  );

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
    await expectEditorRevision(1);
    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
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
    await expectEditorRevision(1);
    await act(async () => { resolveMaterialized({ asset_id: "materialized-bgm" }); });

    expect(updateMusic).not.toHaveBeenCalled();
    expect(updateSfx).not.toHaveBeenCalled();
    expect(updateBroll).not.toHaveBeenCalled();
    await expectEditorRevision(1);
    expect(screen.queryByText("변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeNull();
  });

  it("keeps the manifest editor usable when an asset list fails and gives contained retry-safe guidance", async () => {
    vi.spyOn(api, "listMediaLibraryAssets").mockRejectedValue(new Error("offline"));

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);

    await expectEditorRevision(1);
    expect(await screen.findByText("일부 자산을 불러오지 못했어요. 편집은 계속할 수 있어요. 잠시 후 다시 확인해 주세요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "n-1 클립 선택" })).toBeEnabled();
  });

  it("never displays the old A session while B is loading", async () => {
    let resolveB!: (value: ReturnType<typeof manifest>) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => sessionId === "session-a" ? Promise.resolve(manifest(projectId, sessionId)) : new Promise((resolve) => { resolveB = resolve; }));
    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(screen.queryByRole("region", { name: "편집 작업판" })).toBeNull();
    expect(screen.getByText("편집 내용을 불러오는 중이에요.")).toBeVisible();
    resolveB(manifest("project-b", "session-b"));
    await expectEditorRevision(1);
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
    mockEditingSessionRevisions(1, 2);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds")
      .mockImplementation(() => new Promise((resolve) => { resolveUpdate = resolve; }) as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
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
    await expectEditorRevision(2);
  });

  it("saves linked caption text through the same revision fence and refreshes the manifest", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(captionManifest(4) as never)
      .mockResolvedValueOnce(captionManifest(5, "새 자막") as never);
    mockEditingSessionRevisions(4, 5);
    const update = vi.spyOn(api, "updateEditingSessionCaption").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(4);
    fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));
    expect(await screen.findByRole("dialog", { name: "자산과 대본" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "원래 자막 대본 선택" }));
    fireEvent.change(screen.getByRole("textbox", { name: "segment-1 자막 텍스트" }), { target: { value: "새 자막" } });
    fireEvent.click(screen.getByRole("button", { name: "자막 저장" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith("project-a", "session-a", "segment-1", { caption_text: "새 자막", expected_revision: 4 }));
    await expectEditorRevision(5);
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("refreshes after a linked-caption revision conflict without retrying the caption command", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(captionManifest(4) as never)
      .mockResolvedValueOnce(captionManifest(5, "다른 변경 자막") as never);
    mockEditingSessionRevisions(4, 5);
    const update = vi.spyOn(api, "updateEditingSessionCaption").mockRejectedValue(
      new ApiConflictError({}, "/api/projects/project-a/editing-sessions/session-a/segments/segment-1/caption"),
    );

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(4);
    fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));
    expect(await screen.findByRole("dialog", { name: "자산과 대본" })).toBeVisible();
    fireEvent.change(screen.getByRole("textbox", { name: "segment-1 자막 텍스트" }), { target: { value: "새 자막" } });
    fireEvent.click(screen.getByRole("button", { name: "자막 저장" }));

    expect(await screen.findByText("다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(update).toHaveBeenCalledTimes(1);
    await expectEditorRevision(5);
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("keeps the current view, refreshes after a revision conflict, and does not retry the command", async () => {
    let resolveRefresh!: (value: ReturnType<typeof narrationManifest>) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve as typeof resolveRefresh; }));
    mockEditingSessionRevisions(1, 2);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds").mockRejectedValue(
      new ApiConflictError({}, "/api/projects/project-a/editing-sessions/session-a/segments/segment-1/bounds"),
    );

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    expect(await screen.findByText("다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    await expectEditorRevision(1);
    expect(update).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(update).toHaveBeenCalledTimes(1);

    resolveRefresh(narrationManifest(2, 0));
    await expectEditorRevision(2);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("commits one complete narration reorder layout on pointer release", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(twoNarrationManifest(3) as never)
      .mockResolvedValueOnce(twoNarrationManifest(4) as never);
    mockEditingSessionRevisions(3, 4);
    const reorder = vi.spyOn(api, "reorderEditingSessionSegments").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(3);
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
    mockEditingSessionRevisions(5, 5);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds").mockRejectedValue(new Error("offline"));

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(5);
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

  it("routes toolbar undo and redo through the current revision and refreshes after each command", async () => {
    const manifestLoad = vi.mocked(api.getEditorPlaybackManifest);
    manifestLoad.mockReset()
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(8) as never)
      .mockResolvedValueOnce(inspectorManifest(9) as never);
    const sessionLoad = vi.mocked(api.getEditingSession);
    sessionLoad.mockReset()
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never)
      .mockResolvedValueOnce(inspectorSession(9) as never);
    const undo = vi.spyOn(api, "undoEditingSession").mockResolvedValue({} as never);
    const redo = vi.spyOn(api, "redoEditingSession").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    fireEvent.click(screen.getByRole("button", { name: "실행 취소" }));
    await waitFor(() => expect(undo).toHaveBeenCalledWith("project-a", "session-a", 7));
    await expectEditorRevision(8);

    fireEvent.click(screen.getByRole("button", { name: "다시 실행" }));
    await waitFor(() => expect(redo).toHaveBeenCalledWith("project-a", "session-a", 8));
    await expectEditorRevision(9);
    expect(manifestLoad).toHaveBeenCalledTimes(3);
    expect(sessionLoad).toHaveBeenCalledTimes(3);
  });

  it("keeps toolbar history commands single-flight across undo and redo", async () => {
    let resolveUndo!: (value: unknown) => void;
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(8) as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    const undo = vi.spyOn(api, "undoEditingSession")
      .mockImplementation(() => new Promise((resolve) => { resolveUndo = resolve; }) as never);
    const redo = vi.spyOn(api, "redoEditingSession");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    const undoButton = screen.getByRole("button", { name: "실행 취소" });
    const redoButton = screen.getByRole("button", { name: "다시 실행" });
    fireEvent.click(undoButton);
    fireEvent.click(undoButton);
    fireEvent.click(redoButton);

    await waitFor(() => expect(undo).toHaveBeenCalledTimes(1));
    expect(redo).not.toHaveBeenCalled();
    expect(undoButton).toBeDisabled();
    expect(redoButton).toBeDisabled();
    await act(async () => { resolveUndo({}); });
    await expectEditorRevision(8);
  });

  it("routes split, merge, and explicit keep/remove cut actions through one revisioned Inspector lane", async () => {
    const manifestLoad = vi.mocked(api.getEditorPlaybackManifest);
    manifestLoad.mockReset();
    const sessionLoad = vi.mocked(api.getEditingSession);
    sessionLoad.mockReset();
    for (const revision of [7, 8, 9, 10, 11]) {
      manifestLoad.mockResolvedValueOnce(inspectorManifest(revision) as never);
      sessionLoad.mockResolvedValueOnce(inspectorSession(revision) as never);
    }
    const split = vi.spyOn(api, "splitEditingSessionSegment").mockResolvedValue({} as never);
    const merge = vi.spyOn(api, "mergeEditingSessionSegments").mockResolvedValue({} as never);
    const cut = vi.spyOn(api, "updateEditingSessionCutAction").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();

    fireEvent.click(screen.getByRole("button", { name: "구간 중간에서 나누기" }));
    await waitFor(() => expect(split).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
      expected_revision: 7,
      split_sec: 0.5,
    }));
    await expectEditorRevision(8);

    fireEvent.click(screen.getByRole("button", { name: "다음 구간과 합치기" }));
    await waitFor(() => expect(merge).toHaveBeenCalledWith("project-a", "session-a", {
      expected_revision: 8,
      left_segment_id: "segment-1",
      right_segment_id: "segment-2",
    }));
    await expectEditorRevision(9);

    fireEvent.change(screen.getByLabelText("선택 구간 처리"), { target: { value: "remove" } });
    fireEvent.click(screen.getByRole("button", { name: "컷 저장" }));
    await waitFor(() => expect(cut).toHaveBeenNthCalledWith(1, "project-a", "session-a", "segment-1", {
      cut_action: "remove",
      expected_revision: 9,
    }));
    await expectEditorRevision(10);

    fireEvent.change(screen.getByLabelText("선택 구간 처리"), { target: { value: "keep" } });
    fireEvent.click(screen.getByRole("button", { name: "컷 저장" }));
    await waitFor(() => expect(cut).toHaveBeenNthCalledWith(2, "project-a", "session-a", "segment-1", {
      cut_action: "keep",
      expected_revision: 10,
    }));
    await expectEditorRevision(11);
  });

  it("applies and clears only an approved TTS candidate through the revisioned single-flight Inspector lane", async () => {
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(8) as never)
      .mockResolvedValueOnce(inspectorManifest(9) as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce({
        ...inspectorSession(8),
        segments: inspectorSession(8).segments.map((segment, index) => index === 0
          ? { ...segment, tts_replacement: { recommendation_id: "tts_candidate_approved", asset_id: "asset-approved" } }
          : segment),
      } as never)
      .mockResolvedValueOnce(inspectorSession(9) as never);
    vi.mocked(api.listTtsCandidates).mockResolvedValue({
      candidates: [
        {
          actual_duration_sec: 1,
          asset_id: "asset-approved",
          candidate_id: "tts_candidate_approved",
          created_at: "2026-07-24T00:00:00Z",
          failure_code: null,
          operator_review_status: "approved",
          project_id: "project-a",
          segment_id: "segment-1",
          source_text: "승인된 음성",
          target_duration_sec: 1,
          technical_status: "accepted",
        },
        {
          actual_duration_sec: 1,
          asset_id: "asset-pending",
          candidate_id: "tts_candidate_pending",
          created_at: "2026-07-24T00:00:00Z",
          failure_code: null,
          operator_review_status: "pending",
          project_id: "project-a",
          segment_id: "segment-1",
          source_text: "승인 전 음성",
          target_duration_sec: 1,
          technical_status: "accepted",
        },
      ],
    });
    let resolveApply!: (value: unknown) => void;
    const apply = vi.spyOn(api, "updateEditingSessionTtsReplacement")
      .mockImplementation(() => new Promise((resolve) => { resolveApply = resolve; }) as never);
    const clear = vi.spyOn(api, "clearEditingSessionTtsReplacement").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    expect(await screen.findByRole("option", { name: "승인 후보 1 · 승인된 음성" })).toBeVisible();
    expect(screen.queryByText("승인 전 음성")).toBeNull();

    const applyButton = screen.getByRole("button", { name: "승인한 음성 적용" });
    fireEvent.click(applyButton);
    fireEvent.click(applyButton);
    await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
    expect(apply).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
      asset_id: "asset-approved",
      expected_revision: 7,
      recommendation_id: "tts_candidate_approved",
    });
    await act(async () => { resolveApply({}); });
    await expectEditorRevision(8);

    fireEvent.click(await screen.findByRole("button", { name: "적용한 음성 해제" }));
    await waitFor(() => expect(clear).toHaveBeenCalledWith("project-a", "session-a", "segment-1", 8));
    await expectEditorRevision(9);
  });

  it.each([
    { fixture: "broll" as const, label: "B-roll 지우기", endpoint: "broll" as const },
    { fixture: "bgm" as const, label: "배경 음악 지우기", endpoint: "bgm" as const },
    { fixture: "sfx" as const, label: "효과음 지우기", endpoint: "sfx" as const },
  ])("clears the selected $fixture target with the current revision", async ({ endpoint, fixture, label }) => {
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7, fixture) as never)
      .mockResolvedValueOnce(inspectorManifest(8, fixture) as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    const clearBroll = vi.spyOn(api, "clearEditingSessionBrollOverride").mockResolvedValue({} as never);
    const clearBgm = vi.spyOn(api, "clearEditingSessionMusicOverride").mockResolvedValue({} as never);
    const clearSfx = vi.spyOn(api, "clearEditingSessionSfxOverride").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    fireEvent.click(screen.getByRole("button", { name: label }));

    const expected = endpoint === "broll" ? clearBroll : endpoint === "bgm" ? clearBgm : clearSfx;
    await waitFor(() => expect(expected).toHaveBeenCalledWith("project-a", "session-a", "segment-1", 7));
    expect(clearBroll.mock.calls.length + clearBgm.mock.calls.length + clearSfx.mock.calls.length).toBe(1);
    await expectEditorRevision(8);
  });

  it.each([
    {
      fixture: "bgm" as const,
      label: "배경 음악",
      saveEndpoint: "bgm" as const,
    },
    {
      fixture: "sfx" as const,
      label: "효과음",
      saveEndpoint: "sfx" as const,
    },
  ])("preserves hidden $fixture controls while routing visible fade edits through the current revision", async ({ fixture, label, saveEndpoint }) => {
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7, fixture) as never)
      .mockResolvedValueOnce(inspectorManifest(8, fixture) as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    const saveBgm = vi.spyOn(api, "updateEditingSessionMusicOverride").mockResolvedValue({} as never);
    const saveSfx = vi.spyOn(api, "updateEditingSessionSfxOverride").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    fireEvent.change(screen.getByLabelText(`${label} 페이드 인`), { target: { value: "1.25" } });
    fireEvent.change(screen.getByLabelText(`${label} 페이드 아웃`), { target: { value: "0.75" } });
    fireEvent.click(screen.getByRole("button", { name: `${label} 설정 저장` }));

    const save = saveEndpoint === "bgm" ? saveBgm : saveSfx;
    await waitFor(() => expect(save).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
      asset_id: `asset-${fixture}`,
      expected_revision: 7,
      media_controls: { ducking: true, fade_in_sec: 1.25, fade_out_sec: 0.75, gain_db: -8 },
    }));
    expect(saveBgm.mock.calls.length + saveSfx.mock.calls.length).toBe(1);
    await expectEditorRevision(8);
  });

  it("routes a complete caption style edit without exposing independent caption timing", async () => {
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7, "caption") as never)
      .mockResolvedValueOnce(inspectorManifest(8, "caption") as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    const save = vi.spyOn(api, "updateEditingSessionCaptionStyle").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    expect(screen.queryByLabelText(/자막 시작|자막 종료/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("글자 크기"), { target: { value: "32" } });
    fireEvent.change(screen.getByLabelText("가로 정렬"), { target: { value: "left" } });
    fireEvent.click(screen.getByRole("button", { name: "자막 스타일 저장" }));

    await waitFor(() => expect(save).toHaveBeenCalledWith("project-a", "session-a", {
      expected_revision: 7,
      scope: "current_caption",
      segment_ids: ["segment-1"],
      style: { ...inspectorStyle, font_size_px: 32, horizontal_align: "left" },
    }));
    await expectEditorRevision(8);
  });

  it.each([
    { fixture: "explanation" as const, label: "설명 카드" },
    { fixture: "image" as const, label: "이미지" },
    { fixture: "table" as const, label: "표" },
  ])("routes supported $label overlay save and clear through consecutive revisions", async ({ fixture, label }) => {
    const manifestLoad = vi.mocked(api.getEditorPlaybackManifest);
    manifestLoad.mockReset()
      .mockResolvedValueOnce(inspectorManifest(7, fixture) as never)
      .mockResolvedValueOnce(inspectorManifest(8, fixture) as never)
      .mockResolvedValueOnce(inspectorManifest(9, fixture) as never);
    const sessionLoad = vi.mocked(api.getEditingSession);
    sessionLoad.mockReset()
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never)
      .mockResolvedValueOnce(inspectorSession(9) as never);
    const saveExplanation = vi.spyOn(api, "updateEditingSessionExplanationCard").mockResolvedValue({} as never);
    const clearExplanation = vi.spyOn(api, "removeEditingSessionExplanationCard").mockResolvedValue({} as never);
    const saveImage = vi.spyOn(api, "updateEditingSessionImageOverlay").mockResolvedValue({} as never);
    const clearImage = vi.spyOn(api, "removeEditingSessionImageOverlay").mockResolvedValue({} as never);
    const saveTable = vi.spyOn(api, "updateEditingSessionTableOverlay").mockResolvedValue({} as never);
    const clearTable = vi.spyOn(api, "removeEditingSessionTableOverlay").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    fireEvent.click(screen.getByRole("button", { name: `${label} 저장` }));

    if (fixture === "explanation") {
      await waitFor(() => expect(saveExplanation).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
        body: "본문", expected_revision: 7, text: "설명", title: "제목",
      }));
    } else if (fixture === "image") {
      await waitFor(() => expect(saveImage).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
        asset_id: "asset-image", expected_revision: 7, text: "이미지 설명",
      }));
    } else {
      await waitFor(() => expect(saveTable).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
        columns: ["항목", "값"], expected_revision: 7, rows: [["길이", "10초"]], text: "요약표",
      }));
    }
    await expectEditorRevision(8);
    fireEvent.click(screen.getByRole("button", { name: `${label} 지우기` }));

    const clear = fixture === "explanation" ? clearExplanation : fixture === "image" ? clearImage : clearTable;
    await waitFor(() => expect(clear).toHaveBeenCalledWith("project-a", "session-a", "segment-1", 8));
    await expectEditorRevision(9);
  });

  it("requires impact preflight before one explicit partial run, then resumes only from an explicit result read", async () => {
    let resolveRun!: (value: typeof partialRun) => void;
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(8) as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    vi.mocked(api.listJobs).mockResolvedValue([{
      job_id: "partial-job-1",
      project_id: "project-a",
      job_type: "partial_regeneration",
      status: "succeeded",
      input_ref: "session-a",
      output_ref: "partial-run-1",
      error_message: null,
      started_at: "2026-07-24T00:00:00Z",
      finished_at: "2026-07-24T00:00:01Z",
    }]);
    const preflight = vi.spyOn(api, "previewPartialRegeneration").mockResolvedValue(partialPreflight as never);
    const run = vi.spyOn(api, "runPartialRegeneration")
      .mockImplementation(() => new Promise((resolve) => { resolveRun = resolve; }) as never);
    const resume = vi.spyOn(api, "getPartialRegenerationResult")
      .mockResolvedValue(partialJob(inspectorSession(8).updated_at) as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    const runButton = screen.getByRole("button", { name: "부분 재생성 실행" });
    expect(runButton).toBeDisabled();
    fireEvent.click(runButton);
    expect(run).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "재생성 범위 미리보기" }));
    await waitFor(() => expect(preflight).toHaveBeenCalledWith("project-a", "session-a", {
      fields: ["caption", "music"],
      segment_ids: ["segment-1"],
    }));
    await waitFor(() => expect(runButton).toBeEnabled());
    fireEvent.click(runButton);
    fireEvent.click(runButton);
    await waitFor(() => expect(run).toHaveBeenCalledWith("project-a", "session-a", {
      expected_revision: 7,
      fields: ["caption", "music"],
      segment_ids: ["segment-1"],
    }));
    expect(run).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("다시 만든 항목")).toBeNull();

    await act(async () => { resolveRun(partialRun); });
    await expectEditorRevision(8);
    const openResult = screen.getByRole("button", { name: "이전 결과 열기" });
    await waitFor(() => expect(openResult).toBeEnabled());
    const readsBeforeOpen = resume.mock.calls.length;
    fireEvent.click(openResult);
    await waitFor(() => expect(resume.mock.calls.length).toBeGreaterThan(readsBeforeOpen));
    expect(await screen.findByText("현재 편집본과 맞는 이전 결과를 열었어요.")).toBeVisible();
    const result = screen.getByText("다시 만든 항목").closest("dl");
    expect(result).toHaveTextContent("succeeded");
    expect(result).toHaveTextContent("caption, music");
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("recovers the latest succeeded same-session result after a fresh route mount", async () => {
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(8) as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    vi.mocked(api.listJobs).mockResolvedValue([{
      job_id: "partial-job-1",
      project_id: "project-a",
      job_type: "partial_regeneration",
      status: "succeeded",
      input_ref: "session-a",
      output_ref: "partial-run-1",
      error_message: null,
      started_at: "2026-07-24T00:00:00Z",
      finished_at: "2026-07-24T00:00:01Z",
    }]);
    const read = vi.spyOn(api, "getPartialRegenerationResult")
      .mockResolvedValue(partialJob(inspectorSession(7).updated_at) as never);
    vi.spyOn(api, "undoEditingSession").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    const openResult = screen.getByRole("button", { name: "이전 결과 열기" });
    await waitFor(() => expect(openResult).toBeEnabled());
    fireEvent.click(openResult);

    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("현재 편집본과 맞는 이전 결과를 열었어요.")).toBeVisible();
    expect(screen.getByText("다시 만든 항목").closest("dl")).toHaveTextContent("caption, music");

    fireEvent.click(screen.getByRole("button", { name: "실행 취소" }));
    await expectEditorRevision(8);
    expect(await screen.findByText("현재 편집본과 맞지 않는 이전 결과를 닫았어요.")).toBeVisible();
    expect(screen.queryByText("다시 만든 항목")).toBeNull();
  });

  it("disables a recovered but unopened result only after an authoritative revision advance", async () => {
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(8) as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    vi.mocked(api.listJobs).mockResolvedValue([{
      job_id: "partial-job-1",
      project_id: "project-a",
      job_type: "partial_regeneration",
      status: "succeeded",
      input_ref: "session-a",
      output_ref: "partial-run-1",
      error_message: null,
      started_at: "2026-07-24T00:00:00Z",
      finished_at: "2026-07-24T00:00:01Z",
    }]);
    vi.spyOn(api, "getPartialRegenerationResult")
      .mockResolvedValue(partialJob(inspectorSession(7).updated_at) as never);
    vi.spyOn(api, "undoEditingSession").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    const openResult = screen.getByRole("button", { name: "이전 결과 열기" });
    await waitFor(() => expect(openResult).toBeEnabled());

    fireEvent.click(screen.getByRole("button", { name: "실행 취소" }));
    await expectEditorRevision(8);
    await waitFor(() => expect(openResult).toBeDisabled());
    expect(await screen.findByText("현재 편집본과 맞지 않는 이전 결과를 닫았어요.")).toBeVisible();
  });

  it("does not recover a latest-job response carrying a different job identity", async () => {
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(inspectorManifest(7) as never);
    vi.mocked(api.getEditingSession).mockResolvedValue(inspectorSession(7) as never);
    vi.mocked(api.listJobs).mockResolvedValue([{
      job_id: "partial-job-1",
      project_id: "project-a",
      job_type: "partial_regeneration",
      status: "succeeded",
      input_ref: "session-a",
      output_ref: "partial-run-1",
      error_message: null,
      started_at: "2026-07-24T00:00:00Z",
      finished_at: "2026-07-24T00:00:01Z",
    }]);
    const read = vi.spyOn(api, "getPartialRegenerationResult").mockResolvedValue({
      ...partialJob(inspectorSession(7).updated_at),
      job_id: "partial-job-other",
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    await waitFor(() => expect(read).toHaveBeenCalledWith("project-a", "partial-job-1"));

    expect(screen.getByRole("button", { name: "이전 결과 열기" })).toBeDisabled();
    expect(screen.queryByText("다시 만든 항목")).toBeNull();
  });

  it("keeps manual editing available and retries a failed historical result discovery in the same mount", async () => {
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(inspectorManifest(7) as never);
    vi.mocked(api.getEditingSession).mockResolvedValue(inspectorSession(7) as never);
    vi.mocked(api.listJobs)
      .mockRejectedValueOnce(new Error("temporary recovery failure"))
      .mockResolvedValue([{
        job_id: "partial-job-1",
        project_id: "project-a",
        job_type: "partial_regeneration",
        status: "succeeded",
        input_ref: "session-a",
        output_ref: "partial-run-1",
        error_message: null,
        started_at: "2026-07-24T00:00:00Z",
        finished_at: "2026-07-24T00:00:01Z",
      }]);
    vi.spyOn(api, "getPartialRegenerationResult")
      .mockResolvedValue(partialJob(inspectorSession(7).updated_at) as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    expect(await screen.findByText("이전 재생성 결과를 찾지 못했어요. 직접 편집은 계속할 수 있어요.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "이전 결과 다시 찾기" }));
    await openInspector();

    await waitFor(() => expect(screen.getByRole("button", { name: "이전 결과 열기" })).toBeEnabled());
    expect(screen.queryByRole("button", { name: "이전 결과 다시 찾기" })).toBeNull();
    expect(screen.queryByText("이전 재생성 결과를 찾지 못했어요. 직접 편집은 계속할 수 있어요.")).toBeNull();
    expect(screen.getByText("이전 재생성 결과를 다시 찾았어요.")).toBeVisible();
  });

  it("clears a recovery error when an explicit retry confirms there is no historical result", async () => {
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(inspectorManifest(7) as never);
    vi.mocked(api.getEditingSession).mockResolvedValue(inspectorSession(7) as never);
    vi.mocked(api.listJobs)
      .mockRejectedValueOnce(new Error("temporary recovery failure"))
      .mockResolvedValue([]);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    expect(await screen.findByText("이전 재생성 결과를 찾지 못했어요. 직접 편집은 계속할 수 있어요.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "이전 결과 다시 찾기" }));

    expect(await screen.findByText("저장된 이전 재생성 결과가 없어요.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "이전 결과 다시 찾기" })).toBeNull();
  });

  it("keeps the same current result open after a failed mutation and same-timestamp refresh", async () => {
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(7) as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(7) as never);
    vi.mocked(api.listJobs).mockResolvedValue([{
      job_id: "partial-job-1",
      project_id: "project-a",
      job_type: "partial_regeneration",
      status: "succeeded",
      input_ref: "session-a",
      output_ref: "partial-run-1",
      error_message: null,
      started_at: "2026-07-24T00:00:00Z",
      finished_at: "2026-07-24T00:00:01Z",
    }]);
    vi.spyOn(api, "getPartialRegenerationResult")
      .mockResolvedValue(partialJob(inspectorSession(7).updated_at) as never);
    vi.spyOn(api, "undoEditingSession").mockRejectedValue(new Error("offline"));

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    const openResult = screen.getByRole("button", { name: "이전 결과 열기" });
    await waitFor(() => expect(openResult).toBeEnabled());
    fireEvent.click(openResult);
    expect(await screen.findByText("다시 만든 항목")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "실행 취소" }));
    expect(await screen.findByText("변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    await waitFor(() => expect(screen.getByText("다시 만든 항목")).toBeVisible());
    expect(openResult).toBeEnabled();
  });

  it("fails closed when a preflight response does not match the prepared segment", async () => {
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(inspectorManifest(7) as never);
    vi.mocked(api.getEditingSession).mockResolvedValue(inspectorSession(7) as never);
    vi.spyOn(api, "previewPartialRegeneration").mockResolvedValue({
      ...partialPreflight,
      segment_ids: ["segment-2"],
    } as never);
    const run = vi.spyOn(api, "runPartialRegeneration");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    fireEvent.click(screen.getByRole("button", { name: "재생성 범위 미리보기" }));

    expect(await screen.findByText("영향 범위를 확인하지 못했어요. 직접 편집은 계속할 수 있어요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "부분 재생성 실행" })).toBeDisabled();
    expect(run).not.toHaveBeenCalled();
  });

  it("ignores an old result read after a manual mutation advances the session", async () => {
    let resolveResume!: (value: ReturnType<typeof partialJob>) => void;
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(8) as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    vi.mocked(api.listJobs).mockResolvedValue([{
      job_id: "partial-job-1",
      project_id: "project-a",
      job_type: "partial_regeneration",
      status: "succeeded",
      input_ref: "session-a",
      output_ref: "partial-run-1",
      error_message: null,
      started_at: "2026-07-24T00:00:00Z",
      finished_at: "2026-07-24T00:00:01Z",
    }]);
    vi.spyOn(api, "getPartialRegenerationResult")
      .mockResolvedValueOnce(partialJob(inspectorSession(7).updated_at) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveResume = resolve; }) as never)
      .mockResolvedValue(partialJob(inspectorSession(7).updated_at) as never);
    vi.spyOn(api, "undoEditingSession").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    const openResult = screen.getByRole("button", { name: "이전 결과 열기" });
    await waitFor(() => expect(openResult).toBeEnabled());
    fireEvent.click(openResult);
    fireEvent.click(screen.getByRole("button", { name: "실행 취소" }));
    await expectEditorRevision(8);
    await act(async () => { resolveResume(partialJob(inspectorSession(7).updated_at)); });

    expect(screen.queryByText("현재 편집본과 맞는 이전 결과를 열었어요.")).toBeNull();
    expect(screen.queryByText("다시 만든 항목")).toBeNull();
  });

  it.each([
    {
      label: "conflict",
      error: new ApiConflictError({}, "/api/projects/project-a/editing-sessions/session-a/partial-regeneration"),
      message: "다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.",
    },
    {
      label: "failure",
      error: new Error("partial failed"),
      message: "변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.",
    },
  ])("authoritatively refreshes manifest and session after partial run $label", async ({ error, message }) => {
    const manifestLoad = vi.mocked(api.getEditorPlaybackManifest);
    manifestLoad.mockReset()
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(8) as never);
    const sessionLoad = vi.mocked(api.getEditingSession);
    sessionLoad.mockReset()
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    vi.spyOn(api, "previewPartialRegeneration").mockResolvedValue(partialPreflight as never);
    const run = vi.spyOn(api, "runPartialRegeneration").mockRejectedValue(error);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    fireEvent.click(screen.getByRole("button", { name: "재생성 범위 미리보기" }));
    const runButton = screen.getByRole("button", { name: "부분 재생성 실행" });
    await waitFor(() => expect(runButton).toBeEnabled());
    fireEvent.click(runButton);

    expect(await screen.findByText(message)).toBeVisible();
    expect(screen.getByText("부분 재생성을 완료하지 못했어요. 영향 범위를 다시 확인해 주세요.")).toBeVisible();
    expect(screen.queryByText("선택한 범위를 다시 만들고 있어요.")).toBeNull();
    expect(run).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(manifestLoad).toHaveBeenCalledTimes(2));
    expect(sessionLoad).toHaveBeenCalledTimes(2);
    await expectEditorRevision(8);
  });

  it("invalidates an unresolved A partial preflight after route navigation to B", async () => {
    let resolvePreflight!: (value: typeof partialPreflight) => void;
    vi.mocked(api.getEditorPlaybackManifest).mockImplementation(
      (projectId, sessionId) => Promise.resolve(
        projectId === "project-a" ? inspectorManifest(7) : {
          ...inspectorManifest(3),
          project_id: projectId,
          session_id: sessionId,
          timeline_id: `timeline-${sessionId}`,
          source_status: { status: "current", source_session_id: sessionId, source_session_revision: 3 },
        },
      ) as never,
    );
    vi.mocked(api.getEditingSession).mockImplementation(
      (projectId, sessionId) => Promise.resolve({
        ...inspectorSession(projectId === "project-a" ? 7 : 3),
        project_id: projectId,
        session_id: sessionId,
        timeline_id: `timeline-${sessionId}`,
      }) as never,
    );
    const preflight = vi.spyOn(api, "previewPartialRegeneration")
      .mockImplementation(() => new Promise((resolve) => { resolvePreflight = resolve; }) as never);
    const run = vi.spyOn(api, "runPartialRegeneration");

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    fireEvent.click(screen.getByRole("button", { name: "재생성 범위 미리보기" }));
    await waitFor(() => expect(preflight).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(3);
    await act(async () => { resolvePreflight(partialPreflight); });

    fireEvent.click(screen.getByRole("button", { name: "편집 항목 열기" }));
    const runButton = screen.getByRole("button", { name: "부분 재생성 실행" });
    expect(runButton).toBeDisabled();
    fireEvent.click(runButton);
    expect(run).not.toHaveBeenCalled();
    await expectEditorRevision(3);
  });

  it("ignores an old A partial run completion after route navigation to B", async () => {
    let resolveRun!: (value: typeof partialRun) => void;
    const manifestLoad = vi.mocked(api.getEditorPlaybackManifest);
    manifestLoad.mockReset().mockImplementation(
      (projectId, sessionId) => Promise.resolve(
        projectId === "project-a" ? inspectorManifest(7) : {
          ...inspectorManifest(3),
          project_id: projectId,
          session_id: sessionId,
          timeline_id: `timeline-${sessionId}`,
          source_status: { status: "current", source_session_id: sessionId, source_session_revision: 3 },
        },
      ) as never,
    );
    vi.mocked(api.getEditingSession).mockImplementation(
      (projectId, sessionId) => Promise.resolve({
        ...inspectorSession(projectId === "project-a" ? 7 : 3),
        project_id: projectId,
        session_id: sessionId,
        timeline_id: `timeline-${sessionId}`,
      }) as never,
    );
    vi.spyOn(api, "previewPartialRegeneration").mockResolvedValue(partialPreflight as never);
    const run = vi.spyOn(api, "runPartialRegeneration")
      .mockImplementation(() => new Promise((resolve) => { resolveRun = resolve; }) as never);
    const resume = vi.spyOn(api, "getPartialRegenerationResult");

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    fireEvent.click(screen.getByRole("button", { name: "재생성 범위 미리보기" }));
    const runButton = screen.getByRole("button", { name: "부분 재생성 실행" });
    await waitFor(() => expect(runButton).toBeEnabled());
    fireEvent.click(runButton);
    await waitFor(() => expect(run).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(3);
    await act(async () => { resolveRun(partialRun); });

    expect(manifestLoad).toHaveBeenCalledTimes(2);
    expect(resume).not.toHaveBeenCalled();
    await expectEditorRevision(3);
  });

  it("blocks editor history mutation while a Director batch apply lane is in flight", async () => {
    let resolveDirectorPreflight!: (value: { status: string }) => void;
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(inspectorManifest(7) as never);
    vi.mocked(api.getEditingSession).mockResolvedValue(inspectorSession(7) as never);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: directorProposal(), references: [],
    } as never);
    vi.spyOn(api, "preflightDirectorProposal")
      .mockImplementation(() => new Promise((resolve) => { resolveDirectorPreflight = resolve; }) as never);
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal");
    const undo = vi.spyOn(api, "undoEditingSession");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
    fireEvent.click(await screen.findByRole("button", { name: "선택한 추천 적용" }));
    await waitFor(() => expect(api.preflightDirectorProposal).toHaveBeenCalledTimes(1));

    const undoButton = screen.getByRole("button", { name: "실행 취소" });
    expect(undoButton).toBeDisabled();
    fireEvent.click(undoButton);
    expect(undo).not.toHaveBeenCalled();
    expect(batchApply).not.toHaveBeenCalled();
    await act(async () => { resolveDirectorPreflight({ status: "ready" }); });
  });

  it("blocks Director apply while an editor history mutation lane is in flight", async () => {
    let resolveUndo!: (value: unknown) => void;
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(8) as never);
    vi.mocked(api.getEditingSession)
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: directorProposal(), references: [],
    } as never);
    vi.spyOn(api, "undoEditingSession")
      .mockImplementation(() => new Promise((resolve) => { resolveUndo = resolve; }) as never);
    const directorPreflight = vi.spyOn(api, "preflightDirectorProposal");
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    fireEvent.click(screen.getByRole("button", { name: "실행 취소" }));
    await waitFor(() => expect(api.undoEditingSession).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
    const apply = await screen.findByRole("button", { name: "선택한 추천 적용" });

    expect(apply).toBeDisabled();
    fireEvent.click(apply);
    expect(directorPreflight).not.toHaveBeenCalled();
    expect(batchApply).not.toHaveBeenCalled();
    await act(async () => { resolveUndo({}); });
    await expectEditorRevision(8);
  });

  it("ignores an old A mutation after navigating A to B to A while a new A mutation is saving", async () => {
    let resolveOldUpdate!: (value: unknown) => void;
    let resolveNewUpdate!: (value: unknown) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(manifest("project-b", "session-b") as never)
      .mockResolvedValueOnce(narrationManifest(10) as never)
      .mockResolvedValueOnce(narrationManifest(11, 1) as never);
    mockEditingSessionRevisions(1, 1, 10, 11);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds")
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOldUpdate = resolve; }) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNewUpdate = resolve; }) as never);

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    let track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    let trim = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(10);
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
    await expectEditorRevision(10);
    expect(screen.getByText("변경 내용을 저장하고 있어요.")).toBeVisible();
    expect(trim).toBeDisabled();

    resolveNewUpdate({});
    await waitFor(() => expect(load).toHaveBeenCalledTimes(4));
    await expectEditorRevision(11);
    expect(screen.getByText("변경 내용을 저장했어요.")).toBeVisible();
  });

  it("keeps the committed A mutation current when an uncommitted B render is abandoned", async () => {
    let navigate!: (route: "a" | "b") => void;
    let resolveUpdate!: (value: unknown) => void;
    const never = new Promise<never>(() => undefined);
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(twoNarrationManifest(1) as never)
      .mockResolvedValueOnce(twoNarrationManifest(2) as never);
    mockEditingSessionRevisions(1, 2);
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
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const reorder = screen.getByRole("button", { name: "n-1 순서 바꾸기" });
    fireEvent.keyDown(reorder, { key: "ArrowRight" });
    await waitFor(() => expect(screen.getByText("변경 내용을 저장하고 있어요.")).toBeVisible());

    act(() => {
      startTransition(() => navigate("b"));
    });
    await expectEditorRevision(1);

    await act(async () => { resolveUpdate({}); });
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    await expectEditorRevision(2);
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
    mockEditingSessionRevisions(1, 1, 10, 2);
    const startPreview = vi.spyOn(api, "startExactPreview")
      .mockImplementation(() => new Promise((resolve) => { resolveOldPreview = resolve; }) as never);

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "미리보기 새로 만들기" }));
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(10);

    await act(async () => { resolveOldPreview({}); });
    expect(load).toHaveBeenCalledTimes(3);
    await expectEditorRevision(10);
  });

  it("keeps polling while an exact preview remains pending across more than one refresh", async () => {
    const pending = {
      ...narrationManifest(1),
      exact_preview: {
        status: "pending" as const,
        url: null,
        source_session_id: "session-a",
        source_session_revision: 1,
        generation_id: "generation-1",
        artifact_revision: 1,
        timeline_start_sec: 0,
        timeline_end_sec: 5,
      },
    };
    const succeeded = {
      ...pending,
      exact_preview: {
        ...pending.exact_preview,
        status: "succeeded" as const,
        url: "/api/projects/project-a/exact-previews/generation-1/content",
      },
    };
    const load = vi.mocked(api.getEditorPlaybackManifest);
    load.mockReset();
    load.mockResolvedValueOnce(pending as never);
    load.mockResolvedValueOnce(pending as never);
    load.mockResolvedValueOnce(succeeded as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);

    expect(await screen.findByText("미리보기를 준비하고 있어요.")).toBeVisible();
    expect(await screen.findByLabelText("편집본 미리보기", {}, { timeout: 5_000 })).toHaveAttribute(
      "src",
      "/api/projects/project-a/exact-previews/generation-1/content",
    );
    expect(load).toHaveBeenCalledTimes(3);
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
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
    expect(await screen.findByText("한 가지를 골랐어요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "추천 미리 듣기" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "추천 미리 듣기" }));
    expect(document.querySelectorAll(".vb-preview-stage")).toHaveLength(1);
    expect(document.querySelectorAll(".vb-editor-right-dock audio, .vb-editor-right-dock video")).toHaveLength(0);

    vi.spyOn(api, "reloadDirectorSession").mockRejectedValueOnce(new Error("blocked"));
    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
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
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
    fireEvent.change(await screen.findByLabelText("유진에게 요청하기"), { target: { value: "A 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await waitFor(() => expect(prepared).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    await act(async () => { resolveOldSend({ kind: "exchange", exchange: { user_message: {}, assistant_message: { proposal_id: "proposal-session-a", text: "stale A" } } }); });
    expect(screen.queryByText("stale A")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
    fireEvent.click(await screen.findByRole("button", { name: "선택한 추천 적용" }));
    await waitFor(() => expect(preflight).toHaveBeenCalledWith("project-b", "proposal-session-b"));
    expect(batchApply).toHaveBeenCalledWith("project-b", "proposal-session-b", { candidate_ids: ["candidate-1"], expected_revision: 1 });
  });

  it("keeps reload read-only until the creator explicitly starts Eugene, then creates one conversation and proposal", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({ conversation: null, messages: [], proposal: null, references: [] } as never);
    const createConversation = vi.spyOn(api, "createDirectorConversation").mockResolvedValue({ conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" } as never);
    const createProposal = vi.spyOn(api, "createDirectorProposal").mockResolvedValue(directorProposal() as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    expect(createConversation).not.toHaveBeenCalled();
    expect(createProposal).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
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
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
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

  it("keeps Workbench local state mounted until a same-route Director refresh pair swaps atomically", async () => {
    let resolveManifestRefresh!: (value: ReturnType<typeof narrationManifest>) => void;
    let resolveSessionRefresh!: (value: ReturnType<typeof editingSession>) => void;
    const manifestLoad = vi.mocked(api.getEditorPlaybackManifest);
    manifestLoad.mockReset()
      .mockResolvedValueOnce(twoNarrationManifest(1) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveManifestRefresh = resolve as typeof resolveManifestRefresh; }));
    const sessionLoad = vi.mocked(api.getEditingSession);
    sessionLoad.mockReset()
      .mockResolvedValueOnce(editingSession("project-a", "session-a", 1) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSessionRefresh = resolve as typeof resolveSessionRefresh; }));
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [],
      proposal: directorProposal(),
      references: [],
    } as never);
    vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
    vi.spyOn(api, "batchApplyDirectorProposal").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    const workbench = screen.getByRole("region", { name: "편집 작업판" });
    const timeline = screen.getByTestId("timeline-track");
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
    const composer = await screen.findByLabelText("유진에게 요청하기");
    fireEvent.change(composer, { target: { value: "작성 중인 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "n-2 클립 선택" }));
    timeline.scrollLeft = 37;
    fireEvent.click(screen.getByRole("button", { name: "선택한 추천 적용" }));

    await waitFor(() => expect(manifestLoad).toHaveBeenCalledTimes(2));
    expect(sessionLoad).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("region", { name: "편집 작업판" })).toBe(workbench);
    expect(screen.getByTestId("timeline-track")).toBe(timeline);
    expect(screen.getByTestId("timeline-track").scrollLeft).toBe(37);
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("작성 중인 요청");
    expect(screen.getByRole("button", { name: "n-2 클립 선택" })).toHaveAttribute("aria-pressed", "true");
    await expectEditorRevision(1);

    await act(async () => { resolveManifestRefresh(twoNarrationManifest(2)); });
    await expectEditorRevision(1);
    expect(screen.getByRole("region", { name: "편집 작업판" })).toBe(workbench);

    await act(async () => { resolveSessionRefresh(editingSession("project-a", "session-a", 2)); });
    await expectEditorRevision(2);
    expect(screen.getByRole("region", { name: "편집 작업판" })).toBe(workbench);
    expect(screen.getByTestId("timeline-track")).toBe(timeline);
    expect(screen.getByTestId("timeline-track").scrollLeft).toBe(37);
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("작성 중인 요청");
    expect(screen.getByRole("button", { name: "n-2 클립 선택" })).toHaveAttribute("aria-pressed", "true");
  });

  it("atomically refreshes the manifest and editing session after a Director batch apply failure", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [],
      proposal: directorProposal(),
      references: [],
    } as never);
    vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
    vi.spyOn(api, "batchApplyDirectorProposal").mockRejectedValue(new Error("apply failed"));
    const manifestLoad = vi.mocked(api.getEditorPlaybackManifest);
    manifestLoad.mockReset()
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockRejectedValueOnce(new Error("refresh failed"));
    const sessionLoad = vi.mocked(api.getEditingSession);
    sessionLoad.mockReset()
      .mockResolvedValueOnce(editingSession("project-a", "session-a", 1) as never)
      .mockResolvedValueOnce(editingSession("project-a", "session-a", 1) as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    const workbench = screen.getByRole("region", { name: "편집 작업판" });
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
    fireEvent.click(await screen.findByRole("button", { name: "선택한 추천 적용" }));

    await waitFor(() => expect(manifestLoad).toHaveBeenCalledTimes(2));
    expect(sessionLoad).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("button", { name: "직접 편집하기" })).toBeVisible();
    expect(screen.getByText("최신 편집 내용을 불러오지 못했어요. 새로고침한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(screen.getByRole("region", { name: "편집 작업판" })).toBe(workbench);
    await expectEditorRevision(1);
  });

  it("locks the composer while Eugene is sending and reuses its client ID only for the explicit Retry-After retry", async () => {
    let resolveSend!: (value: { kind: "in_progress"; retryAfterSeconds: number }) => void;
    const retry = vi.fn().mockResolvedValue({ kind: "exchange", exchange: { user_message: { message_id: "user-2", text: "A 요청" }, assistant_message: { message_id: "assistant-2", proposal_id: null, text: "다시 확인했어요." } } });
    const prepare = vi.spyOn(api, "prepareDirectorMessage").mockImplementation(() => ({ clientMessageId: "stable-a", send: () => new Promise((resolve) => { resolveSend = resolve; }), retry }) as never);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" }, messages: [], proposal: null, references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
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
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "유진에게 요청하기" }), { target: { value: "A 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await act(async () => { resolveSend({ kind: "in_progress", retryAfterSeconds: 0 }); });
    fireEvent.click(await screen.findByRole("button", { name: "같은 요청 다시 보내기" }));
    expect(retry).toHaveBeenCalledTimes(1);

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    await act(async () => { resolveRetry({ kind: "exchange", exchange: { user_message: { message_id: "user-a", text: "A 요청" }, assistant_message: { message_id: "assistant-a", proposal_id: null, text: "stale retry" } } }); });
    expect(screen.queryByText("stale retry")).toBeNull();
    await expectEditorRevision(1);
  });
});
