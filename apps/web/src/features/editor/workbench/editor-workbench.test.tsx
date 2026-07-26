import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { EditorWorkbench, persistedPanelPixels } from "./EditorWorkbench";
import * as previewStageModule from "../preview/preview-stage";

const assetCards = [{
  id: "broll:image-1",
  kind: "broll" as const,
  assetId: "image-1",
  label: "이미지 B-roll",
  title: "제품 사진",
  durationLabel: "4초",
  status: "준비됨 · 검토 불필요",
  audioPresence: "오디오 없음" as const,
  license: "프로젝트 로컬 B-roll",
  canApply: true,
  previewUrl: "/api/projects/project-a/assets/image-1/content",
  previewKind: "image" as const,
  sourceMetadata: { tags: [], source: "프로젝트 로컬 B-roll", creator: "", officialLicenseUrl: "", attributionRequired: false, attributionText: "" },
}] as const;

beforeEach(() => { vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1000 } as DOMRect); vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined); Object.defineProperty(window, "innerWidth", { configurable: true, value: 1920 }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.localStorage.clear(); });

const view = { projectId: "project-a", sessionId: "session-a", timelineId: "timeline-a", timelineVersion: "v1", expectedRevision: 1, timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sampleAspectRatio: "1:1", rotation: 0, durationSec: 1 }, tracks: [], captions: [], gaps: [], source: { status: "current" }, playback: { auditionUrls: {}, exactPreview: { status: "unavailable" } }, local: { selectedSegmentId: null, seekSec: 0 } } as const;

describe("EditorWorkbench", () => {
  it("uses the measured workbench width rather than viewport width", async () => {
    render(<EditorWorkbench view={view} />);
    expect(await screen.findByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-density", "desktop-single");
    expect(screen.getByText("편집 작업판", { selector: "strong" })).toBeInTheDocument();
    expect(screen.queryByText("읽기 전용 편집 작업판", { selector: "strong" })).toBeNull();
    expect(screen.getByRole("region", { name: "미리보기" }).parentElement).toHaveAttribute("data-preview-min-width", "640");
  });

  it("opens a narrow drawer, focuses it, and restores the trigger after Escape", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    render(<EditorWorkbench view={view} />);
    const trigger = screen.getByRole("button", { name: "유진과 편집 항목" });
    fireEvent.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "유진과 편집 항목" });
    expect(dialog).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it.each([
    ["desktop", 1920],
    ["narrow left drawer", 390],
  ])("sends an asset-card preview through the workbench stage in the %s", async (_layout, width) => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
    const { container } = render(<EditorWorkbench view={view} assetCards={assetCards} />);

    if (width === 390) fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));
    fireEvent.click(await screen.findByRole("button", { name: "제품 사진 원본 미리보기" }));

    expect(screen.getByLabelText("제품 사진 소스 미리보기")).toBeInTheDocument();
    expect(screen.getByLabelText("제품 사진 소스 미리보기").tagName).toBe("IMG");
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    expect(container.querySelectorAll("img")).toHaveLength(1);
  });

  it("uses audio elements for both B-roll audio and library audio cards", async () => {
    const audioCards = [
      { ...assetCards[0], id: "broll:audio-1", assetId: "audio-1", title: "현장 오디오", label: "오디오 B-roll", previewUrl: "/api/projects/project-a/assets/audio-1/content", previewKind: "audio" as const },
      { ...assetCards[0], id: "library:bgm-1", assetId: "starter-bgm", libraryAssetId: "bgm-1", title: "BGM 1", label: "BGM", previewUrl: "/api/media-library/assets/bgm-1/preview", previewKind: "audio" as const },
    ];
    const { container } = render(<EditorWorkbench view={view} assetCards={audioCards} />);

    fireEvent.click(await screen.findByRole("button", { name: "현장 오디오 원본 미리보기" }));
    expect(screen.getByLabelText("현장 오디오 소스 미리보기").tagName).toBe("AUDIO");
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "BGM 1 원본 미리보기" }));
    expect(screen.getByLabelText("BGM 1 소스 미리보기").tagName).toBe("AUDIO");
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
  });

  it("uses only a selected narration clip as the asset apply target and forwards it upward", () => {
    const onApplyAssetCard = vi.fn();
    const narrationView = {
      ...view,
      output: { ...view.output, durationSec: 4 },
      tracks: [{ trackId: "narration", role: "narration", clips: [{ clipId: "n-1", segmentId: "segment-1", type: "narration", assetId: null, assetUri: null, startSec: 1, endSec: 3, controls: {} }] }],
    } as const;
    render(<EditorWorkbench view={narrationView} assetCards={assetCards} onApplyAssetCard={onApplyAssetCard} />);

    expect(screen.getByRole("button", { name: "제품 사진 적용" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    expect(screen.getAllByText("적용 구간: 1.00–3.00초").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "제품 사진 적용" }));
    expect(onApplyAssetCard).toHaveBeenCalledWith(assetCards[0], "segment-1");
  });

  it("uses a selected session caption as the asset target when narration is one long source clip", () => {
    const onApplyAssetCard = vi.fn();
    const sessionSegmentView = {
      ...view,
      output: { ...view.output, durationSec: 10 },
      tracks: [{ trackId: "narration", role: "narration", clips: [
        { clipId: "n-1", segmentId: "visible-1", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 10, controls: {} },
      ] }],
      captions: [
        { segmentId: "visible-1", placementId: "caption:visible-1", text: "첫 장면", startSec: 0, endSec: 5, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0 } },
        { segmentId: "visible-2", placementId: "caption:visible-2", text: "둘째 장면", startSec: 5, endSec: 10, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0 } },
      ],
    } as const;
    render(<EditorWorkbench view={sessionSegmentView} assetCards={assetCards} onApplyAssetCard={onApplyAssetCard} />);

    fireEvent.click(screen.getByRole("button", { name: "caption:visible-2 클립 선택" }));
    expect(screen.getAllByText("적용 구간: 5.00–10.00초").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "제품 사진 적용" }));
    expect(onApplyAssetCard).toHaveBeenCalledWith(assetCards[0], "visible-2");
  });

  it("renders the disabled Eugene draft from the route-owned Director control", () => {
    window.localStorage.setItem("videobox.editor-workbench.ui", JSON.stringify({ leftOpen: false, rightOpen: true, activeDrawer: null, leftSize: 280, rightSize: 320 }));
    const director = {
      state: "idle",
      messages: [],
      proposal: null,
      draft: "다음에 확인할 추천 초안",
      runState: { kind: "idle" },
      selectedCandidateIds: [],
      conversationScroll: { key: "project-a:session-a", top: 0, pinnedToBottom: true },
      composerDisabled: true,
      onDraftChange: vi.fn(),
      onSelectedCandidateIdsChange: vi.fn(),
      onConversationScrollChange: vi.fn(),
      onSendMessage: vi.fn(),
      onApplyProposal: vi.fn(),
      onManualEdit: vi.fn(),
      onPreviewCandidate: vi.fn(),
    } as const;
    const rendered = render(<EditorWorkbench director={director} view={view} />);
    const composer = screen.getByLabelText("유진에게 요청하기");
    expect(composer).toHaveValue("다음에 확인할 추천 초안");
    expect(composer).toBeDisabled();
    rendered.unmount();
    render(<EditorWorkbench director={director} view={view} />);
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("다음에 확인할 추천 초안");
  });

  it("persists finite panel pixel values and rejects invalid resize values", () => {
    expect(persistedPanelPixels({ asPercentage: 30, inPixels: 401.2 }, 260, 320)).toBe(401);
    expect(persistedPanelPixels({ asPercentage: 30, inPixels: Number.NaN }, 260, 320)).toBe(320);
  });

  it("keeps manual controls available when global localStorage is denied or full", () => {
    vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockReturnValue({
      width: 1600,
    } as DOMRect);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("PRIVATE denied", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("PRIVATE full", "QuotaExceededError");
    });
    const onManualEdit = vi.fn();
    const director = {
      state: "blocked",
      messages: [{ id: "user-1", role: "user", text: "남아 있는 요청" }],
      proposal: null,
      draft: "보존된 초안",
      runState: { kind: "unavailable", message: "유진의 답을 받지 못했어요." },
      selectedCandidateIds: [],
      conversationScroll: { key: "project-a:session-a", top: 0, pinnedToBottom: true },
      onDraftChange: vi.fn(),
      onSelectedCandidateIdsChange: vi.fn(),
      onConversationScrollChange: vi.fn(),
      onSendMessage: vi.fn(),
      onApplyProposal: vi.fn(),
      onManualEdit,
      onPreviewCandidate: vi.fn(),
    } as const;

    render(<EditorWorkbench director={director} view={view} />);

    expect(screen.getByText("남아 있는 요청")).toBeVisible();
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("보존된 초안");
    fireEvent.click(screen.getByRole("button", { name: "Yujin 없이 계속 편집" }));
    expect(onManualEdit).toHaveBeenCalledOnce();
  });

  it("keeps transcript, playback position, and narration clip selection on one segment id", () => {
    const transcriptView = {
      ...view,
      output: { ...view.output, durationSec: 2 },
      tracks: [{ trackId: "narration", role: "narration", clips: [
        { clipId: "n-1", segmentId: "segment-1", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {} },
        { clipId: "n-2", segmentId: "segment-2", type: "narration", assetId: null, assetUri: null, startSec: 1, endSec: 2, controls: {} },
      ] }],
      captions: [
        { segmentId: "segment-1", text: "첫 자막", startSec: 0, endSec: 1, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0 } },
        { segmentId: "segment-2", text: "둘째 자막", startSec: 1, endSec: 2, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0 } },
      ],
      playback: { auditionUrls: {}, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-preview/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 2 } },
    } as const;
    const rendered = render(<EditorWorkbench view={transcriptView} />);
    const player = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    Object.defineProperty(player, "currentTime", { configurable: true, writable: true, value: 0 });

    fireEvent.click(screen.getByRole("button", { name: "n-2 클립 선택" }));
    expect(screen.getByRole("button", { name: "둘째 자막 대본 선택" })).toHaveAttribute("aria-current", "true");
    fireEvent.click(screen.getByRole("button", { name: "첫 자막 대본 선택" }));
    expect(screen.getByRole("button", { name: "n-1 클립 선택" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
    fireEvent.click(screen.getByRole("button", { name: "둘째 자막 대본 선택" }));
    expect(player.currentTime).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: "첫 자막 대본 선택" }));
    fireEvent.click(screen.getByRole("button", { name: "n-2 클립 선택" }));
    rendered.rerender(<EditorWorkbench view={{ ...transcriptView, expectedRevision: 2, tracks: [{ ...transcriptView.tracks[0], clips: [transcriptView.tracks[0].clips[0]] }], captions: [transcriptView.captions[0]] }} />);
    expect(screen.getByRole("button", { name: "첫 자막 대본 선택" })).not.toHaveAttribute("aria-current");
  });

  it("replaces only the preview slot with the exact-preview stage while keeping read-only docks and timeline", () => {
    const currentView = {
      ...view,
      playback: { auditionUrls: { "asset-b": "/api/projects/project-a/assets/asset-b/content" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "broll", role: "broll", clips: [{ clipId: "clip-b", segmentId: "segment-b", type: "broll", assetId: "asset-b", assetUri: null, startSec: 0, endSec: 1, controls: {} }] }],
    } as const;
    render(<EditorWorkbench view={currentView} />);
    expect(screen.getByRole("region", { name: "미리보기" })).toBeInTheDocument();
    expect(screen.getByLabelText("편집본 미리보기")).toHaveAttribute("src", "/api/projects/project-a/exact-previews/g4/content");
    expect(screen.getByRole("region", { name: "타임라인" })).toHaveTextContent("1개 트랙");
  });

  it("uses the Inspector registry instead of exposing an unsupported B-roll track", () => {
    const brollOnlyView = {
      ...view,
      local: { selectedSegmentId: "segment-b", seekSec: 0 },
      tracks: [{ trackId: "broll", role: "broll", clips: [{ clipId: "clip-b", segmentId: "segment-b", type: "broll", assetId: "asset-b", assetUri: null, startSec: 0, endSec: 1, controls: {} }] }],
    } as const;
    window.localStorage.setItem("videobox.editor-workbench.ui", JSON.stringify({ leftOpen: false, rightOpen: true, activeDrawer: null, leftSize: 280, rightSize: 320 }));
    render(<EditorWorkbench view={brollOnlyView} />);
    fireEvent.click(screen.getByRole("button", { name: "편집 항목 열기" }));
    expect(screen.getByRole("region", { name: "편집 항목" })).not.toHaveTextContent("broll 트랙");
    expect(screen.getByText("현재 편집 명령이 지원하는 항목만 표시됩니다.")).toBeInTheDocument();
  });

  it("uses an audio element for a narration audition and never mounts a second player", () => {
    const narrationView = {
      ...view,
      playback: { auditionUrls: { "asset-n": "/api/projects/project-a/assets/asset-n/content" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "narration", role: "narration", clips: [{ clipId: "clip-n", segmentId: "segment-n", type: "narration", assetId: "asset-n", assetUri: null, startSec: 0, endSec: 1, controls: {} }] }],
    } as const;
    const { container } = render(<EditorWorkbench view={narrationView} />);
    fireEvent.click(screen.getByRole("button", { name: "NARRATION · segment-n 원본 열기" }));
    expect(screen.getByLabelText("NARRATION · segment-n 소스 미리보기").tagName).toBe("AUDIO");
    expect(screen.getByLabelText("NARRATION · segment-n 소스 미리보기")).not.toHaveAttribute("autoplay");
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
  });

  it("resets selection, seek, and audition media when a different route reuses the same segment id", () => {
    const routeA = {
      ...view,
      output: { ...view.output, durationSec: 2 },
      playback: { auditionUrls: { "asset-shared": "/api/projects/project-a/assets/asset-shared/content" }, exactPreview: { status: "unavailable" as const } },
      local: { selectedSegmentId: null, seekSec: 0 },
      tracks: [{ trackId: "narration", role: "narration" as const, clips: [{ clipId: "clip-a", segmentId: "segment-shared", type: "narration", assetId: "asset-shared", assetUri: null, startSec: 1, endSec: 2, controls: {} }] }],
    };
    const rendered = render(<EditorWorkbench view={routeA as never} />);
    fireEvent.click(screen.getByRole("button", { name: "NARRATION · segment-shared 원본 열기" }));
    expect(screen.getByLabelText("NARRATION · segment-shared 소스 미리보기")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "clip-a 클립 선택" }));
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "1");

    rendered.rerender(<EditorWorkbench view={{
      ...routeA,
      projectId: "project-b",
      sessionId: "session-b",
      timelineId: "timeline-b",
      playback: { auditionUrls: { "asset-shared": "/api/projects/project-b/assets/asset-shared/content" }, exactPreview: { status: "unavailable" as const } },
      tracks: [{ ...routeA.tracks[0], clips: [{ ...routeA.tracks[0].clips[0], clipId: "clip-b" }] }],
    } as never} />);

    expect(screen.queryByLabelText("NARRATION · segment-shared 소스 미리보기")).toBeNull();
    expect(screen.getByRole("button", { name: "clip-b 클립 선택" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
  });

  it("never passes a previous route audition into the first render of a new route", async () => {
    vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockReturnValue({
      width: 1600,
    } as DOMRect);
    const observed: Array<previewStageModule.AuditionRequest | null | undefined> = [];
    vi.spyOn(previewStageModule, "PreviewStage").mockImplementation((props) => {
      observed.push(props.auditionRequest);
      return <section aria-label="미리보기" />;
    });
    const routeA = {
      ...view,
      playback: {
        auditionUrls: {},
        exactPreview: { status: "unavailable" as const },
      },
    };
    const director = {
      state: "proposal_ready",
      messages: [],
      proposal: {
        proposalId: "proposal-a",
        status: "ready",
        candidates: [{
          candidateId: "candidate-a",
          visibleReferenceCode: "A-01",
          mediaType: "broll",
          previewUrl: "/api/projects/project-a/assets/candidate-a/content",
        }],
      },
      draft: "",
      runState: { kind: "idle" },
      selectedCandidateIds: ["candidate-a"],
      conversationScroll: { key: "project-a:session-a", top: 0, pinnedToBottom: true },
      onDraftChange: vi.fn(),
      onSelectedCandidateIdsChange: vi.fn(),
      onConversationScrollChange: vi.fn(),
      onSendMessage: vi.fn(),
      onApplyProposal: vi.fn(),
      onManualEdit: vi.fn(),
      onPreviewCandidate: vi.fn(),
    } as const;
    const rendered = render(<EditorWorkbench director={director} view={routeA} />);

    fireEvent.click(screen.getByRole("button", { name: "추천 미리 듣기" }));
    await waitFor(() => expect(observed.at(-1)?.source.url).toContain("/project-a/"));

    observed.length = 0;
    rendered.rerender(<EditorWorkbench
      director={director}
      view={{ ...routeA, expectedRevision: 2 }}
    />);
    expect(observed.some((request) => request?.source.url.includes("/project-a/"))).toBe(true);

    observed.length = 0;
    rendered.rerender(<EditorWorkbench
      director={director}
      view={{
        ...routeA,
        projectId: "project-b",
        sessionId: "session-b",
        timelineId: "timeline-b",
      }}
    />);
    expect(observed[0]).toBeNull();
    expect(observed.every((request) => request == null)).toBe(true);
  });

  it("uses a video element for a source-backed visual overlay audition rather than treating it as audio", () => {
    const overlayView = {
      ...view,
      playback: { auditionUrls: { "asset-o": "/api/projects/project-a/assets/asset-o/content" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "overlay", role: "overlay", clips: [{ clipId: "clip-o", segmentId: "segment-o", type: "overlay", assetId: "asset-o", assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: null, overlayPayload: {} }] }],
    } as const;
    render(<EditorWorkbench view={overlayView} />);
    fireEvent.click(screen.getByRole("button", { name: "OVERLAY · segment-o 원본 열기" }));
    expect(screen.getByLabelText("OVERLAY · segment-o 소스 미리보기").tagName).toBe("VIDEO");
  });

  it("excludes an image overlay from the video or audio audition player", () => {
    const imageOverlayView = {
      ...view,
      playback: { auditionUrls: { "asset-image": "/api/projects/project-a/assets/asset-image/content.png" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "overlay", role: "overlay", clips: [{ clipId: "clip-image", segmentId: "segment-image", type: "overlay", assetId: "asset-image", assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "image_overlay", overlayPayload: {} }] }],
    } as const;
    const { container } = render(<EditorWorkbench view={imageOverlayView} />);
    expect(screen.queryByRole("button", { name: "OVERLAY · segment-image 원본 열기" })).toBeNull();
    expect(container.querySelectorAll("video, audio")).toHaveLength(1);
    expect(screen.getByLabelText("편집본 미리보기")).toBeInTheDocument();
  });
});
