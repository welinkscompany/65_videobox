import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { startTransition, StrictMode, Suspense, useState } from "react";

import { ApiConflictError, DirectorProposalBlockedError, api } from "../../../api";
import { EditorWorkbenchRoute, affectedAreaLabel, findHermesRunProposalId, partialStatusLabel, prepareProjectAssetBrowserPreview } from "./EditorWorkbenchRoute";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("links a terminal proposal only to the exact Hermes run assistant", () => {
  const messages = [
    { message_id: "old", role: "assistant", proposal_id: "proposal-old", metadata: { hermes_run_id: "run-old" } },
    { message_id: "current", role: "assistant", proposal_id: null, metadata: { hermes_run_id: "run-current" } },
  ] as never;

  expect(findHermesRunProposalId(messages, "run-current")).toBeNull();
  expect(findHermesRunProposalId(messages, "run-missing")).toBeNull();
  expect(findHermesRunProposalId(messages, "run-old")).toBe("proposal-old");
});

it("polls a browser preview until a bounded ready URL is available", async () => {
  const preparing = { status: "running", job_id: "job-1", content_url: null, source_sha256: "sha", profile: "profile", error_code: null } as const;
  vi.spyOn(api, "prepareAssetBrowserPreview").mockResolvedValue(preparing);
  vi.spyOn(api, "getAssetBrowserPreview")
    .mockResolvedValueOnce(preparing)
    .mockResolvedValueOnce({ ...preparing, status: "ready", content_url: "/api/proxy/video-1" });
  const sleep = vi.fn().mockResolvedValue(undefined);

  await expect(prepareProjectAssetBrowserPreview("project-a", "video-1", new AbortController().signal, { sleep, maxPolls: 3 })).resolves.toBe("/api/proxy/video-1");
  expect(sleep).toHaveBeenNthCalledWith(1, 100, expect.any(AbortSignal));
  expect(sleep).toHaveBeenNthCalledWith(2, 200, expect.any(AbortSignal));
});

it("stops browser preview polling on a bounded failed response", async () => {
  vi.spyOn(api, "prepareAssetBrowserPreview").mockResolvedValue({ status: "failed", job_id: "job-1", content_url: null, source_sha256: "sha", profile: "profile", error_code: "PREVIEW_RENDER_FAILED" });
  const getPreview = vi.spyOn(api, "getAssetBrowserPreview");
  await expect(prepareProjectAssetBrowserPreview("project-a", "video-1", new AbortController().signal)).rejects.toThrow("PREVIEW_RENDER_FAILED");
  expect(getPreview).not.toHaveBeenCalled();
});

const manifest = (projectId: string, sessionId: string) => ({ project_id: projectId, session_id: sessionId, timeline_id: `timeline-${sessionId}`, session_revision: 1, timeline_version: "v1", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 1 }, tracks: [], captions: [], gap_slots: [], source_status: { status: "current", source_session_id: sessionId, source_session_revision: 1 }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: sessionId, source_session_revision: 1 } });

// TimelineDock's clip selection button no longer shows the raw clip ID as
// its accessible name (F-3/Task 7) -- it shows a human-readable name like
// "내레이션 1번째 장면, 0초부터". Locating the button by data-clip-id keeps
// these fixtures decoupled from that display-only formatting.
function clipSelectionButton(clipId: string): HTMLElement {
  const clip = screen.getAllByTestId("timeline-clip").find((item) => item.getAttribute("data-clip-id") === clipId);
  if (!clip) throw new Error(`Missing timeline clip ${clipId}`);
  const button = clip.querySelector('[data-native-control="timeline-clip-select"]');
  if (!button) throw new Error(`Missing selection control for ${clipId}`);
  return button as HTMLElement;
}

async function findClipSelectionButton(clipId: string): Promise<HTMLElement> {
  return waitFor(() => clipSelectionButton(clipId));
}
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

// 추천 카드 이름 앞에는 이제 **장면**이 붙는다(`2번째 장면 · 자막 첫머리 — 자산이름 선택`).
// 아래 픽스처들이 확인하는 것은 장면 이름이 아니라 뒤쪽 후보이므로, 이름의 끝만 맞춘다.
const endingWith = (text: string) => (name: string) => name.endsWith(text);

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

const memoryCandidate = (
  patch: Record<string, unknown> = {},
) => ({
  candidate_id: "memory-candidate-1",
  project_id: "project-a",
  conversation_id: "conversation-1",
  client_request_id: "memory-request-1",
  source_message_ids: ["message-1"],
  memory_scope: "creator",
  category: "pacing",
  proposed_text: "빠른 컷 편집을 선호합니다.",
  status: "pending",
  storage_status: "not_requested",
  retryable: false,
  created_at: "2026-07-30T12:00:00Z",
  updated_at: "2026-07-30T12:00:00Z",
  ...patch,
});

const yujinMediaProposal = (
  kind: "broll" | "bgm" | "sfx" = "broll",
  proposalId = `yujin-${kind}`,
) => ({
  ...directorProposal(proposalId),
  diff: { proposal_mode: "yujin_actionable_media_v1" },
  candidates: [{
    ...directorProposal().candidates[0],
    candidate_id: `candidate-${kind}`,
    visible_reference_code: `P01-${kind.toUpperCase()}-01`,
    media_type: kind,
    asset_id: `source-${kind}`,
    availability: "actionable",
    review_status: "approved",
    preview_uri: null,
    controls: kind === "broll"
      ? { fit: "crop" }
      : kind === "bgm"
        ? { volume: 0.6, fade_in_sec: 0.5, fade_out_sec: 0.75 }
        : { volume: 0.4 },
    expected_content_sha256: "a".repeat(64),
    media_revision: "media-r1",
    canonical_metadata: {
      schema_version: "videobox.yujin-response.v1",
      proposal_kind: kind,
      yujin_actionable_media: true,
      source_media_kind: kind === "broll" ? "broll_video" : kind,
      target_segment_id: "segment-1",
      preview_summary: `${kind} 추천 세부 내용`,
      base_session_revision: 1,
      asset_index_revision: 1,
    },
  }],
});

const yujinB4Proposal = (
  kind: "caption-text" | "caption-style" | "voice" | "explanation" | "image" | "table",
) => {
  const mediaType = kind.startsWith("caption") ? "caption" : kind === "voice" ? "voice" : "overlay";
  const commandKind = kind === "caption-text"
    ? "set_caption_text"
    : kind === "caption-style"
      ? "set_caption_style"
      : kind === "voice"
        ? "apply_tts_candidate"
        : "apply_overlay";
  const controls = kind === "caption-text"
    ? { text: "추천 자막" }
    : kind === "caption-style"
      ? {
        scope: "current_caption",
        style: {
          font_family: "Pretendard", font_size_px: 42, text_color: "#FFFFFFFF",
          outline_color: "#000000FF", outline_width_px: 2, background_color: "#00000000",
          position_x_percent: 50, position_y_percent: 88, horizontal_align: "center",
          safe_area_enabled: true, shadow_blur_px: 0,
        },
      }
      : kind === "voice"
        ? { candidate_id: "tts_candidate_001", asset_id: "asset-tts" }
        : kind === "explanation"
          ? { overlay_kind: "explanation-card", title: "핵심", body: "설명", text: "장면 설명" }
          : kind === "image"
            ? { overlay_kind: "image", asset_id: "asset-image", text: "장면 이미지" }
            : { overlay_kind: "table", columns: ["항목", "값"], rows: [["속도", "빠름"]], text: "장면 표" };
  return {
    ...directorProposal(`yujin-${kind}`),
    diff: { proposal_mode: "yujin_actionable_v1" },
    candidates: [{
      ...directorProposal().candidates[0],
      candidate_id: `candidate-${kind}`,
      visible_reference_code: `P01-${kind.toUpperCase()}-01`,
      media_type: mediaType,
      asset_id: kind === "voice" ? "asset-tts" : kind === "image" ? "asset-image" : `candidate-${kind}`,
      availability: "actionable",
      review_status: "approved",
      preview_uri: null,
      controls,
      expected_content_sha256: kind === "voice" || kind === "image" ? "a".repeat(64) : null,
      media_revision: "media-r1",
      canonical_metadata: {
        schema_version: "videobox.yujin-response.v1",
        proposal_kind: mediaType,
        yujin_actionable_operation: true,
        command_kind: commandKind,
        ...(kind === "voice" ? { candidate_id: "tts_candidate_001" } : {}),
        target_segment_id: "segment-1",
        preview_summary: `${kind} 추천 세부 내용`,
        requires_materialization: false,
      },
    }],
  };
};

function pointer(target: Element, type: string, clientX: number) {
  fireEvent(target, new MouseEvent(type, { bubbles: true, cancelable: true, clientX }));
}

async function openAssetBrowser() {
  // 승인 2026-08-30(버튼 단위 벤치마킹 2단계) -- 미디어는 이제 편집기 맨 위의
  // 콘텐츠 탭(`role="tab"`)이다. 예전 아이콘 단추(`role="button"`)가 아니다.
  fireEvent.click(await screen.findByRole("tab", { name: "미디어" }));
  return screen.findByRole("dialog", { name: "미디어" });
}

/** 캡컷식 최상위 탭 분리(2026-08-27) 뒤 음악·효과음은 `오디오` 탭에 있다.
 *  도크를 여는 단추와 이름이 겹치지 않는다 -- 그쪽은 `button`, 이쪽은 `tab`이다. */
function openAudioPane() {
  fireEvent.click(screen.getByRole("tab", { name: "오디오" }));
}

async function openInspector() {
  fireEvent.click(await findClipSelectionButton("n-1"));
  fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
  await screen.findByRole("dialog", { name: "세부 정보" });
  return screen.findByRole("region", { name: "편집 항목" });
}

describe("EditorWorkbenchRoute", () => {
  beforeEach(() => {
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(narrationManifest(1) as never);
    vi.spyOn(api, "getEditingSession").mockImplementation(
      (projectId, sessionId) => Promise.resolve(editingSession(projectId, sessionId)) as never,
    );
    vi.spyOn(api, "listOutputVariants").mockResolvedValue({ variants: [] });
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([] as never);
    vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [] } as never);
    vi.spyOn(api, "listLibraryAssets").mockResolvedValue({ assets: [], total: 0 } as never);
    vi.spyOn(api, "listJobs").mockResolvedValue([]);
    vi.spyOn(api, "listTtsCandidates").mockResolvedValue({ candidates: [] });
    vi.spyOn(api, "listYujinMemoryCandidates").mockResolvedValue([]);
  });

  it("accepts a local-first exchange as a memory source", async () => {
    // The editor screen chats through the local route, which produces no
    // hermes_run_id.  Requiring one left the owner unable to save a memory
    // from any conversation they actually had on screen.
    const localMessages = [
      {
        message_id: "local-user-1",
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
        role: "user",
        text: "자막은 어떻게 두는 게 좋을까?",
        proposal_id: null,
        metadata: {},
        client_message_id: "client-local-1",
        created_at: "2026-08-08T12:00:00Z",
      },
      {
        message_id: "local-assistant-1",
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
        role: "assistant",
        text: "두 줄 이내를 권합니다.",
        proposal_id: null,
        metadata: {},
        client_message_id: null,
        created_at: "2026-08-08T12:00:01Z",
      },
    ];
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: {
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
      },
      messages: localMessages,
      proposal: null,
      references: [],
    } as never);
    const create = vi.spyOn(api, "createYujinMemoryCandidate")
      .mockResolvedValue(memoryCandidate({
        source_message_ids: ["local-user-1", "local-assistant-1"],
        category: "caption",
        proposed_text: "자막은 두 줄 이내를 선호합니다.",
      }) as never);
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000099",
    );

    render(
      <EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />,
    );
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    const panel = await screen.findByRole("region", { name: "유진 기억" });
    fireEvent.change(within(panel).getByLabelText("기억 종류"), {
      target: { value: "caption" },
    });
    fireEvent.change(within(panel).getByLabelText("기억 후보"), {
      target: { value: "자막은 두 줄 이내를 선호합니다." },
    });
    fireEvent.click(within(panel).getByRole(
      "button", { name: "기억 후보 만들기" },
    ));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create.mock.calls[0][1].source_message_ids).toEqual([
      "local-user-1", "local-assistant-1",
    ]);
  });

  it("creates one typed candidate only on explicit click from completed durable current messages", async () => {
    const durableMessages = Array.from({ length: 10 }, (_, index) => ({
      message_id: `message-${index + 1}`,
      conversation_id: "conversation-1",
      project_id: "project-a",
      session_id: "session-a",
      role: index % 2 === 0 ? "user" : "assistant",
      text: `완료된 메시지 ${index + 1}`,
      proposal_id: null,
      metadata: index % 2 === 0
        ? {}
        : { hermes_status: "completed", hermes_run_id: `run-${index}` },
      client_message_id: index % 2 === 0 ? `client-${index}` : null,
      created_at: "2026-07-30T12:00:00Z",
    }));
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: {
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
      },
      messages: durableMessages,
      proposal: null,
      references: [],
    } as never);
    vi.mocked(api.listYujinMemoryCandidates)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        memoryCandidate({
          source_message_ids: durableMessages.slice(-8).map(
            (message) => message.message_id,
          ),
          category: "caption",
          proposed_text: "자막은 두 줄 이내를 선호합니다.",
        }),
      ] as never);
    const create = vi.spyOn(
      api, "createYujinMemoryCandidate",
    ).mockResolvedValue(memoryCandidate({
      source_message_ids: durableMessages.slice(-8).map(
        (message) => message.message_id,
      ),
      category: "caption",
      proposed_text: "자막은 두 줄 이내를 선호합니다.",
    }) as never);
    const approve = vi.spyOn(api, "approveYujinMemoryCandidate");
    const store = vi.spyOn(api, "storeYujinMemoryCandidate");
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000071",
    );

    render(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));
    const panel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    expect(create).not.toHaveBeenCalled();
    expect(approve).not.toHaveBeenCalled();
    expect(store).not.toHaveBeenCalled();

    fireEvent.change(within(panel).getByLabelText("기억 종류"), {
      target: { value: "caption" },
    });
    fireEvent.change(within(panel).getByLabelText("기억 후보"), {
      target: { value: "자막은 두 줄 이내를 선호합니다." },
    });
    expect(create).not.toHaveBeenCalled();
    fireEvent.click(within(panel).getByRole(
      "button", { name: "기억 후보 만들기" },
    ));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create).toHaveBeenCalledWith("project-a", {
      conversation_id: "conversation-1",
      client_request_id:
        "memory-create-00000000-0000-4000-8000-000000000071",
      source_message_ids: [
        "message-3", "message-4", "message-5", "message-6",
        "message-7", "message-8", "message-9", "message-10",
      ],
      memory_scope: "creator",
      category: "caption",
      proposed_text: "자막은 두 줄 이내를 선호합니다.",
    });
    await waitFor(() => expect(
      api.listYujinMemoryCandidates,
    ).toHaveBeenCalledTimes(2));
    expect(api.listYujinMemoryCandidates).toHaveBeenLastCalledWith(
      "project-a", "conversation-1",
    );
    expect(approve).not.toHaveBeenCalled();
    expect(store).not.toHaveBeenCalled();
    expect(within(panel).getByText(
      "자막은 두 줄 이내를 선호합니다.",
    )).toBeVisible();
  });

  it("keeps the post-create list when an older initial list resolves last", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: {
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
      },
      messages: [{
        message_id: "message-1",
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
        role: "user",
        text: "빠른 컷으로 편집해 줘.",
        proposal_id: null,
        metadata: {},
        client_message_id: "client-1",
        created_at: "2026-07-30T12:00:00Z",
      }, {
        message_id: "message-2",
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
        role: "assistant",
        text: "빠른 컷 편집을 제안합니다.",
        proposal_id: null,
        metadata: {
          hermes_status: "completed",
          hermes_run_id: "run-1",
        },
        client_message_id: null,
        created_at: "2026-07-30T12:00:01Z",
      }],
      proposal: null,
      references: [],
    } as never);
    let resolveInitialList!: (value: unknown) => void;
    let resolveFreshList!: (value: unknown) => void;
    vi.mocked(api.listYujinMemoryCandidates)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveInitialList = resolve;
      }) as never)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveFreshList = resolve;
      }) as never);
    vi.spyOn(api, "createYujinMemoryCandidate").mockResolvedValue(
      memoryCandidate({
        source_message_ids: ["message-1", "message-2"],
      }) as never,
    );
    let resolveStore!: (value: unknown) => void;
    vi.spyOn(api, "storeYujinMemoryCandidate").mockImplementation(
      () => new Promise((resolve) => {
        resolveStore = resolve;
      }) as never,
    );
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000073",
    );

    render(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    await waitFor(() => expect(
      api.listYujinMemoryCandidates,
    ).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));
    const panel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    const history = screen.getByRole("log", { name: "유진 대화" });
    Object.defineProperties(history, {
      scrollHeight: { configurable: true, value: 200 },
      clientHeight: { configurable: true, value: 80 },
      scrollTop: {
        configurable: true,
        writable: true,
        value: 51,
      },
    });
    fireEvent.scroll(history);
    fireEvent.change(within(panel).getByLabelText("기억 후보"), {
      target: { value: "빠른 컷 편집을 선호합니다." },
    });
    fireEvent.click(within(panel).getByRole(
      "button", { name: "기억 후보 만들기" },
    ));
    await waitFor(() => expect(
      api.listYujinMemoryCandidates,
    ).toHaveBeenCalledTimes(2));
    await act(async () => {
      resolveFreshList([
        memoryCandidate({
          status: "approved",
          storage_status: "not_requested",
          source_message_ids: ["message-1", "message-2"],
        }),
      ]);
    });
    expect(await within(panel).findByText(
      "빠른 컷 편집을 선호합니다.",
    )).toBeVisible();

    fireEvent.change(within(panel).getByLabelText("기억 후보"), {
      target: { value: "다음 후보 초안" },
    });
    fireEvent.click(within(panel).getByRole(
      "button", { name: "저장하기" },
    ));
    expect(await within(panel).findByText("저장 중")).toBeVisible();

    await act(async () => {
      resolveInitialList([]);
    });

    expect(within(panel).getByText(
      "빠른 컷 편집을 선호합니다.",
    )).toBeVisible();
    expect(within(panel).getByText("저장 중")).toBeVisible();
    expect(within(panel).getByLabelText("기억 후보"))
      .toHaveValue("다음 후보 초안");
    expect(history.scrollTop).toBe(51);

    await act(async () => {
      resolveStore({
        candidate_id: "memory-candidate-1",
        status: "approved",
        storage_status: "stored",
        retryable: false,
      });
    });
  });

  it("fences late explicit candidate creation after route/project/conversation epoch change", async () => {
    vi.mocked(api.getEditorPlaybackManifest).mockImplementation(
      (projectId, sessionId) => Promise.resolve(
        manifest(projectId, sessionId),
      ) as never,
    );
    vi.spyOn(api, "reloadDirectorSession").mockImplementation(
      (projectId, sessionId) => Promise.resolve({
        conversation: {
          conversation_id: `conversation-${projectId}`,
          project_id: projectId,
          session_id: sessionId,
        },
        messages: [{
          message_id: `message-${projectId}`,
          conversation_id: `conversation-${projectId}`,
          project_id: projectId,
          session_id: sessionId,
          role: "assistant",
          text: "완료",
          proposal_id: null,
          metadata: {
            hermes_status: "completed",
            hermes_run_id: `run-${projectId}`,
          },
          client_message_id: null,
          created_at: "2026-07-30T12:00:00Z",
        }],
        proposal: null,
        references: [],
      }) as never,
    );
    vi.mocked(api.listYujinMemoryCandidates).mockResolvedValue([]);
    let resolveCreate!: (value: unknown) => void;
    const create = vi.spyOn(
      api, "createYujinMemoryCandidate",
    ).mockImplementation(() => new Promise((resolve) => {
      resolveCreate = resolve;
    }) as never);
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000072",
    );

    const rendered = render(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));
    const panel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    fireEvent.change(within(panel).getByLabelText("기억 후보"), {
      target: { value: "빠른 컷 편집을 선호합니다." },
    });
    fireEvent.click(within(panel).getByRole(
      "button", { name: "기억 후보 만들기" },
    ));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));

    rendered.rerender(
      <EditorWorkbenchRoute
        projectId="project-b"
        sessionId="session-b"
      />,
    );
    await expectEditorRevision(1);
    const listCallsBeforeLateResult = vi.mocked(
      api.listYujinMemoryCandidates,
    ).mock.calls.length;
    await act(async () => {
      resolveCreate(memoryCandidate({
        project_id: "project-a",
        conversation_id: "conversation-project-a",
      }));
    });

    expect(vi.mocked(api.listYujinMemoryCandidates).mock.calls)
      .toHaveLength(listCallsBeforeLateResult);
    const currentPanel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    expect(currentPanel).not.toHaveTextContent(
      "빠른 컷 편집을 선호합니다.",
    );
  });

  it("owns memory state across the drawer and orders one approve click before store", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: {
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
      },
      messages: [],
      proposal: null,
      references: [],
    } as never);
    vi.mocked(api.listYujinMemoryCandidates).mockResolvedValue([
      memoryCandidate(),
    ] as never);
    const approve = vi.spyOn(
      api, "approveYujinMemoryCandidate",
    ).mockResolvedValue(memoryCandidate({
      status: "approved",
    }) as never);
    let resolveStore!: (value: unknown) => void;
    const store = vi.spyOn(
      api, "storeYujinMemoryCandidate",
    ).mockImplementation(() => new Promise((resolve) => {
      resolveStore = resolve;
    }) as never);
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000031",
    );

    render(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    const player = screen.getByRole("region", { name: "미리보기" });
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));
    const panel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    expect(api.listYujinMemoryCandidates).toHaveBeenCalledWith(
      "project-a", "conversation-1",
    );
    expect(store).not.toHaveBeenCalled();

    const pacingCandidate = within(panel).getByText(
      "빠른 컷 편집을 선호합니다.",
    ).closest("article");
    expect(pacingCandidate).not.toBeNull();
    fireEvent.click(within(pacingCandidate!).getByRole(
      "button", { name: "승인하고 저장" },
    ));
    await waitFor(() => expect(store).toHaveBeenCalledTimes(1));
    expect(approve).toHaveBeenCalledTimes(1);
    expect(approve.mock.invocationCallOrder[0])
      .toBeLessThan(store.mock.invocationCallOrder[0]);
    expect(store).toHaveBeenCalledWith(
      "project-a",
      "memory-candidate-1",
      "memory-store-00000000-0000-4000-8000-000000000031",
    );
    expect(within(panel).getByText("저장 중")).toBeVisible();
    resolveStore({
      candidate_id: "memory-candidate-1",
      status: "approved",
      storage_status: "stored",
      retryable: false,
    });
    await waitFor(() => expect(
      within(panel).getByText("저장됨"),
    ).toBeVisible());

    const history = screen.getByRole("log", { name: "유진 대화" });
    Object.defineProperties(history, {
      scrollHeight: { configurable: true, value: 200 },
      clientHeight: { configurable: true, value: 80 },
      scrollTop: {
        configurable: true,
        writable: true,
        value: 51,
      },
    });
    fireEvent.scroll(history);
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));

    expect(await screen.findByText("저장됨")).toBeVisible();
    expect(screen.getByRole("log", { name: "유진 대화" }).scrollTop)
      .toBe(51);
    expect(screen.getByRole("region", { name: "미리보기" }))
      .toBe(player);
    expect(document.querySelectorAll(".vb-preview-stage")).toHaveLength(1);
  });

  it("keeps chat/manual editing usable after save failure and retries only on a new click", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: {
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
      },
      messages: [],
      proposal: null,
      references: [],
    } as never);
    vi.mocked(api.listYujinMemoryCandidates).mockResolvedValue([
      memoryCandidate(),
      memoryCandidate({
        candidate_id: "memory-rejected",
        client_request_id: "memory-request-2",
        proposed_text: "차분한 영상 분위기를 선호합니다.",
        category: "tone",
      }),
    ] as never);
    vi.spyOn(api, "approveYujinMemoryCandidate").mockImplementation(
      (_projectId, candidateId) => Promise.resolve(memoryCandidate({
        candidate_id: candidateId,
        status: "approved",
      })) as never,
    );
    const reject = vi.spyOn(
      api, "rejectYujinMemoryCandidate",
    ).mockResolvedValue(memoryCandidate({
      candidate_id: "memory-rejected",
      status: "rejected",
      category: "tone",
      proposed_text: "차분한 영상 분위기를 선호합니다.",
    }) as never);
    const store = vi.spyOn(api, "storeYujinMemoryCandidate")
      .mockRejectedValueOnce(new Error("memory unavailable"))
      .mockResolvedValueOnce({
        candidate_id: "memory-candidate-1",
        status: "approved",
        storage_status: "stored",
        retryable: false,
      });
    vi.spyOn(globalThis.crypto, "randomUUID")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000041")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000042");

    render(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));
    const panel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    expect(store).not.toHaveBeenCalled();

    const pacingCandidate = within(panel).getByText(
      "빠른 컷 편집을 선호합니다.",
    ).closest("article");
    expect(pacingCandidate).not.toBeNull();
    fireEvent.click(within(pacingCandidate!).getByRole(
      "button", { name: "승인하고 저장" },
    ));
    expect(await within(panel).findByRole(
      "button", { name: "저장 다시 시도" },
    )).toBeEnabled();
    expect(store).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("유진에게 요청하기")).toBeEnabled();
    expect(clipSelectionButton("n-1"))
      .toBeEnabled();

    fireEvent.click(within(panel).getByRole(
      "button", { name: "저장 다시 시도" },
    ));
    await waitFor(() => expect(store).toHaveBeenCalledTimes(2));
    expect(store.mock.calls.map((call) => call[2])).toEqual([
      "memory-store-00000000-0000-4000-8000-000000000041",
      "memory-store-00000000-0000-4000-8000-000000000042",
    ]);
    fireEvent.click(within(panel).getByRole(
      "button", { name: "거절" },
    ));
    await waitFor(() => expect(reject).toHaveBeenCalledWith(
      "project-a", "memory-rejected",
    ));
    expect(store).toHaveBeenCalledTimes(2);
  });

  it("deletes stored memory only on click and leaves an explicit retry after failure", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: {
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
      },
      messages: [],
      proposal: null,
      references: [],
    } as never);
    vi.mocked(api.listYujinMemoryCandidates).mockResolvedValue([
      memoryCandidate({
        status: "approved",
        storage_status: "stored",
      }),
    ] as never);
    const remove = vi.spyOn(api, "deleteYujinMemoryCandidate")
      .mockRejectedValueOnce(new Error("memory unavailable"))
      .mockResolvedValueOnce({
        candidate_id: "memory-candidate-1",
        status: "approved",
        storage_status: "deleted",
        retryable: false,
      });

    render(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));
    const panel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    expect(remove).not.toHaveBeenCalled();

    fireEvent.click(within(panel).getByRole(
      "button", { name: "기억 삭제" },
    ));
    expect(await within(panel).findByRole(
      "button", { name: "삭제 다시 시도" },
    )).toBeEnabled();
    expect(remove).toHaveBeenCalledTimes(1);

    fireEvent.click(within(panel).getByRole(
      "button", { name: "삭제 다시 시도" },
    ));
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(2));
    expect(await within(panel).findByText("삭제됨")).toBeVisible();
  });

  it("does not store when explicit approval fails", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: {
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
      },
      messages: [],
      proposal: null,
      references: [],
    } as never);
    vi.mocked(api.listYujinMemoryCandidates).mockResolvedValue([
      memoryCandidate(),
    ] as never);
    const approve = vi.spyOn(
      api, "approveYujinMemoryCandidate",
    ).mockRejectedValue(new Error("stale candidate"));
    const store = vi.spyOn(api, "storeYujinMemoryCandidate");

    render(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));
    const panel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );

    fireEvent.click(within(panel).getByRole(
      "button", { name: "승인하고 저장" },
    ));
    await waitFor(() => expect(approve).toHaveBeenCalledTimes(1));
    expect(store).not.toHaveBeenCalled();
    expect(within(panel).getByRole(
      "button", { name: "승인하고 저장" },
    )).toBeEnabled();
  });

  it("retries an expired claimed memory only after an explicit click", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: {
        conversation_id: "conversation-1",
        project_id: "project-a",
        session_id: "session-a",
      },
      messages: [],
      proposal: null,
      references: [],
    } as never);
    vi.mocked(api.listYujinMemoryCandidates).mockResolvedValue([
      memoryCandidate({
        status: "approved",
        storage_status: "claimed",
        retryable: true,
      }),
    ] as never);
    const store = vi.spyOn(
      api, "storeYujinMemoryCandidate",
    ).mockResolvedValue({
      candidate_id: "memory-candidate-1",
      status: "approved",
      storage_status: "stored",
      retryable: false,
    });
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000051",
    );

    render(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));
    const panel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    expect(store).not.toHaveBeenCalled();

    fireEvent.click(within(panel).getByRole(
      "button", { name: "저장 다시 시도" },
    ));
    await waitFor(() => expect(store).toHaveBeenCalledWith(
      "project-a",
      "memory-candidate-1",
      "memory-store-00000000-0000-4000-8000-000000000051",
    ));
    expect(await within(panel).findByText("저장됨")).toBeVisible();
  });

  it("ignores late memory list and approval results after route navigation", async () => {
    vi.mocked(api.getEditorPlaybackManifest).mockImplementation(
      (projectId, sessionId) => Promise.resolve(
        manifest(projectId, sessionId),
      ) as never,
    );
    vi.spyOn(api, "reloadDirectorSession").mockImplementation(
      (projectId, sessionId) => Promise.resolve({
        conversation: {
          conversation_id: `conversation-${projectId}`,
          project_id: projectId,
          session_id: sessionId,
        },
        messages: [],
        proposal: null,
        references: [],
      }) as never,
    );
    let resolveListA!: (value: unknown) => void;
    vi.mocked(api.listYujinMemoryCandidates).mockImplementation(
      (projectId) => projectId === "project-a"
        ? new Promise((resolve) => { resolveListA = resolve; }) as never
        : Promise.resolve([]),
    );
    const rendered = render(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    await waitFor(() => expect(
      api.listYujinMemoryCandidates,
    ).toHaveBeenCalledWith("project-a", "conversation-project-a"));

    rendered.rerender(
      <EditorWorkbenchRoute
        projectId="project-b"
        sessionId="session-b"
      />,
    );
    await expectEditorRevision(1);
    await waitFor(() => expect(
      api.listYujinMemoryCandidates,
    ).toHaveBeenCalledWith("project-b", "conversation-project-b"));
    await act(async () => {
      resolveListA([memoryCandidate()]);
    });
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));
    expect(await screen.findByRole(
      "region", { name: "유진 기억" },
    )).not.toHaveTextContent("빠른 컷 편집을 선호합니다.");

    vi.mocked(api.listYujinMemoryCandidates).mockImplementation(
      (projectId) => Promise.resolve(projectId === "project-a"
        ? [memoryCandidate({
          project_id: "project-a",
          conversation_id: "conversation-project-a",
        })]
        : []) as never,
    );
    rendered.rerender(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    let resolveApprove!: (value: unknown) => void;
    const approvePromise = new Promise((resolve) => {
      resolveApprove = resolve;
    });
    const approve = vi.spyOn(
      api, "approveYujinMemoryCandidate",
    ).mockReturnValue(approvePromise as never);
    const store = vi.spyOn(api, "storeYujinMemoryCandidate");
    const routePanel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    fireEvent.click(within(routePanel).getByRole(
      "button", { name: "승인하고 저장" },
    ));
    await waitFor(() => expect(approve).toHaveBeenCalledTimes(1));

    rendered.rerender(
      <EditorWorkbenchRoute
        projectId="project-b"
        sessionId="session-b"
      />,
    );
    await expectEditorRevision(1);
    await act(async () => {
      resolveApprove(memoryCandidate({
        status: "approved",
      }));
    });
    expect(store).not.toHaveBeenCalled();
  });

  it.each([
    {
      action: "store",
      storageStatus: "claimed",
      retryable: true,
      button: "저장 다시 시도",
      terminalStatus: "stored",
    },
    {
      action: "delete",
      storageStatus: "stored",
      retryable: false,
      button: "기억 삭제",
      terminalStatus: "deleted",
    },
  ] as const)("ignores a late memory $action result after route navigation", async ({
    action,
    storageStatus,
    retryable,
    button,
    terminalStatus,
  }) => {
    vi.mocked(api.getEditorPlaybackManifest).mockImplementation(
      (projectId, sessionId) => Promise.resolve(
        manifest(projectId, sessionId),
      ) as never,
    );
    vi.spyOn(api, "reloadDirectorSession").mockImplementation(
      (projectId, sessionId) => Promise.resolve({
        conversation: {
          conversation_id: `conversation-${projectId}`,
          project_id: projectId,
          session_id: sessionId,
        },
        messages: [],
        proposal: null,
        references: [],
      }) as never,
    );
    vi.mocked(api.listYujinMemoryCandidates).mockImplementation(
      (projectId) => Promise.resolve(projectId === "project-a"
        ? [memoryCandidate({
          project_id: "project-a",
          conversation_id: "conversation-project-a",
          status: "approved",
          storage_status: storageStatus,
          retryable,
        })]
        : []) as never,
    );
    let resolveMutation!: (value: unknown) => void;
    const store = vi.spyOn(
      api, "storeYujinMemoryCandidate",
    ).mockImplementation(() => action === "store"
      ? new Promise((resolve) => { resolveMutation = resolve; }) as never
      : Promise.resolve({}) as never);
    const remove = vi.spyOn(
      api, "deleteYujinMemoryCandidate",
    ).mockImplementation(() => action === "delete"
      ? new Promise((resolve) => { resolveMutation = resolve; }) as never
      : Promise.resolve({}) as never);
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000061",
    );

    const rendered = render(
      <EditorWorkbenchRoute
        projectId="project-a"
        sessionId="session-a"
      />,
    );
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole(
      "button", { name: "세부 정보" },
    ));
    const panel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    fireEvent.click(within(panel).getByRole(
      "button", { name: button },
    ));
    await waitFor(() => expect(
      action === "store" ? store : remove,
    ).toHaveBeenCalledTimes(1));

    rendered.rerender(
      <EditorWorkbenchRoute
        projectId="project-b"
        sessionId="session-b"
      />,
    );
    await expectEditorRevision(1);
    await act(async () => {
      resolveMutation({
        candidate_id: "memory-candidate-1",
        status: "approved",
        storage_status: terminalStatus,
        retryable: false,
      });
    });

    const currentPanel = await screen.findByRole(
      "region", { name: "유진 기억" },
    );
    expect(currentPanel).toHaveTextContent(
      "현재 대화에는 확인할 기억이 없어요.",
    );
    expect(currentPanel).not.toHaveTextContent(
      terminalStatus === "stored" ? "저장됨" : "삭제됨",
    );
  });

  it.each([
    ["caption-text", "updateEditingSessionCaption"],
    ["caption-style", "updateEditingSessionCaptionStyle"],
    ["voice", "updateEditingSessionTtsReplacement"],
    ["explanation", "updateEditingSessionExplanationCard"],
    ["image", "updateEditingSessionImageOverlay"],
    ["table", "updateEditingSessionTableOverlay"],
  ] as const)("applies one exact Yujin %s command without materialize or batch", async (kind, apiMethod) => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: yujinB4Proposal(kind), references: [],
    } as never);
    const preflight = vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
    const command = vi.spyOn(api, apiMethod).mockResolvedValue({} as never);
    const materialize = vi.spyOn(api, "materializeDirectorCandidate");
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("radio", { name: endingWith(`P01-${kind.toUpperCase()}-01 선택`) }));
    const applyButton = screen.getByRole("button", { name: "선택한 추천 적용" });
    fireEvent.click(applyButton);
    fireEvent.click(applyButton);

    await waitFor(() => expect(command).toHaveBeenCalledTimes(1));
    expect(preflight).toHaveBeenCalledTimes(1);
    expect(command.mock.calls[0].at(-1)).toEqual(expect.objectContaining({
      proposal_id: `yujin-${kind}`,
      candidate_id: `candidate-${kind}`,
    }));
    if (kind === "image") {
      expect(command).toHaveBeenCalledWith(
        "project-a",
        "session-a",
        "segment-1",
        {
          asset_id: "asset-image",
          candidate_id: "candidate-image",
          expected_revision: 1,
          proposal_id: "yujin-image",
          text: "장면 이미지",
        },
      );
    }
    expect(materialize).not.toHaveBeenCalled();
    expect(batchApply).not.toHaveBeenCalled();
  });

  it.each([
    [false, 100, 100],
    [true, 95, 94],
    [true, 100, 94],
  ] as const)(
    "matches backend caption safe-area semantics for safe=%s y=%s",
    async (safeAreaEnabled, positionYPercent, expectedPositionYPercent) => {
      const base = yujinB4Proposal("caption-style");
      const style = {
        ...(base.candidates[0].controls.style as Record<string, unknown>),
        position_y_percent: positionYPercent,
        safe_area_enabled: safeAreaEnabled,
      };
      vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
        conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
        messages: [],
        proposal: {
          ...base,
          candidates: [{
            ...base.candidates[0],
            controls: { scope: "current_caption", style },
          }],
        },
        references: [],
      } as never);
      vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
      const command = vi.spyOn(api, "updateEditingSessionCaptionStyle").mockResolvedValue({} as never);

      render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
      await expectEditorRevision(1);
      fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
      fireEvent.click(await screen.findByRole("radio", { name: endingWith("P01-CAPTION-STYLE-01 선택") }));
      fireEvent.click(screen.getByRole("button", { name: "선택한 추천 적용" }));

      await waitFor(() => expect(command).toHaveBeenCalledWith(
        "project-a",
        "session-a",
        expect.objectContaining({
          expected_revision: 1,
          scope: "current_caption",
          segment_ids: ["segment-1"],
          style: expect.objectContaining({
            position_y_percent: expectedPositionYPercent,
            safe_area_enabled: safeAreaEnabled,
          }),
        }),
      ));
    },
  );

  it("accepts bounded table items at 256 code points and 1024 UTF-8 bytes", async () => {
    const bounded = "😀".repeat(256);
    const base = yujinB4Proposal("table");
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [],
      proposal: {
        ...base,
        candidates: [{
          ...base.candidates[0],
          controls: {
            overlay_kind: "table",
            columns: [bounded],
            rows: [[bounded]],
            text: "장면 표",
          },
        }],
      },
      references: [],
    } as never);
    vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
    const command = vi.spyOn(api, "updateEditingSessionTableOverlay").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("radio", { name: endingWith("P01-TABLE-01 선택") }));
    fireEvent.click(screen.getByRole("button", { name: "선택한 추천 적용" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "project-a",
      "session-a",
      "segment-1",
      {
        candidate_id: "candidate-table",
        columns: [bounded],
        expected_revision: 1,
        proposal_id: "yujin-table",
        rows: [[bounded]],
        text: "장면 표",
      },
    ));
    expect([...bounded]).toHaveLength(256);
    expect(new TextEncoder().encode(bounded)).toHaveLength(1024);
  });

  it.each([
    ["caption-text", { text: "추천 자막", placement: "bottom" }],
    ["caption-style", {
      scope: "current_caption",
      style: {
        font_family: "Pretendard", font_size_px: 42, text_color: "#FFFFFFFF",
        outline_color: "#000000FF", outline_width_px: 2, background_color: "#00000000",
        position_x_percent: 50, position_y_percent: 101, horizontal_align: "center",
        safe_area_enabled: false, shadow_blur_px: 0,
      },
    }],
    ["voice", { candidate_id: "tts_candidate_001", asset_id: "asset-tts", speed: 1 }],
    ["explanation", {
      overlay_kind: "explanation-card", title: "핵심", body: "설명", text: "장면 설명",
      x: 0.5, y: 0.5, opacity: 1,
    }],
    ["table", {
      overlay_kind: "table", columns: ["항목", "값"], rows: [["한 칸뿐"]], text: "잘못된 표",
    }],
    ["table", {
      overlay_kind: "table", columns: ["a".repeat(257)], rows: [["값"]], text: "긴 열",
    }],
    ["table", {
      overlay_kind: "table", columns: ["항목"], rows: [["a".repeat(257)]], text: "긴 셀",
    }],
  ] as const)("keeps malformed persisted Yujin %s controls disabled", async (kind, controls) => {
    const base = yujinB4Proposal(kind);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [],
      proposal: {
        ...base,
        candidates: [{ ...base.candidates[0], controls }],
      },
      references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    const radio = await screen.findByRole("radio", { name: endingWith(`P01-${kind.toUpperCase()}-01 선택`) });
    fireEvent.click(radio);

    expect(radio).toBeDisabled();
    expect(screen.getByRole("button", { name: "선택한 추천 적용" })).toBeDisabled();
  });

  it("issues zero editor mutations for a forged unsupported persisted Yujin candidate", async () => {
    const base = yujinB4Proposal("caption-text");
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [],
      proposal: {
        ...base,
        candidates: [{
          ...base.candidates[0],
          canonical_metadata: {
            ...base.candidates[0].canonical_metadata,
            command_kind: "delete_project",
          },
        }],
      },
      references: [],
    } as never);
    const captionMutation = vi.spyOn(api, "updateEditingSessionCaption");
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal");
    const materialize = vi.spyOn(api, "materializeDirectorCandidate");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    const candidate = await screen.findByRole("radio", { name: endingWith("P01-CAPTION-TEXT-01 선택") });
    fireEvent.click(candidate);
    fireEvent.click(screen.getByRole("button", { name: "선택한 추천 적용" }));

    expect(candidate).toBeDisabled();
    expect(captionMutation).not.toHaveBeenCalled();
    expect(batchApply).not.toHaveBeenCalled();
    expect(materialize).not.toHaveBeenCalled();
  });

  it("issues zero B4 commands when the route changes while preflight is pending", async () => {
    let resolvePreflight!: (value: { status: string }) => void;
    vi.mocked(api.getEditorPlaybackManifest).mockImplementation(
      (projectId, sessionId) => Promise.resolve(manifest(projectId, sessionId)) as never,
    );
    vi.spyOn(api, "reloadDirectorSession").mockImplementation((projectId, sessionId) => Promise.resolve({
      conversation: { conversation_id: `conversation-${sessionId}`, project_id: String(projectId), session_id: String(sessionId) },
      messages: [], proposal: projectId === "project-a" ? yujinB4Proposal("caption-text") : null, references: [],
    }) as never);
    vi.spyOn(api, "preflightDirectorProposal").mockImplementation(
      () => new Promise((resolve) => { resolvePreflight = resolve; }) as never,
    );
    const caption = vi.spyOn(api, "updateEditingSessionCaption");
    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("radio", { name: endingWith("P01-CAPTION-TEXT-01 선택") }));
    fireEvent.click(screen.getByRole("button", { name: "선택한 추천 적용" }));
    await waitFor(() => expect(api.preflightDirectorProposal).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    await act(async () => { resolvePreflight({ status: "ready" }); });

    expect(caption).not.toHaveBeenCalled();
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
    await waitFor(() => expect(clipSelectionButton("n-2")).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.change(await screen.findByLabelText("유진에게 요청하기"), { target: { value: "작성 중인 요청" } });
    fireEvent.click(clipSelectionButton("n-1"));
    timeline.scrollLeft = 31;

    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-2" />);

    expect(clipSelectionButton("n-1")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("작성 중인 요청");
    expect(screen.getByTestId("timeline-track")).toBe(timeline);
    expect(screen.getByRole("region", { name: "미리보기" })).toBe(preview);
    expect(screen.getByRole("region", { name: "편집 작업판" })).toBe(workbench);
    expect(screen.getByTestId("timeline-track").scrollLeft).toBe(31);
    expect(load).toHaveBeenCalledTimes(1);
    expect(reloadDirector).toHaveBeenCalledTimes(1);

    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-1" />);
    await act(async () => { await Promise.resolve(); });
    expect(clipSelectionButton("n-1")).toHaveAttribute("aria-pressed", "true");
    expect(clipSelectionButton("n-2")).toHaveAttribute("aria-pressed", "false");
    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-2" />);
    await act(async () => { await Promise.resolve(); });
    expect(clipSelectionButton("n-1")).toHaveAttribute("aria-pressed", "false");
    expect(clipSelectionButton("n-2")).toHaveAttribute("aria-pressed", "true");
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("does not focus a blank or unknown requested segment", async () => {
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(twoNarrationManifest(1) as never);
    const blank = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId=" " />);
    await expectEditorRevision(1);
    expect(clipSelectionButton("n-2")).toHaveAttribute("aria-pressed", "false");
    blank.unmount();

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-missing" />);
    await expectEditorRevision(1);
    expect(clipSelectionButton("n-2")).toHaveAttribute("aria-pressed", "false");
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
      await waitFor(() => expect(clipSelectionButton("n-1")).toHaveAttribute("aria-pressed", "true"));

      rendered.rerender(
        <EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId={intermediateSegmentId} />,
      );
      fireEvent.click(clipSelectionButton("n-2"));
      timeline.scrollLeft = 43;

      rendered.rerender(
        <EditorWorkbenchRoute projectId="project-a" sessionId="session-a" requestedSegmentId="segment-1" />,
      );

      await waitFor(() => expect(clipSelectionButton("n-1")).toHaveAttribute("aria-pressed", "true"));
      expect(clipSelectionButton("n-2")).toHaveAttribute("aria-pressed", "false");
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
    openAudioPane();
    expect(await screen.findByRole("button", { name: "배경 음악 1 적용" })).toBeEnabled();
    fireEvent.click(clipSelectionButton("n-1"));
    const applyButton = screen.getByRole("button", { name: "배경 음악 1 적용" });
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
    openAudioPane();
    await screen.findByRole("button", { name: "배경 음악 1 적용" });
    fireEvent.click(clipSelectionButton("n-1"));
    fireEvent.click(screen.getByRole("button", { name: "배경 음악 1 적용" }));

    expect(await screen.findByText("변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(updateMusic).not.toHaveBeenCalled();
    expect(updateSfx).not.toHaveBeenCalled();
    expect(updateBroll).not.toHaveBeenCalled();
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });

  // 이미지 오버레이 endpoint와 렌더는 처음부터 있었는데 화면에 부르는 자리가
  // 없었다. 자산 목록의 이미지 카드가 그 선택기다.
  it("lays an image asset over the selected scene through the image overlay command", async () => {
    const imageAsset = {
      asset_id: "image-1",
      asset_type: "broll_image",
      storage_uri: "file:///image-1.png",
      created_at: "2026-08-20T00:00:00Z",
      metadata: { title: "제품 사진", analysis_status: "succeeded", review_required: false },
    };
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([imageAsset] as never);
    const applyOverlay = vi.spyOn(api, "updateEditingSessionImageOverlay").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await openAssetBrowser();
    await screen.findByRole("button", { name: "제품 사진 화면에 얹기" });
    fireEvent.click(clipSelectionButton("n-1"));
    fireEvent.click(screen.getByRole("button", { name: "제품 사진 화면에 얹기" }));

    await waitFor(() => expect(applyOverlay).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
      asset_id: "image-1",
      text: "",
      expected_revision: 1,
    }));
  });

  it("copies a shared-library picture into the project before laying it over the scene", async () => {
    // 라이브러리 그림은 프로젝트 자산이 아니라서 오버레이가 부를 식별자가
    // 없다. 먼저 프로젝트로 복사하고, 그 결과 자산으로 얹는다 -- 이미 있는
    // 이미지 오버레이 경로를 그대로 쓴다.
    vi.spyOn(api, "listLibraryAssets").mockResolvedValue({
      assets: [{
        library_asset_id: "user_image_1",
        media_type: "image",
        origin: "user",
        lifecycle: "ready",
        user_metadata: { filename: "바다.png" },
        thumbnail_url: "/api/library/assets/user_image_1/thumbnail",
        preview_url: "/api/library/assets/user_image_1/preview",
      }],
      total: 1,
    } as never);
    const materialize = vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({
      asset: { asset_id: "project-image-9", asset_type: "image", storage_uri: "file:///x.png" },
      reference: { reference_id: "ref-1", project_id: "project-a", library_asset_id: "user_image_1" },
    } as never);
    const applyOverlay = vi.spyOn(api, "updateEditingSessionImageOverlay").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await openAssetBrowser();
    await screen.findByRole("button", { name: "바다.png 화면에 얹기" });
    fireEvent.click(clipSelectionButton("n-1"));
    fireEvent.click(screen.getByRole("button", { name: "바다.png 화면에 얹기" }));

    await waitFor(() => expect(materialize).toHaveBeenCalledWith("user_image_1", "project-a"));
    await waitFor(() => expect(applyOverlay).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
      asset_id: "project-image-9",
      text: "",
      expected_revision: 1,
    }));
  });

  it("applies B-roll through the current revision fence without materializing it", async () => {
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([broll] as never);
    const materialize = vi.spyOn(api, "materializeMediaLibraryAsset");
    const apply = vi.spyOn(api, "updateEditingSessionBroll").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await openAssetBrowser();
    await screen.findByRole("button", { name: "B-roll 1 적용" });
    fireEvent.click(clipSelectionButton("n-1"));
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
    openAudioPane();
    await screen.findByRole("button", { name: "배경 음악 1 적용" });
    fireEvent.click(clipSelectionButton("n-1"));
    fireEvent.click(screen.getByRole("button", { name: "배경 음악 1 적용" }));
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
    expect(await screen.findByText("일부 미디어를 불러오지 못했어요. 편집은 계속할 수 있어요. 잠시 후 다시 확인해 주세요.")).toBeVisible();
    expect(clipSelectionButton("n-1")).toBeEnabled();
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
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });

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

  it("unmounts the invalidated exact-preview video as soon as a mutation starts", async () => {
    let resolveUpdate!: (value: unknown) => void;
    const current = {
      ...narrationManifest(1),
      exact_preview: {
        status: "succeeded",
        url: "/api/projects/project-a/exact-previews/exact-1/content",
        source_session_id: "session-a",
        source_session_revision: 1,
        artifact_revision: 1,
        timeline_start_sec: 0,
        timeline_end_sec: 5,
      },
    };
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValueOnce(current as never);
    mockEditingSessionRevisions(1);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds")
      .mockImplementation(() => {
        expect(screen.queryByLabelText("편집본 미리보기")).toBeNull();
        return new Promise((resolve) => { resolveUpdate = resolve; }) as never;
      });

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    expect(screen.getByLabelText("편집본 미리보기")).toBeVisible();
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    await waitFor(() => expect(resolveUpdate).toBeDefined());
    expect(update).toHaveBeenCalledOnce();
    expect(screen.queryByLabelText("편집본 미리보기")).toBeNull();
  });

  it("previews only the selected scene range before starting the exact render", async () => {
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValueOnce(narrationManifest(1) as never);
    mockEditingSessionRevisions(1);
    const selectedRange = vi.spyOn(api, "previewEditingSessionSelectedRange").mockResolvedValue({ start_sec: 1, end_sec: 3, captions: [], overlays: [], fixed_timeline: true } as never);
    const exactPreview = vi.spyOn(api, "startExactPreview").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    await openInspector();
    fireEvent.click(clipSelectionButton("n-1"));
    fireEvent.click(screen.getByRole("button", { name: "선택 구간 미리보기" }));

    await waitFor(() => expect(selectedRange).toHaveBeenCalledWith("project-a", "session-a", { start_sec: 0, end_sec: 5 }));
    await waitFor(() => expect(exactPreview).toHaveBeenCalledWith("project-a", "session-a", { expected_revision: 1, start_sec: 0, end_sec: 5 }));
  });

  it("shows a recoverable message when selected scene preview fails", async () => {
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValueOnce(narrationManifest(1) as never);
    mockEditingSessionRevisions(1);
    vi.spyOn(api, "previewEditingSessionSelectedRange").mockRejectedValue(new Error("preview unavailable"));
    vi.spyOn(api, "startExactPreview").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    await openInspector();
    fireEvent.click(clipSelectionButton("n-1"));
    fireEvent.click(screen.getByRole("button", { name: "선택 구간 미리보기" }));

    expect(await screen.findByText("선택 구간 미리보기를 만들지 못했어요. 최신 편집본을 확인해 주세요.")).toBeVisible();
  });

  it("automatically starts a new preview after a successful edit instead of waiting for a manual click (F-4)", async () => {
    let resolveUpdate!: (value: unknown) => void;
    vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(narrationManifest(2, 1) as never);
    mockEditingSessionRevisions(1, 2);
    vi.spyOn(api, "updateEditingSessionSegmentBounds")
      .mockImplementation(() => new Promise((resolve) => { resolveUpdate = resolve; }) as never);
    const startPreview = vi.spyOn(api, "startExactPreview").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    // 편집기를 열면 미리보기를 한 번 만든다 -- 빈 화면으로 열리지 않게. 이 시험이
    // 재는 것은 **편집 뒤**의 생성이므로, 화면이 다 뜬 뒤부터 다시 센다.
    vi.mocked(api.startExactPreview).mockClear();
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });

    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);
    await waitFor(() => expect(resolveUpdate).toBeDefined());
    expect(startPreview).not.toHaveBeenCalled();

    resolveUpdate({});
    await expectEditorRevision(2);

    await waitFor(() => expect(startPreview).toHaveBeenCalledWith("project-a", "session-a", { expected_revision: 2 }));
  });

  it("does not automatically queue a full exact render after editing a long project", async () => {
    const longManifest = (revision: number) => ({
      ...narrationManifest(revision),
      output: { ...narrationManifest(revision).output, duration_sec: 494.8 },
    });
    vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(longManifest(1) as never)
      .mockResolvedValueOnce(longManifest(2) as never);
    mockEditingSessionRevisions(1, 2);
    vi.spyOn(api, "updateEditingSessionSegmentBounds").mockResolvedValue({} as never);
    const startPreview = vi.spyOn(api, "startExactPreview").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    // 편집기를 열면 미리보기를 한 번 만든다 -- 빈 화면으로 열리지 않게. 이 시험이
    // 재는 것은 **편집 뒤**의 생성이므로, 화면이 다 뜬 뒤부터 다시 센다.
    vi.mocked(api.startExactPreview).mockClear();
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    await expectEditorRevision(2);
    expect(startPreview).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "미리보기 새로 만들기" })).toBeEnabled();
  });

  it("fails closed when mutation rehydration returns mismatched manifest and session revisions", async () => {
    vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(narrationManifest(2) as never);
    mockEditingSessionRevisions(1, 3);
    vi.spyOn(api, "updateEditingSessionSegmentBounds").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    expect(await screen.findByText("최신 편집 상태가 일치하지 않아요. 새로고침한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(screen.queryByRole("region", { name: "편집 작업판" })).toBeNull();
  });

  it("fails closed when mutation rehydration returns a matching pair for a different route", async () => {
    vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(manifest("other-project", "other-session") as never);
    const sessions = vi.mocked(api.getEditingSession);
    sessions.mockReset()
      .mockResolvedValueOnce(editingSession("project-a", "session-a", 1) as never)
      .mockResolvedValueOnce(editingSession("other-project", "other-session", 1) as never);
    vi.spyOn(api, "updateEditingSessionSegmentBounds").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    expect(await screen.findByText("최신 편집 상태가 일치하지 않아요. 새로고침한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(screen.queryByRole("region", { name: "편집 작업판" })).toBeNull();
  });

  it("fails closed when an ordinary preview refresh returns mismatched revisions", async () => {
    vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(narrationManifest(2) as never);
    mockEditingSessionRevisions(1, 3);
    vi.spyOn(api, "startExactPreview").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    // 편집기를 열면 미리보기를 한 번 만든다 -- 빈 화면으로 열리지 않게. 이 시험이
    // 재는 것은 **편집 뒤**의 생성이므로, 화면이 다 뜬 뒤부터 다시 센다.
    vi.mocked(api.startExactPreview).mockClear();
    fireEvent.click(screen.getByRole("button", { name: "미리보기 새로 만들기" }));

    expect(await screen.findByText("편집 세션 정보가 일치하지 않아요. 다시 열어 주세요.")).toBeVisible();
    expect(screen.queryByRole("region", { name: "편집 작업판" })).toBeNull();
  });

  it("opening the editor makes a preview instead of showing an empty stage", async () => {
    // owner가 사무실에서 편집기를 보고 "완전 캡컷과 다른데"라고 했다. 그 인상의
    // 한 몫이 **열면 비어 있는 미리보기**였다 -- 예전에는 편집을 한 번 해야
    // 생겼고, 그전까지는 `아직 편집본 미리보기가 없어요`와 단추뿐이었다.
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(narrationManifest(1) as never);
    mockEditingSessionRevisions(1);
    const startPreview = vi.spyOn(api, "startExactPreview").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);

    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(1));
    expect(startPreview).toHaveBeenCalledWith("project-a", "session-a", { expected_revision: 1 });
  });

  it("opening the same editing draft does not queue a second preview", async () => {
    // 편집 뒤의 생성은 mutation 쪽이 맡는다. 여는 쪽까지 판수를 따라가면 편집할
    // 때마다 두 곳이 같은 일을 시킨다 -- 실측으로 확인하고 열쇠를 편집본 하나로 좁혔다.
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(narrationManifest(1) as never);
    mockEditingSessionRevisions(1);
    const startPreview = vi.spyOn(api, "startExactPreview").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(1));

    // 편집본을 다시 읽어도(폴링·되돌리기 등) 또 시키지 않는다.
    await act(async () => { await Promise.resolve(); });
    expect(startPreview).toHaveBeenCalledTimes(1);
  });

  it("keeps the manual preview button as a fallback when the automatic refresh fails", async () => {
    let resolveUpdate!: (value: unknown) => void;
    vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(narrationManifest(2, 1) as never);
    mockEditingSessionRevisions(1, 2);
    vi.spyOn(api, "updateEditingSessionSegmentBounds")
      .mockImplementation(() => new Promise((resolve) => { resolveUpdate = resolve; }) as never);
    const startPreview = vi.spyOn(api, "startExactPreview").mockRejectedValue(new Error("network error"));

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    // 편집기를 열면 미리보기를 한 번 만든다 -- 빈 화면으로 열리지 않게. 이 시험이
    // 재는 것은 **편집 뒤**의 생성이므로, 화면이 다 뜬 뒤부터 다시 센다.
    vi.mocked(api.startExactPreview).mockClear();
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });

    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);
    await waitFor(() => expect(resolveUpdate).toBeDefined());
    resolveUpdate({});
    await expectEditorRevision(2);

    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "미리보기 새로 만들기" })).toBeEnabled();
  });

  it("saves linked caption text through the same revision fence and refreshes the manifest", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(captionManifest(4) as never)
      .mockResolvedValueOnce(captionManifest(5, "새 자막") as never);
    mockEditingSessionRevisions(4, 5);
    const update = vi.spyOn(api, "updateEditingSessionCaption").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(4);
    fireEvent.click(screen.getByRole("tab", { name: "미디어" }));
    expect(await screen.findByRole("dialog", { name: "미디어" })).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "자막" }));
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
    fireEvent.click(screen.getByRole("tab", { name: "미디어" }));
    expect(await screen.findByRole("dialog", { name: "미디어" })).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "자막" }));
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
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
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
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" });

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
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    expect(await screen.findByText("변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(update).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("fails closed when both a mutation attempt and its authoritative refresh fail", async () => {
    vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(5) as never)
      .mockRejectedValueOnce(new Error("refresh offline"));
    const sessions = vi.mocked(api.getEditingSession);
    sessions.mockReset()
      .mockResolvedValueOnce(editingSession("project-a", "session-a", 5) as never)
      .mockRejectedValueOnce(new Error("refresh offline"));
    vi.spyOn(api, "updateEditingSessionSegmentBounds").mockRejectedValue(new Error("mutation offline"));

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(5);
    fireEvent.click(clipSelectionButton("n-1"));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    expect(await screen.findByText("최신 편집 내용을 불러오지 못했어요. 새로고침한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(screen.queryByRole("region", { name: "편집 작업판" })).toBeNull();
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
    // 청취 승인 음성은 이제 부를 때만 부른다 -- 편집기를 여는 것만으로 조회가
    // 나가지 않게 하기 위해서다.
    fireEvent.click(screen.getByRole("button", { name: "승인한 음성 불러오기" }));
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

  it.each([
    { fixture: "bgm" as const, label: "배경 음악", saveEndpoint: "bgm" as const },
    { fixture: "sfx" as const, label: "효과음", saveEndpoint: "sfx" as const },
  ])("routes the $fixture loudness slider into the saved gain_db request body", async ({ fixture, label, saveEndpoint }) => {
    // 슬라이더 오른쪽 끝(크게)은 +6dB다. 화면 조작이 emit을 지나 실제 요청
    // body의 gain_db까지 닿는지 본다. 렌더 반영은 백엔드 테스트 몫이다.
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
    fireEvent.change(screen.getByLabelText(`${label} 소리 크기`), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: `${label} 설정 저장` }));

    const save = saveEndpoint === "bgm" ? saveBgm : saveSfx;
    await waitFor(() => expect(save).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
      asset_id: `asset-${fixture}`,
      expected_revision: 7,
      media_controls: { ducking: true, fade_in_sec: 0.5, fade_out_sec: 1, gain_db: 6 },
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
    const preflight = vi.spyOn(api, "previewEditingSessionCaptionStyleScope").mockResolvedValue({ affected_segment_ids: ["segment-1"] });

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    await openInspector();
    expect(screen.queryByLabelText(/자막 시작|자막 종료/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("글자 크기"), { target: { value: "32" } });
    fireEvent.change(screen.getByLabelText("가로 정렬"), { target: { value: "left" } });
    fireEvent.click(screen.getByRole("button", { name: "자막 스타일 저장" }));

    await waitFor(() => expect(preflight).toHaveBeenCalledWith("project-a", "session-a", {
      expected_revision: 7,
      scope: "current_caption",
      segment_ids: ["segment-1"],
      style: { ...inspectorStyle, font_size_px: 32, horizontal_align: "left" },
    }));
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
    expect(result).toHaveTextContent("완료");
    expect(result).toHaveTextContent("자막, 배경 음악");
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
    expect(screen.getByText("다시 만든 항목").closest("dl")).toHaveTextContent("자막, 배경 음악");

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

    openInspector();
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
      messages: [], proposal: { ...directorProposal(), base_session_revision: 7 }, references: [],
    } as never);
    vi.spyOn(api, "preflightDirectorProposal")
      .mockImplementation(() => new Promise((resolve) => { resolveDirectorPreflight = resolve; }) as never);
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal");
    const undo = vi.spyOn(api, "undoEditingSession");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
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
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
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
    fireEvent.click(clipSelectionButton("n-1"));
    let track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    let trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(10);
    fireEvent.click(clipSelectionButton("n-1"));
    track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    trim = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
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
    fireEvent.click(clipSelectionButton("n-1"));
    const reorder = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" });
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
    // 편집기를 열면 미리보기를 한 번 만든다 -- 빈 화면으로 열리지 않게. 이 시험이
    // 재는 것은 **편집 뒤**의 생성이므로, 화면이 다 뜬 뒤부터 다시 센다.
    vi.mocked(api.startExactPreview).mockClear();
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
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    expect(await screen.findByText("한 가지를 골랐어요.")).toBeVisible();
    expect(screen.getByRole("button", { name: endingWith("P01-B-01 미리 보기") })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: endingWith("P01-B-01 미리 보기") }));
    expect(document.querySelectorAll(".vb-preview-stage")).toHaveLength(1);
    expect(document.querySelectorAll(".vb-editor-right-dock audio, .vb-editor-right-dock video")).toHaveLength(0);

    vi.spyOn(api, "reloadDirectorSession").mockRejectedValueOnce(new Error("blocked"));
    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("button", { name: "유진 없이 계속 편집" }));
    expect(await screen.findByRole("tab", { name: "미디어" })).toBeVisible();
  });

  it("names the scene each candidate targets, in words the creator already reads elsewhere", async () => {
    // 2026-08-20 owner 실측: 추천 카드 열세 개가 전부 `20260612_091959 · 미디어`.
    // 서버는 후보마다 다른 `target_segment_id`를 실어 보내고 화면 코드도 그것을
    // 받는데 **카드가 한 번도 쓰지 않았다.** 장면 번호는 타임라인 순서를 따르고
    // (`EditorWorkbench`의 미리 듣기 이름과 같은 규칙), 자막이 있으면 그 첫머리를
    // 함께 적어 사람이 아는 말로 부른다.
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue({
      ...twoNarrationManifest(1),
      captions: [
        { segment_id: "segment-2", caption_id: "caption-2", placement_id: "caption:segment-2", text: "오름에 올라 바다를 봅니다. 두 번째 문장은 잘립니다.", start_sec: 1, end_sec: 2, style: captionManifest(1).captions[0].style },
        { segment_id: "segment-1", caption_id: "caption-1", placement_id: "caption:segment-1", text: "안녕하세요, 제주입니다", start_sec: 0, end_sec: 1, style: captionManifest(1).captions[0].style },
      ],
    } as never);
    const proposal = directorProposal();
    proposal.target_segment_ids = ["segment-1", "segment-2"];
    proposal.candidates.push({
      ...proposal.candidates[0],
      candidate_id: "candidate-2",
      target_segment_id: "segment-2",
      canonical_metadata: { display_name: "20260612_091959" },
    } as never);
    proposal.candidates[0] = {
      ...proposal.candidates[0],
      target_segment_id: "segment-1",
      canonical_metadata: { display_name: "20260612_091959" },
    } as never;
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal, references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    expect(await screen.findByRole("checkbox", { name: "1번째 장면 · 안녕하세요, 제주입니다 — 20260612_091959 선택" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "2번째 장면 · 오름에 올라 바다를 봅니다 — 20260612_091959 선택" })).toBeInTheDocument();
  });

  it("says only the scene number when that scene has no caption yet", async () => {
    // 자막이 없으면 첫머리도 없다. 그때는 번호와 시작 시각만 말한다 --
    // 타임라인 클립이 이미 그렇게 부른다.
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(twoNarrationManifest(1) as never);
    const proposal = directorProposal();
    proposal.candidates[0] = { ...proposal.candidates[0], target_segment_id: "segment-2" } as never;
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal, references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    expect(await screen.findByRole("checkbox", { name: "2번째 장면 · 1초부터 — P01-B-01 선택" })).toBeInTheDocument();
  });

  it("never prints the ranker's internal word on a card, and says the same thing in Korean", async () => {
    // 2026-08-20 실화면: 카드 열세 개가 전부 `metadata`를 이유로 달고 있었다.
    // 자막과 겹치는 말이 하나도 없을 때 순위 매기기가 남기는 표시인데, 그 표시가
    // 그대로 창작자 화면에 나갔다(§10.13 위반).
    const proposal = directorProposal();
    proposal.candidates[0] = { ...proposal.candidates[0], reason_chips: ["metadata"] } as never;
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal, references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    const cards = await screen.findByRole("group", { name: "추천 후보" });
    expect(cards.textContent).not.toContain("metadata");
    expect(within(cards).getByText("자막과 겹치는 말은 없어요. 영상 길이와 내용을 보고 골랐어요.")).toBeVisible();
  });

  it("lists the words a candidate actually matched, instead of only the first one", async () => {
    const proposal = directorProposal();
    proposal.candidates[0] = { ...proposal.candidates[0], reason_chips: ["바다", "하늘"] } as never;
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal, references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    expect(await screen.findByText("자막과 겹치는 말: 바다, 하늘")).toBeVisible();
  });

  it("calls a b-roll candidate a video, not just media", async () => {
    // `media_type`은 `broll`인데 화면 사전에는 `broll_video`만 있어서, 모든
    // B-roll 후보가 `· 미디어`로 떨어졌다.
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: directorProposal(), references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    const cards = await screen.findByRole("group", { name: "추천 후보" });
    expect(cards.textContent).toContain("P01-B-01 · 영상");
  });

  it("fills every empty scene in one press, as one edit the creator can undo once", async () => {
    // 2026-08-20 owner 실측: 빈 구간 열두 개면 고르기·적용을 열두 번 반복해야 했다.
    // `batch-apply`는 처음부터 여러 후보를 받아 **한 번의 CAS 쓰기**로 적용한다 --
    // 되돌리기 기록도 하나다. 없던 것은 여러 개를 고를 화면뿐이었다.
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(twoNarrationManifest(1) as never);
    const proposal = directorProposal();
    proposal.target_segment_ids = ["segment-1", "segment-2"];
    proposal.candidates[0] = { ...proposal.candidates[0], target_segment_id: "segment-1" } as never;
    proposal.candidates.push({
      ...proposal.candidates[0],
      candidate_id: "candidate-2",
      visible_reference_code: "P01-B-02",
      target_segment_id: "segment-2",
    } as never);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal, references: [],
    } as never);
    const preflight = vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("button", { name: "장면마다 하나씩 모두 고르기" }));
    fireEvent.click(await screen.findByRole("button", { name: "고른 추천 2개 적용" }));

    await waitFor(() => expect(preflight).toHaveBeenCalledTimes(1));
    expect(batchApply).toHaveBeenCalledTimes(1);
    expect(batchApply).toHaveBeenCalledWith("project-a", "proposal-1", { candidate_ids: ["candidate-1", "candidate-2"], expected_revision: 1 });
  });

  it("keeps a Yujin-run recommendation on one pick, because the server refuses a batch of those", async () => {
    // `reject_yujin_direct_apply`가 422로 막는다. 고를 수는 있는데 적용이 거절되는
    // 화면을 만들지 않는다.
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: yujinMediaProposal(), references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    expect(await screen.findByRole("radio", { name: endingWith("P01-BROLL-01 선택") })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "장면마다 하나씩 모두 고르기" })).toBeNull();
  });

  it("preflights then batch-applies only the current route proposal after navigation", async () => {
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => Promise.resolve(manifest(projectId, sessionId)) as never);
    vi.spyOn(api, "reloadDirectorSession").mockImplementation((projectId, sessionId) => Promise.resolve({
      conversation: { conversation_id: `conversation-${sessionId}`, project_id: String(projectId), session_id: String(sessionId) }, messages: [], proposal: directorProposal(`proposal-${sessionId}`), references: [],
    }) as never);
    const preflight = vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal").mockResolvedValue({} as never);
    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("button", { name: "선택한 추천 적용" }));
    await waitFor(() => expect(preflight).toHaveBeenCalledWith("project-b", "proposal-session-b"));
    expect(batchApply).toHaveBeenCalledWith("project-b", "proposal-session-b", { candidate_ids: ["candidate-1"], expected_revision: 1 });
  });

  it.each([
    ["broll", "updateEditingSessionBroll", { fit: "crop" }],
    ["bgm", "updateEditingSessionMusicOverride", { volume: 0.6, fade_in_sec: 0.5, fade_out_sec: 0.75 }],
    ["sfx", "updateEditingSessionSfxOverride", { volume: 0.4 }],
  ] as const)("materializes then explicitly applies one selected Yujin %s operation through EditorCommandPort", async (kind, endpoint, controls) => {
    const proposal = yujinMediaProposal(kind);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal, references: [],
    } as never);
    const preflight = vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
    const materialize = vi.spyOn(api, "materializeDirectorCandidate").mockResolvedValue({ asset_id: `materialized-${kind}` } as never);
    const apply = vi.spyOn(api, endpoint).mockResolvedValue({} as never);
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    expect(screen.getByText(`${kind} 추천 세부 내용`)).toBeVisible();
    expect(screen.getByRole("radio", { name: endingWith(`${proposal.candidates[0].visible_reference_code} 선택`) })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "선택한 추천 적용" })).toBeDisabled();
    expect(preflight).not.toHaveBeenCalled();
    expect(materialize).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("radio", { name: endingWith(`${proposal.candidates[0].visible_reference_code} 선택`) }));
    const button = screen.getByRole("button", { name: "선택한 추천 적용" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    fireEvent.click(button);

    await waitFor(() => expect(materialize).toHaveBeenCalledWith(
      "project-a",
      proposal.proposal_id,
      proposal.candidates[0].candidate_id,
    ));
    await waitFor(() => expect(apply).toHaveBeenCalledWith(
      "project-a",
      "session-a",
      "segment-1",
      {
        asset_id: `materialized-${kind}`,
        media_controls: controls,
        expected_revision: 1,
      },
    ));
    expect(materialize).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledTimes(1);
    expect(batchApply).not.toHaveBeenCalled();
  });

  it.each([
    ["broll", "미리 보기"],
    ["bgm", "미리 듣기"],
    ["sfx", "미리 듣기"],
  ] as const)("lets the owner see or hear a Yujin %s recommendation before applying it", async (kind, verb) => {
    // 유진이 만든 후보는 `preview_uri`가 늘 비어 온다. 화면이 그 값만 보고
    // 있었기 때문에 단추가 한 번도 그려지지 않았고, 추천을 확인할 방법은
    // 적용해 보는 것뿐이었다. 실제 파일을 흘려 주는 주소는 따로 있다.
    const proposal = yujinMediaProposal(kind);
    expect(proposal.candidates[0].preview_uri).toBeNull();
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal, references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    const reference = proposal.candidates[0].visible_reference_code;
    fireEvent.click(screen.getByRole("button", { name: endingWith(`${reference} ${verb}`) }));

    await waitFor(() => expect(
      document.querySelector<HTMLMediaElement>(".vb-preview-stage audio, .vb-preview-stage video")?.getAttribute("src"),
    ).toBe(
      `/api/projects/project-a/director/proposals/${proposal.proposal_id}/candidates/candidate-${kind}/preview`,
    ));
    expect(document.querySelectorAll(".vb-editor-right-dock audio, .vb-editor-right-dock video")).toHaveLength(0);
  });

  it("offers a way back to 유진 after the server rejects a stale recommendation", async () => {
    // 낡은 추천으로 적용을 누르면 서버가 "다시 받으라"고 답하고 화면이 막힌다.
    // 그런데 새 추천 받기는 이미 추천이 있으면 눌리지 않는다 -- 이 자리가
    // 없으면 유진에게 돌아갈 길이 아예 없었다.
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: directorProposal(), references: [],
    } as never);
    vi.spyOn(api, "preflightDirectorProposal")
      .mockResolvedValue({ status: "stale", code: "stale_proposal", action: "refresh" } as never);
    const refresh = vi.spyOn(api, "refreshDirectorProposal")
      .mockResolvedValue({ ...directorProposal("proposal-2"), base_session_revision: 1 } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("button", { name: "선택한 추천 적용" }));

    const again = await screen.findByRole("button", { name: "지금 편집본으로 다시 추천받기" });
    fireEvent.click(again);

    await waitFor(() => expect(refresh).toHaveBeenCalledWith("project-a", "proposal-1"));
    expect(await screen.findByRole("button", { name: "선택한 추천 적용" })).toBeVisible();
    await waitFor(() => expect(
      screen.queryByRole("button", { name: "지금 편집본으로 다시 추천받기" }),
    ).toBeNull());
  });

  it("re-asks by itself when the recommendation is out of date and the creator is looking at it", async () => {
    // 예전에는 죽은 카드와 `다시 추천받기` 단추만 남았고, 창작자가 그걸 눈치채고
    // 눌러야 대화가 이어졌다. 편집을 몇 번만 해도 매번 그렇게 된다.
    //
    // 편집본이 바뀌면 추천이 무효가 되는 것은 백엔드가 여러 겹으로 지키는 계약이라
    // 그대로 둔다. 바뀐 것은 **그다음**이다 -- 도크가 보이면 대신 물어본다.
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(inspectorManifest(7) as never);
    vi.mocked(api.getEditingSession).mockResolvedValue(inspectorSession(7) as never);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: { ...directorProposal(), base_session_revision: 3 }, references: [],
    } as never);
    const refresh = vi.spyOn(api, "refreshDirectorProposal")
      .mockResolvedValue({ ...directorProposal("proposal-2"), base_session_revision: 7 } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    // 누르지 않았는데 스스로 다시 물어본다.
    await waitFor(() => expect(refresh).toHaveBeenCalledWith("project-a", "proposal-1"));
    await waitFor(() => expect(
      screen.queryByText("편집본이 바뀌어서 이 추천은 그대로 적용할 수 없어요."),
    ).toBeNull());
  });

  it("disables stale Yujin Apply before materialize or edit mutation", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [],
      proposal: { ...yujinMediaProposal(), base_session_revision: 0 },
      references: [],
    } as never);
    const materialize = vi.spyOn(api, "materializeDirectorCandidate");
    const apply = vi.spyOn(api, "updateEditingSessionBroll");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    expect(screen.getByRole("button", { name: "선택한 추천 적용" })).toBeDisabled();
    expect(materialize).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
  });

  it.each([
    ["broll", "bgm"],
    ["bgm", "sfx"],
    ["sfx", "broll_video"],
  ] as const)("disables Yujin %s when source media kind is %s", async (kind, sourceMediaKind) => {
    const proposal = yujinMediaProposal(kind);
    proposal.candidates[0].canonical_metadata.source_media_kind = sourceMediaKind;
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal, references: [],
    } as never);
    const materialize = vi.spyOn(api, "materializeDirectorCandidate");
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    expect(screen.getByRole("radio", { name: endingWith(`${proposal.candidates[0].visible_reference_code} 선택`) })).toBeDisabled();
    expect(screen.getByRole("button", { name: "선택한 추천 적용" })).toBeDisabled();
    expect(materialize).not.toHaveBeenCalled();
    expect(batchApply).not.toHaveBeenCalled();
  });

  it("drops a Yujin materialize completion after route epoch changes", async () => {
    let resolveMaterialize!: (value: unknown) => void;
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation(
      (projectId, sessionId) => Promise.resolve(manifest(projectId, sessionId)) as never,
    );
    vi.spyOn(api, "reloadDirectorSession").mockImplementation((projectId, sessionId) => Promise.resolve({
      conversation: { conversation_id: `conversation-${sessionId}`, project_id: String(projectId), session_id: String(sessionId) },
      messages: [],
      proposal: projectId === "project-a" ? yujinMediaProposal() : null,
      references: [],
    }) as never);
    vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
    const materialize = vi.spyOn(api, "materializeDirectorCandidate")
      .mockImplementation(() => new Promise((resolve) => { resolveMaterialize = resolve; }) as never);
    const apply = vi.spyOn(api, "updateEditingSessionBroll");
    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("radio", { name: endingWith("P01-BROLL-01 선택") }));
    fireEvent.click(await screen.findByRole("button", { name: "선택한 추천 적용" }));
    await waitFor(() => expect(materialize).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    await act(async () => { resolveMaterialize({ asset_id: "materialized-stale" }); });

    expect(apply).not.toHaveBeenCalled();
  });

  it("keeps manual editing and issues zero edit commands when Yujin materialize fails", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: yujinMediaProposal(), references: [],
    } as never);
    vi.spyOn(api, "preflightDirectorProposal").mockResolvedValue({ status: "ready" } as never);
    vi.spyOn(api, "materializeDirectorCandidate").mockRejectedValue(new Error("materialize failed"));
    const apply = vi.spyOn(api, "updateEditingSessionBroll");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("radio", { name: endingWith("P01-BROLL-01 선택") }));
    fireEvent.click(await screen.findByRole("button", { name: "선택한 추천 적용" }));

    expect(await screen.findByRole("button", { name: "유진 없이 계속 편집" })).toBeVisible();
    expect(clipSelectionButton("n-1")).toBeEnabled();
    expect(apply).not.toHaveBeenCalled();
  });

  it("keeps reload read-only until the creator explicitly starts Eugene, then creates one conversation and proposal", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({ conversation: null, messages: [], proposal: null, references: [] } as never);
    const createConversation = vi.spyOn(api, "createDirectorConversation").mockResolvedValue({ conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" } as never);
    const createProposal = vi.spyOn(api, "createDirectorProposal").mockResolvedValue(directorProposal() as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    expect(createConversation).not.toHaveBeenCalled();
    expect(createProposal).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("button", { name: "유진에게 추천받기" }));

    await waitFor(() => expect(createConversation).toHaveBeenCalledWith("project-a", { session_id: "session-a" }));
    expect(createConversation).toHaveBeenCalledTimes(1);
    expect(createProposal).toHaveBeenCalledWith("project-a", { session_id: "session-a" });
    expect(createProposal).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("textbox", { name: "유진에게 요청하기" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "선택한 추천 적용" })).toBeEnabled();
  });

  // 화면이 기본으로 쓰는 것은 유진 경로가 아니라 로컬 경로다. 그런데 미리보기
  // 단추 조건이 유진 후보 전용이라, owner가 실제로 보는 추천에는 단추가 한 번도
  // 뜨지 않았다. 서버는 그 후보의 원본을 그대로 내준다.
  it("lets the creator look at a local-path recommendation before applying it", async () => {
    const proposal = directorProposal();
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [],
      // 실제 응답은 이 자리를 늘 비워서 보낸다. 시험 자료가 채워 두고 있어서
      // 단추가 안 뜨는 것을 아무도 못 봤다.
      proposal: { ...proposal, candidates: [{ ...proposal.candidates[0], preview_uri: null }] },
      references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    expect(await screen.findByRole("button", { name: endingWith("P01-B-01 미리 보기") })).toBeVisible();
  });

  // 서버가 "촬영본 분석이 안 끝나 추천을 만들 수 없다"고 409로 답해도 화면은
  // "아직 추천이 없어요"에 머물렀다. 눌러도 아무 일이 없으니 owner는 고장인지
  // 자기가 잘못 누른 것인지 알 수 없다. 이유를 말하고, 다시 누를 수 있게 남긴다.
  it("says why Eugene refused to start, and keeps the request retryable", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({ conversation: null, messages: [], proposal: null, references: [] } as never);
    vi.spyOn(api, "createDirectorConversation").mockResolvedValue({ conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" } as never);
    const createProposal = vi.spyOn(api, "createDirectorProposal")
      .mockRejectedValueOnce(new DirectorProposalBlockedError("analyse_or_retry_assets"))
      .mockResolvedValueOnce(directorProposal() as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("button", { name: "유진에게 추천받기" }));

    expect(await screen.findByText("촬영본 확인이 아직 끝나지 않아서 추천을 만들 수 없어요. 미디어 화면에서 확인한 뒤 다시 눌러 주세요.")).toBeVisible();

    const retry = screen.getByRole("button", { name: "유진에게 추천받기" });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);

    await waitFor(() => expect(createProposal).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText("촬영본 확인이 아직 끝나지 않아서 추천을 만들 수 없어요. 미디어 화면에서 확인한 뒤 다시 눌러 주세요.")).toBeNull());
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
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
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
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    const composer = await screen.findByLabelText("유진에게 요청하기");
    fireEvent.change(composer, { target: { value: "작성 중인 요청" } });
    fireEvent.click(clipSelectionButton("n-2"));
    timeline.scrollLeft = 37;
    fireEvent.click(screen.getByRole("button", { name: "선택한 추천 적용" }));

    await waitFor(() => expect(manifestLoad).toHaveBeenCalledTimes(2));
    expect(sessionLoad).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("region", { name: "편집 작업판" })).toBe(workbench);
    expect(screen.getByTestId("timeline-track")).toBe(timeline);
    expect(screen.getByTestId("timeline-track").scrollLeft).toBe(37);
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("작성 중인 요청");
    expect(clipSelectionButton("n-2")).toHaveAttribute("aria-pressed", "true");
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
    expect(clipSelectionButton("n-2")).toHaveAttribute("aria-pressed", "true");
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
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.click(await screen.findByRole("button", { name: "선택한 추천 적용" }));

    await waitFor(() => expect(manifestLoad).toHaveBeenCalledTimes(2));
    expect(sessionLoad).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("최신 편집 내용을 불러오지 못했어요. 새로고침한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(screen.queryByRole("region", { name: "편집 작업판" })).toBeNull();
  });

  it("projects persisted Director rows as ordered flat bubbles without adjacent pairing", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [
        { message_id: "user-1", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "첫 요청", proposal_id: null, metadata: {}, client_message_id: "client-1", created_at: "1" },
        { message_id: "user-2", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "동시 요청", proposal_id: null, metadata: {}, client_message_id: "client-2", created_at: "2" },
        { message_id: "assistant-1", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "첫 답", proposal_id: null, metadata: {}, client_message_id: null, created_at: "3" },
        { message_id: "assistant-2", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "둘째 답", proposal_id: null, metadata: {}, client_message_id: null, created_at: "4" },
      ],
      proposal: null,
      references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    const rows = Array.from((await screen.findByRole("log", { name: "유진 대화" })).querySelectorAll("article"))
      .map((row) => row.textContent);
    expect(rows).toEqual(["나 첫 요청", "나 동시 요청", "유진 첫 답", "유진 둘째 답"]);
  });

  it("fills a Yujin starter through the route without creating, sending, proposing, or applying", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: null,
      messages: [],
      proposal: null,
      references: [],
    } as never);
    const createConversation = vi.spyOn(api, "createDirectorConversation");
    const send = vi.spyOn(api, "sendDirectorMessage");
    const createProposal = vi.spyOn(api, "createDirectorProposal");
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    const starter = await screen.findByRole("button", { name: "이 장면에 어울리는 B-roll 추천해 줘" });
    fireEvent.click(starter);

    const composer = screen.getByRole("textbox", { name: "유진에게 요청하기" });
    expect(composer).toHaveValue("이 장면에 어울리는 B-roll 추천해 줘");
    expect(composer).toHaveFocus();
    expect(createConversation).not.toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
    expect(createProposal).not.toHaveBeenCalled();
    expect(batchApply).not.toHaveBeenCalled();
  });

  it("sends a message and shows the persisted Yujin reply from the local endpoint", async () => {
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000001");
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: null, references: [],
    } as never);
    const send = vi.spyOn(api, "sendDirectorMessage").mockResolvedValue({
      kind: "exchange",
      exchange: {
        user_message: { message_id: "user-1", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "장면을 설명해 줘", proposal_id: null, metadata: {}, client_message_id: "00000000-0000-4000-8000-000000000001", created_at: "1" },
        assistant_message: { message_id: "assistant-1", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "차분한 장면이에요.", proposal_id: null, metadata: {}, client_message_id: null, created_at: "2" },
      },
    } as never);

    render(<StrictMode><EditorWorkbenchRoute projectId="project-a" sessionId="session-a" /></StrictMode>);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    const composer = await screen.findByRole("textbox", { name: "유진에게 요청하기" });
    fireEvent.change(composer, { target: { value: "장면을 설명해 줘" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));

    expect(await screen.findByText("차분한 장면이에요.")).toBeVisible();
    expect(send).toHaveBeenCalledWith("project-a", "conversation-1", {
      session_id: "session-a",
      client_message_id: "00000000-0000-4000-8000-000000000001",
      text: "장면을 설명해 줘",
    }, expect.any(AbortSignal));
    expect(composer).toHaveValue("");
    expect(composer).toBeEnabled();
    expect(clipSelectionButton("n-1")).toBeEnabled();
  });

  it("creates a candidate-only editing proposal only after the creator explicitly asks for one", async () => {
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000002");
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: null, references: [],
    } as never);
    vi.spyOn(api, "sendDirectorMessage").mockResolvedValueOnce({
      kind: "exchange",
      exchange: {
        user_message: { message_id: "user-edit", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "두 번째 장면을 빠르게", proposal_id: null, metadata: {}, client_message_id: "00000000-0000-4000-8000-000000000002", created_at: "1" },
        assistant_message: { message_id: "assistant-edit", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "속도를 조절할 수 있어요.", proposal_id: null, metadata: {}, client_message_id: null, created_at: "2" },
      },
    } as never).mockResolvedValueOnce({
      kind: "exchange",
      exchange: {
        user_message: { message_id: "user-edit-next", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "세 번째 장면도 다듬어 줘", proposal_id: null, metadata: {}, client_message_id: "00000000-0000-4000-8000-000000000002", created_at: "3" },
        assistant_message: { message_id: "assistant-edit-next", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "세 번째 장면도 확인할게요.", proposal_id: null, metadata: {}, client_message_id: null, created_at: "4" },
      },
    } as never);
    const createEditingProposal = vi.spyOn(api, "createYujinEditingProposal").mockResolvedValue({
      proposal_id: "yujin-edit-1", revision_code: "YE01", revision: 1, base_session_revision: 1, asset_index_revision: 0,
      source_session_id: "session-a", target_segment_ids: ["segment-2"], source_script_segment_ids: [], status: "ready", expires_at: null, candidates: [],
      diff: { proposal_mode: "yujin_editing_candidate_v1", operations: [{ intent: "set_scene_speed", segment_id: "segment-2", rate: 2 }], follow_up_questions: [] },
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    const composer = await screen.findByRole("textbox", { name: "유진에게 요청하기" });
    fireEvent.change(composer, { target: { value: "두 번째 장면을 빠르게" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await screen.findByText("속도를 조절할 수 있어요.");

    expect(createEditingProposal).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "이 대화로 편집안 만들기" }));

    await screen.findByText("편집안을 준비했어요.");
    expect(createEditingProposal).toHaveBeenCalledWith("project-a", "session-a", { instruction: "두 번째 장면을 빠르게" });
    fireEvent.click(screen.getByRole("button", { name: "편집안 보기" }));
    expect(await screen.findByRole("dialog", { name: "편집안" })).toHaveTextContent("2배로 속도를 바꿔요.");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    fireEvent.change(composer, { target: { value: "세 번째 장면도 다듬어 줘" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));

    await waitFor(() => expect(screen.queryByText("편집안을 준비했어요.")).toBeNull());
    expect(screen.getByRole("button", { name: "이 대화로 편집안 만들기" })).toBeEnabled();
  });

  // 후보 결과 미리보기(Task 3). 2026-08-26까지 `이 구간 미리보기`는 **저장된
  // 편집본**을 보여 줬다 -- 창작자는 바뀐 결과를 봤다고 믿었지만 실제로는 바뀌기
  // 전 영상을 본 것이다. 적용 전에는 저장을 건드리는 어떤 호출도 하지 않는다.
  async function openEditingProposalDialog() {
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000003");
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: null, references: [],
    } as never);
    vi.spyOn(api, "sendDirectorMessage").mockResolvedValue({
      kind: "exchange",
      exchange: {
        user_message: { message_id: "user-edit", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "두 번째 장면을 빠르게", proposal_id: null, metadata: {}, client_message_id: "00000000-0000-4000-8000-000000000003", created_at: "1" },
        assistant_message: { message_id: "assistant-edit", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "속도를 조절할 수 있어요.", proposal_id: null, metadata: {}, client_message_id: null, created_at: "2" },
      },
    } as never);
    vi.spyOn(api, "createYujinEditingProposal").mockResolvedValue({
      proposal_id: "yujin-edit-1", revision_code: "YE01", revision: 1, base_session_revision: 1, asset_index_revision: 0,
      source_session_id: "session-a", target_segment_ids: ["segment-2"], source_script_segment_ids: [], status: "ready", expires_at: null, candidates: [],
      diff: { proposal_mode: "yujin_editing_candidate_v1", operations: [{ intent: "set_scene_speed", segment_id: "segment-2", rate: 2 }], follow_up_questions: [] },
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    const composer = await screen.findByRole("textbox", { name: "유진에게 요청하기" });
    fireEvent.change(composer, { target: { value: "두 번째 장면을 빠르게" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await screen.findByText("속도를 조절할 수 있어요.");
    fireEvent.click(screen.getByRole("button", { name: "이 대화로 편집안 만들기" }));
    await screen.findByText("편집안을 준비했어요.");
    fireEvent.click(screen.getByRole("button", { name: "편집안 보기" }));
    return screen.getByRole("dialog", { name: "편집안" });
  }

  it("shows the candidate result and never touches the saved session before apply", async () => {
    const selectedRange = vi.spyOn(api, "previewEditingSessionSelectedRange").mockResolvedValue({} as never);
    const exactPreview = vi.spyOn(api, "startExactPreview").mockResolvedValue({} as never);
    const startProposalPreview = vi.spyOn(api, "startYujinEditingProposalPreview")
      .mockResolvedValue({ status: "pending", generationId: "proposal-preview-1", contentUrl: null, errorMessage: null });
    const proposalPreviewStatus = vi.spyOn(api, "getYujinEditingProposalPreviewStatus")
      .mockResolvedValueOnce({ status: "running", generationId: "proposal-preview-1", contentUrl: null, errorMessage: null })
      .mockResolvedValue({ status: "succeeded", generationId: "proposal-preview-1", contentUrl: "/api/projects/project-a/proposal-previews/proposal-preview-1/content", errorMessage: null });

    const dialog = await openEditingProposalDialog();
    // 편집기를 열면 편집본 미리보기를 한 번 만든다. 이 시험이 재는 것은 **누른 뒤**다.
    exactPreview.mockClear();
    fireEvent.click(within(dialog).getByRole("button", { name: "이 구간 미리보기" }));

    expect(await screen.findByText("편집안 미리보기를 만들고 있어요.")).toBeVisible();
    expect(await screen.findByLabelText("편집안 미리보기", {}, { timeout: 8_000 })).toHaveAttribute(
      "src",
      "/api/projects/project-a/proposal-previews/proposal-preview-1/content",
    );
    expect(startProposalPreview).toHaveBeenCalledWith("project-a", "session-a", "yujin-edit-1");
    expect(proposalPreviewStatus).toHaveBeenCalledWith("project-a", "proposal-preview-1");
    // 핵심 안전 성질: 적용 전 저장 변경 호출 0.
    expect(selectedRange).not.toHaveBeenCalled();
    expect(exactPreview).not.toHaveBeenCalled();
  }, 15_000);

  it("refuses to show a stale candidate result and tells the creator what to do", async () => {
    const selectedRange = vi.spyOn(api, "previewEditingSessionSelectedRange").mockResolvedValue({} as never);
    vi.spyOn(api, "startExactPreview").mockResolvedValue({} as never);
    vi.spyOn(api, "startYujinEditingProposalPreview")
      .mockResolvedValue({ status: "stale", action: "새 편집안을 받아 보세요." });

    const dialog = await openEditingProposalDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: "이 구간 미리보기" }));

    expect(await screen.findByText("편집본이 바뀌었어요. 새 편집안을 받아 보세요.")).toBeVisible();
    expect(screen.queryByLabelText("편집안 미리보기")).toBeNull();
    expect(selectedRange).not.toHaveBeenCalled();
  }, 15_000);

  it("aborts an in-flight local send on explicit cancel and keeps manual editing enabled", async () => {
    let sendSignal!: AbortSignal;
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: null, references: [],
    } as never);
    vi.spyOn(api, "sendDirectorMessage").mockImplementation((_projectId, _conversationId, _payload, signal) => {
      sendSignal = signal!;
      return new Promise((_resolve, reject) => {
        signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      });
    });

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.change(
      await screen.findByRole("textbox", { name: "유진에게 요청하기" }),
      { target: { value: "취소할 요청" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "답변 중단" })).toBeEnabled());
    expect(clipSelectionButton("n-1")).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "답변 중단" }));

    expect(sendSignal.aborted).toBe(true);
    expect(await screen.findByText("유진의 답을 받지 못했어요.")).toBeVisible();
    expect(screen.queryByText("나 취소할 요청")).toBeNull();
    expect(screen.getByRole("button", { name: "유진에게 추천받기" })).toBeEnabled();
    expect(screen.getByRole("textbox", { name: "유진에게 요청하기" })).toBeEnabled();
    expect(clipSelectionButton("n-1")).toBeEnabled();
  });

  it("fences a late local reply after a different Director operation starts on the same route", async () => {
    let releaseSend!: (value: unknown) => void;
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000024",
    );
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [],
      proposal: directorProposal("proposal-existing"),
      references: [],
    } as never);
    vi.spyOn(api, "sendDirectorMessage").mockImplementation(
      () => new Promise((resolve) => { releaseSend = resolve; }) as never,
    );
    const preflight = vi.spyOn(api, "preflightDirectorProposal").mockImplementation(
      () => new Promise(() => undefined) as never,
    );

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.change(
      await screen.findByRole("textbox", { name: "유진에게 요청하기" }),
      { target: { value: "늦게 끝날 요청" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await waitFor(() => expect(releaseSend).toBeTypeOf("function"));

    fireEvent.click(screen.getByRole("button", { name: "선택한 추천 적용" }));
    await waitFor(() => expect(preflight).toHaveBeenCalledWith(
      "project-a",
      "proposal-existing",
    ));

    await act(async () => {
      releaseSend({
        kind: "exchange",
        exchange: {
          user_message: { message_id: "user-late", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "늦게 끝날 요청", proposal_id: null, metadata: {}, client_message_id: "00000000-0000-4000-8000-000000000024", created_at: "1" },
          assistant_message: { message_id: "assistant-late", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "오래된 답", proposal_id: null, metadata: {}, client_message_id: null, created_at: "2" },
        },
      });
    });

    expect(screen.queryByText("오래된 답")).toBeNull();
  });

  it("retries a failed send with the same client message id and keeps manual editing enabled", async () => {
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000022",
    );
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: null, references: [],
    } as never);
    const send = vi.spyOn(api, "sendDirectorMessage")
      .mockRejectedValueOnce(new Error("PRIVATE upstream failure"))
      .mockResolvedValueOnce({
        kind: "exchange",
        exchange: {
          user_message: { message_id: "user-retry", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "다시 시도할 요청", proposal_id: null, metadata: {}, client_message_id: "00000000-0000-4000-8000-000000000022", created_at: "1" },
          assistant_message: { message_id: "assistant-retry", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "다시 받은 답", proposal_id: null, metadata: {}, client_message_id: null, created_at: "2" },
        },
      } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.change(
      await screen.findByRole("textbox", { name: "유진에게 요청하기" }),
      { target: { value: "다시 시도할 요청" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));

    const retryButton = await screen.findByRole("button", {
      name: "같은 요청 다시 보내기",
    });
    expect(retryButton).toBeEnabled();
    expect(clipSelectionButton("n-1")).toBeEnabled();
    fireEvent.click(retryButton);

    await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
    expect(send).toHaveBeenNthCalledWith(2, "project-a", "conversation-1", {
      session_id: "session-a",
      client_message_id: "00000000-0000-4000-8000-000000000022",
      text: "다시 시도할 요청",
    }, expect.any(AbortSignal));
    expect(await screen.findByText("다시 받은 답")).toBeVisible();
    expect(clipSelectionButton("n-1")).toBeEnabled();
  });

  it("fences a late local reply after a same-route revision advance", async () => {
    let releaseSend!: (value: unknown) => void;
    vi.mocked(api.getEditorPlaybackManifest)
      .mockReset()
      .mockResolvedValueOnce(inspectorManifest(7) as never)
      .mockResolvedValueOnce(inspectorManifest(8) as never);
    vi.mocked(api.getEditingSession)
      .mockReset()
      .mockResolvedValueOnce(inspectorSession(7) as never)
      .mockResolvedValueOnce(inspectorSession(8) as never);
    vi.spyOn(api, "undoEditingSession").mockResolvedValue({} as never);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: null, references: [],
    } as never);
    vi.spyOn(api, "sendDirectorMessage").mockImplementation(
      () => new Promise((resolve) => { releaseSend = resolve; }) as never,
    );

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(7);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.change(
      await screen.findByRole("textbox", { name: "유진에게 요청하기" }),
      { target: { value: "곧 오래될 요청" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await waitFor(() => expect(releaseSend).toBeTypeOf("function"));

    fireEvent.click(screen.getByRole("button", { name: "실행 취소" }));
    await expectEditorRevision(8);
    await act(async () => {
      releaseSend({
        kind: "exchange",
        exchange: {
          user_message: { message_id: "user-stale-rev", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "곧 오래될 요청", proposal_id: null, metadata: {}, client_message_id: "client-stale-rev", created_at: "1" },
          assistant_message: { message_id: "assistant-stale-rev", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "오래된 답", proposal_id: null, metadata: {}, client_message_id: null, created_at: "2" },
        },
      });
    });

    expect(screen.queryByText("오래된 답")).toBeNull();
    expect(clipSelectionButton("n-1")).toBeEnabled();
    expect(screen.queryByRole("button", { name: "답변 중단" })).toBeNull();
    expect(screen.getByRole("textbox", { name: "유진에게 요청하기" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "유진에게 추천받기" })).toBeEnabled();
  });

  it("shows the local policy guard's own blocked reply without any technical fallback text", async () => {
    // The backend's YujinLocalConversationService (Task 13/14) already returns a
    // clean, human-facing Korean message for restricted requests -- there is no
    // separate frontend localization/redaction step for the local send path.
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [], proposal: null, references: [],
    } as never);
    vi.spyOn(api, "sendDirectorMessage").mockResolvedValue({
      kind: "exchange",
      exchange: {
        user_message: { message_id: "user-blocked", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "데이터베이스 삭제해줘", proposal_id: null, metadata: {}, client_message_id: "client-blocked", created_at: "1" },
        assistant_message: { message_id: "assistant-blocked", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "이 요청은 유진이 직접 할 수 없어요.", proposal_id: null, metadata: { status: "blocked", error_code: "policy_restricted_intent" }, client_message_id: null, created_at: "2" },
      },
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "유진에게 요청하기" }), { target: { value: "데이터베이스 삭제해줘" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));

    expect(await screen.findByText("이 요청은 유진이 직접 할 수 없어요.")).toBeVisible();
    expect(screen.queryByText(/Hermes|local_only_blocked/)).toBeNull();
    expect(clipSelectionButton("n-1")).toBeEnabled();
  });

  it("preserves the draft and manual controls when the local send fails", async () => {
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [{ message_id: "user-old", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "남아 있는 대화", proposal_id: null, metadata: {}, client_message_id: "old", created_at: "1" }],
      proposal: null, references: [],
    } as never);
    vi.spyOn(api, "sendDirectorMessage").mockRejectedValue(new Error("PRIVATE upstream failure"));
    const createProposal = vi.spyOn(api, "createDirectorProposal");
    const captionMutation = vi.spyOn(api, "updateEditingSessionCaption");
    const batchApply = vi.spyOn(api, "batchApplyDirectorProposal");
    const materialize = vi.spyOn(api, "materializeDirectorCandidate");

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    const composer = await screen.findByRole("textbox", { name: "유진에게 요청하기" });
    fireEvent.change(composer, { target: { value: "보존할 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));

    expect(await screen.findByText("유진의 답을 받지 못했어요.")).toBeVisible();
    expect(composer).toHaveValue("보존할 요청");
    expect(screen.getByText("남아 있는 대화")).toBeVisible();
    expect(clipSelectionButton("n-1")).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "유진 없이 계속 편집" }));
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    expect(screen.getByText("유진의 답을 받지 못했어요.")).toBeVisible();
    expect(screen.getByText("남아 있는 대화")).toBeVisible();
    expect(createProposal).not.toHaveBeenCalled();
    expect(captionMutation).not.toHaveBeenCalled();
    expect(batchApply).not.toHaveBeenCalled();
    expect(materialize).not.toHaveBeenCalled();
  });

  it("keeps route-owned draft, candidate, history scroll, and player while the right drawer unmounts", async () => {
    const proposal = directorProposal();
    proposal.candidates.push({
      ...proposal.candidates[0],
      candidate_id: "candidate-2",
      visible_reference_code: "P01-B-02",
    });
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({
      conversation: { conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a" },
      messages: [
        { message_id: "user-1", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "user", text: "요청", proposal_id: null, metadata: {}, client_message_id: "client", created_at: "1" },
        { message_id: "assistant-1", conversation_id: "conversation-1", project_id: "project-a", session_id: "session-a", role: "assistant", text: "답변", proposal_id: null, metadata: {}, client_message_id: null, created_at: "2" },
      ],
      proposal,
      references: [],
    } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    const player = screen.getByRole("region", { name: "미리보기" });
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    const composer = await screen.findByRole("textbox", { name: "유진에게 요청하기" });
    fireEvent.change(composer, { target: { value: "작성 중" } });
    fireEvent.click(screen.getByRole("checkbox", { name: endingWith("P01-B-02 선택") }));
    const history = screen.getByRole("log", { name: "유진 대화" });
    Object.defineProperties(history, {
      scrollHeight: { configurable: true, value: 200 },
      clientHeight: { configurable: true, value: 80 },
      scrollTop: { configurable: true, writable: true, value: 72 },
    });
    fireEvent.scroll(history);
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(screen.queryByRole("log", { name: "유진 대화" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    expect(await screen.findByRole("textbox", { name: "유진에게 요청하기" })).toHaveValue("작성 중");
    expect(screen.getByText("요청")).toBeVisible();
    expect(screen.getByText("답변")).toBeVisible();
    expect(screen.getByRole("checkbox", { name: endingWith("P01-B-02 선택") })).toBeChecked();
    expect(screen.getByRole("log", { name: "유진 대화" }).scrollTop).toBe(72);
    expect(screen.getByRole("region", { name: "미리보기" })).toBe(player);
    expect(document.querySelectorAll(".vb-preview-stage")).toHaveLength(1);
  });

  it("keeps unsent drafts isolated by route across A to B to A navigation", async () => {
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => Promise.resolve(manifest(projectId, sessionId)) as never);
    vi.spyOn(api, "reloadDirectorSession").mockImplementation((projectId, sessionId) => Promise.resolve({
      conversation: { conversation_id: `conversation-${sessionId}`, project_id: String(projectId), session_id: String(sessionId) },
      messages: [], proposal: null, references: [],
    }) as never);
    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "유진에게 요청하기" }), { target: { value: "A 초안" } });

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    expect(await screen.findByRole("textbox", { name: "유진에게 요청하기" })).toHaveValue("");
    fireEvent.change(screen.getByRole("textbox", { name: "유진에게 요청하기" }), { target: { value: "B 초안" } });

    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    expect(await screen.findByRole("textbox", { name: "유진에게 요청하기" })).toHaveValue("A 초안");
  });

  it("ignores a late local reply that resolves after route navigation", async () => {
    let releaseSend!: (value: unknown) => void;
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => Promise.resolve(manifest(projectId, sessionId)) as never);
    vi.spyOn(api, "reloadDirectorSession").mockImplementation((projectId, sessionId) => Promise.resolve({
      conversation: { conversation_id: `conversation-${sessionId}`, project_id: String(projectId), session_id: String(sessionId) },
      messages: [], proposal: null, references: [],
    }) as never);
    const send = vi.spyOn(api, "sendDirectorMessage").mockImplementation(
      () => new Promise((resolve) => { releaseSend = resolve; }) as never,
    );

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "유진에게 요청하기" }), { target: { value: "A 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await waitFor(() => expect(send).toHaveBeenCalledOnce());

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    await act(async () => {
      releaseSend({
        kind: "exchange",
        exchange: {
          user_message: { message_id: "user-stale-route", conversation_id: "conversation-session-a", project_id: "project-a", session_id: "session-a", role: "user", text: "A 요청", proposal_id: null, metadata: {}, client_message_id: "client-stale-route", created_at: "1" },
          assistant_message: { message_id: "assistant-stale-route", conversation_id: "conversation-session-a", project_id: "project-a", session_id: "session-a", role: "assistant", text: "A 최종", proposal_id: null, metadata: {}, client_message_id: null, created_at: "2" },
        },
      });
    });

    expect(screen.queryByText("A 최종")).toBeNull();
    expect(screen.queryByText("유진의 답을 받지 못했어요.")).toBeNull();
  });

  it("aborts an in-flight local send on route change, ignores the late AbortError, and aborts again on unmount", async () => {
    let sendSignalA!: AbortSignal;
    let sendSignalB!: AbortSignal;
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => Promise.resolve(manifest(projectId, sessionId)) as never);
    vi.spyOn(api, "reloadDirectorSession").mockImplementation((projectId, sessionId) => Promise.resolve({
      conversation: { conversation_id: `conversation-${sessionId}`, project_id: String(projectId), session_id: String(sessionId) },
      messages: [], proposal: null, references: [],
    }) as never);
    let call = 0;
    vi.spyOn(api, "sendDirectorMessage").mockImplementation((_projectId, _conversationId, _payload, signal) => {
      call += 1;
      if (call === 1) sendSignalA = signal!; else sendSignalB = signal!;
      return new Promise((_resolve, reject) => {
        signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      });
    });

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "유진에게 요청하기" }), { target: { value: "A 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await waitFor(() => expect(sendSignalA).not.toBeUndefined());

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    await expectEditorRevision(1);
    expect(sendSignalA.aborted).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
    fireEvent.change(screen.getByRole("textbox", { name: "유진에게 요청하기" }), { target: { value: "B 요청" } });
    fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
    await waitFor(() => expect(sendSignalB).not.toBeUndefined());
    expect(sendSignalB.aborted).toBe(false);
    expect(screen.queryByText("유진의 답을 받지 못했어요.")).toBeNull();
    expect(screen.getByRole("button", { name: "답변 중단" })).toBeEnabled();
    expect(screen.getByRole("textbox", { name: "유진에게 요청하기" })).toBeDisabled();

    rendered.unmount();
    expect(sendSignalB.aborted).toBe(true);
  });
});

describe("부분 재생성 표시", () => {
  it("영향 범위와 결과를 내부 값이 아니라 창작자 언어로 말한다", () => {
    expect(affectedAreaLabel("subtitle render")).toBe("자막 입히기");
    expect(affectedAreaLabel("capcut export")).toBe("CapCut 내보내기");
    expect(affectedAreaLabel("segment copy")).toBe("장면 대본");
    // 모르는 값이 와도 영어 원값을 그대로 내보내지 않는다.
    expect(affectedAreaLabel("something_new")).toBe("영상 일부");

    expect(partialStatusLabel("succeeded")).toBe("완료");
    expect(partialStatusLabel("failed")).toBe("실패");
  });
});

describe("서버 출력 변형 연결", () => {
  it("loads a server variant and sends explicit patch/materialize commands", async () => {
    const variant = {
      variant_id: "vertical-full",
      kind: "vertical_full",
      source_session_id: "session-a",
      source_session_revision: 1,
      variant_revision: 3,
      overrides: { crop: null, focal: null, caption: null, safe_area: null, audio: null },
      locks: [],
      conflicts: [],
    };
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(narrationManifest(1) as never);
    vi.spyOn(api, "getEditingSession").mockResolvedValue(editingSession("project-a", "session-a") as never);
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([] as never);
    vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [] } as never);
    vi.spyOn(api, "listLibraryAssets").mockResolvedValue({ assets: [], total: 0 } as never);
    vi.spyOn(api, "listJobs").mockResolvedValue([]);
    vi.spyOn(api, "listTtsCandidates").mockResolvedValue({ candidates: [] });
    vi.spyOn(api, "listYujinMemoryCandidates").mockResolvedValue([]);
    vi.spyOn(api, "reloadDirectorSession").mockResolvedValue({ conversation: null, messages: [], proposal: null, references: [] } as never);
    vi.spyOn(api, "listOutputVariants").mockResolvedValue({ variants: [variant] } as never);
    const patch = vi.spyOn(api, "patchOutputVariant").mockResolvedValue({ variant: { ...variant, variant_revision: 4, overrides: { ...variant.overrides, crop: { mode: "creator_adjusted" } } } } as never);
    const materialize = vi.spyOn(api, "materializeOutputVariant").mockResolvedValue({ materialization: { timeline_id: "timeline-variant", source_session_id: "session-a", source_session_revision: 1, source_variant_id: "vertical-full", source_variant_revision: 4 } } as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await screen.findByRole("region", { name: "편집 작업판" });
    fireEvent.click(screen.getByRole("button", { name: "출력 변형 펼치기" }));
    fireEvent.click(screen.getByRole("tab", { name: "세로" }));
    expect(await screen.findByText("서버 변형 버전 3")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "크롭 저장" }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("project-a", "vertical-full", expect.objectContaining({ expected_variant_revision: 3 })));
    fireEvent.click(screen.getByRole("button", { name: "세로 변형 준비" }));
    await waitFor(() => expect(materialize).toHaveBeenCalledWith("project-a", "vertical-full", { expected_master_session_revision: 1 }));
  });
});
