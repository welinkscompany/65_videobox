import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { EditorWorkbench, persistedPanelPixels } from "./EditorWorkbench";
import * as previewStageModule from "../preview/preview-stage";
import * as timelineDockModule from "../timeline/TimelineDock";

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

// 왼쪽 재료 열은 이제 기본으로 펴져 있다(owner 승인 2026-08-17). 그냥 누르면 열리는
// 게 아니라 **닫힌다** -- 이 토글이 아래 테스트 13개를 한 번에 깨뜨렸다. 좁은 폭에서는
// 여전히 닫힌 서랍으로 시작하므로 누르는 동작 자체는 남겨 둔다.
function openMaterialDock(): void {
  if (screen.queryByRole("complementary", { name: "자산과 대본" })) return;
  fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));
}


// 편집 항목은 이제 기본으로 펴져 있다(캡컷처럼 고른 것의 속성이 바로 보인다).
// 무조건 누르면 오히려 **닫힌다** -- 좁은 화면이나 접어 둔 상태에서만 누른다.
function openInspector(): void {
  if (screen.queryByRole("region", { name: "편집 항목" })) return;
  fireEvent.click(screen.getByRole("button", { name: "편집 항목 열기" }));
}

describe("EditorWorkbench", () => {
  it("lets the creator decide how tall the timeline is", async () => {
    // 컷을 딸 때는 타임라인을 키우고 화면을 볼 때는 미리보기를 키운다 -- 편집자가
    // 실제로 하는 일이다. 지금은 내가 CSS로 정해 놓아서 못 바꾼다.
    //
    // 이걸 넣으면 "타임라인이 화면의 몇 %여야 하나"라는 물음 자체가 사라진다.
    // 좌우 도크는 이미 끌어서 폭을 바꾼다 -- 위아래도 같아야 한다.
    render(<EditorWorkbench view={view} />);
    const workbench = await screen.findByRole("region", { name: "편집 작업판" });
    const handle = screen.getByLabelText("타임라인 높이 조절");

    fireEvent.keyDown(handle, { key: "ArrowUp" });

    expect(workbench.style.getPropertyValue("--vb-timeline-height")).toBe("21rem");
  });

  it("keeps the timeline height between a floor and a ceiling", async () => {
    // 0으로 줄이면 타임라인이 사라지고, 끝까지 키우면 미리보기가 사라진다.
    render(<EditorWorkbench view={view} />);
    const workbench = await screen.findByRole("region", { name: "편집 작업판" });
    const handle = screen.getByLabelText("타임라인 높이 조절");

    for (let index = 0; index < 40; index += 1) fireEvent.keyDown(handle, { key: "ArrowDown" });
    expect(workbench.style.getPropertyValue("--vb-timeline-height")).toBe("6rem");

    for (let index = 0; index < 80; index += 1) fireEvent.keyDown(handle, { key: "ArrowUp" });
    expect(workbench.style.getPropertyValue("--vb-timeline-height")).toBe("32rem");
  });

  it("remembers the chosen timeline height across a reload, like the dock widths", async () => {
    // 어제 세션이 남긴 구멍: 끌어서 정한 높이가 새로고침하면 기본값으로 돌아갔다.
    // 좌우 도크 폭이 저장되는 자리(`editorUiState`)에 같이 저장한다.
    const first = render(<EditorWorkbench view={view} />);
    await screen.findByRole("region", { name: "편집 작업판" });
    fireEvent.keyDown(screen.getByLabelText("타임라인 높이 조절"), { key: "ArrowUp" });
    first.unmount();

    render(<EditorWorkbench view={view} />);
    const workbench = await screen.findByRole("region", { name: "편집 작업판" });

    expect(workbench.style.getPropertyValue("--vb-timeline-height")).toBe("21rem");
  });

  it("shows the dock the creator just asked for, instead of leaving the button dead", async () => {
    // 2026-08-19 배포 화면에서 확인: 좁은 데스크톱에서는 도크가 하나만 보이는데
    // **왼쪽이 늘 이겨서** `유진과 편집 항목`을 눌러도 아무 일이 없는 것처럼
    // 보였다. 왼쪽을 먼저 닫아야 오른쪽이 나왔다 -- 처음 쓰는 사람은 고장으로 읽는다.
    render(<EditorWorkbench view={view} />);
    const workbench = await screen.findByRole("region", { name: "편집 작업판" });
    expect(workbench).toHaveAttribute("data-editor-density", "desktop-single");
    expect(screen.getByRole("complementary", { name: "자산과 대본" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));

    expect(screen.getByRole("complementary", { name: "유진과 편집 항목" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "자산과 대본" })).toBeNull();
  });

  it("gives the material dock back the same way, without needing a second click", async () => {
    render(<EditorWorkbench view={view} />);
    await screen.findByRole("region", { name: "편집 작업판" });
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));

    fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));

    expect(screen.getByRole("complementary", { name: "자산과 대본" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "유진과 편집 항목" })).toBeNull();
  });

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

    openMaterialDock();
    fireEvent.click(await screen.findByRole("button", { name: "제품 사진 원본 미리보기" }));

    expect(screen.getByLabelText("제품 사진 소스 미리보기")).toBeInTheDocument();
    expect(screen.getByLabelText("제품 사진 소스 미리보기").tagName).toBe("IMG");
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    expect(container.querySelectorAll("img")).toHaveLength(1);
  });

  it("uses audio elements for both B-roll audio and library audio cards", async () => {
    const audioCards = [
      { ...assetCards[0], id: "broll:audio-1", assetId: "audio-1", title: "현장 오디오", label: "오디오 B-roll", previewUrl: "/api/projects/project-a/assets/audio-1/content", previewKind: "audio" as const },
      { ...assetCards[0], id: "library:bgm-1", assetId: "starter-bgm", libraryAssetId: "bgm-1", title: "배경 음악 1", label: "배경 음악", previewUrl: "/api/media-library/assets/bgm-1/preview", previewKind: "audio" as const },
    ];
    const { container } = render(<EditorWorkbench view={view} assetCards={audioCards} />);

    openMaterialDock();
    fireEvent.click(await screen.findByRole("button", { name: "현장 오디오 원본 미리보기" }));
    expect(screen.getByLabelText("현장 오디오 소스 미리보기").tagName).toBe("AUDIO");
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "배경 음악 1 원본 미리보기" }));
    expect(screen.getByLabelText("배경 음악 1 소스 미리보기").tagName).toBe("AUDIO");
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
  });

  it("prepares project video before handing its URL to the single PreviewStage player", async () => {
    let resolvePreview!: (url: string) => void;
    const prepared = new Promise<string>((resolve) => { resolvePreview = resolve; });
    const video = { ...assetCards[0], id: "broll:video-1", assetId: "video-1", title: "HEVC 영상", label: "영상 B-roll", previewKind: "video" as const, requiresBrowserPreviewPreparation: true };
    const onPrepareAssetPreview = vi.fn(() => prepared);
    const { container } = render(<EditorWorkbench view={view} assetCards={[video]} onPrepareAssetPreview={onPrepareAssetPreview} />);

    openMaterialDock();
    fireEvent.click(screen.getByRole("button", { name: "HEVC 영상 원본 미리보기" }));
    expect(screen.getByText("원본 미리보기를 준비하고 있어요")).toBeVisible();
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    await act(async () => resolvePreview("/api/proxy/video-1"));

    expect(await screen.findByLabelText("HEVC 영상 소스 미리보기")).toHaveAttribute("src", "/api/proxy/video-1");
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
  });

  it("ignores an older video preparation result after a newer card click", async () => {
    const resolvers: Array<(url: string) => void> = [];
    const first = { ...assetCards[0], id: "broll:video-1", assetId: "video-1", title: "첫 영상", previewKind: "video" as const, requiresBrowserPreviewPreparation: true };
    const second = { ...first, id: "broll:video-2", assetId: "video-2", title: "둘째 영상" };
    const onPrepareAssetPreview = vi.fn(() => new Promise<string>((resolve) => resolvers.push(resolve)));
    render(<EditorWorkbench view={view} assetCards={[first, second]} onPrepareAssetPreview={onPrepareAssetPreview} />);

    openMaterialDock();
    fireEvent.click(screen.getByRole("button", { name: "첫 영상 원본 미리보기" }));
    fireEvent.click(screen.getByRole("button", { name: "둘째 영상 원본 미리보기" }));
    await act(async () => resolvers[0]("/api/proxy/old"));
    expect(screen.queryByLabelText("첫 영상 소스 미리보기")).toBeNull();
    await act(async () => resolvers[1]("/api/proxy/new"));
    expect(await screen.findByLabelText("둘째 영상 소스 미리보기")).toHaveAttribute("src", "/api/proxy/new");
  });

  it("uses only a selected narration clip as the asset apply target and forwards it upward", () => {
    const onApplyAssetCard = vi.fn();
    const narrationView = {
      ...view,
      output: { ...view.output, durationSec: 4 },
      tracks: [{ trackId: "narration", role: "narration", clips: [{ clipId: "n-1", segmentId: "segment-1", type: "narration", assetId: null, assetUri: null, startSec: 1, endSec: 3, controls: {} }] }],
    } as const;
    render(<EditorWorkbench view={narrationView} assetCards={assetCards} onApplyAssetCard={onApplyAssetCard} />);
    openMaterialDock();

    expect(screen.getByRole("button", { name: "제품 사진 적용" })).toBeDisabled();
    fireEvent.click(clipSelectionButton("n-1"));
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
    openMaterialDock();

    fireEvent.click(clipSelectionButton("caption:visible-2"));
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
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));

    expect(screen.getByText("남아 있는 요청")).toBeVisible();
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("보존된 초안");
    fireEvent.click(screen.getByRole("button", { name: "유진 없이 계속 편집" }));
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
    openMaterialDock();
    const player = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    Object.defineProperty(player, "currentTime", { configurable: true, writable: true, value: 0 });

    fireEvent.click(clipSelectionButton("n-2"));
    expect(screen.getByRole("button", { name: "둘째 자막 대본 선택" })).toHaveAttribute("aria-current", "true");
    fireEvent.click(screen.getByRole("button", { name: "첫 자막 대본 선택" }));
    expect(clipSelectionButton("n-1")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
    fireEvent.click(screen.getByRole("button", { name: "둘째 자막 대본 선택" }));
    expect(player.currentTime).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: "첫 자막 대본 선택" }));
    fireEvent.click(clipSelectionButton("n-2"));
    rendered.rerender(<EditorWorkbench view={{ ...transcriptView, expectedRevision: 2, tracks: [{ ...transcriptView.tracks[0], clips: [transcriptView.tracks[0].clips[0]] }], captions: [transcriptView.captions[0]] }} />);
    expect(screen.getByRole("button", { name: "첫 자막 대본 선택" })).not.toHaveAttribute("aria-current");
  });

  it("seeks the preview and selects the segment when an independent B-roll clip is clicked", () => {
    const brollView = {
      ...view,
      output: { ...view.output, durationSec: 10 },
      tracks: [{ trackId: "broll", role: "broll", clips: [{
        clipId: "b-2", placementId: "broll:b-2", segmentId: "segment-2", type: "broll",
        assetId: "asset-b", assetUri: null, startSec: 5, endSec: 10, controls: {},
      }] }],
      captions: [{ segmentId: "segment-2", text: "둘째 자막", startSec: 5, endSec: 10, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0 } }],
      playback: { auditionUrls: {}, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-preview/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 10 } },
    } as const;
    render(<EditorWorkbench view={brollView} />);
    openMaterialDock();
    const player = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    Object.defineProperty(player, "currentTime", { configurable: true, writable: true, value: 0 });

    fireEvent.click(clipSelectionButton("broll:b-2"));

    expect(player.currentTime).toBe(5);
    expect(screen.getByRole("button", { name: "둘째 자막 대본 선택" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "5");
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
    openInspector();
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
    openMaterialDock();
    fireEvent.click(screen.getByRole("button", { name: "내레이션 · 1번째 장면 원본 열기" }));
    expect(screen.getByLabelText("내레이션 · 1번째 장면 소스 미리보기").tagName).toBe("AUDIO");
    expect(screen.getByLabelText("내레이션 · 1번째 장면 소스 미리보기")).not.toHaveAttribute("autoplay");
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
  });

  it("keeps source review in the asset dock, not under the preview, and reaches it from a narrow drawer too", () => {
    const narrationView = {
      ...view,
      playback: { auditionUrls: { "asset-n": "/api/projects/project-a/assets/asset-n/content" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "narration", role: "narration", clips: [{ clipId: "clip-n", segmentId: "segment-n", type: "narration", assetId: "asset-n", assetUri: null, startSec: 0, endSec: 1, controls: {} }] }],
    } as const;
    render(<EditorWorkbench view={narrationView} />);
    openMaterialDock();
    const preview = screen.getByRole("region", { name: "미리보기" });
    const dock = screen.getByRole("complementary", { name: "자산과 대본" });
    const button = screen.getByRole("button", { name: "내레이션 · 1번째 장면 원본 열기" });
    expect(preview.contains(button)).toBe(false);
    expect(dock.contains(button)).toBe(true);
    cleanup();

    // Narrow drawer mode: the same button must still be reachable, not stranded.
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    render(<EditorWorkbench view={narrationView} />);
    openMaterialDock();
    fireEvent.click(screen.getByRole("button", { name: "내레이션 · 1번째 장면 원본 열기" }));
    expect(screen.getByLabelText("내레이션 · 1번째 장면 소스 미리보기").tagName).toBe("AUDIO");
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
    openMaterialDock();
    fireEvent.click(screen.getByRole("button", { name: "내레이션 · 1번째 장면 원본 열기" }));
    expect(screen.getByLabelText("내레이션 · 1번째 장면 소스 미리보기")).toBeInTheDocument();
    fireEvent.click(clipSelectionButton("clip-a"));
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "1");

    rendered.rerender(<EditorWorkbench view={{
      ...routeA,
      projectId: "project-b",
      sessionId: "session-b",
      timelineId: "timeline-b",
      playback: { auditionUrls: { "asset-shared": "/api/projects/project-b/assets/asset-shared/content" }, exactPreview: { status: "unavailable" as const } },
      tracks: [{ ...routeA.tracks[0], clips: [{ ...routeA.tracks[0].clips[0], clipId: "clip-b" }] }],
    } as never} />);

    expect(screen.queryByLabelText("내레이션 · 1번째 장면 소스 미리보기")).toBeNull();
    expect(clipSelectionButton("clip-b")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
  });

  it("keys all route-local player and timeline state before the first render of a new route", async () => {
    vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockReturnValue({
      width: 1600,
    } as DOMRect);
    const observedPreview: Array<Readonly<{
      auditionRequest: previewStageModule.AuditionRequest | null | undefined;
      playbackSec: number | undefined;
    }>> = [];
    const observedTimeline: Array<Readonly<{
      projectId: string;
      selectedSegmentId: string | null | undefined;
      playbackSec: number | undefined;
    }>> = [];
    vi.spyOn(previewStageModule, "PreviewStage").mockImplementation((props) => {
      observedPreview.push({
        auditionRequest: props.auditionRequest,
        playbackSec: props.playbackSec,
      });
      return <section aria-label="미리보기" />;
    });
    vi.spyOn(timelineDockModule, "TimelineDock").mockImplementation((props) => {
      observedTimeline.push({
        projectId: props.view.projectId,
        selectedSegmentId: props.selectedSegmentId,
        playbackSec: props.playbackSec,
      });
      return <section aria-label="타임라인" />;
    });
    const routeA = {
      ...view,
      output: { ...view.output, durationSec: 3 },
      local: { selectedSegmentId: "segment-shared", seekSec: 1.25 },
      tracks: [{
        trackId: "narration",
        role: "narration" as const,
        clips: [{
          clipId: "clip-a",
          segmentId: "segment-shared",
          type: "narration",
          assetId: null,
          assetUri: null,
          startSec: 0,
          endSec: 2,
          controls: {},
        }],
      }],
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
    fireEvent.click(screen.getByRole("button", { name: "유진과 편집 항목" }));

    fireEvent.click(screen.getByRole("button", { name: "A-01 미리 보기" }));
    await waitFor(() => expect(
      observedPreview.at(-1)?.auditionRequest?.source.url,
    ).toContain("/project-a/"));

    observedPreview.length = 0;
    observedTimeline.length = 0;
    rendered.rerender(<EditorWorkbench
      director={director}
      view={{ ...routeA, expectedRevision: 2 }}
    />);
    expect(observedPreview.at(-1)).toMatchObject({
      auditionRequest: expect.objectContaining({
        source: expect.objectContaining({ url: expect.stringContaining("/project-a/") }),
      }),
      playbackSec: 1.25,
    });
    expect(observedTimeline.at(-1)).toMatchObject({
      projectId: "project-a",
      selectedSegmentId: "segment-shared",
      playbackSec: 1.25,
    });

    observedPreview.length = 0;
    observedTimeline.length = 0;
    rendered.rerender(<EditorWorkbench
      director={director}
      view={{
        ...routeA,
        projectId: "project-b",
        sessionId: "session-b",
        timelineId: "timeline-b",
        local: { selectedSegmentId: null, seekSec: 0.25 },
      }}
    />);
    expect(observedPreview[0]).toEqual({
      auditionRequest: null,
      playbackSec: 0.25,
    });
    expect(observedTimeline[0]).toEqual({
      projectId: "project-b",
      selectedSegmentId: null,
      playbackSec: 0.25,
    });
  });

  it("uses a video element for a source-backed visual overlay audition rather than treating it as audio", () => {
    const overlayView = {
      ...view,
      playback: { auditionUrls: { "asset-o": "/api/projects/project-a/assets/asset-o/content" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "overlay", role: "overlay", clips: [{ clipId: "clip-o", segmentId: "segment-o", type: "overlay", assetId: "asset-o", assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: null, overlayPayload: {} }] }],
    } as const;
    render(<EditorWorkbench view={overlayView} />);
    openMaterialDock();
    fireEvent.click(screen.getByRole("button", { name: "화면 표시 · 1번째 장면 원본 열기" }));
    expect(screen.getByLabelText("화면 표시 · 1번째 장면 소스 미리보기").tagName).toBe("VIDEO");
  });

  it("starts with output variants collapsed, expands on demand, and remembers the choice per project", async () => {
    const { unmount } = render(<EditorWorkbench view={view} />);
    const toggle = screen.getByRole("button", { name: "출력 변형 펼치기" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    // Collapsed: only the header/toggle are present, none of the expanded body.
    expect(screen.queryByRole("tablist", { name: "출력 변형 보기" })).toBeNull();
    expect(screen.queryByText("현재 마스터 편집본을 기준으로 출력 변형을 확인합니다.")).toBeNull();

    fireEvent.click(toggle);
    expect(await screen.findByRole("button", { name: "출력 변형 접기" })).toHaveAttribute("aria-expanded", "true");
    // Expanded: everything that was there before this task is still reachable.
    expect(screen.getByRole("tablist", { name: "출력 변형 보기" })).toBeInTheDocument();
    expect(screen.getByText("현재 마스터 편집본을 기준으로 출력 변형을 확인합니다.")).toBeInTheDocument();

    unmount();
    // Same project+session: remembers expanded.
    render(<EditorWorkbench view={view} />);
    expect(screen.getByRole("button", { name: "출력 변형 접기" })).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps a fresh project's output variants collapsed even after another project was expanded", async () => {
    const { unmount } = render(<EditorWorkbench view={view} />);
    fireEvent.click(screen.getByRole("button", { name: "출력 변형 펼치기" }));
    expect(await screen.findByRole("button", { name: "출력 변형 접기" })).toBeInTheDocument();
    unmount();

    render(<EditorWorkbench view={{ ...view, projectId: "project-b", sessionId: "session-b" }} />);
    expect(screen.getByRole("button", { name: "출력 변형 펼치기" })).toHaveAttribute("aria-expanded", "false");
  });

  it("excludes an image overlay from the video or audio audition player", () => {
    const imageOverlayView = {
      ...view,
      playback: { auditionUrls: { "asset-image": "/api/projects/project-a/assets/asset-image/content.png" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "overlay", role: "overlay", clips: [{ clipId: "clip-image", segmentId: "segment-image", type: "overlay", assetId: "asset-image", assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "image_overlay", overlayPayload: {} }] }],
    } as const;
    const { container } = render(<EditorWorkbench view={imageOverlayView} />);
    expect(screen.queryByRole("button", { name: "화면 표시 · 1번째 장면 원본 열기" })).toBeNull();
    expect(container.querySelectorAll("video, audio")).toHaveLength(1);
    expect(screen.getByLabelText("편집본 미리보기")).toBeInTheDocument();
  });
});

describe("EditorWorkbench 되돌리기 단축키", () => {
  const session = { undoCount: 2, redoCount: 1 } as never;

  it("Ctrl+Z 로 한 단계씩 되돌린다", () => {
    const onUndo = vi.fn();
    render(<EditorWorkbench view={view} session={session} onUndo={onUndo} />);

    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    expect(onUndo).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: "z", metaKey: true });
    expect(onUndo).toHaveBeenCalledTimes(2);
  });

  it("다시 실행은 두 관습을 모두 받는다", () => {
    // Creative apps use Ctrl+Shift+Z; Office-style apps use Ctrl+Y. Accepting
    // only one leaves the other silently doing nothing.
    const onRedo = vi.fn();
    render(<EditorWorkbench view={view} session={session} onRedo={onRedo} />);

    fireEvent.keyDown(window, { key: "z", ctrlKey: true, shiftKey: true });
    expect(onRedo).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: "y", ctrlKey: true });
    expect(onRedo).toHaveBeenCalledTimes(2);
  });

  it("표준이 아닌 Alt+Z 로는 아무 일도 하지 않는다", () => {
    // Alt+Z means undo nowhere. Binding it would invite pressing it for redo
    // and getting a second undo instead.
    const onUndo = vi.fn();
    const onRedo = vi.fn();
    render(<EditorWorkbench view={view} session={session} onUndo={onUndo} onRedo={onRedo} />);

    fireEvent.keyDown(window, { key: "z", altKey: true });

    expect(onUndo).not.toHaveBeenCalled();
    expect(onRedo).not.toHaveBeenCalled();
  });

  it("글자를 치는 중에는 편집을 되돌리지 않는다", () => {
    // Undoing the whole edit while the owner is fixing a caption would throw
    // away their typing and a real edit at once.
    const onUndo = vi.fn();
    render(<EditorWorkbench view={view} session={session} onUndo={onUndo} />);
    const field = document.createElement("textarea");
    document.body.appendChild(field);
    field.focus();

    fireEvent.keyDown(field, { key: "z", ctrlKey: true });

    expect(onUndo).not.toHaveBeenCalled();
    field.remove();
  });

  it("되돌릴 것이 없으면 아무 일도 하지 않는다", () => {
    const onUndo = vi.fn();
    render(<EditorWorkbench view={view} session={{ undoCount: 0, redoCount: 0 } as never} onUndo={onUndo} />);

    fireEvent.keyDown(window, { key: "z", ctrlKey: true });

    expect(onUndo).not.toHaveBeenCalled();
  });
});
