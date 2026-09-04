import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { EditorWorkbench, persistedPanelPixels } from "./EditorWorkbench";
import * as previewStageModule from "../preview/preview-stage";
import { ShellCanvasProvider, useShellCanvas } from "../../shell/shellCanvas";
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
  if (screen.queryByRole("complementary", { name: "미디어" })) return;
  // 승인 2026-08-30(버튼 단위 벤치마킹 2단계) -- 예전엔 아이콘 단추
  // 하나(`role="button"`)가 이 도크를 열고 닫았다. 지금은 캡컷처럼 편집기
  // 맨 위에 늘 떠 있는 콘텐츠 탭(`role="tab"`)이 그 자리를 맡는다.
  fireEvent.click(screen.getByRole("tab", { name: "미디어" }));
}


// 세부 정보(오른쪽) 도크도 이제 기본으로 펴져 있다(2026-08-22, 캡컷 배치).
// **무조건 누르면 오히려 닫힌다** -- 좁아서 안 보일 때만 누른다.
function openDetailDock(): void {
  if (screen.queryByRole("complementary", { name: "세부 정보" })) return;
  fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));
}

// 편집 항목은 `세부 정보` 도크 안에 직접 있다 -- 도크 자신이 이제 탭
// 없는 단일 패널이다(2026-08-30 후속, 추천이 유진 패널로 옮겨가면서
// `속성` 탭 구분 자체가 없어졌다). 도크가 닫혀 있을 때만 연다.
function openInspector(): void {
  openDetailDock();
}

// 유진 대화창은 2026-08-30 후속으로 속성/추천 도크에서 완전히 빠져
// 독립된 떠있는 패널이 됐다(owner 지시: "우리 유진 대화창도 캡컷처럼
// 해도 되" -- 캡컷 EditPilot과 같은 자리, `docs/reference/capcut-observed-2026-08-22.ko.md`
// §7). 도크와 무관하게 화면 구석의 알약 버튼을 눌러 연다. 기본은 닫힘이다.
function openYujin(): void {
  if (screen.queryByRole("region", { name: "유진" })) return;
  fireEvent.click(screen.getByRole("button", { name: "유진" }));
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
    // **왼쪽이 늘 이겨서** `세부 정보`을 눌러도 아무 일이 없는 것처럼
    // 보였다. 왼쪽을 먼저 닫아야 오른쪽이 나왔다 -- 처음 쓰는 사람은 고장으로 읽는다.
    render(<EditorWorkbench view={view} />);
    const workbench = await screen.findByRole("region", { name: "편집 작업판" });
    expect(workbench).toHaveAttribute("data-editor-density", "desktop-single");
    expect(screen.getByRole("complementary", { name: "미디어" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    expect(screen.getByRole("complementary", { name: "세부 정보" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "미디어" })).toBeNull();
  });

  it("gives the material dock back the same way, without needing a second click", async () => {
    render(<EditorWorkbench view={view} />);
    await screen.findByRole("region", { name: "편집 작업판" });
    fireEvent.click(screen.getByRole("button", { name: "세부 정보" }));

    fireEvent.click(screen.getByRole("tab", { name: "미디어" }));

    expect(screen.getByRole("complementary", { name: "미디어" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "세부 정보" })).toBeNull();
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
    const trigger = screen.getByRole("button", { name: "세부 정보" });
    fireEvent.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "세부 정보" });
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
        { segmentId: "visible-1", placementId: "caption:visible-1", text: "첫 장면", startSec: 0, endSec: 5, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0, bold: false, italic: false, letterSpacingPx: 0 } },
        { segmentId: "visible-2", placementId: "caption:visible-2", text: "둘째 장면", startSec: 5, endSec: 10, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0, bold: false, italic: false, letterSpacingPx: 0 } },
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
    openYujin();
    const composer = screen.getByLabelText("유진에게 요청하기");
    expect(composer).toHaveValue("다음에 확인할 추천 초안");
    expect(composer).toBeDisabled();
    rendered.unmount();
    render(<EditorWorkbench director={director} view={view} />);
    openYujin();
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
    openDetailDock();
    openYujin();

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
        { segmentId: "segment-1", text: "첫 자막", startSec: 0, endSec: 1, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0, bold: false, italic: false, letterSpacingPx: 0 } },
        { segmentId: "segment-2", text: "둘째 자막", startSec: 1, endSec: 2, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0, bold: false, italic: false, letterSpacingPx: 0 } },
      ],
      playback: { auditionUrls: {}, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-preview/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 2 } },
    } as const;
    const rendered = render(<EditorWorkbench view={transcriptView} />);
    openMaterialDock();
    // **갱신 이유(2026-08-27).** 자막은 캡컷 `텍스트` 자리처럼 탭이 됐다. 도크가
    // 한 번에 하나만 보여 주므로(11.7배 스크롤을 없앤 변경) 대본은 그 탭에 있다.
    // 지키려는 것은 "대본·재생 위치·클립 선택이 한 segment id로 묶인다"이지
    // 대본이 기본 화면에 있는 것이 아니었다.
    fireEvent.click(screen.getByRole("tab", { name: "자막" }));
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
      captions: [{ segmentId: "segment-2", text: "둘째 자막", startSec: 5, endSec: 10, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0, bold: false, italic: false, letterSpacingPx: 0 } }],
      playback: { auditionUrls: {}, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-preview/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 10 } },
    } as const;
    render(<EditorWorkbench view={brollView} />);
    openMaterialDock();
    const player = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    Object.defineProperty(player, "currentTime", { configurable: true, writable: true, value: 0 });

    fireEvent.click(clipSelectionButton("broll:b-2"));

    expect(player.currentTime).toBe(5);
    // 자막은 이제 `자막` 탭에 있다(2026-08-27). 지키려는 것은 "B-roll 클립을 눌러도
    // 그 장면의 대본이 함께 골라진다"이므로 탭을 열어 그대로 확인한다.
    fireEvent.click(screen.getByRole("tab", { name: "자막" }));
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
    // **갱신 이유(2026-08-22).** 문구만 바뀌었다 -- owner 지시로 화면 문구를
    // 설명 문장에서 키워드 중심으로 옮기는 중이다. 지키려는 것은 "다룰 항목이
    // 없을 때 화면이 그 사실을 말한다"이지 그 문장 자체가 아니었다.
    expect(screen.getByText("이 명령이 다루는 항목 없음")).toBeInTheDocument();
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
    const dock = screen.getByRole("complementary", { name: "미디어" });
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
    openDetailDock();
    openYujin();

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

describe("편집 툴바 — 승인 기록 2026-08-20 항목 2", () => {
  // owner가 사무실에서 편집 화면을 보고 "완전 캡컷과 다른데?"라고 했고, 캡처를
  // 놓고 세어 보니 이유가 넷이었다. 배경(1)·빈 미리보기(3)·밋밋한 클립(4)은
  // 닫혔고 **툴바(2)만 남아 있었다** — `큰 주황 알약 단추 여덟 개가 위에 줄지어
  // 있음. 캡컷 툴바는 작은 회색 아이콘`.
  //
  // 채운 주황은 이 저장소에서 **강조**를 뜻한다(승인 기록: 활성 메뉴, 선택된 항목,
  // 주요 단추). 도구 여덟 개가 전부 그 색이면 강조가 강조를 못 한다.

  function toolbarButtons(): HTMLElement[] {
    // 화면에 `banner`가 둘이라(제품 껍데기와 작업판) 툴바로 좁힌다.
    const toolbar = document.querySelector(".vb-editor-workbench__toolbar");
    if (!toolbar) throw new Error("편집 툴바를 찾지 못했다");
    return Array.from(toolbar.querySelectorAll("button"));
  }

  it("도구 단추는 조용하다 — 채운 주황은 열린 도크만 가져간다", async () => {
    render(<EditorWorkbench view={view} />);
    await screen.findByRole("region", { name: "편집 작업판" });

    // **지키는 원칙은 그대로다**(승인 2026-08-20 항목 2): 채운 주황은 열린 도크
    // 하나만 가져가고 나머지는 조용하다. 2026-09-04에 패널 탭이 도구줄에서
    // 왼쪽 세로 띠로 옮겨가면서(계획서 3단계) **자리만 바뀌었다** -- 그래서
    // 도구줄은 이제 하나도 안 채워져 있어야 하고, 채운 하나는 띠에 있다.
    const filledInToolbar = toolbarButtons()
      .filter((button) => button.className.includes("bg-primary"))
      .map((button) => button.textContent);
    expect(filledInToolbar, "도구줄 단추가 강조를 가져갔다").toEqual([]);

    const rail = document.querySelector(".vb-editor-workbench__rail");
    if (!rail) throw new Error("왼쪽 세로 띠를 찾지 못했다");
    const filledInRail = Array.from(rail.querySelectorAll("button"))
      .filter((button) => button.className.includes("bg-primary"))
      .map((button) => button.textContent);

    // 넓은 화면에서 왼쪽 재료 열은 기본으로 펴져 있다(owner 승인 2026-08-17).
    // 그 하나만 강조를 가져가고 나머지 띠 항목은 조용하다.
    expect(filledInRail).toEqual(["미디어"]);
  });

  it("열려 있는 도크만 강조를 가져간다 — 그것이 '선택된 항목'이다", async () => {
    render(<EditorWorkbench view={view} />);
    await screen.findByRole("region", { name: "편집 작업판" });

    const materials = screen.getByRole("tab", { name: "미디어" });

    // 넓은 화면에서는 왼쪽 재료 열이 기본으로 펴져 있다(owner 승인 2026-08-17).
    // 승인 2026-08-30 이후로는 `aria-pressed`가 아니라 탭의 `aria-selected`다.
    expect(materials.getAttribute("aria-selected")).toBe("true");
    fireEvent.click(materials);
    expect(screen.getByRole("tab", { name: "미디어" }).getAttribute("aria-selected")).toBe("false");
  });

  it("이름은 그대로 읽힌다 — 아이콘만 남기지 않는다", async () => {
    // 아이콘만 두면 캡컷을 안 써 본 사람은 무엇인지 알 수 없고, 읽어 주는 도구도
    // 잃는다. 작게 만드는 것과 이름을 없애는 것은 다른 일이다.
    render(<EditorWorkbench view={view} />);
    await screen.findByRole("region", { name: "편집 작업판" });

    for (const name of ["실행 취소", "다시 실행", "나누기", "앞과 붙이기", "빼기", "다음 장면에도", "세부 정보"]) {
      expect(screen.getByRole("button", { name })).toBeVisible();
    }
    // 승인 2026-08-30(버튼 단위 벤치마킹 2단계) -- 미디어는 이제 콘텐츠 탭이다.
    for (const name of ["미디어", "오디오", "자막", "전환"]) {
      expect(screen.getByRole("tab", { name })).toBeVisible();
    }
  });
});

describe("좁은 화면의 도크 단추", () => {
  // 좁은 화면에서는 도크가 **서랍**으로 열린다. 데스크톱 상태만 보고 눌림을
  // 판단하면, 서랍을 열어 놓고도 단추가 "안 눌림"이라고 말한다 -- 읽어 주는
  // 도구에게 거짓말이고, 강조색도 따라오지 않는다.
  it("서랍이 열려 있으면 그 단추가 눌린 것으로 읽힌다", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 640 });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 640 } as DOMRect);
    render(<EditorWorkbench view={view} />);
    await screen.findByRole("region", { name: "편집 작업판" });

    // 시작 상태는 단정하지 않는다 -- 서랍은 마지막으로 열었던 쪽을 기억한다.
    // 여기서 재는 것은 **열림과 눌림이 같이 움직이는가**다.
    if (!screen.queryByRole("dialog", { name: "미디어" })) {
      fireEvent.click(screen.getByRole("tab", { name: "미디어" }));
    }
    await screen.findByRole("dialog", { name: "미디어" });
    // 승인 2026-08-30 이후로는 `aria-pressed`가 아니라 탭의 `aria-selected`다.
    expect(screen.getByRole("tab", { name: "미디어" }).getAttribute("aria-selected")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "닫기" }));

    await waitFor(() => expect(screen.queryByRole("dialog", { name: "미디어" })).toBeNull());
    expect(screen.getByRole("tab", { name: "미디어" }).getAttribute("aria-selected")).toBe("false");
  });
});

/** 캡컷은 위 툴바에 화면 비율을 띄운다. 우리 띠도 그걸 말하는데, **띠는 그 값을
 *  스스로 불러오지 않는다** — 껍데기가 프로젝트마다 무언가를 더 물어보면 모든
 *  화면에 요청이 하나씩 는다. 아는 화면이 알려 주는 구조이고, 그 아는 화면이
 *  편집기다(재생 매니페스트에 이미 크기가 들어 있다).
 *
 *  이 시험이 없으면 띠는 **영원히 비어 있는데 아무 시험도 안 깨진다** — 알려 주는
 *  쪽을 빼먹는 것은 이 저장소가 반복해 온 "부품은 있는데 부르는 자리가 없다"다. */
describe("편집기가 껍데기에 화면 비율을 알린다", () => {
  function Probe() {
    const canvas = useShellCanvas();
    return <p data-testid="probe">{canvas ? `${canvas.width}x${canvas.height}` : "없음"}</p>;
  }

  it("열려 있는 초안의 크기를 그대로 알린다", () => {
    render(<ShellCanvasProvider><Probe /><EditorWorkbench view={view} /></ShellCanvasProvider>);

    expect(screen.getByTestId("probe")).toHaveTextContent("1080x1920");
  });

  it("편집기를 떠나면 지운다", () => {
    // 안 지우면 내 라이브러리로 옮겨도 아까 그 초안의 비율이 띠에 남아, 띠가 지금
    // 화면과 아무 상관 없는 사실을 말한다.
    const workbench = render(<ShellCanvasProvider><Probe /><EditorWorkbench view={view} /></ShellCanvasProvider>);

    workbench.rerender(<ShellCanvasProvider><Probe /></ShellCanvasProvider>);

    expect(screen.getByTestId("probe")).toHaveTextContent("없음");
  });
});

/** owner(2026-08-27): "우리 메뉴가 너무 각각 페이지별로 따로 놀아. 이걸 캡컷처럼
 *  편집기 기반처럼 쉽게 확인하도록 팝업으로 만든다던지 하는게 나을거 같어."
 *
 *  편집을 끝내고 완성본을 받으려면 **화면을 떠나야 했다.** 캡컷은 편집기 안에서
 *  `내보내기`를 누르면 팝업이 뜬다. 남은 "따로 노는" 자리 중 가장 큰 곳이다.
 *
 *  지키는 것은 **편집기를 떠나지 않고 내보내기에 닿는가**다. 무엇이 막고 있는지
 *  판정하는 일은 출력 화면이 이미 한다 -- 여기서 새로 적지 않는다. 두 벌로 적으면
 *  무엇을 언제 내보낼 수 있는지가 조용히 갈라진다.
 *  → `docs/decisions/2026-08-27-editor-centered-shell-direction.ko.md` */
describe("편집기에서 내보내기", () => {
  it("편집기를 떠나지 않고 내보내기를 연다", async () => {
    render(<EditorWorkbench view={view} />);

    fireEvent.click(await screen.findByRole("button", { name: "내보내기" }));

    expect(await screen.findByRole("dialog", { name: "내보내기" })).toBeVisible();
  });

  it("내보내기 단추는 툴바 안에 있다", async () => {
    render(<EditorWorkbench view={view} />);
    await screen.findByRole("region", { name: "편집 작업판" });

    const toolbar = document.querySelector(".vb-editor-workbench__toolbar");
    expect(Array.from(toolbar?.querySelectorAll("button") ?? []).map((button) => button.textContent?.trim())).toContain("내보내기");
  });

  /** owner(2026-08-27)의 지시대로 "검토"도 팝업 안에 들어와야 한다 -- 체크리스트의
   *  `검토 화면 열기`가 `/review`로 통째로 이동시키면 편집기를 떠나는 것과
   *  같다. 검토·출력을 이미 한 화면으로 합친 `ReviewAndOutputPage`를 그대로
   *  재사용해서, 팝업을 열면 검토 내용이 처음부터 같은 다이얼로그 안에 보여야
   *  한다(새 창·새 라우트로 이동하지 않고). */
  it("내보내기 팝업 안에 검토 화면도 함께 있다", async () => {
    render(<EditorWorkbench view={view} />);

    fireEvent.click(await screen.findByRole("button", { name: "내보내기" }));

    const dialog = await screen.findByRole("dialog", { name: "내보내기" });
    expect(await within(dialog).findByTestId("review-and-output-page")).toBeInTheDocument();
    expect(within(dialog).getByTestId("outputs-page")).toBeInTheDocument();
    // 이 문구가 다시 나타나면 그 링크가 되살아난 것이다 -- 누르면 `/review`로
    // 통째로 이동해 팝업 안에 머문다는 이번 변경의 계약이 깨진다(코드리뷰에서
    // 잡힘: 회귀를 잡는 테스트가 없었다).
    expect(within(dialog).queryByText("검토 화면 열기")).not.toBeInTheDocument();
  });
});

/** owner(2026-08-27): "버튼에 글자를 안넣어도 되고, 마우스 가져다대면 설명 글자가
 *  보이기 해도되. 캡컷도 편집화면떄문에 글자를 최소화 했더라고."
 *
 *  > "지금 너가 만든 프로그램은 너무 메뉴도 어렵고 뭐가 뭔지 하나도 모르겠어.
 *  >  그래서 그냥 내가 캡컷하고 아예 똑같이 하라고 한거잖아"
 *
 *  툴바에 글자 단추가 아홉이었다. 캡컷 툴바는 작은 아이콘 줄이다. 아이콘은 이미
 *  전부 붙어 있었고 **글자가 같이 나오는 것**이 달랐다.
 *
 *  **글자를 지우는 것이 아니라 눈에서만 뺀다.** 접근 이름은 그대로 남아야 화면
 *  낭독기가 읽고, 마우스를 대면 툴팁으로 보인다. 지우면 눈이 보이는 사람만 쓰는
 *  도구가 된다. */
describe("편집 툴바는 캡컷처럼 아이콘 줄이다", () => {
  function toolbar(): HTMLElement {
    const found = document.querySelector(".vb-editor-workbench__toolbar");
    if (!found) throw new Error("편집 툴바를 찾지 못했다");
    return found as HTMLElement;
  }

  /** 눈에 보이는 글자만 센다. **`<span>`만 훑으면 안 된다** -- 글자가 텍스트
   *  노드로 바로 들어 있으면 아무것도 못 보고 그냥 통과한다(2026-08-27에 실제로
   *  그렇게 헛통과하는 시험을 썼다). 복제해서 `sr-only`를 떼고 남은 것을 본다. */
  function visibleLabel(button: HTMLElement): string {
    const clone = button.cloneNode(true) as HTMLElement;
    clone.querySelectorAll(".sr-only").forEach((node) => node.remove());
    return (clone.textContent ?? "").trim();
  }

  it("단추에 글자가 눈에 보이지 않는다", async () => {
    render(<EditorWorkbench view={view} />);
    await screen.findByRole("region", { name: "편집 작업판" });

    // 승인 2026-08-30(버튼 단위 벤치마킹 2단계) -- 왼쪽 콘텐츠 탭(미디어·오디오
    // ·자막·전환)은 이 규칙 밖이다. 캡컷 참조 캡처도 이 탭엔 글자를 그대로
    // 보여 준다(아이콘 하나였던 예전 `미디어` 단추와 달리, 탭은 여러 개를
    // 구별해야 해서 아이콘만으로는 무엇인지 알 수 없다).
    const buttons = Array.from(toolbar().querySelectorAll("button"))
      .filter((button) => !button.closest(".vb-editor-workbench__panes"));
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect(visibleLabel(button), `${button.textContent?.trim()} 단추에 보이는 글자가 남아 있다`).toBe("");
    }
  });

  it("이름은 그대로 남아 낭독기와 시험이 찾을 수 있다", async () => {
    render(<EditorWorkbench view={view} />);
    await screen.findByRole("region", { name: "편집 작업판" });

    for (const name of ["실행 취소", "다시 실행", "세부 정보", "내보내기"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    // 승인 2026-08-30(버튼 단위 벤치마킹 2단계) -- 미디어는 이제 콘텐츠 탭이다.
    expect(screen.getByRole("tab", { name: "미디어" })).toBeInTheDocument();
  });
});
